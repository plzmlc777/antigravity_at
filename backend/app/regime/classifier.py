"""
RegimeClassifier — discretize the 4 continuous regime scores into 3-way labels.

Output: a DataFrame with one row per input bar:
    timestamp, trend_score, volatility_score, liquidity_score, momentum_score,
    trend, volatility, liquidity, momentum, cell_id

`cell_id` is "trend|volatility|liquidity|momentum" (string), used as a stable
key in the fitness tensor (Phase 4).

Thresholds are deliberately fixed (not learned) for v1. The continuous scores
are already self-calibrating (z-scored / percentile-ranked) so fixed cutoffs
produce sensible buckets across symbols and time periods.

Edge handling:
  - The first `slow` bars (≈60 by default) have NaN scores. Their labels
    fall back to the neutral middle bucket ("sideways"/"mid"/"normal"/"neutral").
    The cell_id is still computable but flagged via `is_warmup` column.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from .features import (
    compute_liquidity_score,
    compute_momentum_score,
    compute_trend_score,
    compute_volatility_score,
)


TrendLabel = Literal["trending_down", "sideways", "trending_up"]
VolatilityLabel = Literal["low", "mid", "high"]
LiquidityLabel = Literal["thin", "normal", "deep"]
MomentumLabel = Literal["negative", "neutral", "positive"]

TREND_LABELS: tuple[TrendLabel, ...] = ("trending_down", "sideways", "trending_up")
VOLATILITY_LABELS: tuple[VolatilityLabel, ...] = ("low", "mid", "high")
LIQUIDITY_LABELS: tuple[LiquidityLabel, ...] = ("thin", "normal", "deep")
MOMENTUM_LABELS: tuple[MomentumLabel, ...] = ("negative", "neutral", "positive")

REGIME_DIMS: tuple[str, ...] = ("trend", "volatility", "liquidity", "momentum")


@dataclass(frozen=True)
class RegimeVector:
    """The discrete regime at one moment in time."""
    timestamp: datetime
    trend: TrendLabel
    volatility: VolatilityLabel
    liquidity: LiquidityLabel
    momentum: MomentumLabel
    trend_score: float
    volatility_score: float
    liquidity_score: float
    momentum_score: float
    is_warmup: bool = False

    def cell_id(self) -> str:
        return f"{self.trend}|{self.volatility}|{self.liquidity}|{self.momentum}"


def _bucket_3(values: np.ndarray, lo: float, hi: float, labels: Iterable[str]) -> np.ndarray:
    labs = list(labels)
    if len(labs) != 3:
        raise ValueError("labels must be a 3-tuple")
    out = np.where(values < lo, labs[0], np.where(values > hi, labs[2], labs[1]))
    return out


class RegimeClassifier:
    """Compute the regime DataFrame for an OHLCV input.

    Default thresholds are tuned so that a "neutral" market spends roughly
    a third of the time in each bucket per dim, given symmetric noise.
    Symbol-specific calibration can override via constructor.
    """

    def __init__(
        self,
        *,
        # trend cutoffs on score in [-1, 1]
        trend_lo: float = -0.30,
        trend_hi: float = 0.30,
        # volatility cutoffs on percentile rank in [0, 1]
        vol_lo: float = 0.33,
        vol_hi: float = 0.67,
        # liquidity cutoffs on score in [-1, 1]
        liq_lo: float = -0.30,
        liq_hi: float = 0.30,
        # momentum cutoffs on score in [-1, 1]
        mom_lo: float = -0.30,
        mom_hi: float = 0.30,
        # feature parameters (forwarded)
        trend_fast: int = 20,
        trend_slow: int = 60,
        vol_atr_period: int = 14,
        vol_lookback: int = 200,
        liq_short: int = 20,
        liq_long: int = 200,
        mom_short: int = 10,
        mom_mid: int = 50,
        mom_long: int = 200,
    ) -> None:
        self.trend_lo, self.trend_hi = trend_lo, trend_hi
        self.vol_lo, self.vol_hi = vol_lo, vol_hi
        self.liq_lo, self.liq_hi = liq_lo, liq_hi
        self.mom_lo, self.mom_hi = mom_lo, mom_hi
        self.trend_fast, self.trend_slow = trend_fast, trend_slow
        self.vol_atr_period, self.vol_lookback = vol_atr_period, vol_lookback
        self.liq_short, self.liq_long = liq_short, liq_long
        self.mom_short, self.mom_mid, self.mom_long = mom_short, mom_mid, mom_long

    # ─────────────────────────────────────────── public

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return regime DataFrame indexed by df.index."""
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("Input must have DatetimeIndex")
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                raise ValueError(f"Missing column: {col}")

        ts = compute_trend_score(df, self.trend_fast, self.trend_slow)
        vs = compute_volatility_score(df, self.vol_atr_period, self.vol_lookback)
        ls = compute_liquidity_score(df, self.liq_short, self.liq_long)
        ms = compute_momentum_score(
            df, self.mom_short, self.mom_mid, self.mom_long, self.mom_long
        )

        # warmup detection: any score still NaN
        is_warmup = ts.isna() | vs.isna() | ls.isna() | ms.isna()

        # fill NaNs with the neutral midpoint so labels still work
        ts_f = ts.fillna(0.0).to_numpy()
        vs_f = vs.fillna(0.5).to_numpy()
        ls_f = ls.fillna(0.0).to_numpy()
        ms_f = ms.fillna(0.0).to_numpy()

        trend_lab = _bucket_3(ts_f, self.trend_lo, self.trend_hi, TREND_LABELS)
        vol_lab = _bucket_3(vs_f, self.vol_lo, self.vol_hi, VOLATILITY_LABELS)
        liq_lab = _bucket_3(ls_f, self.liq_lo, self.liq_hi, LIQUIDITY_LABELS)
        mom_lab = _bucket_3(ms_f, self.mom_lo, self.mom_hi, MOMENTUM_LABELS)

        out = pd.DataFrame(
            {
                "trend_score": ts.values,
                "volatility_score": vs.values,
                "liquidity_score": ls.values,
                "momentum_score": ms.values,
                "trend": trend_lab,
                "volatility": vol_lab,
                "liquidity": liq_lab,
                "momentum": mom_lab,
                "is_warmup": is_warmup.values,
            },
            index=df.index,
        )
        out["cell_id"] = (
            out["trend"].astype(str) + "|"
            + out["volatility"].astype(str) + "|"
            + out["liquidity"].astype(str) + "|"
            + out["momentum"].astype(str)
        )
        return out

    def classify_at(self, df: pd.DataFrame, ts: pd.Timestamp) -> RegimeVector:
        """Convenience: classify and return RegimeVector for one timestamp."""
        rdf = self.classify(df)
        if ts not in rdf.index:
            raise KeyError(f"Timestamp {ts} not in input index")
        row = rdf.loc[ts]
        return RegimeVector(
            timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            trend=row["trend"],
            volatility=row["volatility"],
            liquidity=row["liquidity"],
            momentum=row["momentum"],
            trend_score=float(row["trend_score"]) if not pd.isna(row["trend_score"]) else 0.0,
            volatility_score=float(row["volatility_score"]) if not pd.isna(row["volatility_score"]) else 0.5,
            liquidity_score=float(row["liquidity_score"]) if not pd.isna(row["liquidity_score"]) else 0.0,
            momentum_score=float(row["momentum_score"]) if not pd.isna(row["momentum_score"]) else 0.0,
            is_warmup=bool(row["is_warmup"]),
        )

    @staticmethod
    def all_possible_cells() -> list[str]:
        """Enumerate all 81 cell_ids (most will be sparse in practice)."""
        return [
            f"{t}|{v}|{l}|{m}"
            for t in TREND_LABELS
            for v in VOLATILITY_LABELS
            for l in LIQUIDITY_LABELS
            for m in MOMENTUM_LABELS
        ]

    @classmethod
    def for_daily(cls) -> "RegimeClassifier":
        """Preset for 1d/4h timeframes — shorter rolling windows so 1 year
        of bars produces useful (non-warmup) labels."""
        return cls(
            trend_fast=10, trend_slow=30,
            vol_atr_period=10, vol_lookback=60,
            liq_short=10, liq_long=60,
            mom_short=5, mom_mid=20, mom_long=60,
        )

    @classmethod
    def for_intraday(cls) -> "RegimeClassifier":
        """Preset for 1m/5m/15m timeframes (matches default constructor)."""
        return cls()
