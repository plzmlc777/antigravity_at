"""
S36 Short Selling Signal — 공매도 데이터 기반 매매.

데이터: backend/runs/kr_paper/external/<symbol>_short.jsonl (ka10014로 fetch).

가설:
  - 공매도 비중 낮음 → 약세 압력 적음 → 매수
  - 공매도 비중 급감 (어제 vs 5일 평균) → 압력 해소 → 매수
  - 공매도 비중 매우 높음 → short squeeze 가능 → 매수 (contrarian)
"""
import json
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

import numpy as np
import pandas as pd

from ..base import KrStrategyBase


def load_short_data(symbol: str) -> pd.DataFrame:
    path = (
        Path(__file__).resolve().parents[3]
        / "runs" / "kr_paper" / "external"
        / f"{symbol}_short.jsonl"
    )
    if not path.exists():
        raise FileNotFoundError(f"short data not found: {path}")
    rows = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    df = pd.DataFrame(rows)
    df = df.sort_values("dt").reset_index(drop=True)
    return df


def compute_short_indicators(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    df = df.copy()
    # 어제까지 5일 평균 매매비중
    df["wt_5d_avg_lag"] = df["trde_wght"].rolling(5).mean().shift(1).fillna(0)
    df["wt_20d_avg_lag"] = df["trde_wght"].rolling(20).mean().shift(1).fillna(0)
    # 어제 비중 vs 5일 평균 비교
    df["wt_yesterday"] = df["trde_wght"].shift(1).fillna(0)
    df["wt_drop"] = df["wt_5d_avg_lag"] - df["wt_yesterday"]  # 양수 = 어제 비중 작아짐
    # Z-score (어제 vs 20일)
    wt_mean = df["trde_wght"].rolling(lookback).mean().shift(1)
    wt_std = df["trde_wght"].rolling(lookback).std().shift(1)
    df["wt_z"] = ((df["trde_wght"].shift(1) - wt_mean) / wt_std.replace(0, np.nan)).fillna(0)
    return df


class _S36Base(KrStrategyBase):
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "buy_size_pct": 0.7,
        "sl_pct": 0.025,
        "tp_pct": 0.04,
        "exit_time": "15:25",
        "entry_time_first_bar": "09:05",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df["day"] = df["ts"].dt.date.astype(str)
        # short data
        sdf = compute_short_indicators(load_short_data(self.symbol))
        self._short_by_day: Dict[str, Dict[str, float]] = {
            r["dt"]: {
                "wt_yesterday": r["wt_yesterday"],
                "wt_5d_avg_lag": r["wt_5d_avg_lag"],
                "wt_20d_avg_lag": r["wt_20d_avg_lag"],
                "wt_drop": r["wt_drop"],
                "wt_z": r["wt_z"],
            }
            for _, r in sdf.iterrows()
        }
        self._ts_to_day = dict(zip(df["timestamp"], df["day"]))
        self._entry: Optional[float] = None

    def _entry_signal(self, day: str) -> bool:
        raise NotImplementedError

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        day = self._ts_to_day.get(ts, "")
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
            return

        if t != str(self.config["entry_time_first_bar"]):
            return
        if not day or day not in self._short_by_day:
            return
        if not self._entry_signal(day):
            return

        from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
        cash = self.ctx.cash * float(self.config["buy_size_pct"])
        qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
        if qty > 0:
            tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": self.name})
            if tr and tr.get("type") == "buy":
                self._entry = float(tr.get("price", price))


class S36A_LowShortWeight(_S36Base):
    """공매도 비중 어제 < threshold → 매수 (약세 압력 적음)."""
    name = "s36a_low_short_weight"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **_S36Base.DEFAULT_PARAMS,
        "max_yesterday_weight": 2.0,  # 어제 매매비중 2% 이하
    }
    def _entry_signal(self, day: str) -> bool:
        info = self._short_by_day.get(day, {})
        return info.get("wt_yesterday", 100) < float(self.config["max_yesterday_weight"])


class S36B_ShortDrop(_S36Base):
    """공매도 비중 5일 평균 대비 어제 N%p 이상 떨어짐 → 매수."""
    name = "s36b_short_drop"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **_S36Base.DEFAULT_PARAMS,
        "min_drop_pp": 1.0,  # 5일 평균 대비 1%p 이상 감소
    }
    def _entry_signal(self, day: str) -> bool:
        info = self._short_by_day.get(day, {})
        return info.get("wt_drop", 0) > float(self.config["min_drop_pp"])


class S36C_ShortSqueeze(_S36Base):
    """공매도 비중 z-score > threshold → contrarian 매수 (squeeze 가설)."""
    name = "s36c_short_squeeze"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **_S36Base.DEFAULT_PARAMS,
        "min_z": 1.5,
    }
    def _entry_signal(self, day: str) -> bool:
        info = self._short_by_day.get(day, {})
        return info.get("wt_z", 0) > float(self.config["min_z"])


class S36D_LowShortZ(_S36Base):
    """공매도 비중 z-score < threshold → 매수 (비정상 약한 매도 압력)."""
    name = "s36d_low_short_z"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **_S36Base.DEFAULT_PARAMS,
        "max_z": -0.5,
    }
    def _entry_signal(self, day: str) -> bool:
        info = self._short_by_day.get(day, {})
        return info.get("wt_z", 0) < float(self.config["max_z"])
