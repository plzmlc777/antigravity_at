"""BinanceCrossLeaderLagSource — BTC-leader spillover catch-up signal.

Hypothesis (Research Track paradigm `cross_symbol_lead_lag`, R-3 PASS perm_p=0.005
on DOGEUSDT, perm 0.000 on ETCUSDT after BTC 1y backfill 2026-05-05): BTCUSDT
acts as the 5m market leader. When BTC's recent 1-bar log return |R_btc| >
LEAD_THRESH (default 0.005) AND target alt has lagged (alt's recent return is
opposite-direction OR magnitude < FOLLOW_RATIO × |R_btc|), the alt is more
likely to catch up to BTC's direction in the next HOLD_BARS bars (1h) than to
revert.

Output (prefix `bnll_`):
  bnll_signal — discrete in {-1.0, 0.0, +1.0}:
    +1 → enter LONG  (BTC up + alt lagged)
    -1 → enter SHORT (BTC down + alt lagged)
     0 → no signal (BTC move not strong, OR alt already followed)
  bnll_r_btc  — recent N-bar BTC log return (debug)
  bnll_r_alt  — recent N-bar alt log return (debug)

Combine with `PassthroughComposer` (no negation, feature_col=bnll_signal) +
`LongShortThresholdPolicy` (entry_threshold=0.5, sl_pct=0.02, max_hold_bars=12).

Runtime data: caller injects `leader_ohlcv_eval` (BTCUSDT 5m ohlcv df) via
runtime_data['leader_ohlcv_eval'].
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceCrossLeaderLagSource(SignalSource):
    name = "bn_cross_lead_lag"
    feature_prefix = "bnll_"
    requires = ("ohlcv_eval",)

    def __init__(self, leader_ohlcv_eval: pd.DataFrame | None = None,
                 lead_lookback: int = 1, lead_thresh: float = 0.005,
                 follow_ratio: float = 0.5) -> None:
        self.leader = leader_ohlcv_eval
        self.lead_lookback = int(lead_lookback)
        self.lead_thresh = float(lead_thresh)
        self.follow_ratio = float(follow_ratio)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        if self.leader is None or len(self.leader) == 0:
            out["bnll_signal"] = 0.0
            out["bnll_r_btc"] = np.nan
            out["bnll_r_alt"] = np.nan
            return out

        target_close = ctx.ohlcv_eval["close"].astype(float)
        target_close.index = pd.to_datetime(target_close.index)
        leader_close = self.leader["close"].astype(float)
        leader_close.index = pd.to_datetime(leader_close.index)

        df = pd.DataFrame({"alt": target_close, "btc": leader_close}).dropna(how="any")
        if len(df) < 50:
            out["bnll_signal"] = 0.0
            out["bnll_r_btc"] = np.nan
            out["bnll_r_alt"] = np.nan
            return out

        log_ret_alt = np.log(df["alt"] / df["alt"].shift(1))
        log_ret_btc = np.log(df["btc"] / df["btc"].shift(1))
        r_alt = log_ret_alt.rolling(self.lead_lookback).sum()
        r_btc = log_ret_btc.rolling(self.lead_lookback).sum()

        signal = pd.Series(0.0, index=df.index)
        # BTC strong move + alt lagged condition
        btc_strong = r_btc.abs() > self.lead_thresh
        # alt lagged: opposite sign OR magnitude < follow_ratio * |r_btc|
        same_sign = np.sign(r_alt) == np.sign(r_btc)
        alt_lagged = (~same_sign) | (r_alt.abs() < self.follow_ratio * r_btc.abs())
        entry_mask = btc_strong & alt_lagged & r_btc.notna() & r_alt.notna()

        signal.loc[entry_mask] = np.sign(r_btc.loc[entry_mask])

        # Reindex onto eval index
        out = out.copy()
        out["bnll_signal"] = signal.reindex(eval_idx).fillna(0.0).astype(float)
        out["bnll_r_btc"] = r_btc.reindex(eval_idx).astype(float)
        out["bnll_r_alt"] = r_alt.reindex(eval_idx).astype(float)
        return out
