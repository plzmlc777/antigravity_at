"""BinancePremiumIndexZScoreSource — daily premium z-score momentum signal.

Hypothesis (Research Track paradigm `premium_index_zscore`, R-3 PASS perm_p=0.000
on DOGE/LDO/SOL, 0.020 on AVAX, 2026-05-06):

  Daily premium index = (mark_price - index_price) / index_price (1d kline
  aggregation from data.binance.vision archive). When 30-day rolling z-score
  of daily premium close exceeds entry_z (default 2.0), follow direction:
  - z > +entry_z → LONG (sustained premium = strong long pressure, momentum)
  - z < -entry_z → SHORT (sustained discount = bearish pressure)
  - hold for hold_days, exit on SL/TP

R-3 stats (n=200 perm, follow z=2.0 h=5):
  DOGEUSDT: alpha 348.17 sharpe 3.15 PF 11.76 mdd 8.8 wr 76.5 perm_p 0.000 9.0σ
  LDOUSDT:  alpha 290.07 sharpe 2.66 PF 12.00 mdd 6.0 wr 76.9 perm_p 0.000 5.7σ
  SOLUSDT:  alpha 166.52 sharpe 2.62 PF  6.31 mdd 8.7 wr 70.6 perm_p 0.000 5.4σ
  AVAXUSDT: alpha 141.81 sharpe 2.18 PF  4.05 mdd 11.0 wr 76.9 perm_p 0.020 3.0σ

Distinct from existing premium source (`bn_premium` BinancePremiumSource):
  - bn_premium: 9-feature ML output (close/range/cum5d/cum20d/z60d/change1d...)
  - bn_premium_index_zscore: single discrete signal {-1, 0, +1} for rule-based
    paper seed via PassthroughComposer + LongShortThresholdPolicy.

Output (prefix `bnpiz_`):
  bnpiz_signal — discrete in {-1.0, 0.0, +1.0}
  bnpiz_z      — rolling 30-day z-score of daily premium close (debug)

Combine with `PassthroughComposer` (no negation, feature_col=bnpiz_signal) +
`LongShortThresholdPolicy` (entry_threshold=0.5, sl_pct=0.05, max_hold_bars=5
for daily granularity).

Runtime data: `runtime['premium_df']` (joblib daily premium, must contain
`close` column). paper_session_cli + backtest_paper_specs already load this
for `bn_premium` — extend the source-set check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinancePremiumIndexZScoreSource(SignalSource):
    name = "bn_premium_index_zscore"
    feature_prefix = "bnpiz_"
    requires = ("ohlcv_eval",)

    def __init__(self,
                 premium_df: pd.DataFrame | None = None,
                 zwin: int = 30,
                 entry_z: float = 2.0) -> None:
        self.premium_df = premium_df
        self.zwin = int(zwin)
        self.entry_z = float(entry_z)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        if (self.premium_df is None or len(self.premium_df) == 0
                or "close" not in self.premium_df.columns):
            out["bnpiz_signal"] = 0.0
            out["bnpiz_z"] = np.nan
            return out

        df = self.premium_df[["close"]].copy()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"])
        df.index = pd.to_datetime(df.index).normalize()
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]

        if len(df) < self.zwin + 5:
            out["bnpiz_signal"] = 0.0
            out["bnpiz_z"] = np.nan
            return out

        rmean = df["close"].rolling(self.zwin).mean()
        rstd = df["close"].rolling(self.zwin).std()
        z = (df["close"] - rmean) / rstd.replace(0, np.nan)

        signal = pd.Series(0.0, index=df.index)
        signal[z > self.entry_z] = 1.0    # follow LONG
        signal[z < -self.entry_z] = -1.0  # follow SHORT

        # Map daily signal onto eval_idx (eval index may be intraday or daily).
        eval_norm = eval_idx.normalize()
        union_idx = pd.DatetimeIndex(sorted(set(signal.index) | set(eval_norm)))
        sig_ff = signal.reindex(union_idx).ffill().fillna(0.0).reindex(eval_norm)
        z_ff = z.reindex(union_idx).ffill().reindex(eval_norm)

        out["bnpiz_signal"] = sig_ff.astype(float).values
        out["bnpiz_z"] = z_ff.astype(float).values
        return out
