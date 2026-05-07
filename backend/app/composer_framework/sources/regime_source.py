"""RegimeSource — exposes RegimeClassifier continuous scores as features."""
from __future__ import annotations

import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext
from app.regime import RegimeClassifier


class RegimeSource(SignalSource):
    name = "regime"
    feature_prefix = "regime_"
    requires = ("ohlcv_eval",)

    def __init__(self, classifier: RegimeClassifier | None = None,
                 *, daily_preset: bool = True) -> None:
        if classifier is not None:
            self.classifier = classifier
        else:
            self.classifier = (
                RegimeClassifier.for_daily() if daily_preset
                else RegimeClassifier.for_intraday()
            )

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        rdf = self.classifier.classify(ctx.ohlcv_eval)
        out = pd.DataFrame(index=ctx.ohlcv_eval.index)
        for c in ("trend_score", "volatility_score", "liquidity_score", "momentum_score"):
            if c in rdf.columns:
                out[c] = pd.to_numeric(rdf[c], errors="coerce")
        return self._prefixed(out)
