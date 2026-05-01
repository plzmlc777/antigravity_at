"""Strategy name → class lookup for the multi-TF crypto meta-strategy pool."""
from typing import Dict, Type

from .base import CryptoStrategyBase
from .strategies.c40_vwap_atr_1m5m import C40_VWAP_ATR_1m5m
from .strategies.c41_bb_trend_5m1h import C41_BB_Trend_5m1h
from .strategies.c42_rsi_macd_1m import C42_RSI_MACD_1m
from .strategies.c43_donchian_atr_1m1h import C43_Donchian_ATR_1m1h
from .strategies.c46_triple_vote_1m5m1h import C46_TripleVote_1m5m1h
from .strategies.c47_bb_volume_5m import C47_BB_Volume_5m
from .strategies.c50_supertrend_adx_1m1h import C50_Supertrend_ADX_1m1h
from .strategies.c51_williams_volume_5m import C51_Williams_Volume_5m
from .strategies.c52_natr_low_revert_5m import C52_NATR_Low_Revert_5m
from .strategies.c53_volume_breakout_1m1h import C53_Volume_Breakout_1m1h

META_STRATEGY_REGISTRY: Dict[str, Type[CryptoStrategyBase]] = {
    "c40_vwap_atr_1m5m": C40_VWAP_ATR_1m5m,
    "c41_bb_trend_5m1h": C41_BB_Trend_5m1h,
    "c42_rsi_macd_1m": C42_RSI_MACD_1m,
    "c43_donchian_atr_1m1h": C43_Donchian_ATR_1m1h,
    "c46_triple_vote_1m5m1h": C46_TripleVote_1m5m1h,
    "c47_bb_volume_5m": C47_BB_Volume_5m,
    "c50_supertrend_adx_1m1h": C50_Supertrend_ADX_1m1h,
    "c51_williams_volume_5m": C51_Williams_Volume_5m,
    "c52_natr_low_revert_5m": C52_NATR_Low_Revert_5m,
    "c53_volume_breakout_1m1h": C53_Volume_Breakout_1m1h,
}


def get_meta_strategy_class(name: str) -> Type[CryptoStrategyBase]:
    if name not in META_STRATEGY_REGISTRY:
        raise ValueError(
            f"Unknown crypto meta-strategy: {name}. Available: {list(META_STRATEGY_REGISTRY)}"
        )
    return META_STRATEGY_REGISTRY[name]
