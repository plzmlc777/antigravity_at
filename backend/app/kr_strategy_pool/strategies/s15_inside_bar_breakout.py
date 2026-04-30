"""S15: Inside Bar Breakout
inside bar (현재봉의 high<직전봉 high AND low>직전봉 low) 발생 후
다음 봉이 직전 봉 high를 돌파하면 매수. SL=직전봉 low, EOD 청산.
"""
from typing import Any, Dict, Optional
import pandas as pd

from ..base import KrStrategyBase


class S15InsideBarBreakout(KrStrategyBase):
    name = "s15_inside_bar_breakout"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        prev_h = df["high"].shift(1)
        prev_l = df["low"].shift(1)
        prev_prev_h = df["high"].shift(2)
        prev_prev_l = df["low"].shift(2)

        # 직전 봉(t-1)이 inside bar인가?
        inside = (prev_h < prev_prev_h) & (prev_l > prev_prev_l)
        # 현재 봉의 close가 직전 inside bar high 돌파 ?
        df["entry"] = inside & (df["close"] > prev_h)
        # SL을 위한 reference low (직전 봉 low)
        df["ref_low"] = prev_l
        df["ref_high"] = prev_h
        self._entry_sig = dict(zip(df["timestamp"], df["entry"].fillna(False)))
        self._sl_ref = dict(zip(df["timestamp"], df["ref_low"]))
        self._entry: Optional[float] = None
        self._sl_price: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            self._sl_price = None
            return
        if self._has_position() and self._sl_price and price <= self._sl_price:
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl_inside_low"})
            self._entry = None
            self._sl_price = None
            return
        if not self._has_position() and self._entry_sig.get(ts, False):
            sl_ref = self._sl_ref.get(ts)
            if sl_ref is None or pd.isna(sl_ref):
                return
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": "inside_bar_break"},
                )
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
                    self._sl_price = float(sl_ref)
