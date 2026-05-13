"""Concrete SignalSource implementations.

Each source wraps an existing module via a thin adapter. New sources should
subclass `SignalSource` directly without depending on legacy module internals
where possible.
"""
from .pattern_source import PatternSource
from .market_state_source import MarketStateSource
from .regime_source import RegimeSource
from .kr_flow_source import KRInvestorFlowSource
from .binance_micro_source import BinanceMicrostructureSource
from .binance_funding_oi_source import BinanceFundingOISource
from .binance_smart_money_source import BinanceSmartMoneySource
from .binance_taker_flow_source import BinanceTakerFlowSource
from .binance_oi_dynamics_source import BinanceOIDynamicsSource
from .binance_cross_eth_source import BinanceCrossETHSource
from .binance_premium_source import BinancePremiumSource
from .binance_book_depth_source import BinanceBookDepthSource
from .binance_event_detector_source import BinanceEventDetectorSource
from .binance_mtf_alignment_source import BinanceMTFAlignmentSource
from .binance_cascade_reversal_source import BinanceCascadeReversalSource
from .binance_funding_zscore_source import BinanceFundingZScoreSource
from .binance_autocorr_regime_source import BinanceAutocorrRegimeSource
from .binance_funding_dispersion_source import BinanceFundingDispersionSource
from .binance_cross_lead_lag_source import BinanceCrossLeaderLagSource
from .binance_oi_price_decoupling_source import BinanceOIPriceDecouplingSource
from .binance_premium_index_zscore_source import BinancePremiumIndexZScoreSource
from .binance_premium_velocity_zscore_source import BinancePremiumVelocityZScoreSource
from .binance_wick_reversal_multibar_source import BinanceWickReversalMultibarSource
from .binance_lifecycle_decay_source import BinanceLifecycleDecaySource

__all__ = [
    "PatternSource",
    "MarketStateSource",
    "RegimeSource",
    "KRInvestorFlowSource",
    "BinanceMicrostructureSource",
    "BinanceFundingOISource",
    "BinanceSmartMoneySource",
    "BinanceTakerFlowSource",
    "BinanceOIDynamicsSource",
    "BinanceCrossETHSource",
    "BinancePremiumSource",
    "BinanceBookDepthSource",
    "BinanceEventDetectorSource",
    "BinanceMTFAlignmentSource",
    "BinanceCascadeReversalSource",
    "BinanceFundingZScoreSource",
    "BinanceAutocorrRegimeSource",
    "BinanceFundingDispersionSource",
    "BinanceCrossLeaderLagSource",
    "BinanceOIPriceDecouplingSource",
    "BinancePremiumIndexZScoreSource",
    "BinancePremiumVelocityZScoreSource",
    "BinanceWickReversalMultibarSource",
    "BinanceLifecycleDecaySource",
]
