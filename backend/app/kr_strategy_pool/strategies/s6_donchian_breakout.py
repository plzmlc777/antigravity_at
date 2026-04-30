"""
S6: Donchian Channel Breakout (5분봉)

매수: close > 직전 N봉 high (upper channel 돌파)
매도: close < 직전 N봉 low (lower channel 이탈) OR SL/TP

박스권에서는 false breakout 누적으로 적자, 추세 phase에서 살아남는 전략.
동적 선택 시스템의 추세-edge 보험.
"""
from typing import Any, Dict, Optional

import pandas as pd

from ..base import KrStrategyBase
from ..indicators import donchian


class S6DonchianBreakout(KrStrategyBase):
    name = "s6_donchian_breakout"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "dc_period": 20,    # 직전 20개 5분봉 = 100분 ≈ 1.7시간
        "sl_pct": 0.02,     # 손절 -2%
        "tp_pct": 0.05,     # 익절 +5% (추세 익절 비대칭)
        "buy_size_pct": 0.7,
        "force_eod_exit": True,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        upper, mid, lower = donchian(df["high"], df["low"], int(self.config["dc_period"]))
        self._upper = dict(zip(df["timestamp"], upper))
        self._lower = dict(zip(df["timestamp"], lower))
        self._entry_price: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        u = self._upper.get(ts)
        l = self._lower.get(ts)
        if u is None or pd.isna(u):
            return

        # EOD 청산
        if self.config.get("force_eod_exit"):
            t_str = str(ts)[11:16] if len(str(ts)) >= 16 else ""
            if t_str >= str(self.config["exit_time"]) and self._has_position():
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
                self._entry_price = None
                return

        # 보유 중인 경우: SL/TP/lower break
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
            if l is not None and not pd.isna(l) and price < float(l):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "lower_break"})
                self._entry_price = None
                return

        # 진입
        if not self._has_position() and price > float(u):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                trade = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": "dc_upper_break", "upper": float(u)},
                )
                if trade and trade.get("type") == "buy":
                    self._entry_price = float(trade.get("price", price))
