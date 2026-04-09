"""Strategy Transition — audit log of every stage transition.

SISDS Phase 1 (CIO-20260410-001 / CIO-017).

Every stage change in strategy_audition produces one row here. This is the
primary answer to "why is this strategy in this state?" — you can trace the
full history back from retirement to birth.

Transitions are never deleted. Archive by age (e.g., > 1 year) if the table
grows too large, but preserve the row count for recent strategies.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String, Text

from ..db.base import Base


class StrategyTransition(Base):
    __tablename__ = "strategy_transitions"

    id = Column(Integer, primary_key=True, index=True)

    # Which strategy transitioned (logical FK to strategy_audition.strategy_id)
    strategy_id = Column(String, nullable=False, index=True)

    # From state
    from_stage = Column(String, nullable=False)
    from_status = Column(String, nullable=False)

    # To state
    to_stage = Column(String, nullable=False)
    to_status = Column(String, nullable=False)

    # Who / when / why
    transitioned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    transitioned_by = Column(String(64), nullable=False)  # agent name or 'user' or 'migration_script'
    reason = Column(Text, nullable=False)

    # Evidence snapshot (flexible JSON: backtest results, config, KPI snapshot, etc.)
    evidence = Column(JSON, nullable=True)


Index(
    "ix_st_strategy_time",
    StrategyTransition.strategy_id,
    StrategyTransition.transitioned_at.desc(),
)
Index(
    "ix_st_from_state",
    StrategyTransition.from_stage,
    StrategyTransition.from_status,
)
Index(
    "ix_st_to_state",
    StrategyTransition.to_stage,
    StrategyTransition.to_status,
)
