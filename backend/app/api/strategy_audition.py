"""Strategy Audition API — SAS (CIO-20260408-015) + SISDS Phase 1 (CIO-017).

Tracks AI-generated strategies through the 5-stage state machine:
  birth → sandbox → paper → live → retired
                                  └→ degraded (live-specific)

Legacy `status` field is still maintained for backward compat, but internal
logic now uses (stage, stage_status) pairs validated by _VALID_STATE_TRANSITIONS.

Endpoints:
- POST   /                              register new audition entry
- GET    /                              list with filters (by status, stage, category, week)
- GET    /by-stage                      list by (stage, stage_status)
- GET    /{strategy_id}                 single lookup
- PATCH  /{strategy_id}                 update entry (stage transition, metadata merge)
- POST   /{strategy_id}/transition      explicit stage transition with audit log
- GET    /{strategy_id}/history         transition history
- GET    /stats/weekly                  aggregate for current/recent weeks
- GET    /stats/graveyard               eliminated pool summary
- GET    /stats/by-stage                current stage distribution
- POST   /{strategy_id}/resurrect       manual override (emergency only)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.strategy_audition import (
    AUDITION_STATUSES,
    STAGE_STATUSES,
    STRATEGY_CATEGORIES,
    STRATEGY_STAGES,
    StrategyAudition,
)
from ..models.strategy_transition import StrategyTransition

router = APIRouter()


# ─── Legacy `status` transitions (backward compat, deprecated) ───────────
# Forward-only transitions allowed (prevents accidental rollback)
_VALID_TRANSITIONS = {
    "audition": {"graduated", "eliminated", "error"},
    "eliminated": {"resurrected"},
    "error": {"audition"},  # retry after fix
    "graduated": set(),  # terminal
    "resurrected": {"audition"},  # re-enter audition
}


# ─── SISDS Phase 1: stage+stage_status state machine (CIO-017) ───────────
# Each (stage, stage_status) is a valid state; transitions MUST be in the map below.
# Format: (from_stage, from_status): {(to_stage, to_status), ...}

_VALID_STATE_TRANSITIONS: Dict[Tuple[str, str], set] = {
    # ── Birth stage ────────────────────────────────────────────────────
    # Strategy-builder handles birth-check in a single invocation:
    #   POST (birth, pending) → birth backtest → transition.
    # Both (birth, pending) and (birth, running) can go directly to
    # (sandbox, pending) or (retired, failed) — intermediate state is
    # optional if the agent handles it atomically.
    ("birth", "pending"): {
        ("birth", "running"),       # if agent wants intermediate step
        ("sandbox", "pending"),     # direct promote (birth check passed)
        ("retired", "failed"),      # direct fail (api error, zero cycles)
    },
    ("birth", "running"): {
        ("sandbox", "pending"),     # T2: birth backtest passed → sandbox
        ("retired", "failed"),      # T3: api failure / invalid
    },
    ("birth", "passed"): {          # intermediate (rarely used, but allowed)
        ("sandbox", "pending"),
    },
    ("birth", "failed"): {
        ("retired", "failed"),
    },

    # ── Sandbox stage ───────────────────────────────────────────────────
    ("sandbox", "pending"): {
        ("sandbox", "running"),     # T4: researcher picked up
        ("retired", "failed"),      # manual retire while queued
    },
    ("sandbox", "running"): {
        ("sandbox", "passed"),      # T5: 8-gate passed
        ("retired", "failed"),      # T6: timeout or permanent failure
    },
    ("sandbox", "passed"): {
        ("paper", "pending"),       # T7: paper-scheduler queues
    },
    ("sandbox", "failed"): {
        ("retired", "failed"),
    },

    # ── Paper stage ─────────────────────────────────────────────────────
    ("paper", "pending"): {
        ("paper", "running"),       # T8: live-manager started session
        ("retired", "failed"),      # manual cancel before start
    },
    ("paper", "running"): {
        ("paper", "waiting_human"), # T9: 14d + KPI passed
        ("retired", "failed"),      # T10: 14d + failed
    },
    ("paper", "waiting_human"): {
        ("live", "pending"),        # T11: USER APPROVED (the only manual transition)
        ("retired", "passed"),      # T12: user rejected or 30-day timeout
    },
    ("paper", "failed"): {
        ("retired", "failed"),
    },
    ("paper", "passed"): {
        ("paper", "waiting_human"),  # auto-advance from passed (if used)
    },

    # ── Live stage ──────────────────────────────────────────────────────
    ("live", "pending"): {
        ("live", "running"),        # T13: risk-manager final approval
        ("retired", "failed"),      # pre-live aborted
    },
    ("live", "running"): {
        ("live", "degraded"),       # T14: performance drop detected
        ("retired", "passed"),      # user-initiated retirement (success)
    },
    ("live", "degraded"): {
        ("live", "running"),        # T15: recovered within grace
        ("paper", "running"),       # T16: demoted for re-evaluation
        ("retired", "failed"),      # direct retire
    },
    ("live", "failed"): {
        ("retired", "failed"),
    },
    ("live", "passed"): {           # unused normally but valid
        ("retired", "passed"),
    },

    # ── Retired stage ───────────────────────────────────────────────────
    ("retired", "failed"): {
        ("sandbox", "pending"),     # T17: monthly resurrect
        ("retired", "archived"),    # T18: cleanup after 90 days
    },
    ("retired", "passed"): {
        ("retired", "archived"),    # cleanup after 90 days
    },
    ("retired", "archived"): set(),  # terminal

    # ── Legacy stage (pre-SISDS graduated pool) ─────────────────────────
    # Legacy entries generally stay put. Only explicit user action moves them.
    ("legacy", "passed"): {
        ("sandbox", "pending"),     # user-triggered re-evaluation
        ("retired", "passed"),      # user-initiated retirement
    },
}


def _is_valid_state_transition(
    from_stage: str, from_status: str,
    to_stage: str, to_status: str,
) -> bool:
    """Check if a (stage, status) transition is allowed."""
    if from_stage == to_stage and from_status == to_status:
        return True  # same state is always OK (no-op)
    allowed = _VALID_STATE_TRANSITIONS.get((from_stage, from_status), set())
    return (to_stage, to_status) in allowed


def _record_transition(
    db: Session,
    strategy_id: str,
    from_stage: str, from_status: str,
    to_stage: str, to_status: str,
    transitioned_by: str,
    reason: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> StrategyTransition:
    """Append an audit log row for a state transition."""
    tr = StrategyTransition(
        strategy_id=strategy_id,
        from_stage=from_stage,
        from_status=from_status,
        to_stage=to_stage,
        to_status=to_status,
        transitioned_by=transitioned_by,
        reason=reason,
        evidence=evidence,
    )
    db.add(tr)
    return tr


class AuditionCreate(BaseModel):
    strategy_id: str
    gap_signal_id: Optional[str] = None
    category: str
    audition_week: str = Field(..., description="ISO week, e.g. '2026-W15'")
    audition_metadata: Optional[Dict[str, Any]] = None
    # SISDS Phase 1 — allow caller (strategy-builder) to specify initial stage
    # Default: (sandbox, pending) — strategy enters sandbox queue directly
    stage: Optional[str] = Field("sandbox", description="Initial stage (default: sandbox)")
    stage_status: Optional[str] = Field("pending", description="Initial stage status (default: pending)")


class AuditionUpdate(BaseModel):
    # Legacy field (deprecated, but still accepted for backward compat)
    status: Optional[str] = None
    rank_in_week: Optional[int] = None
    backtest_result: Optional[Dict[str, Any]] = None
    judge_notes: Optional[str] = None
    graveyard_path: Optional[str] = None
    audition_metadata: Optional[Dict[str, Any]] = None

    # SISDS Phase 1 state machine fields (CIO-017)
    stage: Optional[str] = None
    stage_status: Optional[str] = None
    last_transition_by: Optional[str] = None
    last_transition_reason: Optional[str] = None
    live_session_id: Optional[str] = None


class StateTransitionRequest(BaseModel):
    """Explicit stage transition with audit trail."""
    to_stage: str
    to_status: str
    transitioned_by: str = Field(..., description="agent name or 'user'")
    reason: str
    evidence: Optional[Dict[str, Any]] = None


def _serialize(a: StrategyAudition) -> Dict[str, Any]:
    return {
        "id": a.id,
        "strategy_id": a.strategy_id,
        "gap_signal_id": a.gap_signal_id,
        "category": a.category,
        "status": a.status,  # legacy, still exposed
        "audition_week": a.audition_week,
        "rank_in_week": a.rank_in_week,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "judged_at": a.judged_at.isoformat() if a.judged_at else None,
        "backtest_result": a.backtest_result,
        "judge_notes": a.judge_notes,
        "graveyard_path": a.graveyard_path,
        "resurrect_count": a.resurrect_count,
        "last_resurrected_at": a.last_resurrected_at.isoformat() if a.last_resurrected_at else None,
        "metadata": a.audition_metadata,
        # SISDS Phase 1 state machine (CIO-017)
        "stage": a.stage,
        "stage_status": a.stage_status,
        "stage_entered_at": a.stage_entered_at.isoformat() if a.stage_entered_at else None,
        "stage_expected_exit_at": a.stage_expected_exit_at.isoformat() if a.stage_expected_exit_at else None,
        "last_transition_by": a.last_transition_by,
        "last_transition_reason": a.last_transition_reason,
        "live_session_id": a.live_session_id,
    }


@router.post("")
def create_audition(body: AuditionCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    # Validate category
    if body.category not in STRATEGY_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid category '{body.category}'. Allowed: {STRATEGY_CATEGORIES}",
        )

    # Dedup on strategy_id (idempotent register)
    existing = db.query(StrategyAudition).filter(
        StrategyAudition.strategy_id == body.strategy_id
    ).first()
    if existing:
        return _serialize(existing)

    # Validate initial stage
    initial_stage = body.stage or "sandbox"
    initial_stage_status = body.stage_status or "pending"
    if initial_stage not in STRATEGY_STAGES:
        raise HTTPException(status_code=400, detail=f"invalid stage '{initial_stage}'")
    if initial_stage_status not in STAGE_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid stage_status '{initial_stage_status}'")

    now = datetime.utcnow()
    entry = StrategyAudition(
        strategy_id=body.strategy_id,
        gap_signal_id=body.gap_signal_id,
        category=body.category,
        status="audition",  # legacy status (backward compat)
        audition_week=body.audition_week,
        audition_metadata=body.audition_metadata,
        # SISDS Phase 1 initial state
        stage=initial_stage,
        stage_status=initial_stage_status,
        stage_entered_at=now,
        last_transition_by="strategy-builder",
        last_transition_reason=f"initial registration into ({initial_stage}, {initial_stage_status})",
    )
    db.add(entry)
    db.flush()  # get the ID before recording transition

    # Audit log: record initial "creation" as a transition from (none → initial)
    _record_transition(
        db,
        strategy_id=body.strategy_id,
        from_stage="none",
        from_status="none",
        to_stage=initial_stage,
        to_status=initial_stage_status,
        transitioned_by="strategy-builder",
        reason="strategy created and registered",
        evidence={"category": body.category, "gap_signal_id": body.gap_signal_id},
    )

    db.commit()
    db.refresh(entry)
    return _serialize(entry)


@router.get("")
def list_auditions(
    status: str = Query("audition", description="audition | graduated | eliminated | resurrected | error | all"),
    category: Optional[str] = Query(None),
    week: Optional[str] = Query(None, description="ISO week filter, e.g. '2026-W15'"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    q = db.query(StrategyAudition)
    if status != "all":
        if status not in AUDITION_STATUSES:
            raise HTTPException(status_code=400, detail=f"invalid status '{status}'")
        q = q.filter(StrategyAudition.status == status)
    if category:
        if category not in STRATEGY_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"invalid category '{category}'")
        q = q.filter(StrategyAudition.category == category)
    if week:
        q = q.filter(StrategyAudition.audition_week == week)
    q = q.order_by(StrategyAudition.created_at.desc()).limit(limit)
    return [_serialize(a) for a in q.all()]


@router.get("/stats/weekly")
def stats_weekly(
    weeks: int = Query(4, ge=1, le=52),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Aggregate stats for the most recent N weeks."""
    # Total counts by status
    total_by_status = dict(
        db.query(StrategyAudition.status, func.count(StrategyAudition.id))
        .group_by(StrategyAudition.status)
        .all()
    )

    # Category distribution
    category_dist = dict(
        db.query(StrategyAudition.category, func.count(StrategyAudition.id))
        .group_by(StrategyAudition.category)
        .all()
    )

    # Recent N weeks — each week's breakdown
    recent_weeks_raw = (
        db.query(
            StrategyAudition.audition_week,
            StrategyAudition.status,
            func.count(StrategyAudition.id),
        )
        .group_by(StrategyAudition.audition_week, StrategyAudition.status)
        .order_by(StrategyAudition.audition_week.desc())
        .limit(weeks * len(AUDITION_STATUSES))
        .all()
    )
    by_week: Dict[str, Dict[str, int]] = {}
    for week_key, status, cnt in recent_weeks_raw:
        by_week.setdefault(week_key, {})[status] = cnt

    # Last winner (most recent graduated)
    last_winner_row = (
        db.query(StrategyAudition)
        .filter(StrategyAudition.status == "graduated")
        .order_by(StrategyAudition.judged_at.desc().nullslast())
        .first()
    )
    last_winner = None
    if last_winner_row:
        last_winner = {
            "strategy_id": last_winner_row.strategy_id,
            "category": last_winner_row.category,
            "week": last_winner_row.audition_week,
            "monthly_return_compound": (
                last_winner_row.backtest_result.get("monthly_return_compound")
                if isinstance(last_winner_row.backtest_result, dict)
                else None
            ),
        }

    return {
        "total_by_status": total_by_status,
        "category_distribution": category_dist,
        "by_week": by_week,
        "last_winner": last_winner,
        "category_set": STRATEGY_CATEGORIES,
    }


@router.get("/stats/graveyard")
def stats_graveyard(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Summary of eliminated pool for resurrect consideration."""
    eliminated = (
        db.query(StrategyAudition)
        .filter(StrategyAudition.status == "eliminated")
        .order_by(StrategyAudition.judged_at.desc())
        .all()
    )

    by_category: Dict[str, int] = {}
    resurrect_candidates = []

    now = datetime.utcnow()
    for e in eliminated:
        by_category[e.category] = by_category.get(e.category, 0) + 1
        # Eligible for resurrect if judged >= 30 days ago
        if e.judged_at and (now - e.judged_at).days >= 30:
            resurrect_candidates.append(e.strategy_id)

    return {
        "total_eliminated": len(eliminated),
        "by_category": by_category,
        "resurrect_eligible_count": len(resurrect_candidates),
        "resurrect_eligible_sample": resurrect_candidates[:10],
    }


# ─── SISDS Phase 1: stage-machine endpoints (CIO-017) ────────────────────

@router.get("/by-stage")
def list_by_stage(
    stage: Optional[str] = Query(None, description="Filter by stage"),
    stage_status: Optional[str] = Query(None, description="Filter by stage_status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List strategies filtered by (stage, stage_status). Returns empty list if none."""
    q = db.query(StrategyAudition)
    if stage:
        if stage not in STRATEGY_STAGES:
            raise HTTPException(status_code=400, detail=f"invalid stage '{stage}'. Allowed: {STRATEGY_STAGES}")
        q = q.filter(StrategyAudition.stage == stage)
    if stage_status:
        if stage_status not in STAGE_STATUSES:
            raise HTTPException(status_code=400, detail=f"invalid stage_status '{stage_status}'. Allowed: {STAGE_STATUSES}")
        q = q.filter(StrategyAudition.stage_status == stage_status)
    q = q.order_by(StrategyAudition.stage_entered_at.desc().nullslast()).limit(limit)
    return [_serialize(a) for a in q.all()]


@router.get("/stats/by-stage")
def stats_by_stage(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Current distribution of strategies across (stage, stage_status).

    Returns a nested dict: {stage: {stage_status: count, ...}, ...}
    Suitable for driving the Workflow page and audition tabs.
    """
    rows = (
        db.query(
            StrategyAudition.stage,
            StrategyAudition.stage_status,
            func.count(StrategyAudition.id),
        )
        .group_by(StrategyAudition.stage, StrategyAudition.stage_status)
        .all()
    )
    distribution: Dict[str, Dict[str, int]] = {s: {} for s in STRATEGY_STAGES}
    total = 0
    for stage, stage_status, cnt in rows:
        if stage not in distribution:
            distribution[stage] = {}
        distribution[stage][stage_status] = cnt
        total += cnt

    return {
        "total": total,
        "distribution": distribution,
        "stages": STRATEGY_STAGES,
        "statuses": STAGE_STATUSES,
    }


@router.get("/{strategy_id}")
def get_audition(strategy_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    a = db.query(StrategyAudition).filter(
        StrategyAudition.strategy_id == strategy_id
    ).first()
    if not a:
        raise HTTPException(
            status_code=404, detail=f"audition entry '{strategy_id}' not found"
        )
    return _serialize(a)


@router.patch("/{strategy_id}")
def update_audition(
    strategy_id: str,
    body: AuditionUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    a = db.query(StrategyAudition).filter(
        StrategyAudition.strategy_id == strategy_id
    ).first()
    if not a:
        raise HTTPException(
            status_code=404, detail=f"audition entry '{strategy_id}' not found"
        )

    # Legacy status validation (only if legacy status is being changed)
    if body.status is not None:
        if body.status not in AUDITION_STATUSES:
            raise HTTPException(status_code=400, detail=f"invalid status '{body.status}'")
        allowed = _VALID_TRANSITIONS.get(a.status, set())
        if body.status != a.status and body.status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"forward-only transition violated: "
                    f"'{a.status}' → '{body.status}' not allowed. "
                    f"Allowed from '{a.status}': {list(allowed) or 'none (terminal)'}"
                ),
            )

    # Legacy status handling (backward compat)
    if body.status is not None:
        a.status = body.status
        if body.status != "audition":
            a.judged_at = datetime.utcnow()

    if body.rank_in_week is not None:
        a.rank_in_week = body.rank_in_week
    if body.backtest_result is not None:
        a.backtest_result = body.backtest_result
    if body.judge_notes is not None:
        a.judge_notes = body.judge_notes
    if body.graveyard_path is not None:
        a.graveyard_path = body.graveyard_path
    if body.audition_metadata is not None:
        # Merge with existing metadata so partial updates (e.g., adding
        # birth_backtest from strategy-builder Step 7.6) don't overwrite
        # fields set at creation time (parent_class, file_lines, etc.).
        merged = dict(a.audition_metadata or {})
        merged.update(body.audition_metadata)
        a.audition_metadata = merged

    # SISDS Phase 1 state machine fields (CIO-017)
    if body.live_session_id is not None:
        a.live_session_id = body.live_session_id

    if body.stage is not None or body.stage_status is not None:
        new_stage = body.stage if body.stage is not None else a.stage
        new_status = body.stage_status if body.stage_status is not None else a.stage_status

        # Validate transition
        if new_stage not in STRATEGY_STAGES:
            raise HTTPException(status_code=400, detail=f"invalid stage '{new_stage}'. Allowed: {STRATEGY_STAGES}")
        if new_status not in STAGE_STATUSES:
            raise HTTPException(status_code=400, detail=f"invalid stage_status '{new_status}'. Allowed: {STAGE_STATUSES}")

        if not _is_valid_state_transition(a.stage, a.stage_status, new_stage, new_status):
            allowed = _VALID_STATE_TRANSITIONS.get((a.stage, a.stage_status), set())
            raise HTTPException(
                status_code=400,
                detail=(
                    f"invalid state transition: "
                    f"({a.stage}, {a.stage_status}) → ({new_stage}, {new_status}). "
                    f"Allowed from ({a.stage}, {a.stage_status}): {sorted(list(allowed)) or 'none (terminal)'}"
                ),
            )

        # Record the transition in audit log
        if (a.stage, a.stage_status) != (new_stage, new_status):
            _record_transition(
                db,
                strategy_id=strategy_id,
                from_stage=a.stage,
                from_status=a.stage_status,
                to_stage=new_stage,
                to_status=new_status,
                transitioned_by=body.last_transition_by or "api_patch",
                reason=body.last_transition_reason or "stage update via PATCH",
                evidence=None,
            )
            a.stage = new_stage
            a.stage_status = new_status
            a.stage_entered_at = datetime.utcnow()
            if body.last_transition_by:
                a.last_transition_by = body.last_transition_by
            if body.last_transition_reason:
                a.last_transition_reason = body.last_transition_reason

    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.post("/{strategy_id}/transition")
def explicit_transition(
    strategy_id: str,
    body: StateTransitionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Explicit stage transition with required audit trail fields.

    Prefer this over PATCH for important state transitions — it forces the
    caller to supply `transitioned_by`, `reason`, and optional `evidence`.
    """
    a = db.query(StrategyAudition).filter(
        StrategyAudition.strategy_id == strategy_id
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"audition entry '{strategy_id}' not found")

    if body.to_stage not in STRATEGY_STAGES:
        raise HTTPException(status_code=400, detail=f"invalid stage '{body.to_stage}'")
    if body.to_status not in STAGE_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid stage_status '{body.to_status}'")

    if not _is_valid_state_transition(a.stage, a.stage_status, body.to_stage, body.to_status):
        allowed = _VALID_STATE_TRANSITIONS.get((a.stage, a.stage_status), set())
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid state transition: "
                f"({a.stage}, {a.stage_status}) → ({body.to_stage}, {body.to_status}). "
                f"Allowed from ({a.stage}, {a.stage_status}): {sorted(list(allowed)) or 'none (terminal)'}"
            ),
        )

    from_stage = a.stage
    from_status = a.stage_status

    # Record transition audit log
    _record_transition(
        db,
        strategy_id=strategy_id,
        from_stage=from_stage,
        from_status=from_status,
        to_stage=body.to_stage,
        to_status=body.to_status,
        transitioned_by=body.transitioned_by,
        reason=body.reason,
        evidence=body.evidence,
    )

    # Apply transition
    a.stage = body.to_stage
    a.stage_status = body.to_status
    a.stage_entered_at = datetime.utcnow()
    a.last_transition_by = body.transitioned_by
    a.last_transition_reason = body.reason

    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.get("/{strategy_id}/history")
def transition_history(
    strategy_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return chronological history of stage transitions for a strategy."""
    a = db.query(StrategyAudition).filter(
        StrategyAudition.strategy_id == strategy_id
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"audition entry '{strategy_id}' not found")

    rows = (
        db.query(StrategyTransition)
        .filter(StrategyTransition.strategy_id == strategy_id)
        .order_by(StrategyTransition.transitioned_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id,
            "strategy_id": t.strategy_id,
            "from_stage": t.from_stage,
            "from_status": t.from_status,
            "to_stage": t.to_stage,
            "to_status": t.to_status,
            "transitioned_at": t.transitioned_at.isoformat() if t.transitioned_at else None,
            "transitioned_by": t.transitioned_by,
            "reason": t.reason,
            "evidence": t.evidence,
        }
        for t in rows
    ]


@router.post("/{strategy_id}/resurrect")
def resurrect_audition(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Manual override: resurrect an eliminated strategy back to audition pool.

    Intended for emergency / explicit user request only. Normal resurrection
    should be driven by meta-learner via the monthly resurrect flow (Phase 4).
    """
    a = db.query(StrategyAudition).filter(
        StrategyAudition.strategy_id == strategy_id
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"audition entry '{strategy_id}' not found")
    if a.status != "eliminated":
        raise HTTPException(
            status_code=400,
            detail=f"cannot resurrect from status '{a.status}' (must be 'eliminated')",
        )

    a.status = "resurrected"
    a.resurrect_count = (a.resurrect_count or 0) + 1
    a.last_resurrected_at = datetime.utcnow()
    db.commit()
    db.refresh(a)
    return _serialize(a)
