"""
S5: VWAP Mean Reversion (5분봉, intraday)

매수: 일중 close < VWAP * (1 - lower_band_pct)
매도: 일중 close >= VWAP (회귀 완료)
강제청산: 15:25
"""
from typing import Any, Dict

import pandas as pd

from ..base import KrStrategyBase
from ..indicators import vwap_intraday


class S5VwapReversion(KrStrategyBase):
    name = "s5_vwap_reversion"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "lower_band_pct": 0.015,  # VWAP - 1.5% 매수
        "buy_size_pct": 0.95,
        "force_eod_exit": True,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df["day_id"] = df["ts"].dt.date.astype(str)
        df["vwap"] = vwap_intraday(
            df["high"], df["low"], df["close"], df["volume"], df["day_id"]
        )
        self._vwap_by_ts = dict(zip(df["timestamp"], df["vwap"]))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        v = self._vwap_by_ts.get(ts)
        if v is None or pd.isna(v):
            return

        # EOD 청산
        if self.config.get("force_eod_exit"):
            t_str = str(ts)[11:16] if len(str(ts)) >= 16 else ""
            if t_str >= str(self.config["exit_time"]) and self._has_position():
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
                return

        lower_band = float(v) * (1 - float(self.config["lower_band_pct"]))

        if not self._has_position() and price < lower_band:
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": "below_vwap_band", "vwap": float(v)},
                )
        elif self._has_position() and price >= float(v):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(
                self.symbol, qty, price=price,
                metadata={"reason": "vwap_reverted", "vwap": float(v)},
            )
