"""S29: Bullish Engulfing Pattern.
직전봉 음봉 + 현재봉이 양봉 + 현재 close>직전 open AND 현재 open<직전 close → 매수.
SL=현재 low, EOD 청산.
"""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase


class S29BullishEngulfing(KrStrategyBase):
    name = "s29_bullish_engulfing"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "tp_pct": 0.025,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        prev_o = df["open"].shift(1)
        prev_c = df["close"].shift(1)
        prev_low = df["low"].shift(1)
        bearish_prev = prev_c < prev_o
        bullish_now = df["close"] > df["open"]
        engulf = bearish_prev & bullish_now & (df["close"] > prev_o) & (df["open"] < prev_c)
        df["entry"] = engulf
        df["sl_ref"] = df["low"]  # 현재봉 low가 SL
        self._entry_sig = dict(zip(df["timestamp"], df["entry"].fillna(False)))
        self._sl_ref = dict(zip(df["timestamp"], df["sl_ref"]))
        self._entry: Optional[float] = None
        self._sl: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            self._sl = None
            return
        if self._has_position():
            if self._sl and price <= self._sl:
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = None
                self._sl = None
                return
            if self._entry and price >= self._entry * (1 + float(self.config["tp_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry = None
                self._sl = None
                return
            return
        if self._entry_sig.get(ts, False):
            sl_ref = self._sl_ref.get(ts)
            if sl_ref is None or pd.isna(sl_ref):
                return
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "engulfing"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
                    self._sl = float(sl_ref)
