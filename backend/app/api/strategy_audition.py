"""Strategy Audition API — SAS (CIO-20260408-015).

Tracks AI-generated strategies through the audition → graduated/eliminated lifecycle.

Endpoints:
- POST   /                          register new audition entry (strategy-builder)
- GET    /                          list with filters
- GET    /{strategy_id}             single lookup
- PATCH  /{strategy_id}             status transition (audition-judge)
- GET    /stats/weekly              aggregate for current/recent weeks
- GET    /stats/graveyard           eliminated pool summary
- POST   /{strategy_id}/resurrect   manual override (emergency only)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.strategy_audition import (
    AUDITION_STATUSES,
    STRATEGY_CATEGORIES,
    StrategyAudition,
)

router = APIRouter()


# Forward-only transitions allowed (prevents accidental rollback)
_VALID_TRANSITIONS = {
    "audition": {"graduated", "eliminated", "error"},
    "eliminated": {"resurrected"},
    "error": {"audition"},  # retry after fix
    "graduated": set(),  # terminal
    "resurrected": {"audition"},  # re-enter audition
}


class AuditionCreate(BaseModel):
    strategy_id: str
    gap_signal_id: Optional[str] = None
    category: str
    audition_week: str = Field(..., description="ISO week, e.g. '2026-W15'")
    audition_metadata: Optional[Dict[str, Any]] = None


class AuditionUpdate(BaseModel):
    status: str
    rank_in_week: Optional[int] = None
    backtest_result: Optional[Dict[str, Any]] = None
    judge_notes: Optional[str] = None
    graveyard_path: Optional[str] = None
    audition_metadata: Optional[Dict[str, Any]] = None


def _serialize(a: StrategyAudition) -> Dict[str, Any]:
    return {
        "id": a.id,
        "strategy_id": a.strategy_id,
        "gap_signal_id": a.gap_signal_id,
        "category": a.category,
        "status": a.status,
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

    entry = StrategyAudition(
        strategy_id=body.strategy_id,
        gap_signal_id=body.gap_signal_id,
        category=body.category,
        status="audition",
        audition_week=body.audition_week,
        audition_metadata=body.audition_metadata,
    )
    db.add(entry)
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

    # Validate status transition
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

    a.status = body.status
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

    if body.status != "audition":
        a.judged_at = datetime.utcnow()

    db.commit()
    db.refresh(a)
    return _serialize(a)


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
