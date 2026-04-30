"""
S1: RSI Mean Reversion (5분봉)

매수: RSI < oversold 이고 미보유
매도: RSI > overbought 이고 보유 중
ATR 또는 동시호가 직전(15:25) 강제청산 옵션은 향후 확장.

이 종목(061090)은 lag-1 자기상관이 음수(-0.175) 이고 박스권 → 평균회귀 적합.
"""
from typing import Any, Dict

import pandas as pd

from ..base import KrStrategyBase
from ..indicators import rsi


class S1RsiReversion(KrStrategyBase):
    name = "s1_rsi_reversion"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "rsi_period": 14,
        "oversold": 30,
        "overbought": 70,
        "buy_size_pct": 0.95,  # 진입 시 가용현금의 95%
        "force_eod_exit": True,  # 종가 동시호가 진입 직전 강제청산 (15:25)
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["rsi"] = rsi(df["close"], int(self.config["rsi_period"]))
        # ts → rsi value lookup
        self._rsi_by_ts = dict(zip(df["timestamp"], df["rsi"]))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        r = self._rsi_by_ts.get(ts)
        if r is None or pd.isna(r):
            return

        # 종가 동시호가 직전 강제청산 (5분봉 15:25 기준)
        if self.config.get("force_eod_exit"):
            t_str = str(ts)[11:16] if len(str(ts)) >= 16 else ""
            if t_str >= "15:25" and self._has_position():
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(
                    self.symbol, qty, price=price,
                    metadata={"reason": "eod_exit"},
                )
                return

        oversold = float(self.config["oversold"])
        overbought = float(self.config["overbought"])

        # entry
        if not self._has_position() and r < oversold:
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            from ..base import KrStrategyBase as _Base  # noqa
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": f"rsi<{oversold}", "rsi": float(r)},
                )

        # exit
        elif self._has_position() and r > overbought:
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(
                self.symbol, qty, price=price,
                metadata={"reason": f"rsi>{overbought}", "rsi": float(r)},
            )
