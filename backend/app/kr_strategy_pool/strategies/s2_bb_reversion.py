"""
S2: Bollinger Band Reversion (5분봉)

매수: close < BB lower (oversold band touch)
매도: close > BB middle (mean reversion target)
"""
from typing import Any, Dict

import pandas as pd

from ..base import KrStrategyBase
from ..indicators import bollinger


class S2BBReversion(KrStrategyBase):
    name = "s2_bb_reversion"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "bb_period": 20,
        "bb_std": 2.0,
        "buy_size_pct": 0.95,
        "force_eod_exit": True,
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        upper, mid, lower = bollinger(
            df["close"], int(self.config["bb_period"]), float(self.config["bb_std"])
        )
        self._upper = dict(zip(df["timestamp"], upper))
        self._mid = dict(zip(df["timestamp"], mid))
        self._lower = dict(zip(df["timestamp"], lower))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        u, m, l = self._upper.get(ts), self._mid.get(ts), self._lower.get(ts)
        if u is None or pd.isna(u):
            return

        # EOD 청산
        if self.config.get("force_eod_exit"):
            t_str = str(ts)[11:16] if len(str(ts)) >= 16 else ""
            if t_str >= "15:25" and self._has_position():
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
                return

        if not self._has_position() and price < l:
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": "bb_lower", "bb_lower": float(l)},
                )
        elif self._has_position() and price > m:
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(
                self.symbol, qty, price=price,
                metadata={"reason": "bb_mid", "bb_mid": float(m)},
            )
