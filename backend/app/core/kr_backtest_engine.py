"""
KR (한국 주식) 전용 백테스트 wrapper.

기존 WaterfallBacktestEngine / BacktestContext는 무수정 — Binance SAS 영향 0.
KrBacktestContext는 buy/sell을 override해 (1) KR 호가 단위 round, (2) 매수/매도
수수료, (3) 매도 거래세를 차감한다.

호가 단위 표는 한국거래소 일반 종목 기준(2023-01-25 개정 이후). KOSPI200/KOSDAQ150
세부 호가 적용 종목은 별도 처리가 필요하나, 본 wrapper의 첫 사용자(061090
세나테크놀로지)는 일반 KOSDAQ 종목으로 본 표만 적용한다.
"""
from typing import Any, Callable, Dict, List, Optional

from .waterfall_engine import (
    BacktestContext,
    StockOrder,
    OrderSide,
    OrderType,
    WaterfallBacktestEngine,
    is_futures_exchange,
)


# ───────────────────────────── 거래 비용 상수 ─────────────────────────────
# 키움 영웅문 API 일반 수수료(소액). 사용자별 약정 수수료가 다르면 조정 필요.
KR_BUY_FEE_RATE = 0.00015   # 0.015%
KR_SELL_FEE_RATE = 0.00015  # 0.015%
# 매도 시 증권거래세 + 농어촌특별세 (KOSPI 0.18% / KOSDAQ 0.18% 동일, 2024년 기준)
KR_SELL_TAX_RATE = 0.0018   # 0.18%


def kr_round_to_tick(price: float) -> float:
    """한국거래소 일반 종목 호가 단위로 round."""
    if price < 2000:
        tick = 1
    elif price < 5000:
        tick = 5
    elif price < 20000:
        tick = 10
    elif price < 50000:
        tick = 50
    elif price < 200000:
        tick = 100
    elif price < 500000:
        tick = 500
    else:
        tick = 1000
    # half-up rounding (거래소 관행 — Python round()의 banker's rounding 회피)
    return int(price / tick + 0.5) * tick


class KrBacktestContext(BacktestContext):
    """
    KR 백테스트 컨텍스트.
    - buy: 호가 round → 매수 수수료 차감
    - sell: 호가 round → 매도 수수료 + 거래세 차감
    - 그 외 동작은 부모 클래스와 동일
    """

    def buy(
        self,
        symbol: str,
        quantity: int,
        price: float = 0,
        order_type: str = "market",
        metadata: Dict[str, Any] = None,
        on_filled: Callable = None,
    ) -> Dict[str, Any]:
        # exclusive lock & single-position checks (parent logic 그대로)
        if self._use_rank_isolation:
            if (
                self._exclusive_lock_holder is not None
                and self._exclusive_lock_holder != self.current_rank
            ):
                self._exclusive_buy_blocked += 1
                return {"status": "failed", "reason": "exclusive_locked"}

        my_holdings = self.holdings
        if len(my_holdings) > 0 and symbol not in my_holdings:
            self.log(
                f"BUY REJECTED: System holds {list(my_holdings.keys())}, cannot buy {symbol}."
            )
            return {"status": "failed", "reason": "System Occupied"}

        raw_price = price if price > 0 else self.get_current_price(symbol)
        if raw_price <= 0:
            self.log(f"BUY FAILED: Invalid Price for {symbol}")
            return {"status": "failed", "reason": "Invalid Price"}

        # KR 호가 단위 round
        exec_price = kr_round_to_tick(raw_price)

        try:
            order = StockOrder(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                price=exec_price if price > 0 else None,
                order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET,
            )
            order.validate()

            gross_cost = exec_price * quantity
            fee = gross_cost * KR_BUY_FEE_RATE
            total_cost = gross_cost + fee

            if self.cash < total_cost:
                self.log(
                    f"BUY REJECTED: Insufficient capital. Need {total_cost:,.0f}, have {self.cash:,.0f}"
                )
                return {"status": "failed", "reason": "Insufficient Capital"}

            self.cash -= total_cost

            # holdings 업데이트
            if self._use_rank_isolation:
                rank_h = self._rank_holdings.setdefault(self.current_rank, {})
                rank_h[symbol] = rank_h.get(symbol, 0) + quantity
            else:
                self._holdings[symbol] = self._holdings.get(symbol, 0) + quantity

            order.add_fill(
                fill_price=exec_price,
                fill_qty=quantity,
                fill_id=f"SIM_BUY_{len(self.trades)+1}",
            )

            trade = {
                "type": "buy",
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat(),
                "strategy_rank": self.current_rank,
                "order_id": order.id,
                "fee": fee,
                "tax": 0.0,
                "raw_price": raw_price,
                "metadata": metadata or {},
            }
            self.trades.append(trade)

            if self._use_rank_isolation and self._exclusive_lock_holder is None:
                self._exclusive_lock_holder = self.current_rank

            self.log(
                f"BUY EXECUTED: {quantity} {symbol} @ {exec_price} (raw {raw_price:.0f}, fee {fee:.0f})"
            )

            if on_filled:
                try:
                    on_filled(
                        order_id=order.id,
                        filled_qty=quantity,
                        filled_price=exec_price,
                        metadata=metadata or {},
                    )
                except Exception:
                    pass

            return trade

        except Exception as e:
            self.log(f"BUY ERROR: {e}")
            return {"status": "failed", "reason": str(e)}

    def sell(
        self,
        symbol: str,
        quantity: int,
        price: float = 0,
        order_type: str = "market",
        metadata: Dict[str, Any] = None,
        on_filled: Callable = None,
    ) -> Dict[str, Any]:
        # holdings 확인
        if self._use_rank_isolation:
            rank_h = self._rank_holdings.get(self.current_rank, {})
            current_qty = rank_h.get(symbol, 0)
        else:
            current_qty = self._holdings.get(symbol, 0)

        if current_qty < quantity:
            self.log("SELL FAILED: Insufficient Holdings")
            return {"status": "failed", "reason": "Insufficient Holdings"}

        raw_price = price if price > 0 else self.get_current_price(symbol)
        if raw_price <= 0:
            return {"status": "failed", "reason": "Invalid Price"}

        # KR 호가 round
        exec_price = kr_round_to_tick(raw_price)

        try:
            order = StockOrder(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                price=exec_price if price > 0 else None,
                order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET,
            )
            order.validate()

            gross_revenue = exec_price * quantity
            fee = gross_revenue * KR_SELL_FEE_RATE
            tax = gross_revenue * KR_SELL_TAX_RATE
            net_revenue = gross_revenue - fee - tax

            self.cash += net_revenue

            # holdings 차감
            if self._use_rank_isolation:
                rank_h = self._rank_holdings.get(self.current_rank, {})
                rank_h[symbol] = rank_h.get(symbol, 0) - quantity
                if rank_h[symbol] <= 0:
                    del rank_h[symbol]
            else:
                self._holdings[symbol] -= quantity
                if self._holdings[symbol] <= 0:
                    del self._holdings[symbol]

            order.add_fill(
                fill_price=exec_price,
                fill_qty=quantity,
                fill_id=f"SIM_SELL_{len(self.trades)+1}",
            )

            trade = {
                "type": "sell",
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat(),
                "strategy_rank": self.current_rank,
                "order_id": order.id,
                "fee": fee,
                "tax": tax,
                "raw_price": raw_price,
                "metadata": metadata or {},
            }
            self.trades.append(trade)

            # release exclusive lock
            if self._use_rank_isolation:
                rank_h = self._rank_holdings.get(self.current_rank, {})
                if not rank_h:
                    self._exclusive_lock_holder = None
            else:
                if len(self._holdings) == 0:
                    self._exclusive_lock_holder = None

            self.log(
                f"SELL EXECUTED: {quantity} {symbol} @ {exec_price} "
                f"(raw {raw_price:.0f}, fee {fee:.0f}, tax {tax:.0f})"
            )

            if on_filled:
                try:
                    on_filled(
                        order_id=order.id,
                        filled_qty=quantity,
                        filled_price=exec_price,
                        metadata=metadata or {},
                    )
                except Exception:
                    pass

            return trade

        except Exception as e:
            self.log(f"SELL ERROR: {e}")
            return {"status": "failed", "reason": str(e)}


class KrBacktestEngine(WaterfallBacktestEngine):
    """
    KR 백테스트 엔진. WaterfallBacktestEngine의 run_single_backtest 흐름은
    그대로 두되, BacktestContext 대신 KrBacktestContext를 주입한다.
    """

    async def run_single_backtest(
        self,
        config: Dict,
        feed: List[Dict],
        initial_capital: int,
        symbol: str,
        optimize_mode: bool = False,
        rank: int = 1,
        extra_feeds: Optional[Dict[str, List[Dict]]] = None,
    ) -> Dict:
        if not feed:
            return self._empty_result(["No data provided"])

        # KR은 현물 — leverage 강제 1
        leverage = 1
        if is_futures_exchange(self._exchange_name):
            # 안전장치: 만약 KR 엔진이 futures 거래소로 잘못 호출되면 부모 위임
            return await super().run_single_backtest(
                config=config,
                feed=feed,
                initial_capital=initial_capital,
                symbol=symbol,
                optimize_mode=optimize_mode,
                rank=rank,
                extra_feeds=extra_feeds,
            )

        feeds = {symbol: feed}
        if extra_feeds:
            for extra_sym, extra_feed in extra_feeds.items():
                if (
                    extra_sym
                    and extra_sym != symbol
                    and extra_feed
                    and extra_sym not in feeds
                ):
                    feeds[extra_sym] = extra_feed

        context = KrBacktestContext(
            feeds,
            initial_capital=initial_capital,
            primary_symbol=symbol,
            leverage=leverage,
        )
        context.current_rank = rank
        context.optimize_mode = optimize_mode

        p_config = config.copy()
        p_config["initial_capital"] = initial_capital
        p_config["symbol"] = symbol
        p_config["exchange_name"] = self._exchange_name

        strat = self.strategy_class(context, p_config)
        if hasattr(strat, "initialize"):
            strat.initialize()

        for candle in feed:
            context.current_timestamp = candle["timestamp"]
            try:
                if hasattr(context, "process_pending_orders"):
                    context.process_pending_orders(candle)
                strat.on_data(candle)
                context.update_equity()
            except Exception:
                pass

        # Force liquidation at end (KR은 long-only — short은 무시)
        long_positions = {}
        for t in context.trades:
            sym = t["symbol"]
            qty = t["quantity"]
            if t["type"] == "buy":
                long_positions[sym] = long_positions.get(sym, 0) + qty
            elif t["type"] == "sell":
                long_positions[sym] = long_positions.get(sym, 0) - qty

        last_price_cache = {}

        def _get_last_price(sym: str) -> float:
            if sym not in last_price_cache:
                p = context.get_current_price(sym)
                if p <= 0:
                    p = feed[-1]["close"] if feed else 100000
                last_price_cache[sym] = p
            return last_price_cache[sym]

        for sym, qty in long_positions.items():
            if qty > 0:
                context.sell(
                    sym,
                    qty,
                    price=_get_last_price(sym),
                    metadata={"force_liquidated": True},
                )

        # 강제청산이 fee/tax를 차감했으므로 equity_curve를 한 번 더 갱신해야
        # final_equity가 net P&L과 일치한다 (KR fee/tax 누락 시 부모 엔진은
        # 차이가 0이지만, KR에서는 청산 시점 friction만큼 차이가 누적된다).
        context.update_equity()

        stats = self._generate_stats(context, feed, optimize_mode=optimize_mode)

        final_equity = initial_capital
        if context.equity_curve:
            last = context.equity_curve[-1]
            try:
                from .waterfall_engine import EQUITY_VALUE_KEY
                final_equity = last[EQUITY_VALUE_KEY]
            except Exception:
                # tuple/list 형식이라면 두 번째 element를 equity로 가정
                try:
                    final_equity = last[1]
                except Exception:
                    final_equity = initial_capital

        stats["symbol"] = symbol
        stats["initial_capital"] = initial_capital
        stats["final_equity"] = final_equity
        stats["return_pct"] = (
            ((final_equity - initial_capital) / initial_capital * 100)
            if initial_capital > 0
            else 0
        )
        stats["pnl"] = final_equity - initial_capital
        stats["trades_count"] = len(context.trades)
        stats["equity_curve"] = context.equity_curve

        # 추가 KR 메타: 누적 수수료/세금
        total_fee = sum(t.get("fee", 0) for t in context.trades)
        total_tax = sum(t.get("tax", 0) for t in context.trades)
        stats["kr_total_fee"] = total_fee
        stats["kr_total_tax"] = total_tax
        stats["kr_total_friction"] = total_fee + total_tax

        return stats
