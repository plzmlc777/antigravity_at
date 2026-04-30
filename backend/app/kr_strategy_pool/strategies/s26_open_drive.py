"""S26: Open Drive. 시초 5분봉(09:00) close가 open 대비 +0.5% 이상이면 09:05 매수, EOD 청산.
시가 강세에서 추세 추종.
"""
from typing import Any, Dict, Optional
from ..base import KrStrategyBase


class S26OpenDrive(KrStrategyBase):
    name = "s26_open_drive"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "min_open_drive_pct": 0.005,
        "sl_pct": 0.015, "tp_pct": 0.04,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
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
            if t == "09:00" and day not in per_day:
                drive_pct = (float(c["close"]) - float(c["open"])) / max(float(c["open"]), 1)
                per_day[day] = {"drive": drive_pct, "ts_first": ts}
        self._drive = per_day
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
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
                self._entry = None
                return
            if self._entry and price <= self._entry * (1 - float(self.config["sl_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = None
                return
            if self._entry and price >= self._entry * (1 + float(self.config["tp_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry = None
                return
            return

        # 09:05 매수 시점
        if t != "09:05":
            return
        info = self._drive.get(day)
        if not info:
            return
        if info["drive"] >= float(self.config["min_open_drive_pct"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": "open_drive", "drive_pct": info["drive"]})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
