"""
S33 Foreign Net Buy Signal — 외국인/기관 일별 순매수 데이터 기반 매매.

데이터: backend/runs/kr_paper/external/<symbol>_foreign.jsonl
  (키움 ka10059로 fetch한 일별 외국인/기관 순매수)

전략:
  - foreign_5day_cum > threshold → 다음 날 시초 매수
  - foreign + institutional 둘 다 양수 → 큰손 합세 → 매수
  - foreign_z (30d 기준) > +1.5 → 비정상 매수 추종

청산: EOD (15:25) 또는 SL/TP

S33A: 외국인 단독 — foreign_5day_cum 기반
S33B: 외국인+기관 합세 (둘 다 양수)
S33C: 외국인 z-score (30d) — outlier
"""
import json
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

import numpy as np
import pandas as pd

from ..base import KrStrategyBase


def load_foreign_data(symbol: str) -> pd.DataFrame:
    """JSONL → DataFrame indexed by date (str YYYY-MM-DD)."""
    path = (
        Path(__file__).resolve().parents[3]
        / "runs" / "kr_paper" / "external"
        / f"{symbol}_foreign.jsonl"
    )
    if not path.exists():
        raise FileNotFoundError(f"foreign data not found: {path}")
    rows = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    df = pd.DataFrame(rows)
    df = df.sort_values("dt").reset_index(drop=True)
    return df


def compute_foreign_indicators(df: pd.DataFrame, lookback_days: int = 30) -> pd.DataFrame:
    """일별 외국인 데이터에 indicator 추가."""
    df = df.copy()
    # 외국인 N일 누적 순매수 (어제까지 — forward-leak 방지)
    df["frgnr_5d_cum"] = df["frgnr"].rolling(5).sum().shift(1).fillna(0)
    df["frgnr_10d_cum"] = df["frgnr"].rolling(10).sum().shift(1).fillna(0)
    # Z-score (어제까지 30일)
    fr_mean = df["frgnr"].rolling(lookback_days).mean().shift(1)
    fr_std = df["frgnr"].rolling(lookback_days).std().shift(1)
    df["frgnr_z"] = ((df["frgnr"].shift(1) - fr_mean) / fr_std.replace(0, np.nan)).fillna(0)
    # 외국인 + 기관 합 (어제)
    df["frgnr_orgn_sum_yesterday"] = (df["frgnr"] + df["orgn"]).shift(1).fillna(0)
    # 어제 외국인 양수
    df["frgnr_yesterday_pos"] = (df["frgnr"].shift(1) > 0).astype(int)
    df["orgn_yesterday_pos"] = (df["orgn"].shift(1) > 0).astype(int)
    return df


class _S33Base(KrStrategyBase):
    """외국인 시그널 기반 strategy 공통 base."""
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "buy_size_pct": 0.7,
        "sl_pct": 0.025,
        "tp_pct": 0.04,
        "exit_time": "15:25",
        "entry_time_first_bar": "09:05",  # 시초 다음 봉 매수 (09:00은 단일가)
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df["day"] = df["ts"].dt.date.astype(str)

        # foreign data 로드 + indicator
        fdf = load_foreign_data(self.symbol)
        fdf = compute_foreign_indicators(fdf)
        # day → indicator dict
        self._foreign_by_day: Dict[str, Dict[str, float]] = {
            r["dt"]: {
                "frgnr": r["frgnr"], "orgn": r["orgn"],
                "frgnr_5d_cum": r["frgnr_5d_cum"], "frgnr_10d_cum": r["frgnr_10d_cum"],
                "frgnr_z": r["frgnr_z"],
                "frgnr_orgn_sum_yesterday": r["frgnr_orgn_sum_yesterday"],
                "frgnr_yesterday_pos": r["frgnr_yesterday_pos"],
                "orgn_yesterday_pos": r["orgn_yesterday_pos"],
            }
            for _, r in fdf.iterrows()
        }

        # ts → day mapping
        self._ts_to_day = dict(zip(df["timestamp"], df["day"]))
        self._entry: Optional[float] = None

    def _entry_signal(self, day: str) -> bool:
        """Override per subclass."""
        raise NotImplementedError

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        day = self._ts_to_day.get(ts, "")
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        # EOD 청산
        if self._has_position() and t >= str(self.config["exit_time"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            return

        # SL/TP
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

        # 진입 — 09:05 시점에 외국인 시그널 체크
        if t != str(self.config["entry_time_first_bar"]):
            return
        if not day or day not in self._foreign_by_day:
            return
        if not self._entry_signal(day):
            return

        from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
        cash = self.ctx.cash * float(self.config["buy_size_pct"])
        qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
        if qty > 0:
            tr = self.ctx.buy(self.symbol, qty, price=price,
                              metadata={"reason": self.name})
            if tr and tr.get("type") == "buy":
                self._entry = float(tr.get("price", price))


class S33A_ForeignCum(_S33Base):
    """외국인 5일 누적 양수 시 매수."""
    name = "s33a_foreign_5d_cum"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **_S33Base.DEFAULT_PARAMS,
        "min_5d_cum": 0,  # 외국인 5일 누적 > 0 (양수) → 매수
    }

    def _entry_signal(self, day: str) -> bool:
        info = self._foreign_by_day.get(day, {})
        return info.get("frgnr_5d_cum", 0) > float(self.config["min_5d_cum"])


class S33B_BothPositive(_S33Base):
    """외국인 + 기관 어제 둘 다 양수 시 매수."""
    name = "s33b_foreign_orgn_both_pos"

    def _entry_signal(self, day: str) -> bool:
        info = self._foreign_by_day.get(day, {})
        return info.get("frgnr_yesterday_pos", 0) == 1 and info.get("orgn_yesterday_pos", 0) == 1


class S33C_ForeignZScore(_S33Base):
    """외국인 어제 z-score > threshold 시 매수 (비정상 큰 매수)."""
    name = "s33c_foreign_z_score"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **_S33Base.DEFAULT_PARAMS,
        "min_z": 1.0,  # z > 1 sigma
    }

    def _entry_signal(self, day: str) -> bool:
        info = self._foreign_by_day.get(day, {})
        return info.get("frgnr_z", 0) > float(self.config["min_z"])


class S33D_BigBuyersSum(_S33Base):
    """외국인 + 기관 어제 합산 순매수 > threshold 시 매수."""
    name = "s33d_big_buyers_sum"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **_S33Base.DEFAULT_PARAMS,
        "min_sum": 1000,  # 단주 — 합산 1000주 이상 매수 시
    }

    def _entry_signal(self, day: str) -> bool:
        info = self._foreign_by_day.get(day, {})
        return info.get("frgnr_orgn_sum_yesterday", 0) > float(self.config["min_sum"])
