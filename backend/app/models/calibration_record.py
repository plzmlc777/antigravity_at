"""Calibration Record — tracks prediction accuracy across stage transitions.

SISDS Phase 7 (CIO-20260410-001 / CIO-017).

Every time a strategy moves from one stage to the next (sandbox → paper,
paper → live), the system records what was PREDICTED (sandbox backtest)
versus what ACTUALLY happened (paper performance). The gap between these
is the calibration error — the key metric for self-improvement.

If calibration error decreases over time, the system is learning.
If it stays flat or increases, something is wrong.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String

from ..db.base import Base


class CalibrationRecord(Base):
    __tablename__ = "calibration_records"

    id = Column(Integer, primary_key=True, index=True)

    # Which strategy and which transition
    strategy_id = Column(String, nullable=False, index=True)
    transition = Column(String, nullable=False, index=True)
    # 'sandbox_to_paper' | 'paper_to_live' | 'live_degradation'

    # When measured
    measured_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Predictions (from prior stage)
    predicted = Column(JSON, nullable=False)
    # {monthly_compound, mdd, sharpe, total_cycles, ...}

    # Actual (from current stage)
    actual = Column(JSON, nullable=False)
    # same keys as predicted

    # Gap analysis
    gap = Column(JSON, nullable=False)
    # per-metric: {monthly_compound: {predicted, actual, absolute_gap, relative_gap}, ...}

    # Overall calibration error score (0-1, lower is better)
    calibration_error = Column(Float, nullable=False)

    # Duration of the stage that produced the 'actual' values
    stage_duration_days = Column(Integer, nullable=True)

    # Meta-learner analysis (filled later during weekly review)
    detected_causes = Column(JSON, nullable=True)
    # [{cause: "slippage", contribution: 0.3}, {cause: "regime_change", contribution: 0.5}]

    resolution = Column(String, nullable=True)
    # 'sandbox_baseline_updated' | 'accepted' | 'unexplained' | 'pending_review'


Index(
    "ix_cal_strategy_time",
    CalibrationRecord.strategy_id,
    CalibrationRecord.measured_at.desc(),
)
Index(
    "ix_cal_transition",
    CalibrationRecord.transition,
    CalibrationRecord.measured_at.desc(),
)
