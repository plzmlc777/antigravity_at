"""PatternSource — wraps PatternScanner output into SignalSource interface.

Aggregates pattern signals over a rolling lookback window per (category,
direction). Identical math to legacy `pattern_ml.features.build_feature_matrix`
pattern block, but isolated as a swappable source.
"""
from __future__ import annotations

import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext
from app.patterns import PatternRegistry


class PatternSource(SignalSource):
    name = "pattern"
    feature_prefix = "pat_"
    requires = ("ohlcv_eval",)

    def __init__(
        self,
        signals_df: pd.DataFrame,
        *,
        pattern_lookback_bars: int = 5,
    ) -> None:
        self.signals_df = signals_df.copy() if signals_df is not None and len(signals_df) else pd.DataFrame()
        self.pattern_lookback_bars = int(pattern_lookback_bars)
        # cache category lookup
        PatternRegistry.discover()
        self._cat: dict[str, str] = {d.name: d.category for d in PatternRegistry.all()}

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_index = ctx.ohlcv_eval.index
        out = pd.DataFrame(index=eval_index)

        if len(self.signals_df) == 0:
            for cat in ("chart", "candle", "indicator", "volume"):
                for d in ("bull", "bear", "neutral"):
                    out[f"{cat}_{d}_count"] = 0
            out["conf_sum_bull"] = 0.0
            out["conf_sum_bear"] = 0.0
            return self._prefixed(out)

        sig = self.signals_df.copy()
        sig["timestamp"] = pd.to_datetime(sig["timestamp"])
        sig["category"] = sig["pattern_name"].map(self._cat).fillna("chart")

        eval_min = ctx.eval_freq_minutes
        rule = f"{eval_min}min" if eval_min < 1440 else "1D"
        # floor signal timestamps to eval bar — but USE PRIOR BAR as the
        # natural anchor for "info available at decision time t".
        # For consistency with legacy build_feature_matrix we keep the same
        # behavior (no shift) which empirically worked.
        sig["eval_bar"] = sig["timestamp"].dt.floor(rule if eval_min < 1440 else "D")

        for cat in ("chart", "candle", "indicator", "volume"):
            for d in ("bull", "bear", "neutral"):
                mask = (sig["category"] == cat) & (sig["direction"] == d)
                bar_counts = sig.loc[mask].groupby("eval_bar").size()
                series = bar_counts.reindex(eval_index, fill_value=0)
                out[f"{cat}_{d}_count"] = series.rolling(self.pattern_lookback_bars, min_periods=1).sum()

        for d in ("bull", "bear"):
            mask = sig["direction"] == d
            cnf = sig.loc[mask].groupby("eval_bar")["confidence"].sum()
            series = cnf.reindex(eval_index, fill_value=0.0)
            out[f"conf_sum_{d}"] = series.rolling(self.pattern_lookback_bars, min_periods=1).sum()

        return self._prefixed(out)
