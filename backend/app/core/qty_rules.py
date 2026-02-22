"""
Centralized Quantity Rules - Single Source of Truth

거래소별 최소 주문 수량, step size, min notional 규칙.
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
