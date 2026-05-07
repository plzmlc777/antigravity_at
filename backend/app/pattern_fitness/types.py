"""Type definitions for the Fitness tensor.

A `FitnessCell` is the unit of learned knowledge:
    "How profitable, on average, is pattern P on timeframe T when the market
     is in regime R, going in direction D?"

Direction is part of the key (rather than baked into edge sign) so that
neutral signals (e.g., Bollinger Squeeze, Doji) get their own bookkeeping
distinct from directional bull/bear signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class FitnessCellKey:
    pattern: str
    timeframe: str
    cell_id: str       # regime cell e.g. "trending_up|high|normal|positive"
    direction: Literal["bull", "bear", "neutral"]

    def to_str(self) -> str:
        return f"{self.pattern}@{self.timeframe}//{self.cell_id}//{self.direction}"


@dataclass(frozen=True)
class FitnessCell:
    """One row of learned knowledge.

    edge_mean / edge_std / edge_ci_low / edge_ci_high are computed on
    *direction-adjusted* forward returns:
      bull   : raw forward return (close[t+h]/close[t] - 1)
      bear   : negated raw forward return (profit on decline)
      neutral: absolute forward return (volatility expansion proxy)
    So edge_mean > 0 across all directions = "going this way pays off."

    win_rate is the fraction of signals where direction-adjusted return > 0.
    It is direction-aware (a 60% win-rate bear signal predicts down moves
    60% of the time, a 60% win-rate neutral signal had positive vol expansion
    60% of the time).

    p_value is from a 2-sided t-test against H0: edge_mean = 0.
    fdr_significant is whether p_value passes Benjamini-Hochberg at alpha=0.05
    across all cells *with sufficient n* in the same learning batch.
    """
    pattern: str
    timeframe: str
    cell_id: str
    direction: str
    n: int
    edge_mean: float
    edge_std: float
    edge_ci_low: float          # 95% bootstrap or Normal CI low
    edge_ci_high: float
    win_rate: float
    p_value: float
    fdr_significant: bool
    last_updated: datetime

    def key(self) -> FitnessCellKey:
        return FitnessCellKey(
            pattern=self.pattern,
            timeframe=self.timeframe,
            cell_id=self.cell_id,
            direction=self.direction,
        )

    @property
    def is_active(self) -> bool:
        """Cell is usable for composer weighting iff: enough samples AND
        FDR-significant. Cells with n>=30 but failing FDR are observed but
        not trusted (treat as edge=0)."""
        return self.fdr_significant


@dataclass(frozen=True)
class FitnessTensorMeta:
    """Provenance metadata stored alongside the tensor."""
    symbol: str
    learned_at: datetime
    train_window_start: datetime
    train_window_end: datetime
    min_samples: int
    fdr_alpha: float
    n_cells_total: int          # all (pattern, tf, cell, direction) tuples evaluated
    n_cells_with_min_samples: int
    n_cells_active: int         # FDR-significant
    forward_horizon_policy: str  # description of how horizon_bars was used


@dataclass
class FitnessTensor:
    """Container for the full set of learned cells + metadata.

    Stored as joblib for now (parquet is cleaner for analytics; switch when
    cross-tool access becomes valuable per master plan note)."""
    meta: FitnessTensorMeta
    cells: dict[FitnessCellKey, FitnessCell] = field(default_factory=dict)

    def get(self, pattern: str, timeframe: str, cell_id: str, direction: str) -> FitnessCell | None:
        key = FitnessCellKey(pattern, timeframe, cell_id, direction)
        return self.cells.get(key)

    def all_active(self) -> list[FitnessCell]:
        return [c for c in self.cells.values() if c.is_active]

    def __len__(self) -> int:
        return len(self.cells)
