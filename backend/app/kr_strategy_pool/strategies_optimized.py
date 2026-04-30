"""
Grid sweep으로 발견된 best params를 적용한 wrapper strategies.
원본 strategy class의 DEFAULT_PARAMS만 override (로직 동일).

원본 보존이라 production system 무영향.
"""
from typing import Any, ClassVar, Dict

from .strategies.s2_bb_reversion import S2BBReversion
from .strategies.s5_vwap_reversion import S5VwapReversion
from .strategies.s13_last_hour_momentum import S13LastHourMomentum
from .strategies.s16_stochastic_reversion import S16StochasticReversion
from .strategies.s25_lunch_fade import S25LunchFade
from .strategies.s26_open_drive import S26OpenDrive


class S2OptBBReversion(S2BBReversion):
    """S2 BB optimized: walk-forward sweep best (bb_period=25, std=2.0)."""
    name = "s2_opt_bb_reversion"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S2BBReversion.DEFAULT_PARAMS,
        "bb_period": 25,
        "bb_std": 2.0,
    }


class S5OptVwapReversion(S5VwapReversion):
    """S5 VWAP optimized: lower_band_pct 1.5% → 0.5% (-9.09% → +6.09%)."""
    name = "s5_opt_vwap_reversion"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S5VwapReversion.DEFAULT_PARAMS,
        "lower_band_pct": 0.005,
    }


class S13OptLastHourMomentum(S13LastHourMomentum):
    """S13 Last Hour optimized: entry 14:00→13:30, min_gain 0.5%→1.5%."""
    name = "s13_opt_last_hour_momentum"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S13LastHourMomentum.DEFAULT_PARAMS,
        "entry_time": "13:30",
        "min_intraday_gain": 0.015,
    }


class S16OptStochasticReversion(S16StochasticReversion):
    """S16 Stochastic optimized: k=9, oversold=20, overbought=75 (Sharpe 4.35)."""
    name = "s16_opt_stochastic_reversion"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S16StochasticReversion.DEFAULT_PARAMS,
        "k_period": 9,
        "oversold": 20,
        "overbought": 75,
    }


class S25OptLunchFade(S25LunchFade):
    """S25 Lunch Fade optimized: 11:30-12:30 → 12:00-13:00."""
    name = "s25_opt_lunch_fade"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S25LunchFade.DEFAULT_PARAMS,
        "lunch_start": "12:00",
        "lunch_end": "13:00",
    }


class S26OptOpenDrive(S26OpenDrive):
    """S26 Open Drive optimized: drive 0.5%→0.8%, tp 4%→2%."""
    name = "s26_opt_open_drive"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S26OpenDrive.DEFAULT_PARAMS,
        "min_open_drive_pct": 0.008,
        "tp_pct": 0.02,
    }
