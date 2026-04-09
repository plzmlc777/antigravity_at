"""Calibration API — SISDS Phase 7 (CIO-20260410-001 / CIO-017).

Tracks and exposes prediction accuracy metrics. The key question:
"Is the system getting better at predicting strategy performance?"

Endpoints:
- POST   /records                     record a new calibration measurement
- GET    /records/recent              recent calibration records
- GET    /trend                       CIR (Calibration Improvement Rate) over time
- GET    /worst-strategies            strategies with worst calibration
- GET    /summary                     overall system calibration health
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.calibration_record import CalibrationRecord

router = APIRouter()


class CalibrationCreate(BaseModel):
    strategy_id: str
    transition: str = Field(..., description="sandbox_to_paper | paper_to_live | live_degradation")
    predicted: Dict[str, Any]
    actual: Dict[str, Any]
    stage_duration_days: Optional[int] = None


def _compute_gap(predicted: Dict, actual: Dict) -> tuple:
    """Compute per-metric gaps and overall calibration error."""
    gap = {}
    errors = []
    for key in predicted:
        p = predicted.get(key)
        a = actual.get(key)
        if p is not None and a is not None and isinstance(p, (int, float)) and isinstance(a, (int, float)):
            abs_gap = abs(a - p)
            rel_gap = abs_gap / abs(p) if abs(p) > 0.001 else 0
            gap[key] = {
                "predicted": p,
                "actual": a,
                "absolute_gap": round(abs_gap, 4),
                "relative_gap": round(rel_gap, 4),
            }
            errors.append(rel_gap)
    overall_error = sum(errors) / len(errors) if errors else 1.0
    return gap, round(overall_error, 4)


def _serialize(r: CalibrationRecord) -> Dict[str, Any]:
    return {
        "id": r.id,
        "strategy_id": r.strategy_id,
        "transition": r.transition,
        "measured_at": r.measured_at.isoformat() if r.measured_at else None,
        "predicted": r.predicted,
        "actual": r.actual,
        "gap": r.gap,
        "calibration_error": r.calibration_error,
        "stage_duration_days": r.stage_duration_days,
        "detected_causes": r.detected_causes,
        "resolution": r.resolution,
    }


@router.post("/records")
def create_calibration_record(
    body: CalibrationCreate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Record a new calibration measurement (typically called by paper-scheduler or live-monitor)."""
    valid_transitions = {"sandbox_to_paper", "paper_to_live", "live_degradation"}
    if body.transition not in valid_transitions:
        raise HTTPException(status_code=400, detail=f"invalid transition '{body.transition}'. Allowed: {valid_transitions}")

    gap, error = _compute_gap(body.predicted, body.actual)

    record = CalibrationRecord(
        strategy_id=body.strategy_id,
        transition=body.transition,
        predicted=body.predicted,
        actual=body.actual,
        gap=gap,
        calibration_error=error,
        stage_duration_days=body.stage_duration_days,
        resolution="pending_review",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize(record)


@router.get("/records/recent")
def recent_records(
    days: int = Query(30, ge=1, le=365),
    transition: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Recent calibration records, optionally filtered by transition type."""
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(CalibrationRecord).filter(CalibrationRecord.measured_at >= since)
    if transition:
        q = q.filter(CalibrationRecord.transition == transition)
    q = q.order_by(CalibrationRecord.measured_at.desc()).limit(limit)
    return [_serialize(r) for r in q.all()]


@router.get("/trend")
def calibration_trend(
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Monthly calibration error trend + CIR (Calibration Improvement Rate).

    CIR > 0 means the system is improving its prediction accuracy.
    CIR = 0 means stagnation.
    CIR < 0 means degradation.
    """
    since = datetime.utcnow() - timedelta(days=months * 31)
    rows = (
        db.query(CalibrationRecord)
        .filter(CalibrationRecord.measured_at >= since)
        .order_by(CalibrationRecord.measured_at.asc())
        .all()
    )

    # Group by month
    monthly: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        month_key = r.measured_at.strftime("%Y-%m") if r.measured_at else "unknown"
        monthly[month_key].append(r.calibration_error)

    monthly_avg = {
        m: round(sum(errors) / len(errors), 4) if errors else None
        for m, errors in sorted(monthly.items())
    }

    # Compute CIR (month-over-month improvement rate)
    sorted_months = sorted(monthly_avg.keys())
    cir_values = []
    for i in range(1, len(sorted_months)):
        prev = monthly_avg[sorted_months[i - 1]]
        curr = monthly_avg[sorted_months[i]]
        if prev and curr and prev > 0:
            cir = (prev - curr) / prev  # positive = improving
            cir_values.append(round(cir, 4))

    overall_cir = round(sum(cir_values) / len(cir_values), 4) if cir_values else None

    return {
        "monthly_avg_error": monthly_avg,
        "cir_values": dict(zip(sorted_months[1:], cir_values)) if cir_values else {},
        "overall_cir": overall_cir,
        "total_records": len(rows),
        "months_covered": len(monthly_avg),
        "interpretation": (
            "improving" if overall_cir and overall_cir > 0.02
            else "stable" if overall_cir and abs(overall_cir) <= 0.02
            else "declining" if overall_cir and overall_cir < -0.02
            else "insufficient_data"
        ),
    }


@router.get("/worst-strategies")
def worst_calibrated(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Strategies with the highest average calibration error (fix these first)."""
    rows = (
        db.query(
            CalibrationRecord.strategy_id,
            func.avg(CalibrationRecord.calibration_error).label("avg_error"),
            func.count(CalibrationRecord.id).label("record_count"),
        )
        .group_by(CalibrationRecord.strategy_id)
        .order_by(func.avg(CalibrationRecord.calibration_error).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "strategy_id": r.strategy_id,
            "avg_calibration_error": round(float(r.avg_error), 4),
            "record_count": r.record_count,
        }
        for r in rows
    ]


@router.get("/summary")
def calibration_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Overall system calibration health snapshot."""
    total = db.query(func.count(CalibrationRecord.id)).scalar() or 0
    if total == 0:
        return {
            "total_records": 0,
            "overall_avg_error": None,
            "by_transition": {},
            "health": "no_data",
            "message": "No calibration records yet. Records are created when strategies transition between stages (sandbox→paper, paper→live).",
        }

    overall_avg = db.query(func.avg(CalibrationRecord.calibration_error)).scalar()

    # By transition type
    by_transition_rows = (
        db.query(
            CalibrationRecord.transition,
            func.avg(CalibrationRecord.calibration_error).label("avg_error"),
            func.count(CalibrationRecord.id).label("cnt"),
        )
        .group_by(CalibrationRecord.transition)
        .all()
    )
    by_transition = {
        r.transition: {"avg_error": round(float(r.avg_error), 4), "count": r.cnt}
        for r in by_transition_rows
    }

    # Recent 30-day average vs all-time
    recent_30 = datetime.utcnow() - timedelta(days=30)
    recent_avg = (
        db.query(func.avg(CalibrationRecord.calibration_error))
        .filter(CalibrationRecord.measured_at >= recent_30)
        .scalar()
    )

    health = "no_data"
    if overall_avg is not None:
        avg = float(overall_avg)
        if avg < 0.2:
            health = "excellent"
        elif avg < 0.35:
            health = "good"
        elif avg < 0.5:
            health = "fair"
        else:
            health = "poor"

    return {
        "total_records": total,
        "overall_avg_error": round(float(overall_avg), 4) if overall_avg else None,
        "recent_30d_avg_error": round(float(recent_avg), 4) if recent_avg else None,
        "by_transition": by_transition,
        "health": health,
    }
