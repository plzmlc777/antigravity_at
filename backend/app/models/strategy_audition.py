"""Strategy Audition — AI 자율 전략 발굴 파이프라인 상태 추적.

CIO-20260408-015 (SAS: Strategy Audition System).
CIO-20260410-001 (SISDS: Self-Improving Strategy Discovery System — Phase 1 state machine).

하루 1개 전략 생성 → 주 1회 오디션 경쟁 → 1개 우승자 선발의 모든 상태 추적.
Phase 1 (SISDS) 부터 birth → sandbox → paper → live → retired 5단계 state machine 도입.

관련: CIO-008 (gap_signals 큐), CIO-014 (strategy-builder autonomous mode),
     CIO-017 (SISDS state machine)
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


# Legacy status lifecycle values (deprecated as of CIO-017, kept for backward compat).
# Internal logic now uses (stage, stage_status) instead.
AUDITION_STATUSES = [
    "audition",      # default after creation, awaiting weekly judging
    "graduated",     # weekly winner, eligible for live promotion (separate flow)
    "eliminated",    # lost audition, moved to graveyard (soft delete)
    "resurrected",   # was eliminated but re-admitted (Phase 4 feature)
    "error",         # generation/backtest/registration failure
]


# SISDS Phase 1 state machine (CIO-017)
# 5 stages × 6 statuses — not all combinations are valid, see _VALID_STATES in api/strategy_audition.py
STRATEGY_STAGES = [
    "birth",      # 생성 직후, 실행 가능성 확인
    "sandbox",    # 가치 탐색 (무한 실험실)
    "paper",      # 실시간 현실 검증
    "live",       # 실거래
    "retired",    # 최종 archive
    "legacy",     # Pre-SISDS 기존 전략 (마이그레이션 과정에서만 사용)
]

STAGE_STATUSES = [
    "pending",         # 다음 작업 대기 (큐잉됨)
    "running",         # 현재 작업 중
    "passed",          # 성공적 완료, 다음 stage 대기
    "failed",          # 실패
    "degraded",        # (live 전용) 성능 저하 중
    "waiting_human",   # (paper 전용) 사용자 승인 대기
    "archived",        # (retired 전용) 오래된 graveyard cleanup 후
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

    # ─── SISDS Phase 1 State Machine (CIO-017) ─────────────────────────
    # Stage: which pipeline stage (birth, sandbox, paper, live, retired, legacy)
    # Stage status: current activity within that stage (pending, running, passed, failed, degraded, waiting_human, archived)
    # Together (stage, stage_status) forms the state; legacy `status` is derived for backward compat.
    stage = Column(String, nullable=False, default="sandbox", index=True)
    stage_status = Column(String, nullable=False, default="pending", index=True)
    stage_entered_at = Column(DateTime, nullable=True)
    stage_expected_exit_at = Column(DateTime, nullable=True)
    last_transition_by = Column(String(64), nullable=True)
    last_transition_reason = Column(Text, nullable=True)

    # Link to live_bot_sessions when the strategy is in paper or live stage
    live_session_id = Column(String, nullable=True, index=True)


Index(
    "ix_strategy_audition_status_week",
    StrategyAudition.status,
    StrategyAudition.audition_week,
)
Index(
    "ix_strategy_audition_stage_composite",
    StrategyAudition.stage,
    StrategyAudition.stage_status,
)
