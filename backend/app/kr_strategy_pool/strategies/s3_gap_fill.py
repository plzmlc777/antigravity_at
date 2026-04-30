"""
S3: Gap Fill (일봉 + 시초 진입)

전제: 이 종목은 |gap|>1%가 58.5% 거래일에 발생, gap up bias 1.9:1.

전략:
  매수 — 시가 갭(전일 종가 대비) <= -gap_threshold 일 때 시초가에 매수
         (갭다운이 메워지길 기대)
  매도 — 같은 날 종가에 청산 (intraday only)

5분봉 데이터로 운영하되, 첫 봉(09:00)을 시가로 사용. 종가는 15:25 봉 close.
"""
from typing import Any, Dict, Optional

from ..base import KrStrategyBase


class S3GapFill(KrStrategyBase):
    name = "s3_gap_fill"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "gap_threshold_pct": 1.0,  # 갭다운 -1% 이상이면 매수
        "buy_size_pct": 0.95,
        "exit_time": "15:25",  # 청산 시각
    }

    def initialize(self) -> None:
        # 일별 첫 봉(09:00)과 전일 마지막 봉(15:25 또는 15:30) close를 매핑
        feed = self.ctx.feeds[self.symbol]
        # 거래일별로 그룹화 → 시초 open, 직전 거래일 close 산출
        from collections import defaultdict
        by_day: Dict[str, Dict[str, Any]] = {}
        for c in feed:
            day = str(c["timestamp"])[:10]
            if day not in by_day:
                by_day[day] = {
                    "first_ts": c["timestamp"],
                    "first_open": float(c["open"]),
                    "last_ts": c["timestamp"],
                    "last_close": float(c["close"]),
                }
            else:
                by_day[day]["last_ts"] = c["timestamp"]
                by_day[day]["last_close"] = float(c["close"])

        days_sorted = sorted(by_day.keys())
        prev_close: Optional[float] = None
        # ts → gap_pct
        self._gap_at_open: Dict[str, float] = {}
        # ts → first_open_ts (오늘 시초 봉 timestamp) for entry detection
        self._is_first_bar: Dict[str, bool] = {}
        # ts → exit_time hit?
        for d in days_sorted:
            entry = by_day[d]
            if prev_close and prev_close > 0:
                gap = (entry["first_open"] - prev_close) / prev_close * 100.0
                self._gap_at_open[entry["first_ts"]] = gap
            self._is_first_bar[entry["first_ts"]] = True
            prev_close = entry["last_close"]

        self._exit_time = str(self.config["exit_time"])

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        t_str = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        # 청산
        if self._has_position() and t_str >= self._exit_time:
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "exit_time"})
            return

        # 시초 진입
        if self._is_first_bar.get(ts) and not self._has_position():
            gap = self._gap_at_open.get(ts)
            if gap is None:
                return
            threshold = -float(self.config["gap_threshold_pct"])
            if gap <= threshold:
                from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
                # 시초가 매수 — open 가격 사용
                entry_price = float(candle["open"])
                cash = self.ctx.cash * float(self.config["buy_size_pct"])
                qty = int(cash / (entry_price * (1 + KR_BUY_FEE_RATE)))
                if qty > 0:
                    self.ctx.buy(
                        self.symbol, qty, price=entry_price,
                        metadata={"reason": "gap_down_fill", "gap_pct": gap},
                    )
