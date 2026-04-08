"""Gap signals queue API.

Produces:
- POST   /api/v1/gap-signals                  agents publish a new gap signal
- GET    /api/v1/gap-signals                  list (filter by status/source/gap_type)
- GET    /api/v1/gap-signals/{signal_id}      fetch by external signal_id
- PATCH  /api/v1/gap-signals/{signal_id}      update status + result (consume/reject/fail)

Consumed by cio INTELLIGENCE phase hook → skill-architect dispatch.
See decision_log CIO-20260408-008.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.gap_signal import GapSignal

router = APIRouter()


_ALLOWED_STATUSES = {"pending", "consumed", "rejected", "failed"}


class GapSignalCreate(BaseModel):
    signal_id: str = Field(..., description="Stable external id, e.g. GAP-20260408-001")
    source: str = Field(..., description="Originating agent name")
    issued_at: datetime
    gap_type: str
    evidence: Optional[Dict[str, Any]] = None
    proposed_intent: Optional[Dict[str, Any]] = None
    activation_policy: Optional[Dict[str, Any]] = None


class GapSignalUpdate(BaseModel):
    status: str = Field(..., description="pending | consumed | rejected | failed")
    consumed_by: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


def _serialize(g: GapSignal) -> Dict[str, Any]:
    return {
        "id": g.id,
        "signal_id": g.signal_id,
        "source": g.source,
        "issued_at": g.issued_at.isoformat() if g.issued_at else None,
        "gap_type": g.gap_type,
        "evidence": g.evidence,
        "proposed_intent": g.proposed_intent,
        "activation_policy": g.activation_policy,
        "status": g.status,
        "consumed_at": g.consumed_at.isoformat() if g.consumed_at else None,
        "consumed_by": g.consumed_by,
        "result": g.result,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


@router.get("")
def list_gap_signals(
    status: str = Query("pending", description="pending | consumed | rejected | failed | all"),
    source: Optional[str] = Query(None),
    gap_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    q = db.query(GapSignal)
    if status != "all":
        if status not in _ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail=f"invalid status '{status}'")
        q = q.filter(GapSignal.status == status)
    if source:
        q = q.filter(GapSignal.source == source)
    if gap_type:
        q = q.filter(GapSignal.gap_type == gap_type)
    q = q.order_by(GapSignal.created_at.desc()).limit(limit)
    return [_serialize(g) for g in q.all()]


@router.post("")
def create_gap_signal(body: GapSignalCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    # Dedupe on signal_id — if it already exists, return existing (idempotent publish).
    existing = db.query(GapSignal).filter(GapSignal.signal_id == body.signal_id).first()
    if existing:
        return _serialize(existing)

    g = GapSignal(
        signal_id=body.signal_id,
        source=body.source,
        issued_at=body.issued_at,
        gap_type=body.gap_type,
        evidence=body.evidence,
        proposed_intent=body.proposed_intent,
        activation_policy=body.activation_policy,
        status="pending",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _serialize(g)


@router.get("/{signal_id}")
def get_gap_signal(signal_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    g = db.query(GapSignal).filter(GapSignal.signal_id == signal_id).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"gap_signal '{signal_id}' not found")
    return _serialize(g)


@router.patch("/{signal_id}")
def update_gap_signal(
    signal_id: str,
    body: GapSignalUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    g = db.query(GapSignal).filter(GapSignal.signal_id == signal_id).first()
    if not g:
        raise HTTPException(status_code=404, detail=f"gap_signal '{signal_id}' not found")

    if body.status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status '{body.status}'")

    g.status = body.status
    if body.status != "pending":
        g.consumed_at = datetime.utcnow()
        g.consumed_by = body.consumed_by
        g.result = body.result

    db.commit()
    db.refresh(g)
    return _serialize(g)
