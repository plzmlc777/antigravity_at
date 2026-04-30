"""S21: ADX Filter + RSI. ADX>threshold 추세 강할 때만 RSI 30 oversold 매수."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import adx, rsi


class S21AdxRsi(KrStrategyBase):
    name = "s21_adx_rsi"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "adx_period": 14, "adx_threshold": 25,
        "rsi_period": 14, "oversold": 35, "overbought": 70,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["adx"] = adx(df["high"], df["low"], df["close"], int(self.config["adx_period"]))
        df["rsi"] = rsi(df["close"], int(self.config["rsi_period"]))
        self._adx = dict(zip(df["timestamp"], df["adx"]))
        self._rsi = dict(zip(df["timestamp"], df["rsi"]))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        a = self._adx.get(ts)
        r = self._rsi.get(ts)
        if a is None or r is None or pd.isna(a) or pd.isna(r):
            return
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            return
        if (not self._has_position()
                and a > float(self.config["adx_threshold"])
                and r < float(self.config["oversold"])):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(self.symbol, qty, price=price,
                             metadata={"reason": "adx_strong+rsi_oversold", "adx": float(a), "rsi": float(r)})
        elif self._has_position() and r > float(self.config["overbought"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price,
                          metadata={"reason": "rsi_overbought", "rsi": float(r)})
