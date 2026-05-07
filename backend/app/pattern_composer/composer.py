"""DynamicPatternComposer — combines active signals + regime + fitness tensor
into a single ensemble decision per evaluation moment.

Core idea:
    score = sum( signal.confidence * fitness_cell.edge_mean * direction_sign )
            for each active signal whose fitness cell is FDR-significant.

Signals whose fitness cell is missing or not FDR-active contribute 0 (we
explicitly distrust un-validated patterns rather than treating them as edge=0
neutral; this is what stops the system from acting on noise).

Multi-TF agreement bonus: if a directional consensus spans >=2 TFs, the
absolute score is amplified (default +20%). Mixed directional signals shrink
the score by the same logic — they cancel naturally in the sum.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import numpy as np
import pandas as pd

from app.pattern_fitness.types import FitnessTensor

from .types import ComposerDecision, DecisionAction

logger = logging.getLogger(__name__)


@dataclass
class ComposerConfig:
    entry_threshold: float = 0.005      # |ensemble| >= this → take a position
    exit_threshold: float = 0.002       # while in position, opposite ensemble >= this → exit
    multi_tf_bonus: float = 0.20         # bonus when >=2 TFs agree on dominant direction
    min_trusted_signals: int = 1         # minimum FDR-active signals required
    long_only: bool = True               # KR equities default
    sl_pct: float = 0.015                # 1.5% stop-loss
    tp_pct: float = 0.030                # 3.0% take-profit (2:1 R:R)
    time_stop_bars: int = 60             # exit after N bars in position (1m frame)
    cooldown_bars: int = 5               # bars to wait after an exit before re-entry


class DynamicPatternComposer:
    """Stateless composer: given current state, returns a Decision.

    The composer is intentionally stateless — Backtester owns position state.
    """

    def __init__(
        self,
        fitness: FitnessTensor,
        config: ComposerConfig | None = None,
    ) -> None:
        self.fitness = fitness
        self.config = config or ComposerConfig()

    def compose(
        self,
        *,
        timestamp: datetime,
        active_signals: pd.DataFrame,
    ) -> ComposerDecision:
        """Build the ensemble decision at `timestamp`.

        active_signals: DataFrame with columns matching scanner output
        (pattern_name, timeframe, direction, confidence, ...) PLUS one extra
        column we expect Backtester to attach:
            cell_id : the regime cell at SIGNAL EMISSION time (consistent with
                       how fitness was learned).

        Empty active_signals → action="hold".
        """
        n_active = len(active_signals)
        if n_active == 0:
            return ComposerDecision(
                timestamp=timestamp,
                action="hold",
                ensemble_score=0.0,
                bull_weight=0.0,
                bear_weight=0.0,
                neutral_weight=0.0,
                n_active_signals=0,
                n_trusted_signals=0,
                note="no signals",
            )

        bull = 0.0
        bear = 0.0
        neutral = 0.0
        trusted = 0
        contributing: list[str] = []
        bull_tfs: set[str] = set()
        bear_tfs: set[str] = set()

        # collect target/stop hints from highest-edge directional signal
        best_dir_weight = 0.0
        best_target: float | None = None
        best_stop: float | None = None

        for _, row in active_signals.iterrows():
            cell_id = row.get("cell_id")
            if pd.isna(cell_id) or cell_id is None:
                continue
            cell = self.fitness.get(
                pattern=row["pattern_name"],
                timeframe=row["timeframe"],
                cell_id=str(cell_id),
                direction=row["direction"],
            )
            if cell is None or not cell.fdr_significant:
                continue
            # Trust only positive-edge cells (negative-edge cells indicate the
            # named direction is *wrong* in this regime — we ignore them rather
            # than flip; flipping is the v2 contra-signal feature).
            if cell.edge_mean <= 0:
                continue

            weight = float(row["confidence"]) * float(cell.edge_mean)
            trusted += 1
            contributing.append(f"{row['pattern_name']}@{row['timeframe']}")

            d = row["direction"]
            if d == "bull":
                bull += weight
                bull_tfs.add(row["timeframe"])
                if weight > best_dir_weight:
                    best_dir_weight = weight
                    best_target = row.get("suggested_target")
                    best_stop = row.get("suggested_stop")
            elif d == "bear":
                bear += weight
                bear_tfs.add(row["timeframe"])
                if weight > best_dir_weight:
                    best_dir_weight = weight
                    best_target = row.get("suggested_target")
                    best_stop = row.get("suggested_stop")
            elif d == "neutral":
                neutral += weight

        # multi-TF agreement bonus: applied to the dominant side only
        if len(bull_tfs) >= 2:
            bull *= 1.0 + self.config.multi_tf_bonus
        if len(bear_tfs) >= 2:
            bear *= 1.0 + self.config.multi_tf_bonus

        ensemble = bull - bear
        action = self._decide_action(ensemble, trusted)

        return ComposerDecision(
            timestamp=timestamp,
            action=action,
            ensemble_score=ensemble,
            bull_weight=bull,
            bear_weight=bear,
            neutral_weight=neutral,
            n_active_signals=n_active,
            n_trusted_signals=trusted,
            contributing_patterns=tuple(contributing),
            suggested_target=float(best_target) if best_target is not None and not pd.isna(best_target) else None,
            suggested_stop=float(best_stop) if best_stop is not None and not pd.isna(best_stop) else None,
            note=f"bull_tfs={len(bull_tfs)} bear_tfs={len(bear_tfs)}",
        )

    def _decide_action(self, ensemble: float, trusted: int) -> DecisionAction:
        if trusted < self.config.min_trusted_signals:
            return "hold"
        if ensemble >= self.config.entry_threshold:
            return "enter_long"
        if not self.config.long_only and ensemble <= -self.config.entry_threshold:
            return "enter_short"
        return "hold"

    def should_exit(self, ensemble: float, side: str) -> bool:
        """Called when in a position to decide if opposite ensemble warrants exit."""
        if side == "long" and -ensemble >= self.config.exit_threshold:
            return True
        if side == "short" and ensemble >= self.config.exit_threshold:
            return True
        return False
