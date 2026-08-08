"""
position_math.py — pure math primitives shared by LiveContext and SkillContext.

Extracted as a single source of truth so the same cash/leverage arithmetic runs
in both the operational backend (DB-backed real execution via adapter) and the
skill-side runner (in-memory simulator + REST recorder). Both call sites must
produce identical outputs for the same inputs.

⚠️ Pure functions only — no I/O, no DB, no SQLAlchemy, no httpx. Stdlib only.
   This guarantees the skill standalone CLI (urllib-based, no backend deps)
   can import this module via the same sys.path bootstrap pattern as
   binance_market_snapshot and symbol_score.
"""
from __future__ import annotations

from typing import Optional, Tuple

# Signal-side string constants — match backend.app.core.signals.Signal values
# but defined locally so the skill side does not need to import the SQLAlchemy
# enum module.
SIGNAL_BUY = "BUY"
SIGNAL_SELL = "SELL"

# Position side strings — match backend.app.core.types.Side values.
SIDE_LONG = "long"
SIDE_SHORT = "short"


def calc_cash_delta(
    signal_type: str,
    price: float,
    qty: float,
    is_futures: bool,
    leverage: int,
    position_side: str = "",
    realized_pnl: float = 0.0,
) -> float:
    """Cash account delta for a single fill.

    Spot:
      BUY  → -notional   (cash decreases by full notional)
      SELL → +notional   (cash increases by full notional)

    Futures (margin-based):
      LONG  entry  = BUY  with position_side in (long, "")
      LONG  exit   = SELL with position_side in (long, "")
      SHORT entry  = SELL with position_side == short
      SHORT exit   = BUY  with position_side == short

      entry → -margin              (margin used)
      exit  → +margin + realized_pnl  (margin returned + PnL)

    Inputs are not mutated; this is a pure function.
    """
    notional = price * qty
    if not is_futures:
        if str(signal_type).upper() == SIGNAL_BUY:
            return -notional
        return notional

    margin = notional / leverage if leverage and leverage > 0 else notional
    pos = (position_side or "").lower()
    sig = str(signal_type).upper()

    is_entry = (sig == SIGNAL_SELL and pos == SIDE_SHORT) or (
        sig == SIGNAL_BUY and pos in (SIDE_LONG, "")
    )

    if is_entry:
        return -margin
    return margin + realized_pnl


def cap_qty_by_cash(
    qty: float,
    price: float,
    available_cash: float,
    leverage: int,
    is_futures: bool = True,
) -> Tuple[float, bool]:
    """Cash guard: cap a buy quantity to what available cash supports.

    Returns (capped_qty, was_capped).
    - capped_qty == qty when no cap was applied
    - capped_qty == 0  when cash is insufficient even for 1 unit
    - was_capped True when the original qty was reduced (or zeroed)

    Spot:    margin per unit = price
    Futures: margin per unit = price / leverage

    The caller is responsible for handling capped_qty == 0 (treat as
    insufficient_cash failure) and for logging the cap decision.
    """
    if qty <= 0 or price <= 0:
        return qty, False

    available = max(available_cash, 0)
    eff_leverage = leverage if (is_futures and leverage and leverage > 0) else 1
    order_cost = qty * price / eff_leverage

    if order_cost <= available:
        return qty, False

    if available <= 0:
        return 0, True

    max_qty = int(available * eff_leverage / price)
    return max_qty, True


def realized_pnl_simple(
    side: str,
    avg_cost: float,
    exit_price: float,
    qty: float,
) -> float:
    """Realized PnL for an in-memory simulator (no fees).

    LONG  : (exit - entry) × qty
    SHORT : (entry - exit) × qty

    Used by SkillContext where avg_cost is tracked in memory. LiveContext
    computes its PnL from DB execution history and includes fees, so it does
    NOT use this helper.
    """
    if avg_cost <= 0 or qty <= 0:
        return 0.0
    if str(side).lower() == SIDE_SHORT:
        return (avg_cost - exit_price) * qty
    return (exit_price - avg_cost) * qty


def resolve_fill_price(fill_price, theoretical_price) -> tuple:
    """체결가를 확정한다. → (가격, 폴백여부)

    `fill_price or theoretical_price` 관용구를 대체한다. `or` 는 0.0 과 None 을
    구분하지 못하는데, 이 코드베이스에서 0은 "거래소가 체결가를 주지 않음"이라는
    **기록된 사실**이고 None 은 "값 없음"이다. 둘 다 이론가로 대체할 수밖에 없지만
    **조용히 넘어가면 안 된다** — 이론가는 전략이 의도한 가격일 뿐 실제 체결가가
    아니어서, 그대로 손익·현금 회계에 들어가면 거래소 원장과 어긋난다.

    2026-08-08 확인: 실계좌 39건 중 23건이 이 경로로 System-2 바 종가로 기록돼
    실현손익이 원장 대비 +0.71 USDT(0.30%) 부풀려져 있었다. 호출측은 두 번째
    반환값이 True 면 경고 로그와 metadata 표식을 남겨야 한다.

    반환 가격이 0일 수도 있다(이론가마저 없을 때). 지어내지 않는다.
    """
    try:
        px = float(fill_price) if fill_price is not None else 0.0
    except (TypeError, ValueError):
        px = 0.0
    if px > 0:
        return (px, False)
    try:
        fallback = float(theoretical_price) if theoretical_price is not None else 0.0
    except (TypeError, ValueError):
        fallback = 0.0
    return (fallback, True)
