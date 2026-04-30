"""S12: Closing Range Breakout
14:30~15:00 사이의 high/low를 'closing range'로 정의.
14:55~15:25 사이에 close > closing_range_high 돌파 시 매수, 15:25 종가 청산.
종가 직전 모멘텀 활용.
"""
from collections import defaultdict
from typing import Any, Dict, Optional

from ..base import KrStrategyBase


class S12ClosingRangeBreakout(KrStrategyBase):
    name = "s12_closing_range_breakout"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "cr_start": "14:30", "cr_end": "15:00",
        "entry_window_start": "15:00", "exit_time": "15:25",
        "buffer_pct": 0.001,
        "sl_pct": 0.01,
        "buy_size_pct": 0.7,
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        per_day: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"high": -1e18, "low": 1e18}
        )
        cr_s, cr_e = str(self.config["cr_start"]), str(self.config["cr_end"])
        for c in feed:
            ts = str(c["timestamp"])
            if len(ts) < 16:
                continue
            day = ts[:10]
            t = ts[11:16]
            if cr_s <= t < cr_e:
                if c["high"] > per_day[day]["high"]:
                    per_day[day]["high"] = float(c["high"])
                if c["low"] < per_day[day]["low"]:
                    per_day[day]["low"] = float(c["low"])
        self._cr_high = {d: v["high"] for d, v in per_day.items()}
        self._buffer = float(self.config["buffer_pct"])
        self._sl = float(self.config["sl_pct"])
        self._entry_start = str(self.config["entry_window_start"])
        self._exit_time = str(self.config["exit_time"])
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = str(candle["timestamp"])
        if len(ts) < 16:
            return
        day = ts[:10]
        t = ts[11:16]
        price = float(candle["close"])

        if self._has_position():
            if t >= self._exit_time:
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "exit_time"})
                self._entry = None
                return
            if self._entry and price <= self._entry * (1 - self._sl):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = None
                return
            return

        if not (self._entry_start <= t < self._exit_time):
            return

        cr_high = self._cr_high.get(day, -1e18)
        if cr_high < 0:
            return
        threshold = cr_high * (1 + self._buffer)
        if price > threshold:
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": "cr_break", "cr_high": cr_high})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
