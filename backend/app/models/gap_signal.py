"""Gap signals queue.

Created when meta-learner / self-critic / cio detects a gap in the system's
analytical or trading capability that requires a new skill. Consumed by
skill-architect via cio INTELLIGENCE phase hook.

See decision_log CIO-20260408-006 / 007 / 008.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String

from ..db.base import Base


class GapSignal(Base):
    __tablename__ = "gap_signals"

    id = Column(Integer, primary_key=True, index=True)

    # Stable external id (e.g. GAP-20260408-001) — unique, used for dedupe
    signal_id = Column(String, nullable=False, unique=True, index=True)

    # Originating agent: meta-learner | self-critic | cio | user
    source = Column(String, nullable=False, index=True)

    # When the signal was issued (UTC ISO8601 from payload, not DB insert time)
    issued_at = Column(DateTime, nullable=False)

    # Semantic classification: missing_analytical_primitive | missing_strategy | ...
    gap_type = Column(String, nullable=False, index=True)

    # Full payloads — kept as JSON for agent-to-agent byte-fidelity
    evidence = Column(JSON, nullable=True)
    proposed_intent = Column(JSON, nullable=True)
    activation_policy = Column(JSON, nullable=True)

    # Lifecycle: pending | consumed | rejected | failed
    status = Column(String, nullable=False, default="pending", index=True)

    # Consumption metadata (filled when skill-architect or cio processes it)
    consumed_at = Column(DateTime, nullable=True)
    consumed_by = Column(String, nullable=True)  # agent name
    result = Column(JSON, nullable=True)  # dispatch result JSON (hashes, verdicts, etc.)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("ix_gap_signals_status_created", GapSignal.status, GapSignal.created_at)
