"""S23: ATR Channel Reversion. close < SMA - k*ATR 매수, close > SMA 매도."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import atr


class S23AtrChannelReversion(KrStrategyBase):
    name = "s23_atr_channel_reversion"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "sma_period": 20, "atr_period": 14, "k": 1.5,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        sma = df["close"].rolling(int(self.config["sma_period"])).mean()
        a = atr(df["high"], df["low"], df["close"], int(self.config["atr_period"]))
        df["lower"] = sma - float(self.config["k"]) * a
        df["mid"] = sma
        self._lower = dict(zip(df["timestamp"], df["lower"]))
        self._mid = dict(zip(df["timestamp"], df["mid"]))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        l, m = self._lower.get(ts), self._mid.get(ts)
        if l is None or m is None or pd.isna(l) or pd.isna(m):
            return
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            return
        if not self._has_position() and price < float(l):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "below_atr_band"})
        elif self._has_position() and price > float(m):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "atr_mid_revert"})
