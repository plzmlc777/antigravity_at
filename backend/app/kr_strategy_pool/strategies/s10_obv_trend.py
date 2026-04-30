"""S10: OBV Trend Follow
OBV의 EMA가 우상향 (slope>0) 이고 close가 OBV-EMA 직전 상향 돌파 시 매수.
SL/TP/EOD/OBV slope 음전환 시 매도.
"""
from typing import Any, Dict, Optional
import pandas as pd

from ..base import KrStrategyBase
from ..indicators import obv, ema


class S10ObvTrend(KrStrategyBase):
    name = "s10_obv_trend"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "obv_ema": 20,
        "slope_window": 5,
        "sl_pct": 0.02,
        "tp_pct": 0.04,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        ob = obv(df["close"], df["volume"])
        ob_ema = ema(ob, int(self.config["obv_ema"]))
        # OBV-EMA의 N봉 변화율 (slope 부호)
        slope = ob_ema.diff(int(self.config["slope_window"]))
        df["slope"] = slope
        df["slope_prev"] = slope.shift(1)
        df["entry"] = (df["slope_prev"] <= 0) & (df["slope"] > 0)
        df["exit"] = (df["slope_prev"] > 0) & (df["slope"] <= 0)
        self._entry_sig = dict(zip(df["timestamp"], df["entry"].fillna(False)))
        self._exit_sig = dict(zip(df["timestamp"], df["exit"].fillna(False)))
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
            if self._exit_sig.get(ts, False):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "obv_slope_neg"})
                self._entry = None
                return
        if not self._has_position() and self._entry_sig.get(ts, False):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "obv_slope_pos"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
