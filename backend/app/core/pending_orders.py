"""
PendingOrderBook - 대기 주문 관리 모듈.
BacktestContext 및 ExecutionEngine에서 공통 사용.

지원 주문 타입:
    MARKET, LIMIT, STOP_MARKET, STOP_LIMIT,
    TRAILING_STOP, TAKE_PROFIT, TAKE_PROFIT_LIMIT

지원 기능:
    OCO (One-Cancels-Other) - group_id 기반
    Bracket - entry 체결 후 exit OCO 자동 등록
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
import uuid


class OrderType(Enum):
    """주문 유형."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class OrderSide(Enum):
    """주문 방향."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class PendingOrder:
    """대기 중인 주문."""
    side: OrderSide
    order_type: OrderType
    price: float = 0.0
    stop_price: float = 0.0
    quantity: float = 0.0
    trailing_delta: float = 0.0  # TRAILING_STOP 콜백 %
    metadata: Dict[str, Any] = field(default_factory=dict)
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    submitted_at: Optional[datetime] = None
    is_active: bool = True
    # STOP_LIMIT: 트리거 후 LIMIT으로 전환
    stop_triggered: bool = False
    # TRAILING_STOP: 추적 중인 고점/저점
    trailing_peak: float = 0.0
    # OCO 그룹 ID
    group_id: str = ""
    # Bracket: entry 체결 후 등록할 연결 주문
    bracket_orders: Optional[List['PendingOrder']] = None
    # on_filled 콜백
    on_filled: Any = None


@dataclass
class PendingFill:
    """대기 주문 체결 결과."""
    order_id: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: float
    time: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    bracket_orders: Optional[List['PendingOrder']] = None
    on_filled: Any = None


class PendingOrderBook:
    """
    대기 주문 관리. 매 캔들마다 OHLC로 체결 여부를 판정.

    Usage:
        book = PendingOrderBook()
        book.add(PendingOrder(side=OrderSide.BUY, order_type=OrderType.LIMIT, price=100))

        # 매 캔들마다:
        fills = book.evaluate(candle, current_time)
        for fill in fills:
            # 체결 처리
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
        self._orders = [o for o in self._orders if not (o.is_active and o.side == side)]

    @property
    def active_orders(self) -> List[PendingOrder]:
        return [o for o in self._orders if o.is_active]

    def evaluate(self, candle: Dict[str, Any], current_time: datetime) -> List[PendingFill]:
        """
        캔들 OHLC로 대기 주문 체결 판정.

        체결 규칙:
        - LIMIT BUY: low <= price
        - LIMIT SELL: high >= price
        - STOP_MARKET BUY: high >= stop_price
        - STOP_MARKET SELL: low <= stop_price
        - STOP_LIMIT: stop_price 트리거 → LIMIT 체결 시도
        - TRAILING_STOP: 고점/저점 추적 → 콜백 도달 시 체결
        - TAKE_PROFIT/TAKE_PROFIT_LIMIT: LIMIT과 동일
        """
        fills: List[PendingFill] = []
        filled_group_ids: set = set()

        low = candle.get("low", candle["close"])
        high = candle.get("high", candle["close"])
        close = candle["close"]

        for order in self._orders:
            if not order.is_active:
                continue

            # OCO: 같은 그룹에서 이미 체결 → 취소
            if order.group_id and order.group_id in filled_group_ids:
                order.is_active = False
                continue

            filled = False
            fill_price = 0.0
            ot = order.order_type

            # --- MARKET ---
            if ot == OrderType.MARKET:
                filled = True
                fill_price = close

            # --- LIMIT / TAKE_PROFIT ---
            elif ot in (OrderType.LIMIT, OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_LIMIT):
                if order.side == OrderSide.BUY and low <= order.price:
                    filled, fill_price = True, order.price
                elif order.side == OrderSide.SELL and high >= order.price:
                    filled, fill_price = True, order.price

            # --- STOP_MARKET ---
            elif ot == OrderType.STOP_MARKET:
                trigger = order.stop_price if order.stop_price > 0 else order.price
                if order.side == OrderSide.BUY and high >= trigger:
                    filled, fill_price = True, trigger
                elif order.side == OrderSide.SELL and low <= trigger:
                    filled, fill_price = True, trigger

            # --- STOP_LIMIT ---
            elif ot == OrderType.STOP_LIMIT:
                trigger = order.stop_price if order.stop_price > 0 else order.price
                if not order.stop_triggered:
                    if order.side == OrderSide.BUY and high >= trigger:
                        order.stop_triggered = True
                    elif order.side == OrderSide.SELL and low <= trigger:
                        order.stop_triggered = True

                if order.stop_triggered:
                    if order.side == OrderSide.BUY and low <= order.price:
                        filled, fill_price = True, order.price
                    elif order.side == OrderSide.SELL and high >= order.price:
                        filled, fill_price = True, order.price

            # --- TRAILING_STOP ---
            elif ot == OrderType.TRAILING_STOP:
                delta_pct = order.trailing_delta / 100.0 if order.trailing_delta > 0 else 0.01

                if order.side == OrderSide.SELL:
                    if order.trailing_peak <= 0:
                        order.trailing_peak = high
                    else:
                        order.trailing_peak = max(order.trailing_peak, high)

                    if order.trailing_peak > 0:
                        drop = (order.trailing_peak - low) / order.trailing_peak
                        if drop >= delta_pct:
                            filled = True
                            fill_price = order.trailing_peak * (1 - delta_pct)

                elif order.side == OrderSide.BUY:
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
                fills.append(PendingFill(
                    order_id=order.order_id,
                    side=order.side,
                    order_type=order.order_type,
                    price=fill_price,
                    quantity=order.quantity,
                    time=current_time,
                    metadata=order.metadata,
                    bracket_orders=order.bracket_orders,
                    on_filled=order.on_filled,
                ))
                order.is_active = False

                if order.group_id:
                    filled_group_ids.add(order.group_id)

        # OCO 후처리
        if filled_group_ids:
            for order in self._orders:
                if order.is_active and order.group_id in filled_group_ids:
                    order.is_active = False

        # 정리
        self._orders = [o for o in self._orders if o.is_active]

        return fills
