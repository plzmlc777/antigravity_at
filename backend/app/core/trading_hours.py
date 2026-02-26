"""
거래소별 거래시간 계산 유틸리티.

캘린더 시간이 아닌 실제 거래시간만 카운트.
- Kiwoom: 평일 09:00~15:30 KST (6.5h/일)
- Binance/BinanceFutures: 24/7 (변환 없음)
"""

from datetime import datetime, time, timedelta
from .config import DEFAULT_EXCHANGE

# 거래소별 거래시간 (캔들 timestamp이 이미 현지시간 기준)
TRADING_HOURS = {
    "Kiwoom": {"open": time(9, 0), "close": time(15, 30), "daily_hours": 6.5, "24h": False},
    "Binance": {"24h": True},
    "BinanceFutures": {"24h": True},
}


def calc_trading_seconds(start: datetime, end: datetime, exchange_name: str = DEFAULT_EXCHANGE) -> float:
    """start~end 사이의 실제 거래시간(초) 계산.

    Binance: 24/7이므로 (end-start).total_seconds() 그대로 반환.
    Kiwoom: 평일 09:00~15:30만 카운트. 주말 제외.
    """
    if start >= end:
        return 0.0

    config = TRADING_HOURS.get(exchange_name, TRADING_HOURS.get(DEFAULT_EXCHANGE))

    # 24h 거래소: 달력 시간 그대로
    if config.get("24h"):
        return (end - start).total_seconds()

    # 거래시간 제한 거래소 (Kiwoom 등)
    market_open = config["open"]
    market_close = config["close"]

    total = 0.0
    current = start

    while current.date() <= end.date():
        # 주말 스킵 (5=토, 6=일)
        if current.weekday() >= 5:
            current = datetime.combine(current.date() + timedelta(days=1), market_open)
            continue

        day_open = datetime.combine(current.date(), market_open)
        day_close = datetime.combine(current.date(), market_close)

        # 이 날의 유효 구간
        effective_start = max(current, day_open)
        effective_end = min(end, day_close)

        if effective_start < effective_end:
            total += (effective_end - effective_start).total_seconds()

        # 다음 날로
        current = datetime.combine(current.date() + timedelta(days=1), market_open)

    return total
