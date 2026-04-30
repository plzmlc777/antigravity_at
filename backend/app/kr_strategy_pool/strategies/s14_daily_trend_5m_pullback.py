"""S14: Daily Trend + 5m RSI Pullback (Multi-Timeframe)
일봉 close가 N일 EMA 위 (상승 추세) AND 5분봉 RSI < oversold → 매수.
RSI > overbought 또는 EOD → 청산.
"""
from typing import Any, Dict, Optional
import pandas as pd

from ..base import KrStrategyBase
from ..indicators import rsi, ema


class S14DailyTrend5mPullback(KrStrategyBase):
    name = "s14_daily_trend_5m_pullback"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "daily_ema": 5,        # 일봉 5일 EMA
        "rsi_period": 14,
        "oversold": 35, "overbought": 65,
        "sl_pct": 0.02,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df["day_id"] = df["ts"].dt.date.astype(str)

        # 일봉 close (당일 마지막 close)
        daily_close = df.groupby("day_id")["close"].last()
        daily_ema = ema(daily_close, int(self.config["daily_ema"]))
        # daily_close > daily_ema → 상승 추세
        daily_uptrend = (daily_close > daily_ema).fillna(False)
        # ❗ shift(1)로 어제까지 정보만 사용 (look-ahead 방지)
        daily_uptrend_lag = daily_uptrend.shift(1).fillna(False)
        df["daily_up"] = df["day_id"].map(daily_uptrend_lag)

        # 5m RSI
        df["rsi"] = rsi(df["close"], int(self.config["rsi_period"]))

        self._daily_up = dict(zip(df["timestamp"], df["daily_up"].fillna(False)))
        self._rsi = dict(zip(df["timestamp"], df["rsi"]))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        r = self._rsi.get(ts)
        if r is None or pd.isna(r):
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
            if r > float(self.config["overbought"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price,
                              metadata={"reason": "rsi_overbought", "rsi": float(r)})
                self._entry = None
                return
        if (not self._has_position() and self._daily_up.get(ts, False)
                and r < float(self.config["oversold"])):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": "daily_up_5m_oversold", "rsi": float(r)},
                )
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
