"""
Crypto Multi-timeframe helpers — KR multi_tf_helpers의 24/7 mirror.

주요 차이:
  - exit_time(EOD) 개념 제거. 대신 max_hold_bars(보유 1m 봉 수 한계) 사용.
  - day_id는 calendar day(UTC) 기준 — VWAP intraday 등에 사용.
  - 매수 수량은 float (BTC 단위 등). 거래수수료는 CRYPTO_TAKER_FEE.
"""
from typing import Any, ClassVar, Dict, List, Optional

import pandas as pd

from .base import CryptoStrategyBase

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def feed_to_df(feed: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(feed)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("ts").sort_index()
    df["day_id"] = df.index.date.astype(str)  # UTC calendar day
    return df


def resample_df(df_1m: pd.DataFrame, freq: str) -> pd.DataFrame:
    if freq.upper() == "1D":
        df = df_1m.copy()
        df["d"] = df.index.normalize()
        out = df.groupby("d").agg(_AGG)
        out.index.name = "ts"
    else:
        out = df_1m.resample(freq).agg(_AGG).dropna(subset=["open"])
    out["day_id"] = out.index.date.astype(str)
    return out


def align_to_1m(sig: pd.DataFrame, df_1m_index: pd.DatetimeIndex, freq: str) -> pd.DataFrame:
    """Look-ahead safe: shift(1) applied — see kr_strategy_pool/multi_tf_helpers.py for explanation.

    Bug fix 2026-05-01: shift(1) added. Affects all crypto multi-TF strategies (c40-c53).
    """
    if freq.upper() == "1D":
        floored = df_1m_index.normalize()
    else:
        floored = df_1m_index.floor(freq)
    sig_safe = sig.shift(1)
    aligned = sig_safe.reindex(floored, method="ffill")
    aligned.index = df_1m_index
    return aligned


class MultiTFBase(CryptoStrategyBase):
    """
    Common multi-TF entry/exit harness — 24/7 crypto.

    Subclasses must:
      1. Set name + DEFAULT_PARAMS (overlaying MultiTFBase.DEFAULT_PARAMS).
      2. Implement _build_signals(self, df_1m, feed_ts).
    """

    TIMEFRAME = "1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "buy_size_pct": 0.7,
        "sl_pct": 0.02,
        "tp_pct": 0.025,
        "max_hold_bars": 480,  # 8h (480 1m bars) — crypto 24/7이라 EOD 대신 시간 기반 강제 청산
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
        self._entry_idx: Optional[int] = None
        self._bar_idx: int = -1

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        self._bar_idx += 1

        if self._has_position():
            held_bars = self._bar_idx - (self._entry_idx or 0)
            max_hold = int(self.config.get("max_hold_bars", 480))
            if max_hold > 0 and held_bars >= max_hold:
                qty = float(self.ctx.holdings.get(self.symbol, 0))
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "max_hold"})
                self._entry = None
                self._entry_idx = None
                return

        if self._has_position() and self._entry is not None:
            if price <= self._entry * (1 - float(self.config["sl_pct"])):
                qty = float(self.ctx.holdings.get(self.symbol, 0))
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = None
                self._entry_idx = None
                return
            if price >= self._entry * (1 + float(self.config["tp_pct"])):
                qty = float(self.ctx.holdings.get(self.symbol, 0))
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry = None
                self._entry_idx = None
                return
            if self._sell.get(ts, False):
                qty = float(self.ctx.holdings.get(self.symbol, 0))
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sell_sig"})
                self._entry = None
                self._entry_idx = None
                return
            return

        if self._buy.get(ts, False):
            from ..core.crypto_backtest_engine import CRYPTO_TAKER_FEE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = cash / (price * (1 + CRYPTO_TAKER_FEE)) if price > 0 else 0.0
            if qty > 0:
                tr = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": self.name},
                )
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
                    self._entry_idx = self._bar_idx
