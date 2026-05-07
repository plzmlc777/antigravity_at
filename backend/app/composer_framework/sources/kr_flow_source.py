"""KRInvestorFlowSource — wraps `microstructure.kr_investor_flow` as SignalSource.

Same math as legacy `attach_flow_to_features`, but isolated and prefixed.
"""
from __future__ import annotations

import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext
from app.microstructure.kr_investor_flow import build_flow_features, fetch_investor_flow


class KRInvestorFlowSource(SignalSource):
    name = "krflow"
    # Legacy column names are already "flow_*". Keep them as-is so existing
    # feature-importance reports remain comparable. We override prefix to "flow_".
    feature_prefix = "flow_"
    requires = ("ohlcv_eval",)

    def __init__(self, flow_df: pd.DataFrame | None = None, *, symbol: str | None = None) -> None:
        if flow_df is None:
            if symbol is None:
                raise ValueError("Either flow_df or symbol must be provided")
            flow_df = fetch_investor_flow(symbol)
        self.flow_df = flow_df

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.flow_df is None or len(self.flow_df) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)
        flow_feats = build_flow_features(self.flow_df)
        if flow_feats.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        # forward-fill onto eval index by date
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        eval_norm = eval_idx.normalize()
        flow_norm = pd.to_datetime(flow_feats.index).normalize()
        flow_feats = flow_feats.copy()
        flow_feats.index = flow_norm
        flow_feats = flow_feats[~flow_feats.index.duplicated(keep="last")]
        mapped = flow_feats.reindex(eval_norm, method="ffill")
        mapped.index = eval_idx
        # legacy columns already start with "flow_" so prefix is no-op for them,
        # but our SignalSource convention enforces the prefix anyway.
        return self._prefixed(mapped)
