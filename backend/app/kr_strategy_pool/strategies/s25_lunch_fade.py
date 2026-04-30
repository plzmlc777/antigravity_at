"""S25: Lunch-Time Fade. 12:00~12:30 박스 high를 13:00~13:30에 close가 다시 닿으면 fade(short impossible → 매수 보류, instead reverse: low touch 매수).
KR long-only 환경: 11:30~12:30 low 터치 시 12:30 이후 reversion 매수, 13:30 청산.
"""
from collections import defaultdict
from typing import Any, Dict, Optional
from ..base import KrStrategyBase


class S25LunchFade(KrStrategyBase):
    name = "s25_lunch_fade"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "lunch_start": "11:30", "lunch_end": "12:30",
        "entry_window_start": "12:30", "entry_window_end": "13:30",
        "exit_time": "13:45",
        "sl_pct": 0.01,
        "buy_size_pct": 0.7,
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        per_day: Dict[str, float] = {}
        ls, le = str(self.config["lunch_start"]), str(self.config["lunch_end"])
        for c in feed:
            ts = str(c["timestamp"])
            if len(ts) < 16:
                continue
            day = ts[:10]
            t = ts[11:16]
            if ls <= t < le:
                if day not in per_day or c["low"] < per_day[day]:
                    per_day[day] = float(c["low"])
        self._lunch_low = per_day
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

        es, ee = str(self.config["entry_window_start"]), str(self.config["entry_window_end"])
        if not (es <= t < ee):
            return
        ll = self._lunch_low.get(day)
        if ll is None:
            return
        # 점심대 low를 다시 닿으면 reversion 매수
        if price <= ll * 1.001:
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": "lunch_low_touch", "lunch_low": ll})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
