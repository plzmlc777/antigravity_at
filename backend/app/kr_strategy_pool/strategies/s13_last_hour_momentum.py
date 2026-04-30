"""S13: Last Hour Momentum
14:00 close가 그날 09:00 open 대비 +threshold% 이상이면 14:00에 매수, 15:25 청산.
종가 동시호가 진입 직전까지 모멘텀 잡기.
"""
from collections import defaultdict
from typing import Any, Dict, Optional

from ..base import KrStrategyBase


class S13LastHourMomentum(KrStrategyBase):
    name = "s13_last_hour_momentum"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "entry_time": "14:00",
        "exit_time": "15:25",
        "min_intraday_gain": 0.005,  # 0.5% 이상
        "sl_pct": 0.015,
        "buy_size_pct": 0.7,
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        per_day: Dict[str, Dict[str, float]] = {}
        for c in feed:
            ts = str(c["timestamp"])
            if len(ts) < 16:
                continue
            day = ts[:10]
            t = ts[11:16]
            if day not in per_day and t >= "09:00":
                per_day[day] = {"open": float(c["open"])}
        self._open_by_day = {d: v["open"] for d, v in per_day.items()}
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = str(candle["timestamp"])
        if len(ts) < 16:
            return
        day = ts[:10]
        t = ts[11:16]
        price = float(candle["close"])

        if self._has_position():
            if t >= str(self.config["exit_time"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "exit_time"})
                self._entry = None
                return
            if self._entry and price <= self._entry * (1 - float(self.config["sl_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = None
                return
            return

        # 진입 시각 정확히 14:00 봉
        if t != str(self.config["entry_time"]):
            return
        day_open = self._open_by_day.get(day)
        if not day_open or day_open <= 0:
            return
        intraday_gain = (price - day_open) / day_open
        if intraday_gain >= float(self.config["min_intraday_gain"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": "last_hour_momentum", "intraday_gain": intraday_gain},
                )
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
