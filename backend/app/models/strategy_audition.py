"""Strategy Audition — AI 자율 전략 발굴 파이프라인 상태 추적.

CIO-20260408-015 (SAS: Strategy Audition System).
하루 1개 전략 생성 → 주 1회 오디션 경쟁 → 1개 우승자 선발의 모든 상태 추적.

관련: CIO-008 (gap_signals 큐), CIO-014 (strategy-builder autonomous mode)
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String, Text

from ..db.base import Base


# Category enum values — validated at API layer (not DB constraint for forward-compat)
STRATEGY_CATEGORIES = [
    "momentum",
    "mean_reversion",
    "breakout",
    "volume",
    "arbitrage",
    "time_based",
    "pattern",
    "news_driven",
]


# Status lifecycle values
AUDITION_STATUSES = [
    "audition",      # default after creation, awaiting weekly judging
    "graduated",     # weekly winner, eligible for live promotion (separate flow)
    "eliminated",    # lost audition, moved to graveyard (soft delete)
    "resurrected",   # was eliminated but re-admitted (Phase 4 feature)
    "error",         # generation/backtest/registration failure
]


class StrategyAudition(Base):
    __tablename__ = "strategy_audition"

    id = Column(Integer, primary_key=True, index=True)

    # Identity
    strategy_id = Column(String, nullable=False, unique=True, index=True)

    # Provenance (soft FK to gap_signals.signal_id)
    gap_signal_id = Column(String, nullable=True, index=True)

    # Classification for diversity rotation
    category = Column(String, nullable=False, index=True)

    # Lifecycle
    status = Column(String, nullable=False, default="audition", index=True)
    audition_week = Column(String, nullable=False, index=True)  # ISO week: "2026-W15"
    rank_in_week = Column(Integer, nullable=True)  # 1 = winner

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    judged_at = Column(DateTime, nullable=True)

    # Results (from backtest-analyst output)
    backtest_result = Column(JSON, nullable=True)
    judge_notes = Column(Text, nullable=True)

    # Graveyard (soft delete tracking)
    graveyard_path = Column(String, nullable=True)

    # Resurrection (Phase 4)
    resurrect_count = Column(Integer, nullable=False, default=0)
    last_resurrected_at = Column(DateTime, nullable=True)

    # Free-form metadata (parent_class, file_lines, parameter_count, etc.)
    audition_metadata = Column("metadata", JSON, nullable=True)


Index(
    "ix_strategy_audition_status_week",
    StrategyAudition.status,
    StrategyAudition.audition_week,
)
