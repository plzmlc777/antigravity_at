"""S16: Stochastic Oscillator Reversion. K<oversold 매수, K>overbought 매도."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import stochastic


class S16StochasticReversion(KrStrategyBase):
    name = "s16_stochastic_reversion"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "k_period": 14, "d_period": 3,
        "oversold": 20, "overbought": 80,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        k, _ = stochastic(df["high"], df["low"], df["close"],
                          int(self.config["k_period"]), int(self.config["d_period"]))
        self._k = dict(zip(df["timestamp"], k))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        k = self._k.get(ts)
        if k is None or pd.isna(k):
            return
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            return
        if not self._has_position() and k < float(self.config["oversold"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(self.symbol, qty, price=price,
                             metadata={"reason": "stoch_oversold", "k": float(k)})
        elif self._has_position() and k > float(self.config["overbought"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price,
                          metadata={"reason": "stoch_overbought", "k": float(k)})
