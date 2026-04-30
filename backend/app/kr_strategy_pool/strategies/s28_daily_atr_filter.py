"""S28: Daily ATR Filter + 5m Entry. 일봉 ATR>threshold일 때만 5m RSI 30 진입."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import atr, rsi


class S28DailyAtrFilter(KrStrategyBase):
    name = "s28_daily_atr_filter"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "daily_atr_period": 5, "min_daily_atr_pct": 2.0,
        "rsi_period": 14, "oversold": 30, "overbought": 70,
        "sl_pct": 0.02,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df["day"] = df["ts"].dt.date.astype(str)
        # 일봉 OHLC
        daily = df.groupby("day").agg(open=("open", "first"), high=("high", "max"),
                                       low=("low", "min"), close=("close", "last"))
        daily_atr = atr(daily["high"], daily["low"], daily["close"], int(self.config["daily_atr_period"]))
        daily_atr_pct = (daily_atr / daily["close"] * 100).fillna(0)
        # 어제 ATR 사용 (오늘 정보 차단)
        atr_lag = daily_atr_pct.shift(1).fillna(0)
        df["daily_atr_pct"] = df["day"].map(atr_lag).fillna(0)

        df["rsi"] = rsi(df["close"], int(self.config["rsi_period"]))
        self._datr = dict(zip(df["timestamp"], df["daily_atr_pct"]))
        self._rsi = dict(zip(df["timestamp"], df["rsi"]))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        d = self._datr.get(ts, 0)
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
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "rsi_overbought"})
                self._entry = None
                return
        if (not self._has_position()
                and d > float(self.config["min_daily_atr_pct"])
                and r < float(self.config["oversold"])):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": "high_dat+rsi_oversold"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
