#!/usr/bin/env python3
"""
Execution Engine - 매매 시그널과 주문 실행을 분리한 공통 엔진.

전략은 Signal만 발신하고, ExecutionEngine이 주문을 실행한다.
Phase 1: MARKET, LIMIT, STOP_MARKET 지원.

Architecture:
    Strategy → Signal → ExecutionEngine
                          ├── BacktestExecutor  (시뮬레이션)
                          └── (향후) LiveExecutor / PaperExecutor

Usage:
    from execution_engine import BacktestExecutor, StrategyAdapter, Signal, OrderType, OrderSide

    executor = BacktestExecutor(initial_capital=10_000_000, leverage=1)
    adapter = StrategyAdapter(strategy)

    for candle in candles:
        fills = executor.on_candle(candle, strategy, initial_capital)
        signals = adapter.process_candle(candle, ts, price, executor.cash, initial_capital)
        for sig in signals:
            executor.submit(sig, strategy, ts, price, initial_capital)
        executor.record_equity(price, ts)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
import uuid


# =============================================================================
# Enums & Data Classes
# =============================================================================

class OrderType(Enum):
    """주문 유형."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"           # Phase 2
    TRAILING_STOP = "trailing_stop"     # Phase 2
    TAKE_PROFIT = "take_profit"         # Phase 2
    TAKE_PROFIT_LIMIT = "take_profit_limit"  # Phase 2


class OrderSide(Enum):
    """주문 방향."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Signal:
    """
    매매 시그널 — 전략이 발신하고 엔진이 실행.

    Attributes:
        side: BUY 또는 SELL
        order_type: 주문 유형 (MARKET, LIMIT, STOP_MARKET 등)
        price: 지정가/스탑 트리거 가격 (MARKET이면 0 = 현재가 사용)
        stop_price: STOP 주문의 트리거 가격
        quantity: 수량 (0이면 엔진이 전략 로직으로 계산)
        level: 마틴게일 레벨 (1=L1, 2+=추가매수)
        is_exit: 청산 시그널 여부
        direction: "long" 또는 "short"
        reason: 시그널 발생 사유
        time_in_force: GTC(기본), IOC, FOK
        trailing_delta: TRAILING_STOP 콜백 %
        linked_signals: 연결 주문 (OCO, 브라켓)
        client_order_id: 전략이 부여한 고유 ID (취소/수정용)
        metadata: 추가 데이터 (cycle_start_equity 등)
    """
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    price: float = 0.0
    stop_price: float = 0.0
    quantity: float = 0.0
    level: int = 0
    is_exit: bool = False
    direction: str = "long"
    reason: str = ""
    time_in_force: str = "GTC"
    trailing_delta: float = 0.0
    linked_signals: Optional[List['Signal']] = None
    client_order_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PendingOrder:
    """대기 중인 주문 (LIMIT, STOP, TRAILING 등)."""
    signal: Signal
    submitted_at: datetime
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    is_active: bool = True
    # STOP_LIMIT: 트리거 후 LIMIT으로 전환됐는지
    stop_triggered: bool = False
    # TRAILING_STOP: 추적 중인 고점/저점
    trailing_peak: float = 0.0
    # linked order group ID (OCO 등)
    group_id: str = ""
    # Bracket: entry 체결 후 등록할 연결 주문
    bracket_signals: Optional[List[Signal]] = None


@dataclass
class Fill:
    """체결 결과."""
    order_id: str
    side: OrderSide
    price: float
    quantity: float
    time: datetime
    level: int = 0
    is_exit: bool = False
    order_type: OrderType = OrderType.MARKET
    # Bracket: entry 체결 시 등록할 exit 주문들
    bracket_signals: Optional[List[Signal]] = None


# =============================================================================
# PendingOrderBook
# =============================================================================

class PendingOrderBook:
    """
    대기 주문 관리.
    매 캔들마다 OHLC를 기준으로 체결 여부를 판정.
    """

    def __init__(self):
        self._orders: List[PendingOrder] = []

    def add(self, order: PendingOrder):
        self._orders.append(order)

    def cancel(self, order_id: str) -> bool:
        for o in self._orders:
            if o.order_id == order_id and o.is_active:
                o.is_active = False
                return True
        return False

    def cancel_all(self):
        self._orders.clear()

    def cancel_by_side(self, side: OrderSide):
        """특정 방향의 대기 주문 모두 취소."""
        self._orders = [o for o in self._orders if not (o.is_active and o.signal.side == side)]

    @property
    def active_orders(self) -> List[PendingOrder]:
        return [o for o in self._orders if o.is_active]

    def evaluate(self, candle: Dict[str, Any], current_time: datetime) -> List[Fill]:
        """
        캔들 OHLC로 대기 주문 체결 판정.

        체결 규칙:
        - LIMIT BUY: low <= price → 체결 at price
        - LIMIT SELL: high >= price → 체결 at price
        - STOP_MARKET BUY: high >= stop_price → 체결 at stop_price
        - STOP_MARKET SELL: low <= stop_price → 체결 at stop_price
        - STOP_LIMIT: stop_price 트리거 → LIMIT으로 전환 → 같은 캔들에서 LIMIT 체결 시도
        - TAKE_PROFIT: LIMIT과 동일 (의미적 구분)
        - TAKE_PROFIT_LIMIT: LIMIT과 동일 (의미적 구분)
        - TRAILING_STOP: 고점/저점 추적 → 콜백 도달 시 시장가 체결
        """
        fills: List[Fill] = []
        filled_group_ids: set = set()

        low = candle.get("low", candle["close"])
        high = candle.get("high", candle["close"])
        close = candle["close"]

        for order in self._orders:
            if not order.is_active:
                continue

            # OCO: 같은 그룹에서 이미 체결된 것이 있으면 취소
            if order.group_id and order.group_id in filled_group_ids:
                order.is_active = False
                continue

            sig = order.signal
            filled = False
            fill_price = 0.0

            # --- MARKET (대기열에 들어올 일은 없지만 안전장치) ---
            if sig.order_type == OrderType.MARKET:
                filled = True
                fill_price = close

            # --- LIMIT ---
            elif sig.order_type in (OrderType.LIMIT, OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_LIMIT):
                if sig.side == OrderSide.BUY and low <= sig.price:
                    filled = True
                    fill_price = sig.price
                elif sig.side == OrderSide.SELL and high >= sig.price:
                    filled = True
                    fill_price = sig.price

            # --- STOP_MARKET ---
            elif sig.order_type == OrderType.STOP_MARKET:
                trigger = sig.stop_price if sig.stop_price > 0 else sig.price
                if sig.side == OrderSide.BUY and high >= trigger:
                    filled = True
                    fill_price = trigger
                elif sig.side == OrderSide.SELL and low <= trigger:
                    filled = True
                    fill_price = trigger

            # --- STOP_LIMIT ---
            elif sig.order_type == OrderType.STOP_LIMIT:
                trigger = sig.stop_price if sig.stop_price > 0 else sig.price
                if not order.stop_triggered:
                    # Step 1: 트리거 확인
                    if sig.side == OrderSide.BUY and high >= trigger:
                        order.stop_triggered = True
                    elif sig.side == OrderSide.SELL and low <= trigger:
                        order.stop_triggered = True

                if order.stop_triggered:
                    # Step 2: LIMIT으로 체결 시도 (같은 캔들에서도 가능)
                    limit_price = sig.price
                    if sig.side == OrderSide.BUY and low <= limit_price:
                        filled = True
                        fill_price = limit_price
                    elif sig.side == OrderSide.SELL and high >= limit_price:
                        filled = True
                        fill_price = limit_price

            # --- TRAILING_STOP ---
            elif sig.order_type == OrderType.TRAILING_STOP:
                delta_pct = sig.trailing_delta / 100.0 if sig.trailing_delta > 0 else 0.01

                if sig.side == OrderSide.SELL:
                    # 매도 트레일링: 고점 추적 → 콜백 하락 시 체결
                    if order.trailing_peak <= 0:
                        order.trailing_peak = high
                    else:
                        order.trailing_peak = max(order.trailing_peak, high)

                    if order.trailing_peak > 0:
                        drop = (order.trailing_peak - low) / order.trailing_peak
                        if drop >= delta_pct:
                            filled = True
                            # 체결가: peak에서 delta만큼 떨어진 가격
                            fill_price = order.trailing_peak * (1 - delta_pct)

                elif sig.side == OrderSide.BUY:
                    # 매수 트레일링: 저점 추적 → 콜백 상승 시 체결
                    if order.trailing_peak <= 0:
                        order.trailing_peak = low
                    else:
                        order.trailing_peak = min(order.trailing_peak, low)

                    if order.trailing_peak > 0:
                        rise = (high - order.trailing_peak) / order.trailing_peak
                        if rise >= delta_pct:
                            filled = True
                            fill_price = order.trailing_peak * (1 + delta_pct)

            # --- 체결 처리 ---
            if filled:
                fills.append(Fill(
                    order_id=order.order_id,
                    side=sig.side,
                    price=fill_price,
                    quantity=sig.quantity,
                    time=current_time,
                    level=sig.level,
                    is_exit=sig.is_exit,
                    order_type=sig.order_type,
                    bracket_signals=order.bracket_signals,
                ))
                order.is_active = False

                # OCO 그룹 추적
                if order.group_id:
                    filled_group_ids.add(order.group_id)

        # OCO 후처리: 체결된 그룹의 나머지 주문도 취소
        if filled_group_ids:
            for order in self._orders:
                if order.is_active and order.group_id in filled_group_ids:
                    order.is_active = False

        # 체결/취소된 주문 제거
        self._orders = [o for o in self._orders if o.is_active]

        return fills


# =============================================================================
# BacktestExecutor
# =============================================================================

class BacktestExecutor:
    """
    백테스트 실행 엔진.
    기존 backtest.py의 캐시/마진/레버리지/포지션 관리 로직을 캡슐화.
    Signal을 받아 주문을 실행하고, 거래 내역과 에쿼티 커브를 기록.
    """

    def __init__(
        self,
        initial_capital: float = 10_000_000,
        leverage: int = 1,
        config: Dict[str, Any] = None,
    ):
        self.initial_capital = initial_capital
        self.leverage = max(1, leverage)
        self.config = config or {}

        # Position state
        self.cash = initial_capital
        self.holdings = 0.0
        self.margin_used = 0.0
        self.notional_cost = 0.0

        # Trade records
        self.raw_trades: List[Dict] = []
        self.equity_curve: List[Dict] = []

        # Pending orders
        self.pending_book = PendingOrderBook()

    # --- Margin logic (API BacktestContext 동일) ---

    def _buy_margin(self, price: float, qty: float) -> bool:
        """Buy: cash에서 마진만 차감."""
        cost = price * qty
        margin = cost / self.leverage if self.leverage > 1 else cost
        if self.cash < margin:
            return False
        self.cash -= margin
        self.holdings += qty
        if self.leverage > 1:
            self.margin_used += margin
            self.notional_cost += cost
        return True

    def _sell_margin(self, price: float, qty: float):
        """Sell: 마진 + PnL 반환."""
        if self.leverage > 1 and self.notional_cost > 0:
            revenue = price * qty
            pnl = revenue - self.notional_cost
            self.cash += self.margin_used + pnl
            self.margin_used = 0.0
            self.notional_cost = 0.0
        else:
            self.cash += price * qty
        self.holdings = 0

    def get_equity(self, current_price: float) -> float:
        """현재 에쿼티 계산."""
        if self.leverage > 1 and self.holdings > 0:
            unrealized_pnl = (current_price * self.holdings) - self.notional_cost
            return self.cash + self.margin_used + unrealized_pnl
        return self.cash + self.holdings * current_price

    # --- Signal execution ---

    def submit(
        self,
        signal: Signal,
        strategy,  # MartingaleStrategy
        current_time: datetime,
        current_price: float,
    ) -> Optional[Fill]:
        """
        시그널을 실행.
        MARKET → 즉시 체결.
        LIMIT/STOP → 대기 주문으로 등록.

        Returns: Fill (즉시 체결 시) 또는 None
        """
        if signal.order_type == OrderType.MARKET:
            return self._execute_market(signal, strategy, current_time, current_price)

        # LIMIT / STOP_MARKET / TRAILING 등 → 대기 등록
        order = PendingOrder(signal=signal, submitted_at=current_time)

        if signal.linked_signals:
            # Entry + Exit linked → Bracket (exit은 entry 체결 후 등록)
            # Exit + Exit linked → OCO (즉시 같은 그룹으로 등록)
            all_exits = all(s.is_exit for s in signal.linked_signals)

            if signal.is_exit and all_exits:
                # OCO: 모두 exit → 같은 그룹으로 즉시 등록
                group_id = str(uuid.uuid4())[:8]
                order.group_id = group_id
                self.pending_book.add(order)
                for linked in signal.linked_signals:
                    self.pending_book.add(PendingOrder(
                        signal=linked, submitted_at=current_time,
                        group_id=group_id,
                    ))
            else:
                # Bracket: entry 주문에 exit을 보관, 체결 시 등록
                order.bracket_signals = signal.linked_signals
                self.pending_book.add(order)
        else:
            self.pending_book.add(order)

        return None

    def _execute_market(
        self,
        signal: Signal,
        strategy,
        current_time: datetime,
        current_price: float,
    ) -> Optional[Fill]:
        """MARKET 주문 즉시 체결."""
        fill_price = signal.price if signal.price > 0 else current_price

        if signal.is_exit:
            return self._execute_sell(signal, strategy, fill_price, current_time)
        else:
            return self._execute_buy(signal, strategy, fill_price, current_time)

    def _execute_buy(
        self,
        signal: Signal,
        strategy,
        price: float,
        time: datetime,
    ) -> Optional[Fill]:
        """매수 체결."""
        qty = signal.quantity
        if qty <= 0:
            qty = strategy.calculate_quantity(
                signal.level, price, self.cash, self.initial_capital
            )
        if qty <= 0:
            return None

        if not self._buy_margin(price, qty):
            return None

        # L1 진입 시 cycle_start_equity 설정
        if signal.level == 1:
            cse = signal.metadata.get("cycle_start_equity")
            if cse is not None:
                strategy._cycle_start_equity = cse
            else:
                strategy._cycle_start_equity = self.get_equity(price)

            strategy.is_short = (signal.direction == "short")
            strategy.peak_price = price

        strategy.add_entry(signal.level, price, qty, time)

        self.raw_trades.append({
            "type": "buy",
            "price": price,
            "quantity": qty,
            "time": time.isoformat() if isinstance(time, datetime) else str(time),
        })

        return Fill(
            order_id=signal.client_order_id or str(uuid.uuid4())[:8],
            side=OrderSide.BUY,
            price=price,
            quantity=qty,
            time=time,
            level=signal.level,
            is_exit=False,
            order_type=signal.order_type,
        )

    def _execute_sell(
        self,
        signal: Signal,
        strategy,
        price: float,
        time: datetime,
    ) -> Optional[Fill]:
        """매도 체결."""
        if strategy.current_level == 0:
            return None

        sell_qty = strategy.total_quantity

        # raw_trade 기록 (FIFO 매칭용)
        raw_entry = {
            "type": "sell",
            "price": price,
            "quantity": sell_qty,
            "time": time.isoformat() if isinstance(time, datetime) else str(time),
            "cycle_start_equity": strategy._cycle_start_equity,
        }
        if signal.metadata.get("force_liquidated"):
            raw_entry["force_liquidated"] = True
        self.raw_trades.append(raw_entry)

        # 전략 포지션 청산 → Trade 생성
        trade = strategy.close_position(price, time)
        self._sell_margin(price, trade.total_quantity)

        # _trigger_armed 리셋 (API 엔진 동일)
        if hasattr(strategy, '_trigger_armed'):
            strategy._trigger_armed = True

        # Trade 저장은 외부에서 수집하지 않고 executor 내부에서 관리
        # (StrategyAdapter에서 접근)
        self._last_trade = trade

        return Fill(
            order_id=signal.client_order_id or str(uuid.uuid4())[:8],
            side=OrderSide.SELL,
            price=price,
            quantity=sell_qty,
            time=time,
            level=0,
            is_exit=True,
            order_type=signal.order_type,
        )

    # --- Pending order processing ---

    def on_candle(
        self,
        candle: Dict[str, Any],
        strategy,
        current_time: datetime,
    ) -> List[Fill]:
        """
        매 캔들마다 대기 주문 체결 확인.
        체결된 주문은 즉시 실행.
        """
        fills_from_pending = self.pending_book.evaluate(candle, current_time)
        executed_fills: List[Fill] = []

        for pending_fill in fills_from_pending:
            # 대기 주문 체결 → 실제 실행
            sig = Signal(
                side=pending_fill.side,
                order_type=pending_fill.order_type,
                price=pending_fill.price,
                quantity=pending_fill.quantity,
                level=pending_fill.level,
                is_exit=pending_fill.is_exit,
            )

            if sig.is_exit:
                fill = self._execute_sell(sig, strategy, pending_fill.price, current_time)
            else:
                fill = self._execute_buy(sig, strategy, pending_fill.price, current_time)

            if fill:
                executed_fills.append(fill)

                # Bracket: entry 체결 → linked exit 주문을 OCO로 등록
                if pending_fill.bracket_signals and not sig.is_exit:
                    oco_group = str(uuid.uuid4())[:8]
                    for bracket_sig in pending_fill.bracket_signals:
                        self.pending_book.add(PendingOrder(
                            signal=bracket_sig,
                            submitted_at=current_time,
                            group_id=oco_group,
                        ))

                # 청산 체결 시 남은 exit 대기 주문 정리
                if sig.is_exit:
                    self.pending_book.cancel_by_side(OrderSide.SELL)

        return executed_fills

    # --- Equity recording ---

    def record_equity(self, current_price: float, ts: datetime):
        """에쿼티 커브 기록."""
        equity = self.get_equity(current_price)
        self.equity_curve.append({
            "date": ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime) else str(ts),
            "equity": equity,
        })

    # --- Force liquidation ---

    def force_liquidate(self, strategy, final_price: float, final_ts: datetime):
        """백테스트 종료 시 잔여 포지션 강제 청산."""
        # 대기 주문 전부 취소
        self.pending_book.cancel_all()

        if strategy.current_level == 0:
            return

        signal = Signal(
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            is_exit=True,
            reason="force_liquidated",
            metadata={"force_liquidated": True},
        )
        self._execute_sell(signal, strategy, final_price, final_ts)

        # 마지막 에쿼티 업데이트
        if self.equity_curve:
            self.equity_curve[-1]["equity"] = self.cash


# =============================================================================
# StrategyAdapter
# =============================================================================

class StrategyAdapter:
    """
    기존 MartingaleStrategy를 Signal 시스템으로 연결하는 어댑터.
    전략의 _check_*_trigger() 호출 → Signal 발신.
    backtest.py의 시뮬레이션 루프 로직을 재현.
    """

    def __init__(self, strategy):
        self.strategy = strategy
        self._current_trading_date = None
        self._trades: list = []

    @property
    def trades(self) -> list:
        return self._trades

    def process_candle(
        self,
        candle: Dict[str, Any],
        ts: datetime,
        current_price: float,
        executor: BacktestExecutor,
    ) -> List[Signal]:
        """
        캔들 하나를 처리하여 Signal 목록을 반환.
        기존 backtest.py 루프 로직과 동일한 순서:
        1. _on_candle 훅
        2. Daily reset
        3. 청산 확인 (전략 / 가격 기반)
        4. 추가매수 확인 (L2+)
        5. L1 진입 확인

        Returns: 발신할 Signal 목록
        """
        strategy = self.strategy
        signals: List[Signal] = []
        exited = False

        # 0. Indicator update hook
        if hasattr(strategy, '_on_candle'):
            strategy._on_candle(candle)

        # 1. Daily reset
        current_date = ts.date() if isinstance(ts, datetime) else None
        if current_date and self._current_trading_date != current_date:
            self._current_trading_date = current_date
            if strategy.current_level == 0:
                if hasattr(strategy, 'reference_price'):
                    strategy.reference_price = None

        # A. Check exits if holding
        if strategy.current_level > 0:
            # A1. Strategy-based exit
            should_strategy_exit = strategy._check_exit_trigger(candle)

            if should_strategy_exit:
                signals.append(Signal(
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    is_exit=True,
                    reason="strategy_exit",
                ))
                exited = True

            else:
                # A2. Price-based exits (trailing, max_loss, timeout)
                exit_reason = strategy.check_exits(current_price, ts)
                if exit_reason:
                    signals.append(Signal(
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        is_exit=True,
                        reason=exit_reason,
                    ))
                    exited = True

                else:
                    # A3. Additional entry (L2+)
                    if (strategy.current_level < strategy.config["max_buy_count"]
                            and not strategy.trailing_active):
                        should_add = False

                        if strategy.config["additional_buy_mode"] == "step":
                            should_add = strategy._check_step_trigger(current_price)
                        else:
                            should_add = strategy._check_additional_trigger(candle)

                        if should_add and strategy._check_require_lower(current_price):
                            next_level = strategy.current_level + 1
                            signals.append(Signal(
                                side=OrderSide.BUY,
                                order_type=OrderType.MARKET,
                                level=next_level,
                                reason="additional_entry",
                            ))

        # B. L1 entry if no position
        # API: exit 후 같은 캔들에서 재진입 불가
        if not exited and strategy.current_level == 0:
            direction = strategy._check_entry_trigger(candle)
            if direction:
                # cycle_start_equity 계산
                cse = executor.get_equity(current_price)

                signals.append(Signal(
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    level=1,
                    direction=direction,
                    reason="entry_trigger",
                    metadata={"cycle_start_equity": cse},
                ))

        return signals

    def execute_signals(
        self,
        signals: List[Signal],
        executor: BacktestExecutor,
        ts: datetime,
        current_price: float,
    ):
        """
        시그널 목록을 실행하고 Trade 결과를 수집.
        """
        for signal in signals:
            executor._last_trade = None
            fill = executor.submit(signal, self.strategy, ts, current_price)
            if fill and fill.is_exit and executor._last_trade is not None:
                self._trades.append(executor._last_trade)
