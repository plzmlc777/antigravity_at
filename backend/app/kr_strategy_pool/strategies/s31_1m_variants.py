"""
S31 1-minute variants for timeframe sensitivity test.

V1: 같은 period 그대로 — 1분봉이라 indicator가 5배 빠르게 반응
V2: period × 5 — 시간 동일성 유지 (5분봉 25 ≈ 1분봉 125)
"""
from typing import Any, ClassVar, Dict

from .s31_robust_confirmation import S31RobustConfirmation


class S31_1m_SamePeriod(S31RobustConfirmation):
    """1분봉, period 그대로 (indicator 5배 빠르게 반응)."""
    name = "s31_1m_same_period"
    TIMEFRAME = "1m"
    # DEFAULT_PARAMS 그대로 (period 변경 없음)


class S31_1m_PeriodX5(S31RobustConfirmation):
    """1분봉, period × 5 (5분봉의 시간 동일성 유지)."""
    name = "s31_1m_period_x5"
    TIMEFRAME = "1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31RobustConfirmation.DEFAULT_PARAMS,
        # period × 5
        "bb_period": 125,        # 25 → 125
        "stoch_k_period": 45,    # 9 → 45
        "z_period": 150,         # 30 → 150
        # SL/TP는 동일 (가격 비율이라 timeframe 무관)
        # lunch 시간도 동일 (시계 기준)
        # confirmation count 동일
    }


class S31_1m_PeriodX3(S31RobustConfirmation):
    """1분봉, period × 3 (중간점)."""
    name = "s31_1m_period_x3"
    TIMEFRAME = "1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31RobustConfirmation.DEFAULT_PARAMS,
        "bb_period": 75,
        "stoch_k_period": 27,
        "z_period": 90,
    }
