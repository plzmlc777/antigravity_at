"""
Centralized Quantity & Price Rules - Single Source of Truth

거래소별 최소 주문 수량, step size, min notional, tick size 규칙.
백테스트와 실거래 모두 동일한 보정 로직 적용.
"""

from .config import DEFAULT_EXCHANGE
import math
import logging

logger = logging.getLogger(__name__)

# ── 거래소별 수량 규칙 ──
# Binance는 심볼별 동적 필터(symbol_filters)로 오버라이드 가능
EXCHANGE_QTY_RULES = {
    "Kiwoom": {
        "min_qty": 1,
        "step_size": 1,
        "min_notional": 0,
        "qty_type": "int",
    },
    # 미국주식: 정수주 1주 단위 (소수점 매매 미지원), 최소 주문금액 없음
    "KiwoomUS": {
        "min_qty": 1,
        "step_size": 1,
        "min_notional": 0,
        "qty_type": "int",
    },
    "Binance": {
        "min_qty": 0.00001,
        "step_size": 0.00001,
        "min_notional": 5,
        "qty_type": "float",
    },
    "BinanceFutures": {
        "min_qty": 0.001,
        "step_size": 0.001,
        "min_notional": 5,
        "qty_type": "float",
    },
}

_DEFAULT_RULES = EXCHANGE_QTY_RULES[DEFAULT_EXCHANGE]


def _count_decimals(value: float) -> int:
    """소수점 자릿수 계산 (과학적 표기법 대응: str(0.00001) → '1e-05')."""
    if value <= 0:
        return 0
    # f-string으로 과학적 표기법 방지
    s = f"{value:.15f}".rstrip('0')
    if '.' not in s:
        return 0
    return len(s.split('.')[-1])


def adjust_qty(
    quantity: float,
    exchange_name: str = DEFAULT_EXCHANGE,
    price: float = 0,
    symbol_filters: dict = None,
    available_cash: float = None,
) -> float:
    """
    거래소별 수량 보정.

    Args:
        quantity: 전략에서 계산된 raw 수량
        exchange_name: "Kiwoom", "Binance", "BinanceFutures"
        price: 현재 가격 (minNotional 체크용)
        symbol_filters: Binance API에서 로드한 심볼별 동적 필터
                       (keys: stepSize, minQty, minNotional)
        available_cash: 사용 가능한 잔고 (제공 시 자금 초과 방지 후 최소 수량 올림)

    Returns:
        보정된 수량 (자금 부족 시 0 반환)
    """
    if quantity <= 0:
        return 0

    rules = EXCHANGE_QTY_RULES.get(exchange_name, _DEFAULT_RULES)

    # 동적 심볼 필터로 정적 기본값 오버라이드
    step_size = float(symbol_filters.get("stepSize", rules["step_size"])) if symbol_filters else rules["step_size"]
    min_qty = float(symbol_filters.get("minQty", rules["min_qty"])) if symbol_filters else rules["min_qty"]
    min_notional = float(symbol_filters.get("minNotional", rules["min_notional"])) if symbol_filters else rules["min_notional"]
    qty_type = rules.get("qty_type", "float")

    # 1. stepSize floor
    if step_size > 0:
        adjusted = math.floor(quantity / step_size) * step_size
    else:
        adjusted = quantity

    # 2. int/float 타입 변환
    if qty_type == "int":
        adjusted = int(adjusted)
    else:
        decimals = _count_decimals(step_size)
        adjusted = round(adjusted, decimals)

    # 3. minQty 체크 — 미달 시 자금 여유가 있으면 최소 수량으로 올림
    if adjusted < min_qty:
        if available_cash is not None and price > 0 and available_cash >= min_qty * price:
            adjusted = min_qty
            logger.debug(f"[qty_rules] Bumped to minQty {min_qty} (cash {available_cash:.0f} sufficient)")
        else:
            logger.debug(f"[qty_rules] {adjusted} < minQty {min_qty}, insufficient cash ({exchange_name})")
            return 0

    # 4. minNotional 체크 — 미달 시 자금 여유가 있으면 최소 notional 충족 수량으로 올림
    if min_notional > 0 and price > 0:
        notional = adjusted * price
        if notional < min_notional:
            min_notional_qty = math.ceil(min_notional / price / step_size) * step_size if step_size > 0 else min_notional / price
            if qty_type != "int":
                decimals = _count_decimals(step_size)
                min_notional_qty = round(min_notional_qty, decimals)
            if available_cash is not None and available_cash >= min_notional_qty * price:
                adjusted = max(adjusted, min_notional_qty)
                logger.debug(f"[qty_rules] Bumped to {adjusted} for minNotional {min_notional} (cash sufficient)")
            else:
                logger.debug(f"[qty_rules] notional {notional:.2f} < minNotional {min_notional}, insufficient cash ({exchange_name})")
                return 0

    return float(adjusted)


# ── 한국 주식 호가단위 (KRX Tick Size Rules) ──
# 가격대별 호가 단위 (2023년 기준)
KRX_TICK_SIZES = [
    (2_000,     1),
    (5_000,     5),
    (20_000,    10),
    (50_000,    50),
    (200_000,   100),
    (500_000,   500),
    (float('inf'), 1_000),
]


def _get_krx_tick_size(price: float) -> float:
    """한국 주식 가격대별 호가단위 반환."""
    for threshold, tick in KRX_TICK_SIZES:
        if price < threshold:
            return tick
    return 1_000


def adjust_price(
    price: float,
    exchange_name: str = DEFAULT_EXCHANGE,
    symbol_filters: dict = None,
) -> float:
    """
    거래소별 가격 보정 (tick size 기준 반올림).

    Args:
        price: 전략에서 계산된 raw 가격
        exchange_name: "Kiwoom", "KIS", "Binance", "BinanceFutures"
        symbol_filters: Binance API exchangeInfo의 심볼별 필터
                       (keys: tickSize, stepSize, minNotional)

    Returns:
        tick size에 맞게 반올림된 가격
    """
    if price <= 0:
        return 0

    # Binance: 동적 tickSize 사용 (symbol_filters 우선)
    if exchange_name in ("Binance", "BinanceFutures"):
        if symbol_filters:
            tick_size = float(symbol_filters.get("tickSize", "0.0001"))
        else:
            # exchangeInfo 미로드 시 가격 크기 기반 합리적 기본값
            if price < 1:
                tick_size = 0.0001
            elif price < 100:
                tick_size = 0.01
            else:
                tick_size = 0.1
        if tick_size <= 0:
            return price
        adjusted = round(price / tick_size) * tick_size
        decimals = _count_decimals(tick_size)
        return round(adjusted, decimals)

    # 미국 주식: SEC Rule 612 — $1.00 이상은 $0.01, 미만은 $0.0001 호가단위
    if exchange_name == "KiwoomUS":
        tick_size = 0.01 if price >= 1.0 else 0.0001
        return round(round(price / tick_size) * tick_size, 4)

    # 한국 주식 (Kiwoom, KIS): 호가단위 규칙
    if exchange_name in ("Kiwoom", "KIS"):
        tick_size = _get_krx_tick_size(price)
        return int(round(price / tick_size) * tick_size)

    # 기타: 원본 반환
    return price
