"""
시장 레짐 detector — 최근 N일 데이터로 현재 시장 환경을 카테고리화한다.

출력 차원:
  vol_regime  : LO / MED / HI    (daily return std 기준)
  trend       : REVERT / SIDEWAYS / TREND  (lag-1 자기상관 부호+크기)
  range_phase : NARROW / NORMAL / WIDE  (최근 H-L range 기준)
  liquidity   : LO / MED / HI    (일평균 거래대금 기준)

전략-레짐 매핑은 dynamic_selector에서 수행.
"""
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd


@dataclass
class RegimeProfile:
    vol_regime: str
    trend: str
    range_phase: str
    liquidity: str
    metrics: Dict[str, float]

    def as_dict(self) -> Dict:
        return {
            "vol_regime": self.vol_regime,
            "trend": self.trend,
            "range_phase": self.range_phase,
            "liquidity": self.liquidity,
            "metrics": self.metrics,
        }


def detect_regime(daily_feed: List[Dict], lookback: int = 30) -> RegimeProfile:
    """
    daily_feed: list of dict with keys timestamp, open, high, low, close, volume.
    lookback : 분석 윈도우 (거래일 수).

    Returns RegimeProfile with categorical labels + raw metrics.
    """
    if not daily_feed:
        return RegimeProfile("LO", "SIDEWAYS", "NARROW", "LO", {})

    df = pd.DataFrame(daily_feed[-lookback:])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["open"] = df["open"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["ret"] = df["close"].pct_change() * 100

    metrics: Dict[str, float] = {}

    # 1) 변동성 (daily return std)
    vol_std = float(df["ret"].std() or 0.0)
    metrics["vol_std"] = vol_std
    if vol_std < 2.0:
        vol_regime = "LO"
    elif vol_std < 4.0:
        vol_regime = "MED"
    else:
        vol_regime = "HI"

    # 2) 추세성 (lag-1 자기상관)
    autocorr = 0.0
    if len(df) > 5:
        s = df["ret"].dropna()
        if len(s) > 2:
            autocorr = float(s.autocorr(lag=1) or 0.0)
    metrics["autocorr_lag1"] = autocorr
    if autocorr <= -0.10:
        trend = "REVERT"
    elif autocorr >= 0.15:
        trend = "TREND"
    else:
        trend = "SIDEWAYS"

    # 3) range_phase — 최근 lookback 기간 (H-L)/저점 비율
    range_pct = (df["high"].max() - df["low"].min()) / df["low"].min() * 100
    metrics["range_pct"] = float(range_pct)
    if range_pct < 15:
        range_phase = "NARROW"
    elif range_pct < 35:
        range_phase = "NORMAL"
    else:
        range_phase = "WIDE"

    # 4) liquidity — 일평균 거래대금 (close*volume)
    daily_value_eok = (df["close"] * df["volume"]).mean() / 1e8
    metrics["liquidity_eok"] = float(daily_value_eok)
    if daily_value_eok < 5:
        liquidity = "LO"
    elif daily_value_eok < 50:
        liquidity = "MED"
    else:
        liquidity = "HI"

    return RegimeProfile(
        vol_regime=vol_regime,
        trend=trend,
        range_phase=range_phase,
        liquidity=liquidity,
        metrics=metrics,
    )
