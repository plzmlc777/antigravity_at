"""S27: 15m EMA Trend + 5m Entry (Multi-Timeframe).
15분봉 close가 EMA20 위 (상승 추세) AND 5분봉 RSI<35 → 매수.
"""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import ema, rsi


class S27_15mEmaTrend(KrStrategyBase):
    name = "s27_15m_ema_trend"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "ema_15m": 20, "rsi_period": 14,
        "oversold": 35, "overbought": 65,
        "sl_pct": 0.02,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        # 5m → 15m resample (3개씩 묶기, 매 15분 단위로 close 추적)
        df["15m_bin"] = df["ts"].dt.floor("15min")
        # 15m close = 각 bin의 마지막 5m close
        last_5m_in_bin = df.groupby("15m_bin")["close"].last()
        ema_15m = ema(last_5m_in_bin, int(self.config["ema_15m"]))
        # bin 별 close > EMA 여부
        uptrend = (last_5m_in_bin > ema_15m).fillna(False)
        # 각 5m row에 자기 bin의 trend 매핑 (현재 bin 정보로 진입은 lookahead 가능 → shift 1bin)
        uptrend_lag = uptrend.shift(1).fillna(False)
        df["bin_uptrend"] = df["15m_bin"].map(uptrend_lag).fillna(False)

        df["rsi"] = rsi(df["close"], int(self.config["rsi_period"]))
        self._uptrend = dict(zip(df["timestamp"], df["bin_uptrend"]))
        self._rsi = dict(zip(df["timestamp"], df["rsi"]))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        up = self._uptrend.get(ts, False)
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
        if not self._has_position() and up and r < float(self.config["oversold"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": "15m_up+5m_oversold"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
