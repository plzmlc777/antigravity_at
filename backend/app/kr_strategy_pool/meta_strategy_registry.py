"""Strategy name → class lookup for the multi-TF meta-strategy pool."""
from typing import Dict, Type

from .base import KrStrategyBase
from .strategies.s40_vwap_atr_1m5m import S40_VWAP_ATR_1m5m
from .strategies.s41_bb_trend_5m1h import S41_BB_Trend_5m1h
from .strategies.s42_rsi_macd_1m import S42_RSI_MACD_1m
from .strategies.s43_donchian_atr_1m1h import S43_Donchian_ATR_1m1h
from .strategies.s44_ema_time_1m1h import S44_EMA_Time_1m1h
from .strategies.s46_triple_vote_1m5m1h import S46_TripleVote_1m5m1h
from .strategies.s47_bb_volume_5m import S47_BB_Volume_5m
from .strategies.s49_vwap_lunch_1m5m import S49_VWAP_Lunch_1m5m
from .strategies.s50_supertrend_adx_1m1h import S50_Supertrend_ADX_1m1h
from .strategies.s51_williams_volume_5m import S51_Williams_Volume_5m
from .strategies.s52_natr_low_revert_5m import S52_NATR_Low_Revert_5m
from .strategies.s53_volume_breakout_1m1h import S53_Volume_Breakout_1m1h

META_STRATEGY_REGISTRY: Dict[str, Type[KrStrategyBase]] = {
    "s40_vwap_atr_1m5m": S40_VWAP_ATR_1m5m,
    "s41_bb_trend_5m1h": S41_BB_Trend_5m1h,
    "s42_rsi_macd_1m": S42_RSI_MACD_1m,
    "s43_donchian_atr_1m1h": S43_Donchian_ATR_1m1h,
    "s44_ema_time_1m1h": S44_EMA_Time_1m1h,
    "s46_triple_vote_1m5m1h": S46_TripleVote_1m5m1h,
    "s47_bb_volume_5m": S47_BB_Volume_5m,
    "s49_vwap_lunch_1m5m": S49_VWAP_Lunch_1m5m,
    "s50_supertrend_adx_1m1h": S50_Supertrend_ADX_1m1h,
    "s51_williams_volume_5m": S51_Williams_Volume_5m,
    "s52_natr_low_revert_5m": S52_NATR_Low_Revert_5m,
    "s53_volume_breakout_1m1h": S53_Volume_Breakout_1m1h,
}


def get_meta_strategy_class(name: str) -> Type[KrStrategyBase]:
    if name not in META_STRATEGY_REGISTRY:
        raise ValueError(
            f"Unknown meta-strategy: {name}. Available: {list(META_STRATEGY_REGISTRY)}"
        )
    return META_STRATEGY_REGISTRY[name]
