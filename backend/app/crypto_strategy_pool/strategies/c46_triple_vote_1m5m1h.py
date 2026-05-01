"""C46: Triple-TF voting (VWAP/BB/RSI × 1m/5m/1h) — Crypto port of S46."""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import bollinger, rsi, vwap_intraday
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


def _signals_at_tf(df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    upper, mid, lower = bollinger(df["close"], int(p["bb_period"]), float(p["bb_std"]))
    out["bb_buy"] = df["close"] < lower
    out["bb_sell"] = df["close"] > mid

    if "day_id" not in df.columns:
        df = df.copy()
        df["day_id"] = df.index.date.astype(str)
    vwap = vwap_intraday(df["high"], df["low"], df["close"], df["volume"], df["day_id"])
    lband = vwap * (1 - float(p["vwap_lower_band_pct"]))
    out["vwap_buy"] = df["close"] < lband
    out["vwap_sell"] = df["close"] >= vwap

    r = rsi(df["close"], int(p["rsi_period"]))
    out["rsi_buy"] = r < float(p["rsi_oversold"])
    out["rsi_sell"] = r > float(p["rsi_overbought"])

    out["buy_count"] = out[["bb_buy", "vwap_buy", "rsi_buy"]].sum(axis=1)
    out["sell_count"] = out[["bb_sell", "vwap_sell", "rsi_sell"]].sum(axis=1)
    return out


class C46_TripleVote_1m5m1h(MultiTFBase):
    name = "c46_triple_vote_1m5m1h"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "bb_period_1m": 75, "bb_period_5m": 25, "bb_period_1h": 14,
        "bb_std": 2.0,
        "vwap_lower_band_pct": 0.005,
        "rsi_period_1m": 14, "rsi_period_5m": 14, "rsi_period_1h": 14,
        "rsi_oversold": 30.0, "rsi_overbought": 70.0,
        "buy_threshold": 5,
        "sell_threshold": 4,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "buy_threshold": {"type": "int", "min": 3, "max": 9},
        "sell_threshold": {"type": "int", "min": 3, "max": 9},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        df_5m = resample_df(df_1m, "5min")
        df_1h = resample_df(df_1m, "60min")

        sig_1m = _signals_at_tf(df_1m, {
            "bb_period": self.config["bb_period_1m"], "bb_std": self.config["bb_std"],
            "vwap_lower_band_pct": self.config["vwap_lower_band_pct"],
            "rsi_period": self.config["rsi_period_1m"],
            "rsi_oversold": self.config["rsi_oversold"],
            "rsi_overbought": self.config["rsi_overbought"],
        })[["buy_count", "sell_count"]]

        sig_5m = _signals_at_tf(df_5m, {
            "bb_period": self.config["bb_period_5m"], "bb_std": self.config["bb_std"],
            "vwap_lower_band_pct": self.config["vwap_lower_band_pct"],
            "rsi_period": self.config["rsi_period_5m"],
            "rsi_oversold": self.config["rsi_oversold"],
            "rsi_overbought": self.config["rsi_overbought"],
        })[["buy_count", "sell_count"]]
        aligned_5m = align_to_1m(sig_5m, df_1m.index, "5min")

        sig_1h = _signals_at_tf(df_1h, {
            "bb_period": self.config["bb_period_1h"], "bb_std": self.config["bb_std"],
            "vwap_lower_band_pct": self.config["vwap_lower_band_pct"],
            "rsi_period": self.config["rsi_period_1h"],
            "rsi_oversold": self.config["rsi_oversold"],
            "rsi_overbought": self.config["rsi_overbought"],
        })[["buy_count", "sell_count"]]
        aligned_1h = align_to_1m(sig_1h, df_1m.index, "60min")

        total_buy = (
            sig_1m["buy_count"].fillna(0).values
            + aligned_5m["buy_count"].fillna(0).values
            + aligned_1h["buy_count"].fillna(0).values
        )
        total_sell = (
            sig_1m["sell_count"].fillna(0).values
            + aligned_5m["sell_count"].fillna(0).values
            + aligned_1h["sell_count"].fillna(0).values
        )

        buy = total_buy >= int(self.config["buy_threshold"])
        sell = total_sell >= int(self.config["sell_threshold"])
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
