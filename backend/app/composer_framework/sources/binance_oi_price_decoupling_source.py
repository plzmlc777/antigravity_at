"""BinanceOIPriceDecouplingSource — joint 5m OI × price z-score signal.

Hypothesis (Research Track paradigm `oi_price_decoupling`, R-3 PASS perm_p=0.0000
on AVAXUSDT/UNIUSDT/AXSUSDT/LINKUSDT/HBARUSDT, 2026-05-06):

  Rolling 288-bar (24h) z-score of 5m log_return AND ΔOI/OI. When BOTH |ret_z|
  and |oi_z| exceed entry_z (default 2.0), the joint extreme reveals a regime
  signal. Per-symbol perm-validated mode chooses entry direction:

  - `confirm` mode (AVAXUSDT lead, alpha 145.65/sharpe 1.73/perm_p 0 6.7σ):
      price↑+OI↑ extreme → LONG (new committed long flow continuation)
      price↓+OI↓ extreme → SHORT (position liquidation/short stacking)

  - `invert_decouple` mode (LINKUSDT alpha 71.21/sharpe 1.17/perm_p 0 5.2σ):
      price↑+OI↓ extreme → LONG (OI fade = profit-taking exhausted, rally continues)
      price↓+OI↑ extreme → SHORT (stubborn longs adding into dip = more pain)

Distinct from existing OI-domain sources:
  - `bn_oi_dynamics` (BinanceOIDynamicsSource): DAILY 4-quadrant feature engineering
    (10+ ML features). This: 5m rule-based single-signal in {-1,0,+1}.
  - `bn_funding_oi` (BinanceFundingOISource): funding × OI combo. This: pure OI × price.

Output (prefix `bnoid_`):
  bnoid_signal — discrete in {-1.0, 0.0, +1.0}
  bnoid_ret_z  — rolling 288-bar log_return z-score (debug)
  bnoid_oi_z   — rolling 288-bar ΔOI/OI z-score (debug)

Combine with `PassthroughComposer` (no negation, feature_col=bnoid_signal) +
`LongShortThresholdPolicy` (entry_threshold=0.5, sl_pct=0.02, max_hold_bars=24).

Runtime data: `runtime['binance_metrics_5m']` (joblib full_metrics 5m, must
contain `open_interest` column). paper_session_cli + backtest_paper_specs
already load this for bn_oi_dynamics — no new injection needed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceOIPriceDecouplingSource(SignalSource):
    name = "bn_oi_price_decoupling"
    feature_prefix = "bnoid_"
    requires = ("ohlcv_eval",)

    def __init__(self,
                 metrics_5m: pd.DataFrame | None = None,
                 mode: str = "confirm",
                 zwin: int = 288,
                 entry_z: float = 2.0) -> None:
        if mode not in ("confirm", "invert_decouple"):
            raise ValueError(f"mode must be 'confirm' or 'invert_decouple', got {mode!r}")
        self.metrics_5m = metrics_5m
        self.mode = mode
        self.zwin = int(zwin)
        self.entry_z = float(entry_z)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        if self.metrics_5m is None or len(self.metrics_5m) == 0 or "open_interest" not in self.metrics_5m.columns:
            out["bnoid_signal"] = 0.0
            out["bnoid_ret_z"] = np.nan
            out["bnoid_oi_z"] = np.nan
            return out

        close = ctx.ohlcv_eval["close"].astype(float)
        close.index = pd.to_datetime(close.index)
        oi = pd.to_numeric(self.metrics_5m["open_interest"], errors="coerce")
        oi.index = pd.to_datetime(oi.index)
        oi = oi.replace(0.0, np.nan).dropna().sort_index()
        oi = oi[~oi.index.duplicated(keep="last")]

        df = pd.concat([close.rename("close"), oi.rename("oi")], axis=1, join="inner").dropna()
        if len(df) < self.zwin + 50:
            out["bnoid_signal"] = 0.0
            out["bnoid_ret_z"] = np.nan
            out["bnoid_oi_z"] = np.nan
            return out

        log_ret = np.log(df["close"] / df["close"].shift(1))
        d_oi = df["oi"].pct_change(fill_method=None)
        ret_z = (log_ret - log_ret.rolling(self.zwin).mean()) / log_ret.rolling(self.zwin).std()
        oi_z = (d_oi - d_oi.rolling(self.zwin).mean()) / d_oi.rolling(self.zwin).std()

        signal = pd.Series(0.0, index=df.index)
        both_extreme = (ret_z.abs() > self.entry_z) & (oi_z.abs() > self.entry_z)

        if self.mode == "confirm":
            same_sign = both_extreme & (ret_z * oi_z > 0)
            signal.loc[same_sign & (ret_z > 0)] = 1.0
            signal.loc[same_sign & (ret_z < 0)] = -1.0
        else:  # invert_decouple
            opp_sign = both_extreme & (ret_z * oi_z < 0)
            signal.loc[opp_sign & (ret_z > 0)] = 1.0
            signal.loc[opp_sign & (ret_z < 0)] = -1.0

        out["bnoid_signal"] = signal.reindex(eval_idx).fillna(0.0).astype(float)
        out["bnoid_ret_z"] = ret_z.reindex(eval_idx).astype(float)
        out["bnoid_oi_z"] = oi_z.reindex(eval_idx).astype(float)
        return out
