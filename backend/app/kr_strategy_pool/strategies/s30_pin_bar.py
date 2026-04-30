"""S30: Bullish Pin Bar Reversal.
현재봉이 long lower wick (lower wick > 2 × body) AND close > open → 매수.
SL=현재 low, TP=2x risk.
"""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase


class S30BullishPinBar(KrStrategyBase):
    name = "s30_bullish_pin_bar"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "wick_body_ratio": 2.0,
        "rr_multiple": 2.0,  # TP = entry + 2 * (entry - SL)
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        body = (df["close"] - df["open"]).abs()
        lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
        upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
        bullish = df["close"] > df["open"]
        ratio = float(self.config["wick_body_ratio"])
        df["entry"] = (
            bullish
            & (lower_wick >= ratio * body.replace(0, 1e-9))
            & (lower_wick > upper_wick)
        )
        df["sl_ref"] = df["low"]
        self._entry_sig = dict(zip(df["timestamp"], df["entry"].fillna(False)))
        self._sl_ref = dict(zip(df["timestamp"], df["sl_ref"]))
        self._entry: Optional[float] = None
        self._sl: Optional[float] = None
        self._tp: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = self._sl = self._tp = None
            return
        if self._has_position():
            if self._sl and price <= self._sl:
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = self._sl = self._tp = None
                return
            if self._tp and price >= self._tp:
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry = self._sl = self._tp = None
                return
            return
        if self._entry_sig.get(ts, False):
            sl_ref = self._sl_ref.get(ts)
            if sl_ref is None or pd.isna(sl_ref) or sl_ref >= price:
                return
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "pin_bar"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
                    self._sl = float(sl_ref)
                    risk = self._entry - self._sl
                    self._tp = self._entry + float(self.config["rr_multiple"]) * risk
