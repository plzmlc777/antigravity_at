"""
AI Analysis Schedule & Report API Endpoints

Provides CRUD for analysis schedules and retrieval of analysis reports.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..api.auth import get_current_user
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Request/Response Models ---

class ScheduleCreate(BaseModel):
    account_id: Optional[int] = None
    schedule_type: str = "daily"  # daily, weekly, monthly
    schedule_time: str = "15:40"  # HH:MM KST
    schedule_day: Optional[int] = None  # 1-7 for weekly, 1-31 for monthly
    target_sessions: Optional[list] = None  # ["session_id",...] or ["all_running"]
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    schedule_type: Optional[str] = None
    schedule_time: Optional[str] = None
    schedule_day: Optional[int] = None
    target_sessions: Optional[list] = None
    enabled: Optional[bool] = None


# --- Schedule CRUD ---

@router.post("/analysis-schedules")
async def create_schedule(
    req: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new AI analysis schedule."""
    from ..models.live_trading import generate_uuid
    from ..core.analysis_scheduler import AnalysisScheduler

    # Validate schedule_type
    if req.schedule_type not in ("daily", "weekly", "monthly"):
        raise HTTPException(400, "schedule_type must be daily, weekly, or monthly")

    # Validate time format
    try:
        h, m = map(int, req.schedule_time.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(400, "schedule_time must be HH:MM format")

    schedule_id = generate_uuid()
    next_run = AnalysisScheduler._compute_next_run(req.schedule_type, req.schedule_time, req.schedule_day)

    db.execute(text("""
        INSERT INTO ai_analysis_schedules
            (id, user_id, account_id, schedule_type, schedule_time, schedule_day,
             target_sessions, enabled, next_run_at, created_at, updated_at)
        VALUES
            (:id, :user_id, :account_id, :type, :time, :day,
             :targets, :enabled, :next_run, :now, :now)
    """), {
        "id": schedule_id,
        "user_id": current_user.id,
        "account_id": req.account_id,
        "type": req.schedule_type,
        "time": req.schedule_time,
        "day": req.schedule_day,
        "targets": json.dumps(req.target_sessions) if req.target_sessions else json.dumps(["all_running"]),
        "enabled": req.enabled,
        "next_run": next_run,
        "now": datetime.utcnow(),
    })
    db.commit()

    return {
        "id": schedule_id,
        "schedule_type": req.schedule_type,
        "schedule_time": req.schedule_time,
        "schedule_day": req.schedule_day,
        "enabled": req.enabled,
        "next_run_at": next_run.isoformat() if next_run else None,
    }


@router.get("/analysis-schedules")
async def list_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all analysis schedules for the current user."""
    rows = db.execute(text("""
        SELECT id, account_id, schedule_type, schedule_time, schedule_day,
               target_sessions, enabled, last_run_at, next_run_at, created_at
        FROM ai_analysis_schedules
        WHERE user_id = :uid
        ORDER BY created_at DESC
    """), {"uid": current_user.id}).fetchall()

    return [
        {
            "id": r[0],
            "account_id": r[1],
            "schedule_type": r[2],
            "schedule_time": r[3],
            "schedule_day": r[4],
            "target_sessions": r[5] if isinstance(r[5], list) else (json.loads(r[5]) if r[5] else ["all_running"]),
            "enabled": r[6],
            "last_run_at": r[7].isoformat() if r[7] else None,
            "next_run_at": r[8].isoformat() if r[8] else None,
            "created_at": r[9].isoformat() if r[9] else None,
        }
        for r in rows
    ]


@router.put("/analysis-schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    req: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing analysis schedule."""
    from ..core.analysis_scheduler import AnalysisScheduler

    # Verify ownership
    row = db.execute(text("""
        SELECT id, schedule_type, schedule_time, schedule_day
        FROM ai_analysis_schedules WHERE id = :sid AND user_id = :uid
    """), {"sid": schedule_id, "uid": current_user.id}).fetchone()

    if not row:
        raise HTTPException(404, "Schedule not found")

    # Build update fields
    updates = {}
    if req.schedule_type is not None:
        if req.schedule_type not in ("daily", "weekly", "monthly"):
            raise HTTPException(400, "schedule_type must be daily, weekly, or monthly")
        updates["schedule_type"] = req.schedule_type
    if req.schedule_time is not None:
        try:
            h, m = map(int, req.schedule_time.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError()
        except (ValueError, AttributeError):
            raise HTTPException(400, "schedule_time must be HH:MM format")
        updates["schedule_time"] = req.schedule_time
    if req.schedule_day is not None:
        updates["schedule_day"] = req.schedule_day
    if req.target_sessions is not None:
        updates["target_sessions"] = json.dumps(req.target_sessions)
    if req.enabled is not None:
        updates["enabled"] = req.enabled

    if not updates:
        raise HTTPException(400, "No fields to update")

    # Build SQL dynamically
    set_clauses = [f"{k} = :{k}" for k in updates]
    set_clauses.append("updated_at = :now")
    updates["now"] = datetime.utcnow()
    updates["sid"] = schedule_id

    db.execute(text(f"""
        UPDATE ai_analysis_schedules
        SET {', '.join(set_clauses)}
        WHERE id = :sid
    """), updates)

    # Recompute next_run_at
    stype = updates.get("schedule_type", row[1])
    stime = updates.get("schedule_time", row[2])
    sday = updates.get("schedule_day", row[3])
    next_run = AnalysisScheduler._compute_next_run(stype, stime, sday)

    db.execute(text("""
        UPDATE ai_analysis_schedules SET next_run_at = :next_run WHERE id = :sid
    """), {"next_run": next_run, "sid": schedule_id})

    db.commit()

    return {"id": schedule_id, "updated": True, "next_run_at": next_run.isoformat()}


@router.delete("/analysis-schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an analysis schedule."""
    row = db.execute(text("""
        SELECT id FROM ai_analysis_schedules WHERE id = :sid AND user_id = :uid
    """), {"sid": schedule_id, "uid": current_user.id}).fetchone()

    if not row:
        raise HTTPException(404, "Schedule not found")

    db.execute(text("DELETE FROM ai_analysis_schedules WHERE id = :sid"), {"sid": schedule_id})
    db.commit()

    return {"deleted": True}


# --- Manual Analysis ---

@router.post("/{session_id}/ai-analysis")
async def run_manual_analysis(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Trigger manual AI analysis for a session. Runs in background."""
    from ..core.analysis_scheduler import analysis_scheduler

    # Verify session exists
    row = db.execute(text("""
        SELECT id, status FROM live_bot_sessions WHERE id = :sid
    """), {"sid": session_id}).fetchone()

    if not row:
        raise HTTPException(404, "Session not found")

    # Run analysis asynchronously
    async def _run():
        return await analysis_scheduler.run_manual_analysis(session_id, current_user.id)

    task = asyncio.create_task(_run())

    return {
        "status": "started",
        "message": "AI analysis started. Check reports for results.",
        "session_id": session_id,
    }


@router.post("/ai-analysis-all")
async def run_analysis_all_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Trigger AI analysis for ALL running sessions. Runs in background."""
    from ..core.analysis_scheduler import analysis_scheduler

    # Find all running sessions
    rows = db.execute(text("""
        SELECT id, symbol, strategy_name FROM live_bot_sessions WHERE status = 'RUNNING'
    """)).fetchall()

    if not rows:
        raise HTTPException(404, "No running sessions found")

    session_ids = [r[0] for r in rows]
    session_names = [f"{r[1]}({r[2]})" for r in rows]

    # Run analysis for each session in background
    async def _run_all():
        for sid in session_ids:
            try:
                await analysis_scheduler.run_manual_analysis(sid, current_user.id)
            except Exception as e:
                logger.error(f"Analysis failed for session {sid}: {e}")

    asyncio.create_task(_run_all())

    return {
        "status": "started",
        "message": f"AI analysis started for {len(session_ids)} sessions",
        "sessions": session_names,
        "session_count": len(session_ids),
    }


# --- Report Retrieval ---

@router.get("/{session_id}/ai-analysis-reports")
async def list_reports(
    session_id: str,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List analysis reports for a session."""
    rows = db.execute(text("""
        SELECT id, schedule_id, report_type, status, grade, action, risk_level,
               telegram_sent, error_message, created_at, completed_at, symbol, strategy_name
        FROM ai_analysis_reports
        WHERE session_id = :sid AND user_id = :uid
        ORDER BY created_at DESC
        LIMIT :lim OFFSET :off
    """), {"sid": session_id, "uid": current_user.id, "lim": limit, "off": offset}).fetchall()

    total = db.execute(text("""
        SELECT COUNT(*) FROM ai_analysis_reports WHERE session_id = :sid AND user_id = :uid
    """), {"sid": session_id, "uid": current_user.id}).scalar()

    return {
        "total": total,
        "reports": [
            {
                "id": r[0],
                "schedule_id": r[1],
                "report_type": r[2],
                "status": r[3],
                "grade": r[4],
                "action": r[5],
                "risk_level": r[6],
                "telegram_sent": r[7],
                "error_message": r[8],
                "created_at": r[9].isoformat() if r[9] else None,
                "completed_at": r[10].isoformat() if r[10] else None,
                "symbol": r[11],
                "strategy_name": r[12],
            }
            for r in rows
        ]
    }


@router.get("/ai-analysis-reports/{report_id}")
async def get_report_detail(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed analysis report."""
    row = db.execute(text("""
        SELECT id, schedule_id, session_id, symbol, strategy_name, report_type, status,
               trade_summary, backtest_comparison, strategy_config,
               ai_analysis, ai_model, news_data,
               grade, key_findings, recommendations, risk_level, action,
               telegram_sent, error_message, created_at, completed_at
        FROM ai_analysis_reports
        WHERE id = :rid AND user_id = :uid
    """), {"rid": report_id, "uid": current_user.id}).fetchone()

    if not row:
        raise HTTPException(404, "Report not found")

    def safe_json(val):
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    return {
        "id": row[0],
        "schedule_id": row[1],
        "session_id": row[2],
        "symbol": row[3],
        "strategy_name": row[4],
        "report_type": row[5],
        "status": row[6],
        "trade_summary": safe_json(row[7]),
        "backtest_comparison": safe_json(row[8]),
        "strategy_config": safe_json(row[9]),
        "ai_analysis": safe_json(row[10]),
        "ai_model": row[11],
        "news_data": safe_json(row[12]),
        "grade": row[13],
        "key_findings": safe_json(row[14]),
        "recommendations": safe_json(row[15]),
        "risk_level": row[16],
        "action": row[17],
        "telegram_sent": row[18],
        "error_message": row[19],
        "created_at": row[20].isoformat() if row[20] else None,
        "completed_at": row[21].isoformat() if row[21] else None,
    }
