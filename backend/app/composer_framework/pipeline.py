"""
Pipeline — orchestrates SignalSources → Composer → TradingPolicy.

Lifecycle:
  pipe = Pipeline(sources=[...], composer=..., policy=...)
  pipe.build_features(ctx)         # combines all source outputs into one DF
  pipe.fit(features, target)       # trains composer
  pipe.predict(features)           # composer.predict
  pipe.run_backtest(...)           # via GenericBacktester

The Pipeline owns NO state across calls — each call is fresh. This makes
walk-forward retraining trivial: just instantiate a new Pipeline per window.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .composer import Composer
from .policy import TradingPolicy
from .signal_source import SignalSource, SourceContext

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Knobs shared across the whole pipeline (passed to backtester etc.)."""
    eval_freq_minutes: int = 1440          # 1 / 5 / 15 / 60 / 240 / 1440
    forward_bars: int = 5                  # target horizon (bars)
    target_col: str = "target_fwd_ret"     # name of target column added by Pipeline
    drop_na_target: bool = True


class Pipeline:
    def __init__(
        self,
        *,
        sources: list[SignalSource],
        composer: Composer,
        policy: TradingPolicy,
        config: PipelineConfig | None = None,
    ) -> None:
        if not sources:
            raise ValueError("Pipeline requires at least one SignalSource")
        # detect duplicate prefixes
        prefixes = [s.feature_prefix for s in sources]
        dupes = {p for p in prefixes if prefixes.count(p) > 1}
        if dupes:
            raise ValueError(f"Duplicate feature prefixes among sources: {dupes}")
        self.sources = list(sources)
        self.composer = composer
        self.policy = policy
        self.config = config or PipelineConfig()

    # ────────────────────────────────────── feature building

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        """Run all sources and concatenate their outputs along columns.

        Adds the target column (forward return on ctx.ohlcv_eval close) if
        ohlcv_eval is provided.
        """
        if ctx.ohlcv_eval is None:
            raise ValueError("Pipeline.build_features requires ctx.ohlcv_eval")

        eval_index = ctx.ohlcv_eval.index
        blocks: list[pd.DataFrame] = []
        for src in self.sources:
            try:
                block = src.build_features(ctx)
            except Exception as exc:
                raise RuntimeError(f"SignalSource {src.name!r} failed: {exc}") from exc
            if not isinstance(block, pd.DataFrame):
                raise TypeError(f"{src.name}.build_features must return DataFrame, got {type(block)}")
            # align to eval_index
            block = block.reindex(eval_index)
            blocks.append(block)
        feat = pd.concat(blocks, axis=1) if len(blocks) > 1 else blocks[0]

        # add target column
        close = ctx.ohlcv_eval["close"].astype(float)
        feat[self.config.target_col] = np.log(
            close.shift(-self.config.forward_bars) / close
        )
        return feat

    # ────────────────────────────────────── fit/predict

    def fit(self, features: pd.DataFrame) -> None:
        """Fit the composer on features (target column included)."""
        target_col = self.config.target_col
        if target_col not in features.columns:
            raise ValueError(f"features missing target column {target_col!r}")
        df = features.copy()
        if self.config.drop_na_target:
            df = df.dropna(subset=[target_col])
        if len(df) < 30:
            raise ValueError(f"Too few training samples: {len(df)}")
        feature_cols = [c for c in df.columns if c != target_col]
        X = df[feature_cols]
        y = df[target_col]
        self.composer.fit(X, y)

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Predict on a feature matrix (target column ignored if present)."""
        feature_cols = [c for c in features.columns if c != self.config.target_col]
        return self.composer.predict(features[feature_cols])

    # ────────────────────────────────────── helpers

    def feature_summary(self, ctx: SourceContext) -> dict[str, list[str]]:
        """Quickly enumerate which columns each source contributes — useful
        for diagnostics / feature-importance grouping."""
        out: dict[str, list[str]] = {}
        feat = self.build_features(ctx)
        for src in self.sources:
            cols = [c for c in feat.columns if c.startswith(src.feature_prefix)]
            out[src.name] = cols
        return out

    def __repr__(self) -> str:
        src_names = [s.name for s in self.sources]
        return (
            f"<Pipeline sources={src_names} composer={type(self.composer).__name__} "
            f"policy={type(self.policy).__name__}>"
        )
