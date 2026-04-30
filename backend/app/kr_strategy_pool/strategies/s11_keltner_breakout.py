"""S11: Keltner Channel Breakout
close > Keltner upper 돌파 시 매수, mid 회귀 시 매도. SL/EOD.
"""
from typing import Any, Dict, Optional
import pandas as pd

from ..base import KrStrategyBase
from ..indicators import keltner


class S11KeltnerBreakout(KrStrategyBase):
    name = "s11_keltner_breakout"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "ema_period": 20, "atr_period": 10, "multiplier": 2.0,
        "sl_pct": 0.02,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        u, m, l = keltner(df["high"], df["low"], df["close"],
                          int(self.config["ema_period"]),
                          int(self.config["atr_period"]),
                          float(self.config["multiplier"]))
        self._upper = dict(zip(df["timestamp"], u))
        self._mid = dict(zip(df["timestamp"], m))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        u, m = self._upper.get(ts), self._mid.get(ts)
        if u is None or pd.isna(u):
            return
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
            if price <= float(m):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "kc_mid_revert"})
                self._entry = None
                return
        if not self._has_position() and price > float(u):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "kc_break"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
