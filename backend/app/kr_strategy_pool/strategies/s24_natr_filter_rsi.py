"""S24: NATR Filter + RSI. NATR(변동성%)이 충분히 클 때만 RSI mean reversion 진입."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import natr, rsi


class S24NatrFilterRsi(KrStrategyBase):
    name = "s24_natr_filter_rsi"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "natr_period": 14, "natr_min": 0.3,  # 최소 0.3% 변동성
        "rsi_period": 14, "oversold": 30, "overbought": 70,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["natr"] = natr(df["high"], df["low"], df["close"], int(self.config["natr_period"]))
        df["rsi"] = rsi(df["close"], int(self.config["rsi_period"]))
        self._natr = dict(zip(df["timestamp"], df["natr"]))
        self._rsi = dict(zip(df["timestamp"], df["rsi"]))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        n, r = self._natr.get(ts), self._rsi.get(ts)
        if n is None or r is None or pd.isna(n) or pd.isna(r):
            return
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            return
        if (not self._has_position()
                and n > float(self.config["natr_min"])
                and r < float(self.config["oversold"])):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(self.symbol, qty, price=price,
                             metadata={"reason": "natr_high+rsi_oversold"})
        elif self._has_position() and r > float(self.config["overbought"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "rsi_overbought"})
