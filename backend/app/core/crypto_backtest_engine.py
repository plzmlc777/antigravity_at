"""
Crypto (Binance USDT-M Futures) 전용 백테스트 wrapper.

KrBacktestEngine의 mirror — 24/7 시장, futures taker fee. v1은 long-only
(meta-strategy MoE pool은 KR와 동일하게 long-only).

수수료 가정 (v1):
  - taker fee 0.04% 양방향 (round-trip 0.08%) — Binance USDT-M 기본
  - maker fee는 적용 안 함 (전 strategy가 market-style entry/exit)
  - 거래세 없음
  - funding rate 무시 (8h당 ~0.01% — perf_matrix scale에서는 무시할 수준)

float quantity 지원 (KR: int qty, Crypto: BTC 같은 분할 가능 자산).
"""
from typing import Any, Callable, Dict, List, Optional

from .waterfall_engine import (
    BacktestContext,
    StockOrder,
    OrderSide,
    OrderType,
    WaterfallBacktestEngine,
)


# ───────────────────────────── 거래 비용 상수 ─────────────────────────────
CRYPTO_TAKER_FEE = 0.0004   # 0.04% — Binance USDT-M default taker
CRYPTO_MAKER_FEE = 0.0002   # 0.02% — reserved for future use
CRYPTO_ROUND_TRIP_COST = CRYPTO_TAKER_FEE * 2  # 0.08%


class CryptoBacktestContext(BacktestContext):
    """
    Crypto 백테스트 컨텍스트.
    - buy: float qty, taker fee 차감
    - sell: float qty, taker fee 차감 (no tax)
    """

    def buy(
        self,
        symbol: str,
        quantity: float,
        price: float = 0,
        order_type: str = "market",
        metadata: Dict[str, Any] = None,
        on_filled: Callable = None,
    ) -> Dict[str, Any]:
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

        # Crypto: tick size는 실거래 시점에만 의미 (백테스트 raw price 사용)
        exec_price = float(raw_price)

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
            fee = gross_cost * CRYPTO_TAKER_FEE
            total_cost = gross_cost + fee

            if self.cash < total_cost:
                self.log(
                    f"BUY REJECTED: Insufficient capital. Need {total_cost:,.4f}, have {self.cash:,.4f}"
                )
                return {"status": "failed", "reason": "Insufficient Capital"}

            self.cash -= total_cost

            if self._use_rank_isolation:
                rank_h = self._rank_holdings.setdefault(self.current_rank, {})
                rank_h[symbol] = float(rank_h.get(symbol, 0)) + float(quantity)
            else:
                self._holdings[symbol] = float(self._holdings.get(symbol, 0)) + float(quantity)

            order.add_fill(
                fill_price=exec_price,
                fill_qty=quantity,
                fill_id=f"SIM_BUY_{len(self.trades)+1}",
            )

            trade = {
                "type": "buy",
                "symbol": symbol,
                "price": exec_price,
                "quantity": float(quantity),
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
                f"BUY EXECUTED: {quantity:.6f} {symbol} @ {exec_price} (fee {fee:.4f})"
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
        quantity: float,
        price: float = 0,
        order_type: str = "market",
        metadata: Dict[str, Any] = None,
        on_filled: Callable = None,
    ) -> Dict[str, Any]:
        if self._use_rank_isolation:
            rank_h = self._rank_holdings.get(self.current_rank, {})
            current_qty = float(rank_h.get(symbol, 0))
        else:
            current_qty = float(self._holdings.get(symbol, 0))

        # Float comparison tolerance (selling slightly more than held due to FP rounding)
        if current_qty + 1e-12 < quantity:
            self.log("SELL FAILED: Insufficient Holdings")
            return {"status": "failed", "reason": "Insufficient Holdings"}
        # Clamp qty to available (avoid negative residuals)
        quantity = min(float(quantity), current_qty)

        raw_price = price if price > 0 else self.get_current_price(symbol)
        if raw_price <= 0:
            return {"status": "failed", "reason": "Invalid Price"}

        exec_price = float(raw_price)

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
            fee = gross_revenue * CRYPTO_TAKER_FEE
            tax = 0.0
            net_revenue = gross_revenue - fee - tax

            self.cash += net_revenue

            if self._use_rank_isolation:
                rank_h = self._rank_holdings.get(self.current_rank, {})
                rank_h[symbol] = float(rank_h.get(symbol, 0)) - float(quantity)
                if rank_h[symbol] <= 1e-12:
                    del rank_h[symbol]
            else:
                self._holdings[symbol] = float(self._holdings.get(symbol, 0)) - float(quantity)
                if self._holdings[symbol] <= 1e-12:
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
                "quantity": float(quantity),
                "time": self.get_time().isoformat(),
                "strategy_rank": self.current_rank,
                "order_id": order.id,
                "fee": fee,
                "tax": tax,
                "raw_price": raw_price,
                "metadata": metadata or {},
            }
            self.trades.append(trade)

            if self._use_rank_isolation:
                rank_h = self._rank_holdings.get(self.current_rank, {})
                if not rank_h:
                    self._exclusive_lock_holder = None
            else:
                if len(self._holdings) == 0:
                    self._exclusive_lock_holder = None

            self.log(
                f"SELL EXECUTED: {quantity:.6f} {symbol} @ {exec_price} (fee {fee:.4f})"
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


class CryptoBacktestEngine(WaterfallBacktestEngine):
    """
    Crypto 백테스트 엔진. v1 long-only (no leverage, no shorting).

    KR과 동일한 최종-청산 로직 → kr_total_friction 키 대신 crypto_total_friction 사용.
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

        # v1: leverage = 1 (멀티 TF pool은 long-only spot equivalent)
        leverage = 1

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

        context = CryptoBacktestContext(
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

        # Force liquidation at end (long-only)
        long_positions = {}
        for t in context.trades:
            sym = t["symbol"]
            qty = float(t["quantity"])
            if t["type"] == "buy":
                long_positions[sym] = long_positions.get(sym, 0.0) + qty
            elif t["type"] == "sell":
                long_positions[sym] = long_positions.get(sym, 0.0) - qty

        last_price_cache = {}

        def _get_last_price(sym: str) -> float:
            if sym not in last_price_cache:
                p = context.get_current_price(sym)
                if p <= 0:
                    p = feed[-1]["close"] if feed else 1.0
                last_price_cache[sym] = p
            return last_price_cache[sym]

        for sym, qty in long_positions.items():
            if qty > 1e-12:
                context.sell(
                    sym, qty,
                    price=_get_last_price(sym),
                    metadata={"force_liquidated": True},
                )

        context.update_equity()

        stats = self._generate_stats(context, feed, optimize_mode=optimize_mode)

        final_equity = initial_capital
        if context.equity_curve:
            last = context.equity_curve[-1]
            try:
                from .waterfall_engine import EQUITY_VALUE_KEY
                final_equity = last[EQUITY_VALUE_KEY]
            except Exception:
                try:
                    final_equity = last[1]
                except Exception:
                    final_equity = initial_capital

        stats["symbol"] = symbol
        stats["initial_capital"] = initial_capital
        stats["final_equity"] = final_equity
        stats["return_pct"] = (
            ((final_equity - initial_capital) / initial_capital * 100)
            if initial_capital > 0 else 0
        )
        stats["pnl"] = final_equity - initial_capital
        stats["trades_count"] = len(context.trades)
        stats["equity_curve"] = context.equity_curve

        total_fee = sum(t.get("fee", 0) for t in context.trades)
        stats["crypto_total_fee"] = total_fee
        stats["crypto_total_friction"] = total_fee  # tax = 0

        return stats
