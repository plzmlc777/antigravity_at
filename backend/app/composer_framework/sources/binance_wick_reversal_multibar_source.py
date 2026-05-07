"""BinanceWickReversalMultibarSource — 5m intra-bar wick shape reversal signal.

Hypothesis (Research Track paradigm `wick_reversal_multibar`, Q3 #4 R-3 PASS
SOLUSDT 4.49σ POSITIVE single-symbol, 2026-05-06):

  5m candle intra-bar wick shape (high-low excursion asymmetry) carries
  directional reversal information beyond close-to-close returns. Multi-bar
  rolling average (n=2) reduces random_std and elevates signal vs single-bar.

  Per-bar:
    body_top = max(open, close); body_bot = min(open, close)
    range = high - low
    lower_wick_frac = (body_bot - low) / range
    upper_wick_frac = (high - body_top) / range
    prior_ret = close.pct_change(prior_lookback)

  Multi-bar smoothed:
    lwf_mean = rolling N-bar mean of lower_wick_frac
    uwf_mean = rolling N-bar mean of upper_wick_frac

  Entry rule:
    lwf_mean > wick_thresh AND prior_ret < -prior_move_pct → LONG
      (sustained lower wick dominance + prior drop = liquidation cascade
       cleared, reversal up)
    uwf_mean > wick_thresh AND prior_ret > +prior_move_pct → SHORT
      (sustained upper wick dominance + prior rally = climax)
    Hold hold_bars or stop on SL.

R-3 stats (n=200 perm, shuffle high/low pair preserve open/close):
  SOLUSDT: alpha 61.94 sharpe 1.41 trades 122 perm_p 0.0000 sigma 4.49σ ✅ PASS

Multi-symbol: AVAX 3.16σ borderline / DOGE 1.94σ / HBAR 1.30σ (1/4 multi-symbol
consistency = §3-C single-symbol-fit; user-approved single-symbol seed for
SOL only on diversity grounds — different domain than premium_index_zscore).

Distinct NEW dimension from prior 56 paradigms:
  - close-to-close paradigms: ignore intra-bar high/low
  - wick_reversal Q3 #2 (POSITIVE 3σ): single-bar wick — this multi-bar avg
  - vol_regime / range_expansion: magnitude only, no shape
  - **Intra-bar SHAPE asymmetry over rolling N bars**

Output (prefix `bnwrm_`):
  bnwrm_signal — discrete in {-1.0, 0.0, +1.0}
  bnwrm_lwf    — rolling N-bar mean lower_wick_frac (debug)
  bnwrm_uwf    — rolling N-bar mean upper_wick_frac (debug)

Combine with `PassthroughComposer` (feature_col=bnwrm_signal) +
`LongShortThresholdPolicy` (entry_threshold=0.5, sl_pct=0.02,
max_hold_bars=12, eval_freq_minutes=5).

Runtime data: ctx.ohlcv_eval (5m OHLC bars from paper_session_cli normal load).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceWickReversalMultibarSource(SignalSource):
    name = "bn_wick_reversal_multibar"
    feature_prefix = "bnwrm_"
    requires = ("ohlcv_eval",)

    def __init__(self,
                 n_bars: int = 2,
                 wick_thresh: float = 0.35,
                 prior_lookback: int = 12,
                 prior_move_pct: float = 0.03) -> None:
        self.n_bars = int(n_bars)
        self.wick_thresh = float(wick_thresh)
        self.prior_lookback = int(prior_lookback)
        self.prior_move_pct = float(prior_move_pct)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        ohlc = ctx.ohlcv_eval
        for col in ("open", "high", "low", "close"):
            if col not in ohlc.columns:
                out["bnwrm_signal"] = 0.0
                out["bnwrm_lwf"] = np.nan
                out["bnwrm_uwf"] = np.nan
                return out

        df = ohlc[["open", "high", "low", "close"]].astype(float).copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]

        if len(df) < max(self.n_bars, self.prior_lookback) + 50:
            out["bnwrm_signal"] = 0.0
            out["bnwrm_lwf"] = np.nan
            out["bnwrm_uwf"] = np.nan
            return out

        rng = (df["high"] - df["low"]).replace(0.0, np.nan)
        body_top = df[["open", "close"]].max(axis=1)
        body_bot = df[["open", "close"]].min(axis=1)
        lwf = (body_bot - df["low"]) / rng
        uwf = (df["high"] - body_top) / rng

        lwf_mean = lwf.rolling(self.n_bars).mean()
        uwf_mean = uwf.rolling(self.n_bars).mean()
        prior_ret = df["close"].pct_change(self.prior_lookback)

        signal = pd.Series(0.0, index=df.index)
        long_mask = (lwf_mean > self.wick_thresh) & (prior_ret < -self.prior_move_pct)
        short_mask = (uwf_mean > self.wick_thresh) & (prior_ret > self.prior_move_pct)
        signal.loc[long_mask] = 1.0
        signal.loc[short_mask] = -1.0

        out["bnwrm_signal"] = signal.reindex(eval_idx).fillna(0.0).astype(float)
        out["bnwrm_lwf"] = lwf_mean.reindex(eval_idx).astype(float)
        out["bnwrm_uwf"] = uwf_mean.reindex(eval_idx).astype(float)
        return out
