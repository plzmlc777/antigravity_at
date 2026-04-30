"""
S37 Mutated Signal — base 시그널 + filter 조합 자동 생성 strategy.

기존 30개 buy 시그널에 14개 filter를 AND 조건으로 추가:
  - 30 × 14 = 420개 mutations
  - 인간이 manual하게 못 본 변형 자동 발견

filter 종류:
  - 거래량 / 변동성 / 추세 / 시간대 / 이전 봉 패턴 / 외부 데이터
"""
from typing import Any, ClassVar, Dict, Optional

import numpy as np
import pandas as pd

from ..base import KrStrategyBase
from .s32_generic_confirmation import compute_all_30_signals


def compute_filters(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """
    14개 filter — 매수 시그널에 추가 조건으로 AND.
    """
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp"])

    filters: Dict[str, pd.Series] = {}

    # ── 거래량 관련
    filters["f01_vol_above_5avg"] = df["volume"] > df["volume"].rolling(5).mean()
    filters["f02_vol_above_20avg"] = df["volume"] > df["volume"].rolling(20).mean()
    filters["f03_vol_rising"] = df["volume"] > df["volume"].shift(1)

    # ── 캔들 패턴
    filters["f04_bullish_bar"] = df["close"] > df["open"]
    filters["f05_close_above_prev_close"] = df["close"] > df["close"].shift(1)
    filters["f06_higher_low"] = df["low"] > df["low"].shift(1)

    # ── 모멘텀
    filters["f07_close_3up_streak"] = (
        (df["close"] > df["close"].shift(1))
        & (df["close"].shift(1) > df["close"].shift(2))
    )

    # ── VWAP / SMA 관련
    sma20 = df["close"].rolling(20).mean()
    filters["f08_above_sma20"] = df["close"] > sma20
    filters["f09_below_sma20"] = df["close"] < sma20
    sma50 = df["close"].rolling(50).mean()
    filters["f10_above_sma50"] = df["close"] > sma50

    # ── 시간대 (KR 시장 구간)
    df["t_str"] = df["ts"].dt.strftime("%H:%M")
    filters["f11_morning"] = (df["t_str"] >= "09:00") & (df["t_str"] < "11:30")
    filters["f12_afternoon"] = (df["t_str"] >= "13:00") & (df["t_str"] < "15:00")
    filters["f13_first_30min"] = (df["t_str"] >= "09:00") & (df["t_str"] < "09:30")

    # ── ATR 변동성 환경
    high_low = df["high"] - df["low"]
    atr20 = high_low.rolling(20).mean()
    filters["f14_high_atr"] = high_low > atr20

    return {k: v.fillna(False) for k, v in filters.items()}


class S37MutatedSignal(KrStrategyBase):
    """단일 base 시그널 + 단일 filter (AND) — auto-generated mutation."""
    name = "s37_mutated_signal"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "base_signal": "s2_bb",  # 30개 base 중 하나
        "filter": "f04_bullish_bar",  # 14개 filter 중 하나 또는 None
        "use_filter": True,
        "buy_size_pct": 0.7,
        "sl_pct": 0.025,
        "tp_pct": 0.03,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)

        # Base signal
        base_signals = compute_all_30_signals(df, self.config)
        bs = self.config["base_signal"]
        if bs not in base_signals:
            raise ValueError(f"Unknown base signal: {bs}")

        base_buy = base_signals[bs]["buy"].fillna(False)
        base_sell = base_signals[bs]["sell"].fillna(False)

        # Filter
        if self.config.get("use_filter", True):
            filters = compute_filters(df)
            f_name = self.config["filter"]
            if f_name not in filters:
                raise ValueError(f"Unknown filter: {f_name}")
            filter_pass = filters[f_name]
            buy_with_filter = base_buy & filter_pass
        else:
            buy_with_filter = base_buy

        self._buy = dict(zip(df["timestamp"], buy_with_filter.values))
        self._sell = dict(zip(df["timestamp"], base_sell.values))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        if self._has_position() and t >= str(self.config["exit_time"]):
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
            if self._sell.get(ts, False):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "base_sell"})
                self._entry = None
                return
            return

        if self._buy.get(ts, False):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": f"{self.config['base_signal']}+{self.config['filter']}"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
