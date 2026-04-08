"""Pending approvals queue.

Created when risk-manager rejects an action with `pending_user_override` or when
CIO needs explicit human confirmation before EXECUTE. Resolved by the user via the
frontend ApprovalQueue UI.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, Index
from datetime import datetime
from ..db.base import Base


class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)
    rationale = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(String, nullable=True)


Index("ix_pending_approvals_status_created", PendingApproval.status, PendingApproval.created_at)
