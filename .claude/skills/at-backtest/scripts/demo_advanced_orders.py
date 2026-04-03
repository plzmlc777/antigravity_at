#!/usr/bin/env python3
"""
Demo: Extended Order Types (Phase 2)
ExecutionEngine의 LIMIT, STOP_MARKET, STOP_LIMIT, TRAILING_STOP,
TAKE_PROFIT, OCO 주문을 검증하는 데모 스크립트.

Usage:
    python demo_advanced_orders.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from execution_engine import (
    OrderType, OrderSide, Signal, PendingOrder, PendingOrderBook, Fill,
)


def make_candle(ts: datetime, o: float, h: float, l: float, c: float) -> dict:
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c}


def test_limit_buy():
    """LIMIT BUY: low가 지정가 이하이면 체결."""
    print("=== Test: LIMIT BUY ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    sig = Signal(side=OrderSide.BUY, order_type=OrderType.LIMIT, price=100.0, quantity=10)
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # 캔들1: low=101 → 미체결
    fills = book.evaluate(make_candle(t0, 102, 103, 101, 102), t0)
    assert len(fills) == 0, f"Expected 0 fills, got {len(fills)}"
    assert len(book.active_orders) == 1

    # 캔들2: low=99 → 체결
    t1 = t0 + timedelta(minutes=1)
    fills = book.evaluate(make_candle(t1, 101, 102, 99, 100), t1)
    assert len(fills) == 1, f"Expected 1 fill, got {len(fills)}"
    assert fills[0].price == 100.0
    assert fills[0].side == OrderSide.BUY
    print(f"  PASS: filled at {fills[0].price}")


def test_limit_sell():
    """LIMIT SELL: high가 지정가 이상이면 체결."""
    print("=== Test: LIMIT SELL ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    sig = Signal(side=OrderSide.SELL, order_type=OrderType.LIMIT, price=110.0, quantity=10, is_exit=True)
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # 캔들1: high=109 → 미체결
    fills = book.evaluate(make_candle(t0, 105, 109, 104, 108), t0)
    assert len(fills) == 0

    # 캔들2: high=111 → 체결
    t1 = t0 + timedelta(minutes=1)
    fills = book.evaluate(make_candle(t1, 108, 111, 107, 110), t1)
    assert len(fills) == 1
    assert fills[0].price == 110.0
    print(f"  PASS: filled at {fills[0].price}")


def test_stop_market_sell():
    """STOP_MARKET SELL: low가 stop_price 이하이면 체결."""
    print("=== Test: STOP_MARKET SELL (stop loss) ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    sig = Signal(
        side=OrderSide.SELL, order_type=OrderType.STOP_MARKET,
        stop_price=95.0, quantity=10, is_exit=True
    )
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # 캔들1: low=96 → 미체결
    fills = book.evaluate(make_candle(t0, 100, 101, 96, 99), t0)
    assert len(fills) == 0

    # 캔들2: low=94 → 체결
    t1 = t0 + timedelta(minutes=1)
    fills = book.evaluate(make_candle(t1, 98, 99, 94, 95), t1)
    assert len(fills) == 1
    assert fills[0].price == 95.0
    print(f"  PASS: filled at {fills[0].price}")


def test_stop_limit():
    """STOP_LIMIT: stop_price 트리거 후 limit price에서 체결."""
    print("=== Test: STOP_LIMIT BUY ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    # stop_price=105에서 트리거, limit price=103에서 매수
    sig = Signal(
        side=OrderSide.BUY, order_type=OrderType.STOP_LIMIT,
        stop_price=105.0, price=103.0, quantity=10
    )
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # 캔들1: high=104 → 트리거 안됨
    fills = book.evaluate(make_candle(t0, 100, 104, 99, 102), t0)
    assert len(fills) == 0

    # 캔들2: high=106 → 트리거됨, low=104 → limit 103 미체결 (low > limit)
    t1 = t0 + timedelta(minutes=1)
    fills = book.evaluate(make_candle(t1, 103, 106, 104, 105), t1)
    assert len(fills) == 0
    # 트리거는 됐으니 active 유지
    assert len(book.active_orders) == 1

    # 캔들3: low=102 → limit 103 체결
    t2 = t0 + timedelta(minutes=2)
    fills = book.evaluate(make_candle(t2, 105, 106, 102, 104), t2)
    assert len(fills) == 1
    assert fills[0].price == 103.0
    print(f"  PASS: triggered then filled at {fills[0].price}")


def test_stop_limit_same_candle():
    """STOP_LIMIT: 같은 캔들에서 트리거 + 체결."""
    print("=== Test: STOP_LIMIT same-candle fill ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    sig = Signal(
        side=OrderSide.BUY, order_type=OrderType.STOP_LIMIT,
        stop_price=105.0, price=103.0, quantity=5
    )
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # 하나의 캔들에서 high >= 105 (트리거) AND low <= 103 (limit 체결)
    fills = book.evaluate(make_candle(t0, 100, 107, 99, 104), t0)
    assert len(fills) == 1
    assert fills[0].price == 103.0
    print(f"  PASS: same-candle trigger+fill at {fills[0].price}")


def test_trailing_stop_sell():
    """TRAILING_STOP SELL: 고점 추적 후 콜백 도달 시 체결."""
    print("=== Test: TRAILING_STOP SELL ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    # trailing_delta=2% 콜백
    sig = Signal(
        side=OrderSide.SELL, order_type=OrderType.TRAILING_STOP,
        trailing_delta=2.0, quantity=10, is_exit=True
    )
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # 캔들1: high=110 → peak=110, low=109 → drop=0.9% < 2% → 미체결
    fills = book.evaluate(make_candle(t0, 105, 110, 109, 109), t0)
    assert len(fills) == 0

    # 캔들2: high=115 → peak=115, low=114 → drop=0.87% → 미체결
    t1 = t0 + timedelta(minutes=1)
    fills = book.evaluate(make_candle(t1, 110, 115, 114, 114), t1)
    assert len(fills) == 0

    # 캔들3: high=116 → peak=116, low=112 → drop=(116-112)/116=3.4% >= 2% → 체결
    t2 = t0 + timedelta(minutes=2)
    fills = book.evaluate(make_candle(t2, 115, 116, 112, 113), t2)
    assert len(fills) == 1
    expected_price = 116 * (1 - 0.02)  # 113.68
    assert abs(fills[0].price - expected_price) < 0.01
    print(f"  PASS: peak=116, filled at {fills[0].price:.2f} (2% callback)")


def test_trailing_stop_buy():
    """TRAILING_STOP BUY: 저점 추적 후 콜백 상승 시 체결."""
    print("=== Test: TRAILING_STOP BUY ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    sig = Signal(
        side=OrderSide.BUY, order_type=OrderType.TRAILING_STOP,
        trailing_delta=3.0, quantity=5
    )
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # 캔들1: low=90 → trough=90, high=91 → rise=1.1% < 3%
    fills = book.evaluate(make_candle(t0, 95, 91, 90, 91), t0)
    assert len(fills) == 0

    # 캔들2: low=88 → trough=88, high=89 → rise=1.1% < 3%
    t1 = t0 + timedelta(minutes=1)
    fills = book.evaluate(make_candle(t1, 90, 89, 88, 89), t1)
    assert len(fills) == 0

    # 캔들3: low=87 → trough=87, high=92 → rise=(92-87)/87=5.7% >= 3% → 체결
    t2 = t0 + timedelta(minutes=2)
    fills = book.evaluate(make_candle(t2, 88, 92, 87, 91), t2)
    assert len(fills) == 1
    expected_price = 87 * (1 + 0.03)  # 89.61
    assert abs(fills[0].price - expected_price) < 0.01
    print(f"  PASS: trough=87, filled at {fills[0].price:.2f} (3% callback)")


def test_take_profit():
    """TAKE_PROFIT: LIMIT SELL과 동일하게 동작."""
    print("=== Test: TAKE_PROFIT ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)

    sig = Signal(
        side=OrderSide.SELL, order_type=OrderType.TAKE_PROFIT,
        price=120.0, quantity=10, is_exit=True
    )
    book.add(PendingOrder(signal=sig, submitted_at=t0))

    # high=121 >= 120 → 체결
    fills = book.evaluate(make_candle(t0, 115, 121, 114, 119), t0)
    assert len(fills) == 1
    assert fills[0].price == 120.0
    assert fills[0].order_type == OrderType.TAKE_PROFIT
    print(f"  PASS: take profit filled at {fills[0].price}")


def test_oco():
    """OCO: 한쪽 체결 시 같은 그룹의 다른 주문 자동 취소."""
    print("=== Test: OCO (One-Cancels-Other) ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)
    group = "oco-001"

    # Take Profit at 120 + Stop Loss at 90 → OCO
    tp = Signal(side=OrderSide.SELL, order_type=OrderType.TAKE_PROFIT, price=120.0, quantity=10, is_exit=True)
    sl = Signal(side=OrderSide.SELL, order_type=OrderType.STOP_MARKET, stop_price=90.0, quantity=10, is_exit=True)

    book.add(PendingOrder(signal=tp, submitted_at=t0, group_id=group))
    book.add(PendingOrder(signal=sl, submitted_at=t0, group_id=group))

    assert len(book.active_orders) == 2

    # 캔들1: high=119, low=91 → 둘 다 미체결
    fills = book.evaluate(make_candle(t0, 100, 119, 91, 105), t0)
    assert len(fills) == 0

    # 캔들2: high=121 → TP 체결, SL 자동 취소
    t1 = t0 + timedelta(minutes=1)
    fills = book.evaluate(make_candle(t1, 105, 121, 100, 118), t1)
    assert len(fills) == 1
    assert fills[0].price == 120.0
    assert fills[0].order_type == OrderType.TAKE_PROFIT
    assert len(book.active_orders) == 0  # SL도 제거됨
    print(f"  PASS: TP filled at {fills[0].price}, SL auto-cancelled")


def test_oco_stop_fires_first():
    """OCO: 스탑이 먼저 체결되면 TP 취소."""
    print("=== Test: OCO (stop fires first) ===")
    book = PendingOrderBook()
    t0 = datetime(2025, 1, 1, 9, 0)
    group = "oco-002"

    tp = Signal(side=OrderSide.SELL, order_type=OrderType.TAKE_PROFIT, price=120.0, quantity=10, is_exit=True)
    sl = Signal(side=OrderSide.SELL, order_type=OrderType.STOP_MARKET, stop_price=90.0, quantity=10, is_exit=True)

    book.add(PendingOrder(signal=tp, submitted_at=t0, group_id=group))
    book.add(PendingOrder(signal=sl, submitted_at=t0, group_id=group))

    # low=89 → SL 체결, TP 취소
    fills = book.evaluate(make_candle(t0, 100, 110, 89, 92), t0)
    assert len(fills) == 1
    assert fills[0].price == 90.0
    assert fills[0].order_type == OrderType.STOP_MARKET
    assert len(book.active_orders) == 0
    print(f"  PASS: SL filled at {fills[0].price}, TP auto-cancelled")


class MockStrategy:
    """테스트용 간이 전략."""
    current_level = 0
    total_quantity = 0
    is_short = False
    peak_price = 0
    _cycle_start_equity = 0
    config = {"max_buy_count": 1}

    def calculate_quantity(self, level, price, cash, capital):
        return 10

    def add_entry(self, level, price, qty, time):
        self.current_level = level
        self.total_quantity = qty

    def close_position(self, price, time):
        from strategies import Trade
        t = Trade(
            entry_time=time, exit_time=time,
            entries=[{"level": 1, "price": 100, "quantity": 10}],
            exit_price=price, total_quantity=self.total_quantity,
            average_price=100, pnl=(price - 100) * self.total_quantity,
        )
        self.current_level = 0
        self.total_quantity = 0
        return t


def test_bracket_order():
    """브라켓 주문: LIMIT entry 체결 → TP+SL OCO 자동 등록."""
    print("=== Test: Bracket Order (LIMIT entry → OCO exit) ===")
    from execution_engine import BacktestExecutor

    executor = BacktestExecutor(initial_capital=100000, leverage=1)
    strategy = MockStrategy()
    t0 = datetime(2025, 1, 1, 9, 0)

    # 엔트리: LIMIT BUY at 100, linked TP at 110 + SL at 95
    entry_signal = Signal(
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=100.0,
        quantity=10,
        level=1,
        direction="long",
        metadata={"cycle_start_equity": 100000},
        linked_signals=[
            Signal(side=OrderSide.SELL, order_type=OrderType.TAKE_PROFIT,
                   price=110.0, quantity=10, is_exit=True),
            Signal(side=OrderSide.SELL, order_type=OrderType.STOP_MARKET,
                   stop_price=95.0, quantity=10, is_exit=True),
        ],
    )

    fill = executor.submit(entry_signal, strategy, t0, 102.0)
    assert fill is None  # LIMIT → 대기
    # Bracket: entry만 대기열에 등록, TP/SL은 아직 미등록
    assert len(executor.pending_book.active_orders) == 1, \
        f"Expected 1 (entry only), got {len(executor.pending_book.active_orders)}"
    print(f"  Step 1: entry pending, exits deferred")

    # 캔들1: low=99 → LIMIT BUY at 100 체결 → TP+SL OCO 자동 등록
    t1 = t0 + timedelta(minutes=1)
    executed = executor.on_candle(make_candle(t1, 101, 103, 99, 101), strategy, t1)
    assert len(executed) == 1, f"Expected 1 fill, got {len(executed)}"
    assert executed[0].side == OrderSide.BUY
    assert strategy.current_level == 1
    print(f"  Step 2: entry filled at {executed[0].price}")

    # 이제 TP+SL이 OCO로 등록되어 있어야 함
    active = executor.pending_book.active_orders
    assert len(active) == 2, f"Expected 2 exits (TP+SL), got {len(active)}"
    groups = {o.group_id for o in active}
    assert len(groups) == 1 and "" not in groups, "TP+SL should share OCO group"
    print(f"  Step 3: TP+SL registered as OCO group={groups.pop()}")

    # 캔들2: high=111 → TP 체결, SL 자동 취소
    t2 = t0 + timedelta(minutes=2)
    executed = executor.on_candle(make_candle(t2, 101, 111, 100, 109), strategy, t2)
    assert len(executed) == 1
    assert executed[0].price == 110.0
    assert executed[0].is_exit
    assert len(executor.pending_book.active_orders) == 0
    print(f"  Step 4: TP filled at {executed[0].price}, SL auto-cancelled")
    print(f"  PASS: full bracket lifecycle OK")


def test_bracket_stop_loss_fires():
    """브라켓 주문: entry 후 SL이 먼저 체결, TP 취소."""
    print("=== Test: Bracket Order (SL fires, TP cancelled) ===")
    from execution_engine import BacktestExecutor

    executor = BacktestExecutor(initial_capital=100000, leverage=1)
    strategy = MockStrategy()
    t0 = datetime(2025, 1, 1, 9, 0)

    entry_signal = Signal(
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=100.0, quantity=10, level=1,
        direction="long",
        metadata={"cycle_start_equity": 100000},
        linked_signals=[
            Signal(side=OrderSide.SELL, order_type=OrderType.TAKE_PROFIT,
                   price=115.0, quantity=10, is_exit=True),
            Signal(side=OrderSide.SELL, order_type=OrderType.STOP_MARKET,
                   stop_price=92.0, quantity=10, is_exit=True),
        ],
    )

    executor.submit(entry_signal, strategy, t0, 102.0)

    # 캔들1: entry 체결
    t1 = t0 + timedelta(minutes=1)
    executor.on_candle(make_candle(t1, 101, 103, 98, 101), strategy, t1)
    assert strategy.current_level == 1
    assert len(executor.pending_book.active_orders) == 2

    # 캔들2: low=91 → SL 체결
    t2 = t0 + timedelta(minutes=2)
    executed = executor.on_candle(make_candle(t2, 100, 101, 91, 93), strategy, t2)
    assert len(executed) == 1
    assert executed[0].price == 92.0
    assert executed[0].order_type == OrderType.STOP_MARKET
    assert len(executor.pending_book.active_orders) == 0
    print(f"  SL filled at {executed[0].price}, TP auto-cancelled")
    print(f"  PASS")


def main():
    print("=" * 60)
    print("  ExecutionEngine Phase 2: Extended Order Types Demo")
    print("=" * 60)
    print()

    tests = [
        test_limit_buy,
        test_limit_sell,
        test_stop_market_sell,
        test_stop_limit,
        test_stop_limit_same_candle,
        test_trailing_stop_sell,
        test_trailing_stop_buy,
        test_take_profit,
        test_oco,
        test_oco_stop_fires_first,
        test_bracket_order,
        test_bracket_stop_loss_fires,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed / {len(tests)} total")
    print(f"{'=' * 60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
