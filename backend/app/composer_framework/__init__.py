"""
Composer Framework — modular signal/composer/policy architecture.

Replaces the hardcoded glue between Pattern Scanner / KR Flow / Microstructure
/ LightGBM / backtest code with three pluggable abstractions:

  - SignalSource: produces feature columns from raw data
  - Composer: fits a model from features → target, predicts on new features
  - TradingPolicy: turns predictions into trade actions

A Pipeline stitches these together. PaperSession + PaperOrchestrator add
operational state (positions, equity, trade log) for live paper trading.

Existing code (pattern_scanner, microstructure, pattern_ml) is NOT removed.
This framework is built ON TOP of those modules via adapters.

See .claude/plans/pattern_strategy_master.json (Phase 5 final findings) for
context on which combinations have been validated to work.
"""
from .signal_source import SignalSource, SourceContext, source_feature_prefix
from .composer import Composer
from .policy import (
    Action,
    LongOnlyThresholdPolicy,
    LongShortThresholdPolicy,
    PolicyContext,
    TradingPolicy,
)
from .pipeline import Pipeline, PipelineConfig
from .pipeline_spec import build_pipeline, validate_spec
from .backtester import GenericBacktester, BacktestKPIs, BacktestTrade
from .paper_session import (
    CycleResult,
    PaperSession,
    SessionStore,
    TradeRecord,
)
from .orchestrator import PaperOrchestrator, RuntimeBundle

__all__ = [
    # ABCs
    "SignalSource", "Composer", "TradingPolicy",
    # Concrete policies
    "LongOnlyThresholdPolicy", "LongShortThresholdPolicy",
    # Action / context dataclasses
    "Action", "PolicyContext", "SourceContext",
    # Pipeline + backtester
    "Pipeline", "PipelineConfig",
    "build_pipeline", "validate_spec",
    "GenericBacktester", "BacktestKPIs", "BacktestTrade",
    # paper session
    "PaperSession", "SessionStore", "CycleResult", "TradeRecord",
    "PaperOrchestrator", "RuntimeBundle",
    # helpers
    "source_feature_prefix",
]
