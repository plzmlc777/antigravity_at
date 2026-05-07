"""BinanceCrossETHSource — ETH price signal as cross-asset leader for altcoins.

Hypothesis: BTC/ETH가 alt coin universe의 risk-on/off leader. ETH 가격 변화 +
target/ETH ratio drift는 sector rotation 신호. Native asset price만 사용한
pattern source가 못 잡는 macro cross-asset 정보를 보충.

Output (prefix `ce_`):
  ce_eth_ret_1d              — ETH daily log return
  ce_eth_ret_5d_cum          — ETH 5d cumulative return
  ce_eth_ret_20d_cum         — ETH 20d cumulative return
  ce_eth_ret_zscore_60d      — ETH return zscore vs 60d
  ce_eth_realized_vol_20d    — ETH 20d realized vol (sector vol indicator)
  ce_target_eth_ratio_chg_1d — d(target_close/eth_close)
  ce_target_eth_ratio_5d_cum
  ce_target_eth_beta_60d     — rolling cov(target,eth)/var(eth) 60d
  ce_dominance_zscore_60d    — log(target/eth) zscore over 60d (under/overperform)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceCrossETHSource(SignalSource):
    name = "crosseth"
    feature_prefix = "ce_"
    requires = ("ohlcv_eval",)

    def __init__(self, eth_ohlcv_eval: pd.DataFrame) -> None:
        self.eth = eth_ohlcv_eval

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.eth is None or len(self.eth) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        target_close = ctx.ohlcv_eval["close"].astype(float)
        target_close.index = pd.to_datetime(target_close.index)
        eth_close = self.eth["close"].astype(float)
        eth_close.index = pd.to_datetime(eth_close.index)

        # Align by date
        df = pd.DataFrame({"target": target_close, "eth": eth_close}).dropna(how="any")
        if len(df) < 30:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        eth_ret = np.log(df["eth"]).diff()
        target_ret = np.log(df["target"]).diff()
        ratio = np.log(df["target"] / df["eth"])

        out = pd.DataFrame(index=df.index)
        out["eth_ret_1d"] = eth_ret
        out["eth_ret_5d_cum"] = eth_ret.rolling(5, min_periods=2).sum()
        out["eth_ret_20d_cum"] = eth_ret.rolling(20, min_periods=5).sum()
        rmean60 = eth_ret.rolling(60, min_periods=20).mean()
        rstd60 = eth_ret.rolling(60, min_periods=20).std()
        out["eth_ret_zscore_60d"] = (eth_ret - rmean60) / rstd60.replace(0, np.nan)
        out["eth_realized_vol_20d"] = eth_ret.rolling(20, min_periods=5).std()
        out["target_eth_ratio_chg_1d"] = ratio.diff()
        out["target_eth_ratio_5d_cum"] = out["target_eth_ratio_chg_1d"].rolling(5, min_periods=2).sum()

        # 60d rolling beta = cov(target,eth)/var(eth)
        cov60 = target_ret.rolling(60, min_periods=20).cov(eth_ret)
        var60 = eth_ret.rolling(60, min_periods=20).var()
        out["target_eth_beta_60d"] = cov60 / var60.replace(0, np.nan)

        rmean_r = ratio.rolling(60, min_periods=20).mean()
        rstd_r = ratio.rolling(60, min_periods=20).std()
        out["dominance_zscore_60d"] = (ratio - rmean_r) / rstd_r.replace(0, np.nan)

        # Reindex to original eval index
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = out.reindex(eval_idx)
        return self._prefixed(out)
