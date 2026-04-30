"""
S31: Multi-Strategy Confirmation Signal.

Robust 5개 전략 (S2/S5/S16/S18/S25)의 매수 시그널을 사전 계산해두고,
매 candle 시점에 'min_confirmations' 개수 이상이 동시에 매수 신호를 내면 진입.

청산:
  - 동시에 'min_exit_confirmations' 개수가 매도 신호를 내면 청산
  - 또는 EOD (15:25)
  - 또는 SL (entry * (1 - sl_pct))
  - 또는 TP (entry * (1 + tp_pct))

가설:
  - 단일 시그널은 false positive 많음
  - 2-3개 동시 confirmation은 더 강한 진입
  - Trade 수 감소 → friction 절감
  - Win rate 향상 기대
"""
from typing import Any, ClassVar, Dict, Optional

import pandas as pd

from ..base import KrStrategyBase
from ..indicators import (
    rsi, bollinger, vwap_intraday,
    stochastic, zscore as zscore_ind,
)


class S31RobustConfirmation(KrStrategyBase):
    name = "s31_robust_confirmation"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        # confirmation 임계
        "min_buy_confirmations": 2,       # 5개 중 N개 이상 동시 신호
        "min_sell_confirmations": 1,      # 청산은 더 보수적

        # S2 BB params (sweep best)
        "bb_period": 25, "bb_std": 2.0,
        # S5 VWAP params (optimized)
        "vwap_lower_band_pct": 0.005,
        # S16 Stochastic params (optimized)
        "stoch_k_period": 9, "stoch_oversold": 20, "stoch_overbought": 75,
        # S18 Z-score params
        "z_period": 30, "z_entry": -2.0, "z_exit": 0.0,
        # S25 Lunch Fade
        "lunch_start": "12:00", "lunch_end": "13:00",
        "lunch_entry_window_start": "12:30", "lunch_entry_window_end": "13:30",

        # 공통
        "buy_size_pct": 0.7,
        "sl_pct": 0.02,
        "tp_pct": 0.03,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])

        # ── S2 BB
        upper, mid, lower = bollinger(
            df["close"], int(self.config["bb_period"]), float(self.config["bb_std"])
        )
        df["s2_buy"] = df["close"] < lower
        df["s2_sell"] = df["close"] > mid

        # ── S5 VWAP
        df["day_id"] = df["ts"].dt.date.astype(str)
        vwap = vwap_intraday(df["high"], df["low"], df["close"], df["volume"], df["day_id"])
        lband = vwap * (1 - float(self.config["vwap_lower_band_pct"]))
        df["s5_buy"] = df["close"] < lband
        df["s5_sell"] = df["close"] >= vwap

        # ── S16 Stochastic
        k, _ = stochastic(
            df["high"], df["low"], df["close"],
            int(self.config["stoch_k_period"]), 3,
        )
        df["s16_buy"] = k < float(self.config["stoch_oversold"])
        df["s16_sell"] = k > float(self.config["stoch_overbought"])

        # ── S18 Z-score
        z = zscore_ind(df["close"], int(self.config["z_period"]))
        df["s18_buy"] = z < float(self.config["z_entry"])
        df["s18_sell"] = z > float(self.config["z_exit"])

        # ── S25 Lunch Fade — 점심대 low 터치
        ls, le = str(self.config["lunch_start"]), str(self.config["lunch_end"])
        es, ee = str(self.config["lunch_entry_window_start"]), str(self.config["lunch_entry_window_end"])
        df["t_str"] = df["ts"].dt.strftime("%H:%M")
        # day별 lunch low
        in_lunch = (df["t_str"] >= ls) & (df["t_str"] < le)
        lunch_low = df[in_lunch].groupby("day_id")["low"].min()
        df["lunch_low"] = df["day_id"].map(lunch_low)
        in_entry_window = (df["t_str"] >= es) & (df["t_str"] < ee)
        df["s25_buy"] = (
            in_entry_window
            & df["lunch_low"].notna()
            & (df["close"] <= df["lunch_low"] * 1.001)
        )
        df["s25_sell"] = False  # lunch fade는 청산 시그널 별개

        # ── confirmation count
        buy_cols = ["s2_buy", "s5_buy", "s16_buy", "s18_buy", "s25_buy"]
        sell_cols = ["s2_sell", "s5_sell", "s16_sell", "s18_sell", "s25_sell"]
        df["buy_count"] = df[buy_cols].sum(axis=1)
        df["sell_count"] = df[sell_cols].sum(axis=1)

        self._buy_count = dict(zip(df["timestamp"], df["buy_count"]))
        self._sell_count = dict(zip(df["timestamp"], df["sell_count"]))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        bc = self._buy_count.get(ts, 0)
        sc = self._sell_count.get(ts, 0)

        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        # EOD 청산
        if self._has_position() and t >= str(self.config["exit_time"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            return

        # 보유 중 — SL/TP/sell-confirmation
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
            if sc >= int(self.config["min_sell_confirmations"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(
                    self.symbol, qty, price=price,
                    metadata={"reason": f"sell_conf={sc}"},
                )
                self._entry = None
                return
            return

        # 진입 — buy confirmation 충분 시
        if bc >= int(self.config["min_buy_confirmations"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": f"buy_conf={bc}"},
                )
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
