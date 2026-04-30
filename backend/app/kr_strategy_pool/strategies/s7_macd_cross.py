"""
S7: MACD Signal Cross (5분봉)

매수: MACD line이 signal을 상향 돌파 (golden cross)
매도: MACD line이 signal을 하향 돌파 (death cross) OR SL/TP

추세성 종목에서 잘 작동. 박스권에서는 whipsaw 누적.
"""
from typing import Any, Dict, Optional

import pandas as pd

from ..base import KrStrategyBase
from ..indicators import macd


class S7MacdCross(KrStrategyBase):
    name = "s7_macd_cross"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "fast": 12,
        "slow": 26,
        "signal_period": 9,
        "sl_pct": 0.02,
        "tp_pct": 0.05,
        "buy_size_pct": 0.7,
        "force_eod_exit": True,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        m, s, h = macd(
            df["close"],
            int(self.config["fast"]),
            int(self.config["slow"]),
            int(self.config["signal_period"]),
        )
        # cross detection: prev macd vs signal sign change
        df["m"] = m
        df["s"] = s
        df["m_prev"] = df["m"].shift(1)
        df["s_prev"] = df["s"].shift(1)
        df["golden"] = (df["m_prev"] <= df["s_prev"]) & (df["m"] > df["s"])
        df["death"] = (df["m_prev"] >= df["s_prev"]) & (df["m"] < df["s"])
        self._golden = dict(zip(df["timestamp"], df["golden"]))
        self._death = dict(zip(df["timestamp"], df["death"]))
        self._entry_price: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        g = self._golden.get(ts, False)
        d = self._death.get(ts, False)

        # EOD 청산
        if self.config.get("force_eod_exit"):
            t_str = str(ts)[11:16] if len(str(ts)) >= 16 else ""
            if t_str >= str(self.config["exit_time"]) and self._has_position():
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
                self._entry_price = None
                return

        # 보유 중: SL/TP/death cross
        if self._has_position() and self._entry_price:
            if price <= self._entry_price * (1 - float(self.config["sl_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry_price = None
                return
            if price >= self._entry_price * (1 + float(self.config["tp_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry_price = None
                return
            if d:
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "death_cross"})
                self._entry_price = None
                return

        # 진입
        if not self._has_position() and g:
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                trade = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": "golden_cross"},
                )
                if trade and trade.get("type") == "buy":
                    self._entry_price = float(trade.get("price", price))
