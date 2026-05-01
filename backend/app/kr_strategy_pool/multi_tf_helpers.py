"""
Multi-timeframe strategy helpers — Meta-Strategy MoE Phase 1 base.

1m feed → 5m/15m/30m/60min/1D resample, signal alignment to 1m index
(forward-fill of last *closed* higher-TF bar — no look-ahead),
and a common entry/exit loop (SL/TP/sell-signal/EOD) wrapped in MultiTFBase.

Subclasses override _build_signals(df_1m, feed_ts) to set:
  self._buy[ts]  -> bool
  self._sell[ts] -> bool
"""
from typing import Any, ClassVar, Dict, List, Optional

import pandas as pd

from .base import KrStrategyBase

_AGG = {"open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"}


def feed_to_df(feed: List[Dict[str, Any]]) -> pd.DataFrame:
    """list-of-dict 1m feed → DatetimeIndex DataFrame with day_id column."""
    df = pd.DataFrame(feed)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("ts").sort_index()
    df["day_id"] = df.index.date.astype(str)
    return df


def resample_df(df_1m: pd.DataFrame, freq: str) -> pd.DataFrame:
    """1m DF → freq DF. freq examples: '5min', '15min', '60min', '1D'."""
    if freq.upper() == "1D":
        df = df_1m.copy()
        df["d"] = df.index.normalize()
        out = df.groupby("d").agg(_AGG)
        out.index.name = "ts"
    else:
        out = df_1m.resample(freq, origin="start_day").agg(_AGG).dropna(subset=["open"])
    out["day_id"] = out.index.date.astype(str)
    return out


def align_to_1m(sig: pd.DataFrame, df_1m_index: pd.DatetimeIndex, freq: str) -> pd.DataFrame:
    """Forward-fill higher-TF signal onto the 1m index using floored timestamps.

    No look-ahead: at 1m time t the aligned value is the last higher-TF bar
    that *closed* at or before floor(t).
    """
    if freq.upper() == "1D":
        floored = df_1m_index.normalize()
    else:
        floored = df_1m_index.floor(freq)
    aligned = sig.reindex(floored, method="ffill")
    aligned.index = df_1m_index
    return aligned


class MultiTFBase(KrStrategyBase):
    """Common multi-TF entry/exit harness.

    Subclasses must:
      1. Set name + DEFAULT_PARAMS (overlaying MultiTFBase.DEFAULT_PARAMS).
      2. Implement _build_signals(self, df_1m, feed_ts) which populates
         self._buy and self._sell dicts (timestamp str -> bool).
    """

    TIMEFRAME = "1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "buy_size_pct": 0.7,
        "sl_pct": 0.02,
        "tp_pct": 0.025,
        "exit_time": "15:25",
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        raise NotImplementedError

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df_1m = feed_to_df(feed)
        feed_ts = [c["timestamp"] for c in feed]
        self._buy: Dict[str, bool] = {}
        self._sell: Dict[str, bool] = {}
        self._build_signals(df_1m, feed_ts)
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        if self._has_position() and t >= str(self.config["exit_time"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod"})
            self._entry = None
            return

        if self._has_position() and self._entry is not None:
            if price <= self._entry * (1 - float(self.config["sl_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = None
                return
            if price >= self._entry * (1 + float(self.config["tp_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry = None
                return
            if self._sell.get(ts, False):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sell_sig"})
                self._entry = None
                return
            return

        if self._buy.get(ts, False):
            from ..core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": self.name},
                )
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
