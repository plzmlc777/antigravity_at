"""S19: EMA 5/20 Cross. Golden cross 매수, Death cross 매도."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import ema


class S19EmaCross(KrStrategyBase):
    name = "s19_ema_cross"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "fast": 5, "slow": 20,
        "sl_pct": 0.02, "tp_pct": 0.04,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        f = ema(df["close"], int(self.config["fast"]))
        s = ema(df["close"], int(self.config["slow"]))
        f_prev = f.shift(1)
        s_prev = s.shift(1)
        df["golden"] = (f_prev <= s_prev) & (f > s)
        df["death"] = (f_prev >= s_prev) & (f < s)
        self._golden = dict(zip(df["timestamp"], df["golden"].fillna(False)))
        self._death = dict(zip(df["timestamp"], df["death"].fillna(False)))
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
            if self._death.get(ts, False):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "death_cross"})
                self._entry = None
                return
        if not self._has_position() and self._golden.get(ts, False):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "golden_cross"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
