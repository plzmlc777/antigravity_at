"""S20: Ichimoku Cloud Momentum. close가 cloud 위 + tenkan>kijun → 매수."""
from typing import Any, Dict, Optional
import pandas as pd
from ..base import KrStrategyBase
from ..indicators import ichimoku


class S20IchimokuMomentum(KrStrategyBase):
    name = "s20_ichimoku_momentum"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        "tenkan": 9, "kijun": 26, "senkou_b": 52,
        "sl_pct": 0.02, "tp_pct": 0.05,
        "buy_size_pct": 0.7,
        "force_eod_exit": True, "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        conv, base, span_a, span_b = ichimoku(
            df["high"], df["low"], df["close"],
            int(self.config["tenkan"]), int(self.config["kijun"]),
            int(self.config["senkou_b"]),
        )
        cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([span_a, span_b], axis=1).min(axis=1)
        df["above_cloud"] = df["close"] > cloud_top
        df["bull_cross"] = (conv.shift(1) <= base.shift(1)) & (conv > base)
        df["bear_cross"] = (conv.shift(1) >= base.shift(1)) & (conv < base)
        df["below_cloud"] = df["close"] < cloud_bottom
        df["entry"] = df["above_cloud"] & df["bull_cross"]
        df["exit_sig"] = df["bear_cross"] | df["below_cloud"]
        self._entry_sig = dict(zip(df["timestamp"], df["entry"].fillna(False)))
        self._exit_sig = dict(zip(df["timestamp"], df["exit_sig"].fillna(False)))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts, price = candle["timestamp"], float(candle["close"])
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
            if price >= self._entry * (1 + float(self.config["tp_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry = None
                return
            if self._exit_sig.get(ts, False):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "ichimoku_exit"})
                self._entry = None
                return
        if not self._has_position() and self._entry_sig.get(ts, False):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": "ichimoku_bull"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
