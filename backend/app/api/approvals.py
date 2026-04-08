"""Approval queue API.

GET  /api/v1/approvals             list pending (default) or all
POST /api/v1/approvals             create new pending entry (used by agents)
POST /api/v1/approvals/{id}/resolve  approve or reject (used by user UI)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.approval import PendingApproval

router = APIRouter()


class ApprovalCreate(BaseModel):
    decision_id: Optional[str] = None
    action: str
    rationale: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class ApprovalResolve(BaseModel):
    decision: str  # "approve" | "reject"
    resolved_by: Optional[str] = None
    note: Optional[str] = None


def _serialize(a: PendingApproval) -> Dict[str, Any]:
    return {
        "id": a.id,
        "decision_id": a.decision_id,
        "action": a.action,
        "rationale": a.rationale,
        "payload": a.payload,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "resolved_by": a.resolved_by,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "resolution_note": a.resolution_note,
    }


@router.get("")
def list_approvals(
    status: str = Query("pending", description="pending | approved | rejected | all"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    q = db.query(PendingApproval)
    if status != "all":
        q = q.filter(PendingApproval.status == status)
    q = q.order_by(PendingApproval.created_at.desc()).limit(limit)
    return [_serialize(a) for a in q.all()]


@router.post("")
def create_approval(body: ApprovalCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    a = PendingApproval(
        decision_id=body.decision_id,
        action=body.action,
        rationale=body.rationale,
        payload=body.payload,
        status="pending",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.post("/{approval_id}/resolve")
def resolve_approval(
    approval_id: int,
    body: ApprovalResolve,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    a = db.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"approval {approval_id} not found")
    if a.status != "pending":
        raise HTTPException(status_code=400, detail=f"approval already {a.status}")
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")
    a.status = "approved" if body.decision == "approve" else "rejected"
    a.resolved_by = body.resolved_by or "user"
    a.resolved_at = datetime.utcnow()
    a.resolution_note = body.note
    db.commit()
    db.refresh(a)
    return _serialize(a)
