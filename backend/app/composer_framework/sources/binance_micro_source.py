"""BinanceMicrostructureSource — wraps Binance metric archive features."""
from __future__ import annotations

import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext
from app.microstructure.features import aggregate_to_eval_bars


class BinanceMicrostructureSource(SignalSource):
    name = "bnmicro"
    feature_prefix = "micro_"
    requires = ("ohlcv_eval",)

    def __init__(self, metrics_5m: pd.DataFrame) -> None:
        self.metrics_5m = metrics_5m

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.metrics_5m is None or len(self.metrics_5m) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)
        return aggregate_to_eval_bars(self.metrics_5m, ctx.ohlcv_eval.index, ctx.eval_freq_minutes)
