"""
S4: Opening Range Breakout (5분봉)

전략:
  - 09:00~09:30 6봉(5분*6)을 opening range로 정의
  - 09:30 이후 첫 close > range_high * (1 + buffer) 이면 매수
  - 손절: range_low 이하로 close (또는 entry price * (1 - sl_pct))
  - 청산: 15:25 또는 익절(price * (1 + tp_pct))

이 종목은 09:00~09:30이 거래량의 18.78%로 가장 활발 → ORB 환경 적합.
"""
from typing import Any, Dict, Optional

from ..base import KrStrategyBase


class S4OpeningRangeBreakout(KrStrategyBase):
    name = "s4_orb"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "or_minutes": 30,  # opening range 길이 (분)
        "buffer_pct": 0.001,  # range high 위 0.1% 이상 돌파 시 진입
        "sl_pct": 0.02,  # 손절 -2%
        "tp_pct": 0.04,  # 익절 +4%
        "buy_size_pct": 0.95,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        or_minutes = int(self.config["or_minutes"])

        # 일별 opening range high/low 계산
        # 각 거래일의 09:00 ~ 09:00+or_minutes 봉의 high/low
        from collections import defaultdict
        per_day: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"high": -1e18, "low": 1e18}
        )
        for c in feed:
            ts = str(c["timestamp"])
            if len(ts) < 16:
                continue
            day = ts[:10]
            t = ts[11:16]  # HH:MM
            # 09:00 시작, or_minutes 분간만 누적
            hh, mm = int(t[:2]), int(t[3:5])
            minutes_from_open = (hh - 9) * 60 + mm
            if 0 <= minutes_from_open < or_minutes:
                if c["high"] > per_day[day]["high"]:
                    per_day[day]["high"] = float(c["high"])
                if c["low"] < per_day[day]["low"]:
                    per_day[day]["low"] = float(c["low"])

        self._or_high: Dict[str, float] = {d: v["high"] for d, v in per_day.items()}
        self._or_low: Dict[str, float] = {d: v["low"] for d, v in per_day.items()}
        self._or_minutes = or_minutes
        self._buffer = float(self.config["buffer_pct"])
        self._sl = float(self.config["sl_pct"])
        self._tp = float(self.config["tp_pct"])
        self._exit_time = str(self.config["exit_time"])
        # 매수 시점 entry price (손절/익절 계산용)
        self._entry_price: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = str(candle["timestamp"])
        if len(ts) < 16:
            return
        day = ts[:10]
        t = ts[11:16]
        price = float(candle["close"])

        hh, mm = int(t[:2]), int(t[3:5])
        minutes_from_open = (hh - 9) * 60 + mm

        # OR 범위 미완료 → 진입 보류
        if minutes_from_open < self._or_minutes:
            return

        or_high = self._or_high.get(day)
        or_low = self._or_low.get(day)
        if or_high is None or or_high < 0:
            return

        # 청산 조건들 (보유 중이면)
        if self._has_position():
            # 1) 청산 시각
            if t >= self._exit_time:
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "exit_time"})
                self._entry_price = None
                return
            # 2) 손절
            if self._entry_price and price <= self._entry_price * (1 - self._sl):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry_price = None
                return
            # 3) 익절
            if self._entry_price and price >= self._entry_price * (1 + self._tp):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry_price = None
                return
            return

        # 진입 — 같은 날 한 번만 (or_minutes 직후 첫 돌파)
        # entry: close > or_high * (1+buffer)
        threshold = or_high * (1 + self._buffer)
        if price > threshold:
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                trade = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={
                        "reason": "or_breakout",
                        "or_high": or_high, "threshold": threshold,
                    },
                )
                if trade and trade.get("type") == "buy":
                    self._entry_price = float(trade.get("price", price))
