"""S22: Money Flow Index Reversion. MFI<20 매수, MFI>80 매도."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import mfi


class S22MfiReversion(KrStrategyBase):
    name = "s22_mfi_reversion"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "period": 14, "oversold": 20, "overbought": 80,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        m = mfi(df["high"], df["low"], df["close"], df["volume"], int(self.config["period"]))
        self._mfi = dict(zip(df["timestamp"], m))

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
        m = self._mfi.get(ts)
        if m is None or pd.isna(m):
            return
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""
        if self.config.get("force_eod_exit") and t >= str(self.config["exit_time"]) and self._has_position():
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            return
        if not self._has_position() and m < float(self.config["oversold"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "mfi_oversold"})
        elif self._has_position() and m > float(self.config["overbought"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "mfi_overbought"})
