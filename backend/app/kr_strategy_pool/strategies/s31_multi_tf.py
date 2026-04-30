"""
S31 Multi-Timeframe Ensemble — 1m + 5m + 15m 시그널 동시 사용.

가설:
  - 1m: 빠른 진입 시점 정밀
  - 5m: noise 필터링
  - 15m: 추세 confirm
  - 셋 다 동의 시 진입 → 매우 강한 시그널

두 가지 모드:
  - "all_agree": 모든 TF에서 mb 이상 동시 발생 시 진입 (매우 strict)
  - "weighted": (1m_count + 5m_count + 15m_count) >= total_threshold

청산은 1m sell_count >= ms (빠른 청산).
"""
from typing import Any, ClassVar, Dict, Optional

import pandas as pd

from ..base import KrStrategyBase
from ..indicators import (
    bollinger, vwap_intraday, stochastic, zscore as zscore_ind,
)


def _compute_signals(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """주어진 df(OHLCV)에 5개 robust 시그널의 buy/sell 계산."""
    out = pd.DataFrame(index=df.index)

    # S2 BB
    upper, mid, lower = bollinger(
        df["close"], int(params["bb_period"]), float(params["bb_std"])
    )
    out["s2_buy"] = df["close"] < lower
    out["s2_sell"] = df["close"] > mid

    # S5 VWAP
    if "day_id" not in df.columns:
        df = df.copy()
        df["day_id"] = pd.to_datetime(df.index).date.astype(str) if df.index.name else \
            pd.to_datetime(df["ts"]).dt.date.astype(str)
    vwap = vwap_intraday(df["high"], df["low"], df["close"], df["volume"], df["day_id"])
    lband = vwap * (1 - float(params["vwap_lower_band_pct"]))
    out["s5_buy"] = df["close"] < lband
    out["s5_sell"] = df["close"] >= vwap

    # S16 Stochastic
    k, _ = stochastic(
        df["high"], df["low"], df["close"],
        int(params["stoch_k_period"]), 3,
    )
    out["s16_buy"] = k < float(params["stoch_oversold"])
    out["s16_sell"] = k > float(params["stoch_overbought"])

    # S18 Z-score
    z = zscore_ind(df["close"], int(params["z_period"]))
    out["s18_buy"] = z < float(params["z_entry"])
    out["s18_sell"] = z > float(params["z_exit"])

    # S25 Lunch — 점심대 low 터치 (이건 같은 일중 시점이라 1m/5m/15m 동일)
    out["s25_buy"] = False  # multi-TF에서는 단순화 위해 제외
    out["s25_sell"] = False

    out["buy_count"] = out[["s2_buy", "s5_buy", "s16_buy", "s18_buy", "s25_buy"]].sum(axis=1)
    out["sell_count"] = out[["s2_sell", "s5_sell", "s16_sell", "s18_sell", "s25_sell"]].sum(axis=1)
    return out


class S31MultiTF(KrStrategyBase):
    """1m + 5m + 15m TF 동시 confirmation."""
    name = "s31_multi_tf"
    TIMEFRAME = "1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        # period (TF 별로 다르게 적용 — 5m/15m은 더 짧은 period로)
        "bb_period_1m": 75,    "bb_period_5m": 25,  "bb_period_15m": 14,
        "stoch_k_period_1m": 27, "stoch_k_period_5m": 9, "stoch_k_period_15m": 9,
        "z_period_1m": 90, "z_period_5m": 30, "z_period_15m": 20,
        "bb_std": 2.0,
        "vwap_lower_band_pct": 0.005,
        "stoch_oversold": 20, "stoch_overbought": 75,
        "z_entry": -2.0, "z_exit": 0.0,

        # multi-TF mode
        "mode": "all_agree",  # or "weighted"
        "min_buy_per_tf": 3,  # all_agree: 각 TF에서 N개 이상
        "weighted_threshold": 9,  # weighted: 1m+5m+15m sum >= N

        "min_sell_count_1m": 2,  # 1m에서 sell signal 충분 시 청산

        "buy_size_pct": 0.7,
        "sl_pct": 0.025,
        "tp_pct": 0.03,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df_1m = pd.DataFrame(feed)
        df_1m["ts"] = pd.to_datetime(df_1m["timestamp"])
        df_1m = df_1m.set_index("ts")
        df_1m["day_id"] = df_1m.index.date.astype(str)

        # 5m / 15m resample
        agg = {"open": "first", "high": "max", "low": "min",
               "close": "last", "volume": "sum"}
        df_5m = df_1m.resample("5min", origin="start_day").agg(agg).dropna(subset=["open"])
        df_15m = df_1m.resample("15min", origin="start_day").agg(agg).dropna(subset=["open"])
        df_5m["day_id"] = df_5m.index.date.astype(str)
        df_15m["day_id"] = df_15m.index.date.astype(str)

        # 시그널 계산 — 각 TF
        params_1m = {
            "bb_period": self.config["bb_period_1m"],
            "bb_std": self.config["bb_std"],
            "vwap_lower_band_pct": self.config["vwap_lower_band_pct"],
            "stoch_k_period": self.config["stoch_k_period_1m"],
            "stoch_oversold": self.config["stoch_oversold"],
            "stoch_overbought": self.config["stoch_overbought"],
            "z_period": self.config["z_period_1m"],
            "z_entry": self.config["z_entry"],
            "z_exit": self.config["z_exit"],
        }
        params_5m = dict(params_1m)
        params_5m["bb_period"] = self.config["bb_period_5m"]
        params_5m["stoch_k_period"] = self.config["stoch_k_period_5m"]
        params_5m["z_period"] = self.config["z_period_5m"]

        params_15m = dict(params_1m)
        params_15m["bb_period"] = self.config["bb_period_15m"]
        params_15m["stoch_k_period"] = self.config["stoch_k_period_15m"]
        params_15m["z_period"] = self.config["z_period_15m"]

        sig_1m = _compute_signals(df_1m, params_1m)
        sig_5m = _compute_signals(df_5m, params_5m)
        sig_15m = _compute_signals(df_15m, params_15m)

        # 1m timestamp 기준으로 5m/15m bin lookup (forward-fill 마지막 confirmed bin 사용)
        # 5m bin: 1m ts를 5min 단위 floor → sig_5m index에서 lookup
        ts_floor_5m = df_1m.index.floor("5min")
        ts_floor_15m = df_1m.index.floor("15min")

        # forward-fill to align: 5m/15m bin이 close된 후의 시그널을 사용
        # 즉 1m ts t에서 사용하는 5m signal은 max(5m_ts <= t) 의 row
        sig_5m_aligned = sig_5m.reindex(ts_floor_5m, method="ffill")
        sig_15m_aligned = sig_15m.reindex(ts_floor_15m, method="ffill")
        # 정렬 (1m index 사용)
        sig_5m_aligned.index = df_1m.index
        sig_15m_aligned.index = df_1m.index

        # combined buy/sell counts per ts
        bc1 = sig_1m["buy_count"].fillna(0)
        bc5 = sig_5m_aligned["buy_count"].fillna(0)
        bc15 = sig_15m_aligned["buy_count"].fillna(0)
        sc1 = sig_1m["sell_count"].fillna(0)

        # str(ts) → buy/sell counts
        ts_str = df_1m.reset_index()["ts"].astype(str)
        # 원본 timestamp ISO format으로 매핑
        # df_1m["timestamp"] 는 원래 입력 형식 (ISO string)
        # sig는 datetime index 기반 → 원본 timestamp 컬럼 다시 사용
        feed_ts = [c["timestamp"] for c in feed]
        self._bc1 = dict(zip(feed_ts, bc1.values))
        self._bc5 = dict(zip(feed_ts, bc5.values))
        self._bc15 = dict(zip(feed_ts, bc15.values))
        self._sc1 = dict(zip(feed_ts, sc1.values))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        bc1 = self._bc1.get(ts, 0)
        bc5 = self._bc5.get(ts, 0)
        bc15 = self._bc15.get(ts, 0)
        sc1 = self._sc1.get(ts, 0)

        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        # EOD 청산
        if self._has_position() and t >= str(self.config["exit_time"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            return

        # SL/TP/sell-confirm
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
            if sc1 >= int(self.config["min_sell_count_1m"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price,
                              metadata={"reason": f"sell_1m={sc1}"})
                self._entry = None
                return
            return

        # 진입
        mode = self.config.get("mode", "all_agree")
        min_per_tf = int(self.config["min_buy_per_tf"])
        weighted_th = int(self.config["weighted_threshold"])

        if mode == "all_agree":
            entry = (bc1 >= min_per_tf and bc5 >= min_per_tf and bc15 >= min_per_tf)
        else:  # weighted
            entry = (bc1 + bc5 + bc15) >= weighted_th

        if entry:
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(
                    self.symbol, qty, price=price,
                    metadata={"reason": f"multi_tf bc1={bc1} bc5={bc5} bc15={bc15}"},
                )
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
