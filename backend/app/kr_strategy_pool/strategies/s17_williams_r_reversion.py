"""S17: Williams %R Reversion. <-80 oversold 매수, >-20 overbought 매도."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import williams_r


class S17WilliamsRReversion(KrStrategyBase):
    name = "s17_williams_r_reversion"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "period": 14, "oversold": -80, "overbought": -20,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        wr = williams_r(df["high"], df["low"], df["close"], int(self.config["period"]))
        self._wr = dict(zip(df["timestamp"], wr))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        w = self._wr.get(ts)
        if w is None or pd.isna(w):
            return
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            return
        if not self._has_position() and w < float(self.config["oversold"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "wr_oversold"})
        elif self._has_position() and w > float(self.config["overbought"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "wr_overbought"})
