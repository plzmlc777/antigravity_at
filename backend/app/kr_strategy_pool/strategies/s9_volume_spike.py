"""S9: Volume Spike Buy
거래량이 직전 N봉 평균 대비 M배 이상 + 상승봉(close>open)이면 매수.
종가 직전 청산 또는 SL/TP.
"""
from typing import Any, Dict, Optional
import pandas as pd

from ..base import KrStrategyBase


class S9VolumeSpike(KrStrategyBase):
    name = "s9_volume_spike"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "vol_window": 20,
        "spike_mult": 3.0,
        "sl_pct": 0.015,
        "tp_pct": 0.03,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        avg_v = df["volume"].rolling(int(self.config["vol_window"])).mean()
        df["vol_ratio"] = df["volume"] / avg_v.replace(0, 1e9)
        df["bullish"] = df["close"] > df["open"]
        df["signal"] = (df["vol_ratio"] >= float(self.config["spike_mult"])) & df["bullish"]
        self._signal = dict(zip(df["timestamp"], df["signal"].fillna(False)))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            return
        if self._has_position() and self._entry:
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
        if not self._has_position() and self._signal.get(ts, False):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "vol_spike"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
