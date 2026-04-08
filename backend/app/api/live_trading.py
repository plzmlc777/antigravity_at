import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..core.live_manager import live_manager
from ..db.session import get_db
from ..core.user_context import UserAccountContext, get_user_context
from ..core.config import DEFAULT_INITIAL_CAPITAL
from ..core.constants import Signal, Side, Level, AiMode, Mode

logger = logging.getLogger(__name__)

router = APIRouter()

class LiveBotStartRequest(BaseModel):
    symbol: str
    strategy_name: str = "time_momentum"
    strategy_config: Dict[str, Any] = {}
    initial_capital: float = DEFAULT_INITIAL_CAPITAL
    is_paper: bool = True
    account_id: Optional[int] = None  # Phase 5: Explicit account selection
    group_id: Optional[str] = None    # Phase 5: Session grouping for multi-rank parallel/exclusive
    profile_name: Optional[str] = None  # Profile name for display
    profile_id: Optional[str] = None  # Profile ID for lock detection
    auto_start: bool = False  # Phase 5: If False, create session in STOPPED state without starting engine
    ai_symbol_mode: str = "static"  # "static" | "ai" - AI symbol rotation
    ai_search_conditions: Optional[str] = None  # Natural language search conditions for AI mode
    ai_optimize_params: Optional[dict] = None  # Parameter optimization config for AI mode

class StopAllRequest(BaseModel):
    force: bool = False

@router.post("/emergency-stop")
async def emergency_kill_switch(
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Emergency global kill switch — stops ALL RUNNING live sessions across all accounts.
    Bypasses position checks. The only manual session-control surface in the AI-centric UI.
    Intended for "AI orchestrator went rogue" recovery, not routine use.
    """
    if not ctx.user_id:
        raise HTTPException(status_code=401, detail="Login required")

    from ..db.session import SessionLocal
    from ..models.live_session import LiveBotSession, SessionStatus
    db = SessionLocal()
    try:
        before = db.query(LiveBotSession).filter(
            LiveBotSession.status == SessionStatus.RUNNING
        ).count()
    finally:
        db.close()

    try:
        await live_manager.stop_all_sessions()
    except Exception as e:
        logger.error(f"emergency_kill_switch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    db = SessionLocal()
    try:
        after = db.query(LiveBotSession).filter(
            LiveBotSession.status == SessionStatus.RUNNING
        ).count()
    finally:
        db.close()

    logger.warning(f"EMERGENCY KILL SWITCH triggered by user {ctx.user_id}: {before} → {after} running sessions")
    return {
        "status": "success",
        "stopped_count": max(0, before - after),
        "remaining_running": after,
        "message": f"Emergency stop: {before - after} session(s) halted, {after} still running."
    }

@router.post("/stop-all")
async def stop_all_live_bots(
    req: StopAllRequest = StopAllRequest(),
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Stop all RUNNING sessions for the current account.
    force=True: bypass position check (used by START flow to clean up old sessions)
    force=False: block if any session holds a position (used by STOP button)
    """
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account selected")

    try:
        stopped_count = await live_manager.stop_all_sessions_for_account(ctx.account_id, force=req.force)
        return {
            "status": "success",
            "stopped_count": stopped_count,
            "message": f"Stopped {stopped_count} session(s)"
        }
    except ValueError as e:
        err_msg = str(e)
        if err_msg.startswith("POSITION_HELD|"):
            raise HTTPException(status_code=409, detail=err_msg)
        raise HTTPException(status_code=400, detail=err_msg)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start")
async def start_live_bot(
    req: LiveBotStartRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Start a new Live Trading Session.
    Phase 5: Supports explicit account_id selection.
    Note: Call /live/stop-all first if starting multiple sessions to prevent duplicates.
    """
    from ..models.account import ExchangeAccount

    # Determine which account to use
    if req.account_id is not None:
        # Phase 5: Explicit account selection - verify ownership
        account = db.query(ExchangeAccount).filter(
            ExchangeAccount.id == req.account_id,
            ExchangeAccount.user_id == ctx.user_id
        ).first()
        if not account:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        if account.is_disabled:
            raise HTTPException(status_code=400, detail="Account is disabled")
        target_account_id = req.account_id
    else:
        # Fallback to active account (legacy behavior)
        if not ctx.has_active_account:
            raise HTTPException(status_code=400, detail="No active account selected")
        target_account_id = ctx.account_id

    try:
        config = req.dict()
        config["account_id"] = target_account_id  # 선택된 계좌 ID
        session_id = await live_manager.start_session(config)
        return {"status": "success", "session_id": session_id, "message": "Live Session Started"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

async def verify_session_ownership(session_id: str, account_id: int, db: Session) -> bool:
    """Verify that the session belongs to the user's account (single account check)"""
    from ..models.live_trading import LiveBotSession
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.account_id != account_id:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")
    return True

async def verify_session_ownership_by_user(session_id: str, user_id: int, db: Session) -> bool:
    """Verify that the session belongs to any of the user's accounts"""
    from ..models.live_trading import LiveBotSession
    from ..models.account import ExchangeAccount
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    user_account_ids = [a.id for a in db.query(ExchangeAccount.id).filter(ExchangeAccount.user_id == user_id).all()]
    if session.account_id not in user_account_ids:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")
    return True

@router.get("/check-position")
async def check_session_positions(
    session_ids: Optional[str] = None,
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Check if running sessions have open positions.
    Used by frontend to decide whether to show stop confirmation or position warning.

    Args:
        session_ids: Comma-separated session IDs to check (optional).
                     If provided, only checks those sessions.
                     If omitted, checks all running sessions for the account.
    """
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account selected")

    from ..models.live_trading import LiveBotSession, SessionStatus
    from ..db.session import SessionLocal
    db = SessionLocal()
    try:
        if session_ids:
            # Check only specified sessions (selected group)
            sid_list = [s.strip() for s in session_ids.split(",") if s.strip()]
            running_sessions = db.query(LiveBotSession).filter(
                LiveBotSession.account_id == ctx.account_id,
                LiveBotSession.id.in_(sid_list),
                LiveBotSession.status == SessionStatus.RUNNING
            ).all()
        else:
            # Fallback: check all running sessions for account
            running_sessions = db.query(LiveBotSession).filter(
                LiveBotSession.account_id == ctx.account_id,
                LiveBotSession.status == SessionStatus.RUNNING
            ).all()

        for sess in running_sessions:
            pos = live_manager._check_session_position(sess.id)
            if pos:
                return {
                    "has_position": True,
                    "symbol": pos["symbol"],
                    "detail": f"{pos['symbol']} L{pos['level']} {pos['total_quantity']:.0f}주"
                }

        return {"has_position": False}
    finally:
        db.close()

@router.post("/stop/{session_id}")
async def stop_live_bot(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)
    try:
        await live_manager.stop_session(session_id)
        return {"status": "success", "message": f"Session {session_id} Stopped"}
    except ValueError as e:
        err_msg = str(e)
        if err_msg.startswith("POSITION_HELD|"):
            raise HTTPException(status_code=409, detail=err_msg)
        raise HTTPException(status_code=400, detail=err_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/{session_id}")
async def resume_session(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Resume a STOPPED session instead of creating a new one.
    Reuses the existing session ID and restores all state.
    """
    from ..models.live_trading import LiveBotSession, SessionStatus
    from ..models.account import ExchangeAccount
    from datetime import datetime

    # Find the session
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify ownership (session must belong to one of user's accounts)
    user_accounts = db.query(ExchangeAccount.id).filter(
        ExchangeAccount.user_id == ctx.user_id
    ).all()
    user_account_ids = [a.id for a in user_accounts]

    if session.account_id not in user_account_ids:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")

    # Check if session is already running
    if session.status == SessionStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Session is already running"
        )

    # Check if session is already in memory — clean up stale engine if DB says STOPPED/ERROR
    if session_id in live_manager.engines:
        engine = live_manager.engines[session_id]
        if session.status in [SessionStatus.STOPPED, SessionStatus.ERROR]:
            # DB says stopped but engine still in memory → stale engine, clean up
            logger.warning(f"[Resume] Cleaning up stale engine for session {session_id[:8]} "
                          f"(DB status={session.status}, engine in memory)")
            try:
                engine.is_running = False
                if hasattr(engine, 'adapter') and hasattr(engine.adapter, 'stop_realtime'):
                    await engine.adapter.stop_realtime([engine.symbol])
            except Exception as cleanup_err:
                logger.warning(f"[Resume] Stale engine cleanup error: {cleanup_err}")
            del live_manager.engines[session_id]
        else:
            raise HTTPException(
                status_code=400,
                detail="Session is already active in memory"
            )

    # Only allow resuming STOPPED or ERROR sessions
    if session.status not in [SessionStatus.STOPPED, SessionStatus.ERROR]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume session with status: {session.status}"
        )

    try:
        # Sync latest preset parameters before resume
        _sync_preset_params(session, db)

        # Pre-resume validation: Check balance, holdings, strategy config
        validation = await live_manager.validate_before_resume(session, db)

        if not validation["can_resume"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot resume session: {'; '.join(validation['errors'])}"
            )

        # Update session status in DB first
        session.status = SessionStatus.RUNNING
        session.is_active = True
        session.error_log = None  # Clear any previous error
        session.stopped_at = None  # Clear stopped timestamp
        # Don't update started_at - keep the original start time
        db.commit()

        # Restore the engine using existing method
        await live_manager._restore_engine(session)

        # Re-register in exclusive group if applicable
        cfg = session.strategy_config or {}
        if cfg.get("execution_mode") == "exclusive":
            live_manager.register_exclusive_session(session.account_id, session_id)

        # AI Symbol Selection: trigger initial symbol check on resume
        if getattr(session, 'ai_symbol_mode', AiMode.STATIC) == AiMode.AI and getattr(session, 'ai_search_conditions', None):
            engine = live_manager.engines.get(session_id)
            if engine:
                engine._try_ai_symbol_switch()

        return {
            "status": "success",
            "session_id": session_id,
            "message": f"Session resumed: {session.symbol} ({session.strategy_name})",
            "warnings": validation["warnings"] if validation["warnings"] else None
        }

    except Exception as e:
        # Revert DB status on failure
        session.status = SessionStatus.ERROR
        session.error_log = f"Resume failed: {str(e)}"
        db.commit()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to resume session: {str(e)}")


@router.patch("/session/{session_id}/strategy-config")
async def update_session_strategy_config(
    session_id: str,
    body: dict,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Hot-swap strategy parameters on a running session.
    Expects: { "params": { "dip_percent": 1.5, "max_buy_count": 5, ... } }
    Only works for RUNNING sessions with an active engine.
    """
    from ..models.live_trading import LiveBotSession, SessionStatus
    from ..models.account import ExchangeAccount

    params = body.get("params")
    if not params or not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="Missing 'params' dict in request body")

    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify ownership
    user_accounts = db.query(ExchangeAccount.id).filter(
        ExchangeAccount.user_id == ctx.user_id
    ).all()
    if session.account_id not in [a.id for a in user_accounts]:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")

    if session.status != SessionStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Session is not running. Use restart to apply changes.")

    if session_id not in live_manager.engines:
        raise HTTPException(status_code=400, detail="Session engine not active in memory")

    # Also update preset metadata if provided
    preset_info = body.get("preset_info")
    if preset_info:
        params["selected_preset_id"] = preset_info.get("id")
        params["selected_preset_name"] = preset_info.get("version_name")

    try:
        await live_manager.update_session_strategy_config(session_id, params)
        return {
            "status": "success",
            "message": f"Strategy parameters updated ({len(params)} params)",
            "updated_keys": list(params.keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update parameters: {str(e)}")


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Permanently delete a session and all its related data (trade executions, AI evaluations).
    Only allowed for STOPPED or ERROR sessions (not RUNNING).
    """
    from ..models.live_trading import LiveBotSession, LiveTradeExecution, LiveAIEvaluation, SessionStatus
    from ..models.analysis_report import AIAnalysisReport

    # Find the session
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify ownership (session must belong to one of user's accounts)
    from ..models.account import ExchangeAccount
    user_accounts = db.query(ExchangeAccount.id).filter(
        ExchangeAccount.user_id == ctx.user_id
    ).all()
    user_account_ids = [a.id for a in user_accounts]

    if session.account_id not in user_account_ids:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")

    # Check if session is running
    if session.status == SessionStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running session. Stop it first."
        )

    # Check if session is in memory (shouldn't happen if status is not RUNNING, but double-check)
    if session_id in live_manager.engines:
        raise HTTPException(
            status_code=400,
            detail="Session is still active in memory. Stop it first."
        )

    try:
        # Delete related AI analysis reports first (FK constraint)
        deleted_reports = db.query(AIAnalysisReport).filter(
            AIAnalysisReport.session_id == session_id
        ).delete()

        # Delete related AI evaluations
        deleted_evals = db.query(LiveAIEvaluation).filter(
            LiveAIEvaluation.session_id == session_id
        ).delete()

        # Delete related AI symbol history
        from ..models.live_trading import AISymbolHistory
        deleted_history = db.query(AISymbolHistory).filter(
            AISymbolHistory.session_id == session_id
        ).delete()

        # Delete related trade executions
        deleted_trades = db.query(LiveTradeExecution).filter(
            LiveTradeExecution.session_id == session_id
        ).delete()

        # Delete the session
        db.delete(session)
        db.commit()

        return {
            "status": "success",
            "message": f"Session deleted successfully",
            "deleted_trades": deleted_trades,
            "deleted_ai_evaluations": deleted_evals,
            "deleted_ai_reports": deleted_reports,
            "deleted_ai_history": deleted_history
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


@router.post("/session/{session_id}/archive")
async def archive_session(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Toggle archive status for a session (and all sessions in the same group).
    Archived sessions are hidden from the default list but trade history is preserved.
    """
    from ..models.live_trading import LiveBotSession, SessionStatus
    from ..models.account import ExchangeAccount

    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify ownership
    user_accounts = db.query(ExchangeAccount.id).filter(
        ExchangeAccount.user_id == ctx.user_id
    ).all()
    if session.account_id not in [a.id for a in user_accounts]:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")

    # Cannot archive running sessions
    if session.status == SessionStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot archive a running session. Stop it first.")

    new_archived = not (session.is_archived or False)

    # Archive all sessions in the same group
    if session.group_id:
        db.query(LiveBotSession).filter(
            LiveBotSession.group_id == session.group_id
        ).update({"is_archived": new_archived})
        affected = db.query(LiveBotSession).filter(
            LiveBotSession.group_id == session.group_id
        ).count()
    else:
        session.is_archived = new_archived
        affected = 1

    db.commit()
    return {
        "status": "success",
        "is_archived": new_archived,
        "affected_sessions": affected
    }


class ToggleOrdersRequest(BaseModel):
    enabled: bool

class ToggleTickExecutionRequest(BaseModel):
    mode: str  # "tick" or "candle"


class UpdateSessionSettingsRequest(BaseModel):
    initial_capital: Optional[float] = None
    is_paper: Optional[bool] = None
    account_id: Optional[int] = None  # Change account for stopped session
    rank_weights: Optional[Dict[str, float]] = None  # Capital allocation per rank (parallel mode)


@router.patch("/session/{session_id}")
async def update_session_settings(
    session_id: str,
    req: UpdateSessionSettingsRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Update settings for a STOPPED session.
    Only allowed for STOPPED or ERROR sessions (not RUNNING).

    This allows users to change capital/mode before restarting.
    """
    from ..models.live_trading import LiveBotSession, SessionStatus
    from ..models.account import ExchangeAccount

    # Find the session
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify ownership (session must belong to one of user's accounts)
    user_accounts = db.query(ExchangeAccount.id).filter(
        ExchangeAccount.user_id == ctx.user_id
    ).all()
    user_account_ids = [a.id for a in user_accounts]

    if session.account_id not in user_account_ids:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")

    # Only allow updating STOPPED or ERROR sessions
    if session.status not in [SessionStatus.STOPPED, SessionStatus.ERROR]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update settings for session with status: {session.status}. Stop the session first."
        )

    # Apply updates
    updates_made = []

    if req.initial_capital is not None:
        session.initial_capital = req.initial_capital
        # Sync initial_capital inside strategy_config to avoid DB column vs JSON divergence
        config = session.strategy_config or {}
        config["initial_capital"] = req.initial_capital
        session.strategy_config = config
        updates_made.append(f"capital → {req.initial_capital:,.0f}")

    if req.is_paper is not None:
        session.is_paper = req.is_paper
        updates_made.append(f"mode → {'Paper' if req.is_paper else 'Real'}")

    if req.account_id is not None and req.account_id != session.account_id:
        # Verify new account belongs to user
        new_account = db.query(ExchangeAccount).filter(
            ExchangeAccount.id == req.account_id,
            ExchangeAccount.user_id == ctx.user_id
        ).first()
        if not new_account:
            raise HTTPException(status_code=403, detail="Target account not found or access denied")
        if new_account.is_disabled:
            raise HTTPException(status_code=400, detail="Target account is disabled")

        old_account = db.query(ExchangeAccount).filter(ExchangeAccount.id == session.account_id).first()
        old_name = old_account.account_name if old_account else str(session.account_id)
        session.account_id = req.account_id
        updates_made.append(f"account → {new_account.account_name}")

    if req.rank_weights is not None:
        # Update rank_weights in strategy_config
        config = session.strategy_config or {}
        config["rank_weights"] = req.rank_weights
        session.strategy_config = config
        updates_made.append("rank_weights updated")

    if not updates_made:
        return {"status": "no_change", "message": "No settings were changed"}

    db.commit()

    return {
        "status": "success",
        "message": f"Session settings updated: {', '.join(updates_made)}",
        "session_id": session_id,
        "updated": {
            "initial_capital": float(session.initial_capital) if session.initial_capital else None,
            "is_paper": session.is_paper,
            "account_id": session.account_id,
            "rank_weights": req.rank_weights
        }
    }


@router.post("/toggle-orders/{session_id}")
async def toggle_orders(
    session_id: str,
    req: ToggleOrdersRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)
    try:
        await live_manager.toggle_orders(session_id, req.enabled)
        return {"status": "success", "orders_enabled": req.enabled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/toggle-mode/{session_id}")
async def toggle_mode(
    session_id: str,
    req: ToggleOrdersRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Toggle between Paper and Real mode.
    enabled=True means is_paper=True.
    """
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)
    try:
        await live_manager.toggle_mode(session_id, req.enabled)
        return {"status": "success", "is_paper": req.enabled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/toggle-mode-group/{group_id}")
async def toggle_mode_group(
    group_id: str,
    req: ToggleOrdersRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Atomically toggle Paper/Real mode for ALL sessions in a group.
    enabled=True means is_paper=True (Paper mode).
    All-or-nothing: either all sessions switch or none do.
    """
    # Verify at least one session in the group belongs to this user
    group_sessions = db.query(LiveBotSession).filter_by(group_id=group_id).all()
    if not group_sessions:
        raise HTTPException(status_code=404, detail=f"No sessions found for group {group_id}")
    for sess in group_sessions:
        if sess.account_id:
            account = db.query(ExchangeAccount).filter_by(id=sess.account_id).first()
            if account and account.user_id != ctx.user_id:
                raise HTTPException(status_code=403, detail="Not authorized for this session group")
            break
    try:
        result = await live_manager.toggle_mode_group(group_id, req.enabled)
        return {
            "status": "success",
            "is_paper": req.enabled,
            "count": result["count"],
            "session_ids": result["session_ids"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toggle-tick-execution/{session_id}")
async def toggle_tick_execution(
    session_id: str,
    req: ToggleTickExecutionRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """Hot-swap tick execution mode (tick/candle) without stopping the session."""
    if req.mode not in ("tick", "candle"):
        raise HTTPException(status_code=400, detail="mode must be 'tick' or 'candle'")
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)
    try:
        await live_manager.toggle_tick_execution(session_id, req.mode)
        return {"status": "success", "tick_execution": req.mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/liquidate/{session_id}")
async def liquidate_session(
    session_id: str,
    auto_stop: bool = True,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Emergency: Market Sell all positions.
    auto_stop=True (default): also stop the session after liquidation.
    auto_stop=False: only close positions, keep session running.
    """
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)
    try:
        result = await live_manager.liquidate_session(session_id, auto_stop=auto_stop)

        if result.get("action") == "market_closed":
            qty = result.get("qty", 0)
            symbol = result.get("symbol", "")
            raise HTTPException(
                status_code=409,
                detail=f"MARKET_CLOSED|{symbol} {qty}주 보유 중. 거래 시간(09:00~15:30)에 다시 시도해주세요."
            )

        if result.get("action") == "no_position":
            return {"status": "success", "message": f"No position to close for {result.get('symbol', '')}.", "result": result}

        msg = "Liquidation order sent and session stopped." if auto_stop else "Liquidation order sent. Session still running."
        return {"status": "success", "message": msg, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_live_status(
    all_accounts: bool = False,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Get status of active Live Sessions.

    Args:
        all_accounts: If True, returns sessions across all user's accounts (for Session Switcher).
                     If False, returns only current active account's sessions.
    """
    if all_accounts:
        # Phase 5: Get all account IDs for this user
        from ..models.account import ExchangeAccount
        user_accounts = db.query(ExchangeAccount.id).filter(
            ExchangeAccount.user_id == ctx.user_id,
            ExchangeAccount.is_disabled == False
        ).all()
        account_ids = [a.id for a in user_accounts]
        return await live_manager.get_status(account_ids=account_ids)
    else:
        return await live_manager.get_status(account_id=ctx.account_id)


@router.get("/sessions")
async def get_all_sessions(
    all_accounts: bool = False,
    include_stopped: bool = True,
    include_archived: bool = False,
    limit: int = 50,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Phase 5: Get ALL sessions from DB (including STOPPED, PAUSED, ERROR).

    Unlike /status which only returns in-memory running sessions,
    this endpoint queries the database for session records.

    Args:
        all_accounts: If True, returns sessions across all user's accounts
        include_stopped: If True, includes STOPPED sessions (default True)
        limit: Maximum number of sessions to return (default 50)

    Returns:
        List of sessions with status, grouped by (account_id, strategy_name)
    """
    from ..models.live_trading import LiveBotSession, SessionStatus
    from ..models.account import ExchangeAccount
    from datetime import datetime

    # Determine which accounts to query
    if all_accounts:
        user_accounts = db.query(ExchangeAccount.id).filter(
            ExchangeAccount.user_id == ctx.user_id,
            ExchangeAccount.is_disabled == False
        ).all()
        account_ids = [a.id for a in user_accounts]
    else:
        account_ids = [ctx.account_id] if ctx.has_active_account else []

    if not account_ids:
        return []

    # Build query
    query = db.query(LiveBotSession).filter(
        LiveBotSession.account_id.in_(account_ids)
    )

    if not include_stopped:
        query = query.filter(LiveBotSession.status != SessionStatus.STOPPED)

    if not include_archived:
        query = query.filter(LiveBotSession.is_archived != True)

    # Order by status priority (RUNNING first), then by started_at desc
    sessions = query.order_by(
        LiveBotSession.status,  # RUNNING < PAUSED < STOPPED < ERROR (alphabetically)
        LiveBotSession.started_at.desc()
    ).limit(limit).all()

    # Build symbol name map from multiple sources
    symbol_name_map = {}  # symbol_code -> symbol_name

    # Source 1: User-level saved_symbols
    from ..models.user import User
    user = db.query(User).filter(User.id == ctx.user_id).first()
    if user and user.saved_symbols:
        for sym in user.saved_symbols:
            if sym.get("code") and sym.get("name"):
                symbol_name_map[sym["code"]] = sym["name"]

    # Source 2: Account-level saved_symbols
    from ..models.account import ExchangeAccount as EA
    user_accounts = db.query(EA.saved_symbols).filter(
        EA.user_id == ctx.user_id
    ).all()
    for (acct_symbols,) in user_accounts:
        if acct_symbols:
            for sym in acct_symbols:
                if sym.get("code") and sym.get("name") and sym["code"] not in symbol_name_map:
                    symbol_name_map[sym["code"]] = sym["name"]

    # Source 3: Profile-level saved_symbols + rank_configs (if profile_id available)
    profile_ids = list({sess.profile_id for sess in sessions if sess.profile_id})
    # profile_id → {rank_index: selected_preset_id}
    profile_preset_map = {}
    if profile_ids:
        from ..models.live_trading import StrategyProfile
        profiles = db.query(StrategyProfile.id, StrategyProfile.saved_symbols, StrategyProfile.rank_configs).filter(
            StrategyProfile.id.in_(profile_ids)
        ).all()
        for p in profiles:
            if p.saved_symbols:
                for sym in p.saved_symbols:
                    if sym.get("code") and sym.get("name") and sym["code"] not in symbol_name_map:
                        symbol_name_map[sym["code"]] = sym["name"]
            # Build preset map from rank_configs
            if p.rank_configs:
                rank_map = {}
                for rc in p.rank_configs:
                    rank_idx = rc.get("rank")
                    preset_id = rc.get("selected_preset_id") or rc.get("selected_version_id")
                    if rank_idx is not None and preset_id:
                        rank_map[int(rank_idx)] = preset_id
                if rank_map:
                    profile_preset_map[p.id] = rank_map

    # Helper: enrich strategy_config with selected_preset_id from profile
    def _enrich_strategy_config(sess, preset_map):
        config = dict(sess.strategy_config) if sess.strategy_config else {}
        if not config.get("selected_preset_id") and sess.profile_id and sess.profile_id in preset_map:
            rank = config.get("rank")
            if rank is not None:
                pid = preset_map[sess.profile_id].get(int(rank))
                if pid:
                    config["selected_preset_id"] = pid
        return config

    # Check which sessions are actually running in memory
    running_ids = set(live_manager.engines.keys())

    results = []
    for sess in sessions:
        # Determine effective status (memory vs DB can differ)
        is_in_memory = sess.id in running_ids
        # Handle both Enum and string status (DB might return string)
        status_str = sess.status.value if hasattr(sess.status, 'value') else str(sess.status)
        effective_status = status_str

        # If DB says RUNNING but not in memory, it's effectively STOPPED (crashed?)
        is_running_in_db = status_str == 'RUNNING'
        if is_running_in_db and not is_in_memory:
            effective_status = "STOPPED"

        # Get additional info from running engine if available
        engine_info = {}
        if is_in_memory:
            eng = live_manager.engines.get(sess.id)
            if eng:
                engine_info = {
                    "orders_enabled": eng.orders_enabled,
                    "current_price": eng.context.get_current_price(sess.symbol),
                    "pnl": eng.context.calculate_pnl(),
                }

        results.append({
            "session_id": sess.id,
            "account_id": sess.account_id,
            "group_id": sess.group_id,  # Session group ID for multi-rank parallel/exclusive
            "profile_name": sess.profile_name,  # Profile name for display
            "profile_id": sess.profile_id,  # Profile ID for lock detection
            "symbol": sess.symbol,
            "symbol_name": symbol_name_map.get(sess.symbol) or (sess.strategy_config or {}).get("symbol_name") or sess.symbol,
            "strategy_name": sess.strategy_name,
            "status": effective_status,
            "is_running": is_in_memory,
            "is_paper": sess.is_paper,
            "is_active": sess.is_active,
            "initial_capital": float(sess.initial_capital) if sess.initial_capital else 0,
            "started_at": sess.started_at.isoformat() if sess.started_at else None,
            "stopped_at": sess.stopped_at.isoformat() if sess.stopped_at else None,
            "error_log": sess.error_log,
            "is_archived": sess.is_archived or False,
            "strategy_config": _enrich_strategy_config(sess, profile_preset_map),
            "ai_symbol_mode": sess.ai_symbol_mode or AiMode.STATIC,
            "ai_search_conditions": sess.ai_search_conditions or "",
            "ai_optimize_params": sess.ai_optimize_params,
            "original_symbol": getattr(sess, 'original_symbol', None) or sess.symbol,
            "original_symbol_name": getattr(sess, 'original_symbol_name', None),
            **engine_info
        })

    return results


@router.get("/accumulated-stats")
async def get_accumulated_stats(
    symbols: str = "",
    strategy_name: str = "",
    session_ids: str = "",
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Get accumulated trade stats for symbols (even when no session is running).
    Query params:
        - symbols=005930,000660 (comma-separated)
        - strategy_name=rsi_martingale (optional, filter by strategy)
    Returns detailed stats including win rate, recent 10 cycles, max/min/avg PnL
    Aggregates cycles for current user's account sessions with matching (symbol, strategy_name).
    """
    from ..models.live_trading import LiveTradeExecution, ExecutionStatus, LiveBotSession

    if not ctx.has_active_account:
        return {}

    try:
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else []
        session_id_list = [s.strip() for s in session_ids.split(",") if s.strip()] if session_ids else []

        # Build query - filter by user's account
        query = db.query(LiveTradeExecution).join(LiveBotSession).filter(
            LiveTradeExecution.status == ExecutionStatus.FILLED,
            LiveBotSession.account_id == ctx.account_id
        )

        # If strategy_name is provided, filter by sessions with that strategy
        if strategy_name:
            query = query.filter(LiveBotSession.strategy_name == strategy_name)

        # session_ids takes priority over symbols for AI mode sessions
        if session_id_list:
            query = query.filter(LiveTradeExecution.session_id.in_(session_id_list))
        elif symbol_list:
            query = query.filter(LiveTradeExecution.symbol.in_(symbol_list))

        executions = query.order_by(LiveTradeExecution.signal_timestamp).all()

        # Group by symbol and mode, track per-cycle PnLs and durations
        stats_by_symbol = {}
        for ex in executions:
            sym = ex.symbol
            if sym not in stats_by_symbol:
                stats_by_symbol[sym] = {
                    Mode.PAPER: {
                        "trades": 0, "buys": 0, "sells": 0,
                        "buy_queue": [],  # Track buys for FIFO matching
                        "cycle_pnls": [],  # Per-cycle PnL list (absolute, KRW)
                        "cycle_pnl_pcts": [],  # Per-cycle PnL % (for backtest compat)
                        "cycle_entry_costs": [],  # Entry cost per cycle (for % calc)
                        "cycle_durations": [],  # Per-cycle duration in minutes
                        "first_buy_time": None,  # First BUY timestamp in current cycle
                        "trade_dates": set(),  # Unique trade dates (for activity rate)
                        "cumulative_pnls": [],  # Cumulative PnL after each cycle (for MDD)
                    },
                    Mode.REAL: {
                        "trades": 0, "buys": 0, "sells": 0,
                        "buy_queue": [],
                        "cycle_pnls": [],
                        "cycle_pnl_pcts": [],
                        "cycle_entry_costs": [],
                        "cycle_durations": [],
                        "first_buy_time": None,
                        "trade_dates": set(),
                        "cumulative_pnls": [],
                    },
                }

            is_paper = ex.is_paper if ex.is_paper is not None else True
            key = Mode.PAPER if is_paper else Mode.REAL
            s = stats_by_symbol[sym][key]
            s["trades"] += 1
            qty = ex.filled_quantity or 0.0
            price = ex.executed_price or 0.0

            # Track trade date for activity rate
            if ex.signal_timestamp:
                s["trade_dates"].add(ex.signal_timestamp.date())

            # Use trade_metadata to distinguish entries vs closes (supports short positions)
            metadata = ex.trade_metadata or {}
            is_close = metadata.get("level") == Level.CLOSE
            position_side = metadata.get("position_side", "").lower()
            is_short_entry = (position_side == Side.SHORT
                              and isinstance(metadata.get("level"), int))

            if ex.signal_type == Signal.BUY:
                s["buys"] += 1
            elif ex.signal_type == Signal.SELL:
                s["sells"] += 1

            # Determine if this is an entry or a cycle close
            is_entry = False
            is_cycle_close = False

            if is_close:
                is_cycle_close = True
            elif ex.signal_type == Signal.BUY and not is_close:
                if position_side != Side.SHORT:
                    is_entry = True  # Long entry
                # BUY with position_side=short and level=CLOSE → already handled above
            elif ex.signal_type == Signal.SELL and not is_close:
                if is_short_entry:
                    is_entry = True  # Short entry

            if is_entry:
                # Track first entry time for cycle duration
                if s["first_buy_time"] is None:
                    s["first_buy_time"] = ex.signal_timestamp
                s["buy_queue"].append({"qty": qty, "price": price, "timestamp": ex.signal_timestamp})

            elif is_cycle_close:
                # Match with entries (FIFO) to calculate cycle PnL
                close_qty = qty
                close_price = price
                entry_cost = 0.0
                matched_qty = 0.0

                while close_qty > 0 and s["buy_queue"]:
                    entry = s["buy_queue"][0]
                    match_qty = min(close_qty, entry["qty"])
                    entry_cost += match_qty * entry["price"]
                    matched_qty += match_qty
                    close_qty -= match_qty
                    entry["qty"] -= match_qty
                    if entry["qty"] <= 0:
                        s["buy_queue"].pop(0)

                if matched_qty > 0:
                    # PnL depends on direction
                    if position_side == Side.SHORT:
                        cycle_pnl = entry_cost - (close_price * matched_qty)  # Short: sell high, buy low
                    else:
                        cycle_pnl = (close_price * matched_qty) - entry_cost  # Long: buy low, sell high
                    s["cycle_pnls"].append(cycle_pnl)
                    s["cycle_entry_costs"].append(entry_cost)

                    # Calculate cycle PnL percentage
                    cycle_pnl_pct = (cycle_pnl / entry_cost * 100) if entry_cost > 0 else 0
                    s["cycle_pnl_pcts"].append(cycle_pnl_pct)

                    # Track cumulative PnL for max drawdown calculation
                    prev_cum = s["cumulative_pnls"][-1] if s["cumulative_pnls"] else 0
                    s["cumulative_pnls"].append(prev_cum + cycle_pnl)

                    # Calculate cycle duration (first entry to close)
                    if s["first_buy_time"] and ex.signal_timestamp:
                        duration_mins = (ex.signal_timestamp - s["first_buy_time"]).total_seconds() / 60
                        s["cycle_durations"].append(duration_mins)

                # Reset first_buy_time if no more entries in queue (cycle complete)
                if not s["buy_queue"]:
                    s["first_buy_time"] = None

        # Calculate final stats
        import statistics as stat_module
        result = {}
        for sym, modes in stats_by_symbol.items():
            result[sym] = {Mode.PAPER: {}, Mode.REAL: {}}
            for key in [Mode.PAPER, Mode.REAL]:
                s = modes[key]
                cycle_pnls = s["cycle_pnls"]  # Absolute (KRW)
                cycle_pnl_pcts = s["cycle_pnl_pcts"]  # Percentage
                cumulative_pnls = s["cumulative_pnls"]
                cycles = len(cycle_pnls)
                cycle_durations = s["cycle_durations"]
                trade_dates = s["trade_dates"]

                if cycles > 0:
                    total_pnl = sum(cycle_pnls)
                    total_entry_cost = sum(s["cycle_entry_costs"]) if s["cycle_entry_costs"] else 0
                    wins = sum(1 for p in cycle_pnls if p > 0)
                    win_rate = (wins / cycles) * 100

                    # Recent 10 cycles (for trend indicator)
                    recent_10 = cycle_pnls[-10:] if cycles >= 10 else cycle_pnls
                    recent_wins = sum(1 for p in recent_10 if p > 0)
                    recent_win_rate = (recent_wins / len(recent_10)) * 100 if recent_10 else 0

                    # === Backtest-compatible metrics (% based) ===
                    # Total return (% of total entry cost)
                    total_return = (total_pnl / total_entry_cost * 100) if total_entry_cost > 0 else 0

                    # Profit Factor: gross_profit / gross_loss
                    gross_profit = sum(p for p in cycle_pnls if p > 0)
                    gross_loss = abs(sum(p for p in cycle_pnls if p < 0))
                    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99

                    # Sharpe Ratio (cycle-based)
                    if len(cycle_pnl_pcts) > 1:
                        pct_stdev = stat_module.stdev(cycle_pnl_pcts)
                        sharpe_ratio = (stat_module.mean(cycle_pnl_pcts) / pct_stdev * (len(cycle_pnl_pcts) ** 0.5)) if pct_stdev > 0 else 0
                    else:
                        sharpe_ratio = 0

                    # Max Drawdown (from cumulative PnL, as % of peak)
                    max_drawdown = 0
                    if cumulative_pnls:
                        peak = cumulative_pnls[0]
                        for cum in cumulative_pnls:
                            if cum > peak:
                                peak = cum
                            drawdown = peak - cum
                            # Convert to % of peak (or entry cost if peak is 0)
                            dd_pct = (drawdown / peak * 100) if peak > 0 else (drawdown / total_entry_cost * 100 if total_entry_cost > 0 else 0)
                            if dd_pct > max_drawdown:
                                max_drawdown = dd_pct

                    # Avg PnL % per cycle
                    avg_pnl_pct = sum(cycle_pnl_pcts) / cycles if cycles > 0 else 0

                    # Max Profit / Max Loss (% based)
                    max_profit_pct = max(cycle_pnl_pcts) if cycle_pnl_pcts else 0
                    max_loss_pct = min(cycle_pnl_pcts) if cycle_pnl_pcts else 0

                    # Activity Rate (% of days with trades)
                    if trade_dates:
                        min_date = min(trade_dates)
                        max_date = max(trade_dates)
                        total_days = (max_date - min_date).days + 1
                        activity_rate = (len(trade_dates) / total_days * 100) if total_days > 0 else 0
                    else:
                        activity_rate = 0
                        total_days = 0

                    # === Live-only metrics (absolute KRW) ===
                    max_pnl = max(cycle_pnls)
                    min_pnl = min(cycle_pnls)
                    avg_pnl = total_pnl / cycles

                    # Holding time stats (in minutes)
                    if cycle_durations:
                        avg_holding_time = sum(cycle_durations) / len(cycle_durations)
                        max_holding_time = max(cycle_durations)
                        min_holding_time = min(cycle_durations)
                    else:
                        avg_holding_time = None
                        max_holding_time = None
                        min_holding_time = None
                else:
                    # Zero trades case
                    total_pnl = 0
                    total_return = 0
                    win_rate = 0
                    recent_win_rate = 0
                    profit_factor = 0
                    sharpe_ratio = 0
                    max_drawdown = 0
                    avg_pnl_pct = 0
                    max_profit_pct = 0
                    max_loss_pct = 0
                    activity_rate = 0
                    total_days = 0
                    max_pnl = 0
                    min_pnl = 0
                    avg_pnl = 0
                    avg_holding_time = None
                    max_holding_time = None
                    min_holding_time = None

                result[sym][key] = {
                    # === Backtest-compatible stats (same keys as STAT_COLUMNS) ===
                    "total_return": round(total_return, 2),  # %
                    "profit_factor": round(profit_factor, 2),
                    "win_rate": round(win_rate, 1),  # %
                    "recent_10_win_rate": round(recent_win_rate, 1),  # %
                    "sharpe_ratio": round(sharpe_ratio, 2),
                    "total_cycles": cycles,  # = cycle count
                    "stability_score": None,  # N/A for live (needs equity curve)
                    "acceleration_score": None,  # N/A for live
                    "activity_rate": round(activity_rate, 1),  # %
                    "avg_pnl": round(avg_pnl_pct, 2),  # % per cycle
                    "avg_holding_time": round(avg_holding_time) if avg_holding_time is not None else None,
                    "max_holding_time": round(max_holding_time) if max_holding_time is not None else None,
                    "min_holding_time": round(min_holding_time) if min_holding_time is not None else None,
                    "max_profit": round(max_profit_pct, 2),  # %
                    "max_loss": round(max_loss_pct, 2),  # %
                    "max_drawdown": round(max_drawdown, 2),  # %
                    "total_days": total_days,
                    # === Live-only alpha stats (absolute KRW) ===
                    "trades": s["trades"],  # raw order count
                    "buys": s["buys"],
                    "sells": s["sells"],
                    "cycles": cycles,
                    "realized_pnl": round(total_pnl, 0),  # KRW
                    "avg_pnl_krw": round(avg_pnl, 0),  # KRW per cycle
                    "max_pnl_krw": round(max_pnl, 0),  # KRW
                    "min_pnl_krw": round(min_pnl, 0),  # KRW
                }

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import WebSocket, WebSocketDisconnect
import asyncio

@router.websocket("/ws/{session_id}")
async def websocket_live_feed(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for Real-time Tick & Candle updates.
    """
    await websocket.accept()
    
    queue = asyncio.Queue(maxsize=100)
    listeners = None
    
    try:
        # Subscribe
        listeners = await live_manager.subscribe_to_session(session_id, queue)
        
        while True:
            # Wait for data from queue
            data = await queue.get()
            
            # Send to Frontend
            await websocket.send_json(data)
            
    except WebSocketDisconnect:
        # Expected disconnect
        pass
    except Exception as e:
        print(f"WS Error: {e}")
        # Optional: Send error to client before closing?
    finally:
        # Unsubscribe
        if listeners:
            live_manager.unsubscribe_from_session(session_id, listeners)
        # await websocket.close() # Usually auto-closed by FastAPI on disconnect exception


from ..core.market_data_router import market_data_router

@router.websocket("/ws/watch/{symbol}")
async def websocket_watch_symbol(websocket: WebSocket, symbol: str):
    """
    Watch real-time ticks for a specific symbol (No Bot required).
    """
    # Connect directly to Router
    await market_data_router.connect(websocket, symbol)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: Parameter Versioning - Performance Analysis API
# ═══════════════════════════════════════════════════════════════════════════════

import hashlib
import json


def _sync_preset_params(session, db):
    """
    Sync latest profile rank_configs into session's strategy_config before resume.
    Profile stores the authoritative parameter values per rank.
    On resume, we pull the latest from the profile to pick up any changes
    the user made in the Integrated Portfolio page.
    """
    from ..models.live_trading import StrategyProfile

    profile_id = session.profile_id
    if not profile_id:
        return

    cfg = dict(session.strategy_config or {})
    rank = cfg.get("rank")
    if rank is None:
        return

    profile = db.query(StrategyProfile).filter_by(id=profile_id).first()
    if not profile or not profile.rank_configs:
        return

    # Find matching rank_config from profile
    rank_cfg = None
    for rc in profile.rank_configs:
        if rc.get("rank") == rank:
            rank_cfg = rc
            break
    if not rank_cfg:
        return

    # Keys to skip (metadata, not strategy params)
    skip_keys = {
        "uuid", "tabName", "rank", "symbol", "symbol_name", "is_active",
        "days", "from_date", "to_date", "optValues", "optEnabled",
        "lastOptTaskId", "parameter_presets", "session_id",
    }

    # Merge profile rank_config params into session strategy_config
    updated_keys = []
    for key, value in rank_cfg.items():
        if key in skip_keys:
            continue
        if cfg.get(key) != value:
            cfg[key] = value
            updated_keys.append(key)

    if updated_keys:
        session.strategy_config = cfg
        db.commit()
        logger.info(f"[PresetSync] Session {session.id[:8]}: synced {len(updated_keys)} params from profile "
                     f"(rank {rank}): {updated_keys[:10]}")


def _create_config_hash(config_snapshot: dict) -> str:
    """
    Create a deterministic hash from config params for grouping.
    Only uses 'params' key to ignore timestamp differences.
    """
    if not config_snapshot:
        return "no_config"

    params = config_snapshot.get("params", config_snapshot)
    # Sort keys for deterministic hashing
    params_str = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(params_str.encode()).hexdigest()[:12]


def _extract_key_params(config_snapshot: dict) -> dict:
    """
    Extract key parameters for display (human-readable summary).
    """
    if not config_snapshot:
        return {}

    params = config_snapshot.get("params", {})
    strategy_id = config_snapshot.get("strategy_id", "unknown")

    # Extract commonly important params based on strategy
    key_params = {
        "strategy_id": strategy_id,
    }

    if strategy_id in ["dip_martingale", "rsi_martingale"]:
        key_params.update({
            "target_dip": params.get("target_dip"),
            "take_profit": params.get("take_profit"),
            "max_levels": params.get("max_levels"),
            "trailing_trigger": params.get("trailing_trigger"),
            "trailing_stop": params.get("trailing_stop"),
        })
    elif strategy_id == "time_momentum":
        key_params.update({
            "target_percent": params.get("target_percent"),
            "direction": params.get("direction"),
            "start_time": params.get("start_time"),
            "stop_time": params.get("stop_time"),
        })

    # Remove None values
    return {k: v for k, v in key_params.items() if v is not None}


@router.get("/parameter-analysis")
async def get_parameter_analysis(
    symbol: str = "",
    mode: str = "paper",
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Analyze trade performance grouped by config_snapshot (parameter versions).

    Returns performance stats for each unique parameter configuration:
    - config_hash: unique identifier for the parameter set
    - key_params: human-readable summary of important parameters
    - cycles: number of completed buy-sell cycles
    - win_rate: percentage of profitable cycles
    - total_pnl: sum of realized PnL
    - avg_pnl: average PnL per cycle
    - max_pnl / min_pnl: best and worst cycle

    Query params:
    - symbol: filter by symbol (optional)
    - mode: "paper" or "real" (default: paper)
    """
    from ..models.live_trading import LiveTradeExecution, ExecutionStatus, LiveBotSession

    if not ctx.has_active_account:
        return {"message": "No active account found", "data": []}

    try:
        is_paper = mode.lower() == Mode.PAPER

        # Query filled executions with config_snapshot - filter by user's account
        query = db.query(LiveTradeExecution).join(LiveBotSession).filter(
            LiveTradeExecution.status == ExecutionStatus.FILLED,
            LiveTradeExecution.is_paper == is_paper,
            LiveTradeExecution.config_snapshot.isnot(None),
            LiveBotSession.account_id == ctx.account_id
        )

        if symbol:
            query = query.filter(LiveTradeExecution.symbol == symbol)

        executions = query.order_by(LiveTradeExecution.signal_timestamp).all()

        if not executions:
            return {"message": "No trades with config_snapshot found", "data": []}

        # Group by config_hash and calculate stats
        # Structure: {config_hash: {buys: [...], sells: [...], config_snapshot: {...}}}
        groups = {}

        for ex in executions:
            config_hash = _create_config_hash(ex.config_snapshot)

            if config_hash not in groups:
                groups[config_hash] = {
                    "buys": [],
                    "sells": [],
                    "config_snapshot": ex.config_snapshot,
                    "symbol": ex.symbol,
                }

            qty = ex.filled_quantity or 0
            price = ex.executed_price or 0

            if ex.signal_type == Signal.BUY:
                groups[config_hash]["buys"].append({"qty": qty, "price": price})
            elif ex.signal_type == Signal.SELL:
                groups[config_hash]["sells"].append({"qty": qty, "price": price, "buy_queue": []})

        # Calculate per-config stats using FIFO matching
        results = []

        for config_hash, data in groups.items():
            buy_queue = list(data["buys"])  # Copy for FIFO
            cycle_pnls = []

            for sell in data["sells"]:
                sell_qty = sell["qty"]
                sell_price = sell["price"]
                buy_cost = 0.0
                matched_qty = 0.0

                while sell_qty > 0 and buy_queue:
                    buy = buy_queue[0]
                    match_qty = min(sell_qty, buy["qty"])
                    buy_cost += match_qty * buy["price"]
                    matched_qty += match_qty
                    sell_qty -= match_qty
                    buy["qty"] -= match_qty
                    if buy["qty"] <= 0:
                        buy_queue.pop(0)

                if matched_qty > 0:
                    cycle_pnl = (sell_price * matched_qty) - buy_cost
                    cycle_pnls.append(cycle_pnl)

            cycles = len(cycle_pnls)
            if cycles == 0:
                continue

            total_pnl = sum(cycle_pnls)
            wins = sum(1 for p in cycle_pnls if p > 0)
            win_rate = (wins / cycles) * 100
            avg_pnl = total_pnl / cycles
            max_pnl = max(cycle_pnls)
            min_pnl = min(cycle_pnls)

            results.append({
                "config_hash": config_hash,
                "symbol": data["symbol"],
                "key_params": _extract_key_params(data["config_snapshot"]),
                "full_config": data["config_snapshot"],
                "cycles": cycles,
                "total_cycles": len(data["buys"]) + len(data["sells"]),
                "win_rate": round(win_rate, 1),
                "total_pnl": round(total_pnl, 0),
                "avg_pnl": round(avg_pnl, 0),
                "max_pnl": round(max_pnl, 0),
                "min_pnl": round(min_pnl, 0),
            })

        # Sort by cycles (most traded config first)
        results.sort(key=lambda x: x["cycles"], reverse=True)

        return {
            "mode": mode,
            "symbol": symbol or "all",
            "total_configs": len(results),
            "data": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: Parameter Version Management API
# ═══════════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel as PydanticBaseModel

class ParameterVersionCreate(PydanticBaseModel):
    strategy_id: str
    symbol: Optional[str] = None
    description: str  # User provides description, auto-numbered prefix will be added
    params: Dict[str, Any]
    is_default: bool = False

MAX_VERSIONS_PER_RANK = 20  # Maximum versions per strategy_id + symbol combination

class ParameterVersionUpdate(PydanticBaseModel):
    version_name: Optional[str] = None
    description: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


@router.get("/parameter-versions")
async def list_parameter_versions(
    strategy_id: str = "",
    symbol: str = "",
    include_all_symbols: bool = False,
    include_inactive: bool = False
):
    """
    List all saved parameter versions.

    Query params:
    - strategy_id: filter by strategy (e.g., "dip_martingale")
    - symbol: filter by symbol (required unless include_all_symbols=True)
    - include_all_symbols: skip symbol filter, return all symbols
    - include_inactive: include soft-deleted versions

    Returns:
    - total: number of versions
    - max_versions: maximum allowed versions per rank
    - remaining_slots: how many more versions can be saved
    - data: list of versions with is_in_use flag
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion, LiveBotSession, SessionStatus

    db = SessionLocal()
    try:
        query = db.query(StrategyParameterVersion)

        if not include_inactive:
            query = query.filter(StrategyParameterVersion.is_active == True)

        if strategy_id:
            query = query.filter(StrategyParameterVersion.strategy_id == strategy_id)

        # Symbol filtering: consistent with create endpoint
        if not include_all_symbols:
            if symbol:
                query = query.filter(StrategyParameterVersion.symbol == symbol)
            else:
                query = query.filter(StrategyParameterVersion.symbol.is_(None))

        versions = query.order_by(StrategyParameterVersion.version_name.asc()).all()

        # Get active session config hashes for checking if versions are in use
        active_config_hashes = set()
        if strategy_id:
            active_sessions_query = db.query(LiveBotSession).filter(
                LiveBotSession.status == SessionStatus.RUNNING,
                LiveBotSession.strategy_name == strategy_id,
            )
            if symbol:
                active_sessions_query = active_sessions_query.filter(
                    LiveBotSession.symbol == symbol
                )
            else:
                active_sessions_query = active_sessions_query.filter(
                    LiveBotSession.symbol.is_(None)
                )
            for session in active_sessions_query.all():
                session_hash = _create_config_hash(session.strategy_config)
                active_config_hashes.add(session_hash)

        return {
            "total": len(versions),
            "max_versions": MAX_VERSIONS_PER_RANK,
            "remaining_slots": max(0, MAX_VERSIONS_PER_RANK - len(versions)),
            "data": [
                {
                    "id": v.id,
                    "strategy_id": v.strategy_id,
                    "symbol": v.symbol,
                    "version_name": v.version_name,
                    "description": v.description,
                    "params": v.params,
                    "config_hash": v.config_hash,
                    "performance_stats": v.performance_stats,
                    "is_default": v.is_default,
                    "is_in_use": v.config_hash in active_config_hashes if v.config_hash else False,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "updated_at": v.updated_at.isoformat() if v.updated_at else None,
                }
                for v in versions
            ]
        }
    finally:
        db.close()


@router.post("/parameter-versions")
async def create_parameter_version(req: ParameterVersionCreate):
    """
    Save current parameters as a named version.
    Auto-generates version number in format: 001_description
    Maximum versions per strategy_id + symbol combination.
    When limit is reached, auto-archives the oldest non-default, non-in-use version.
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion, LiveBotSession, SessionStatus
    from datetime import datetime
    import uuid
    import re

    db = SessionLocal()
    try:
        # Count existing versions for this strategy_id + symbol
        existing_query = db.query(StrategyParameterVersion).filter(
            StrategyParameterVersion.strategy_id == req.strategy_id,
            StrategyParameterVersion.is_active == True
        )
        if req.symbol:
            existing_query = existing_query.filter(StrategyParameterVersion.symbol == req.symbol)
        else:
            existing_query = existing_query.filter(StrategyParameterVersion.symbol.is_(None))

        existing_versions = existing_query.all()

        # Auto-archive when limit reached
        archived_version_name = None
        if len(existing_versions) >= MAX_VERSIONS_PER_RANK:
            # Get active session config hashes to protect in-use versions
            active_config_hashes = set()
            active_sessions_query = db.query(LiveBotSession).filter(
                LiveBotSession.status == SessionStatus.RUNNING,
                LiveBotSession.strategy_name == req.strategy_id,
            )
            if req.symbol:
                active_sessions_query = active_sessions_query.filter(
                    LiveBotSession.symbol == req.symbol
                )
            else:
                active_sessions_query = active_sessions_query.filter(
                    LiveBotSession.symbol.is_(None)
                )
            for session in active_sessions_query.all():
                session_hash = _create_config_hash(session.strategy_config)
                active_config_hashes.add(session_hash)

            # Find oldest non-default, non-in-use version to archive
            archivable = [
                v for v in sorted(existing_versions, key=lambda v: v.created_at or datetime.min)
                if not v.is_default and (not v.config_hash or v.config_hash not in active_config_hashes)
            ]
            if archivable:
                oldest = archivable[0]
                oldest.is_active = False  # Soft delete (archive)
                archived_version_name = oldest.version_name
                # Remove from existing_versions for numbering
                existing_versions = [v for v in existing_versions if v.id != oldest.id]
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Maximum {MAX_VERSIONS_PER_RANK} versions. All versions are default or in active use — delete manually."
                )

        # Find the next available number by scanning existing version_names
        used_numbers = set()
        for v in existing_versions:
            if v.version_name:
                # Extract number from format "NNN_description"
                match = re.match(r'^(\d{3})_', v.version_name)
                if match:
                    used_numbers.add(int(match.group(1)))

        # Find the lowest available number starting from 1
        next_number = 1
        while next_number in used_numbers:
            next_number += 1

        # Generate version_name with format "001_description"
        # Clean description: remove special characters, limit length
        clean_desc = re.sub(r'[^\w\s가-힣-]', '', req.description or 'unnamed').strip()
        clean_desc = clean_desc[:30] if clean_desc else 'unnamed'  # Limit to 30 chars
        version_name = f"{next_number:03d}_{clean_desc}"

        # Generate config hash for comparison
        config_hash = _create_config_hash({"params": req.params})

        # If marking as default, unset other defaults for this strategy
        if req.is_default:
            db.query(StrategyParameterVersion).filter(
                StrategyParameterVersion.strategy_id == req.strategy_id,
                StrategyParameterVersion.is_default == True
            ).update({"is_default": False})

        new_version = StrategyParameterVersion(
            id=str(uuid.uuid4()),
            strategy_id=req.strategy_id,
            symbol=req.symbol,
            version_name=version_name,
            description=req.description,
            params=req.params,
            config_hash=config_hash,
            is_default=req.is_default,
        )
        db.add(new_version)
        db.commit()
        db.refresh(new_version)

        result = {
            "status": "success",
            "message": f"Version '{version_name}' saved",
            "data": {
                "id": new_version.id,
                "strategy_id": new_version.strategy_id,
                "version_name": new_version.version_name,
                "config_hash": new_version.config_hash,
                "created_at": new_version.created_at.isoformat() if new_version.created_at else None,
                "remaining_slots": MAX_VERSIONS_PER_RANK - len(existing_versions) - 1,
            }
        }
        if archived_version_name:
            result["archived_version"] = archived_version_name
        return result
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/parameter-versions/{version_id}")
async def get_parameter_version(version_id: str):
    """
    Get a specific parameter version by ID.
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion

    db = SessionLocal()
    try:
        version = db.query(StrategyParameterVersion).filter(
            StrategyParameterVersion.id == version_id
        ).first()

        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        return {
            "id": version.id,
            "strategy_id": version.strategy_id,
            "symbol": version.symbol,
            "version_name": version.version_name,
            "description": version.description,
            "params": version.params,
            "config_hash": version.config_hash,
            "performance_stats": version.performance_stats,
            "is_default": version.is_default,
            "created_at": version.created_at.isoformat() if version.created_at else None,
            "updated_at": version.updated_at.isoformat() if version.updated_at else None,
        }
    finally:
        db.close()


@router.put("/parameter-versions/{version_id}")
async def update_parameter_version(version_id: str, req: ParameterVersionUpdate):
    """
    Update a parameter version (name, description, or params).
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion

    db = SessionLocal()
    try:
        version = db.query(StrategyParameterVersion).filter(
            StrategyParameterVersion.id == version_id
        ).first()

        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        if req.version_name is not None:
            version.version_name = req.version_name
        if req.description is not None:
            version.description = req.description
        if req.params is not None:
            version.params = req.params
            version.config_hash = _create_config_hash({"params": req.params})
        if req.is_default is not None:
            if req.is_default:
                # Unset other defaults
                db.query(StrategyParameterVersion).filter(
                    StrategyParameterVersion.strategy_id == version.strategy_id,
                    StrategyParameterVersion.id != version_id,
                    StrategyParameterVersion.is_default == True
                ).update({"is_default": False})
            version.is_default = req.is_default

        db.commit()
        db.refresh(version)

        return {
            "status": "success",
            "message": f"Version '{version.version_name}' updated",
            "data": {
                "id": version.id,
                "version_name": version.version_name,
                "config_hash": version.config_hash,
                "updated_at": version.updated_at.isoformat() if version.updated_at else None,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/parameter-versions/{version_id}")
async def delete_parameter_version(version_id: str, hard_delete: bool = False):
    """
    Delete a parameter version (soft delete by default).
    Cannot delete versions currently active in running live sessions.
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion, LiveBotSession, SessionStatus

    db = SessionLocal()
    try:
        version = db.query(StrategyParameterVersion).filter(
            StrategyParameterVersion.id == version_id
        ).first()

        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        # Check if this version is currently being used in any active session
        if version.config_hash:
            # Find running sessions with matching strategy_id and symbol
            active_sessions_query = db.query(LiveBotSession).filter(
                LiveBotSession.status == SessionStatus.RUNNING,
                LiveBotSession.strategy_name == version.strategy_id,
            )
            if version.symbol:
                active_sessions_query = active_sessions_query.filter(
                    LiveBotSession.symbol == version.symbol
                )
            else:
                active_sessions_query = active_sessions_query.filter(
                    LiveBotSession.symbol.is_(None)
                )

            active_sessions = active_sessions_query.all()

            # Check if any active session has matching config_hash
            for session in active_sessions:
                session_config_hash = _create_config_hash(session.strategy_config)
                if session_config_hash == version.config_hash:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot delete '{version.version_name}' - it is currently being used in an active live session."
                    )

        if hard_delete:
            db.delete(version)
            message = f"Version '{version.version_name}' permanently deleted"
        else:
            version.is_active = False
            message = f"Version '{version.version_name}' archived"

        db.commit()

        return {"status": "success", "message": message}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/parameter-versions/{version_id}/restore")
async def restore_parameter_version(version_id: str):
    """
    Restore a parameter version - returns the params to be applied.
    The frontend should use these params to update the strategy configuration.
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion

    db = SessionLocal()
    try:
        version = db.query(StrategyParameterVersion).filter(
            StrategyParameterVersion.id == version_id
        ).first()

        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        return {
            "status": "success",
            "message": f"Version '{version.version_name}' ready to restore",
            "data": {
                "strategy_id": version.strategy_id,
                "symbol": version.symbol,
                "version_name": version.version_name,
                "params": version.params,
                "config_hash": version.config_hash,
            }
        }
    finally:
        db.close()


@router.post("/parameter-versions/{version_id}/update-stats")
async def update_version_performance_stats(version_id: str):
    """
    Update performance stats for a version based on matching trades.
    Finds trades with matching config_hash and calculates performance.
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion, LiveTradeExecution, ExecutionStatus

    db = SessionLocal()
    try:
        version = db.query(StrategyParameterVersion).filter(
            StrategyParameterVersion.id == version_id
        ).first()

        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        if not version.config_hash:
            raise HTTPException(status_code=400, detail="Version has no config_hash")

        # Find trades with matching config_hash
        executions = db.query(LiveTradeExecution).filter(
            LiveTradeExecution.status == ExecutionStatus.FILLED,
            LiveTradeExecution.config_snapshot.isnot(None)
        ).all()

        # Filter by matching hash
        matching_trades = []
        for ex in executions:
            if _create_config_hash(ex.config_snapshot) == version.config_hash:
                matching_trades.append(ex)

        if not matching_trades:
            return {
                "status": "success",
                "message": "No matching trades found",
                "data": {"trades_found": 0}
            }

        # Calculate stats using FIFO matching (same logic as parameter-analysis)
        buys = []
        sells = []
        for ex in sorted(matching_trades, key=lambda x: x.signal_timestamp):
            qty = ex.filled_quantity or 0
            price = ex.executed_price or 0
            if ex.signal_type == Signal.BUY:
                buys.append({"qty": qty, "price": price})
            elif ex.signal_type == Signal.SELL:
                sells.append({"qty": qty, "price": price})

        buy_queue = list(buys)
        cycle_pnls = []

        for sell in sells:
            sell_qty = sell["qty"]
            sell_price = sell["price"]
            buy_cost = 0.0
            matched_qty = 0.0

            while sell_qty > 0 and buy_queue:
                buy = buy_queue[0]
                match_qty = min(sell_qty, buy["qty"])
                buy_cost += match_qty * buy["price"]
                matched_qty += match_qty
                sell_qty -= match_qty
                buy["qty"] -= match_qty
                if buy["qty"] <= 0:
                    buy_queue.pop(0)

            if matched_qty > 0:
                cycle_pnl = (sell_price * matched_qty) - buy_cost
                cycle_pnls.append(cycle_pnl)

        cycles = len(cycle_pnls)
        if cycles > 0:
            total_pnl = sum(cycle_pnls)
            wins = sum(1 for p in cycle_pnls if p > 0)
            stats = {
                "cycles": cycles,
                "total_cycles": len(matching_trades),
                "win_rate": round((wins / cycles) * 100, 1),
                "total_pnl": round(total_pnl, 0),
                "avg_pnl": round(total_pnl / cycles, 0),
                "max_pnl": round(max(cycle_pnls), 0),
                "min_pnl": round(min(cycle_pnls), 0),
            }
        else:
            stats = {
                "cycles": 0,
                "total_cycles": len(matching_trades),
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "max_pnl": 0,
                "min_pnl": 0,
            }

        version.performance_stats = stats
        db.commit()

        return {
            "status": "success",
            "message": "Performance stats updated",
            "data": stats
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# AI Evaluation API - Live Trading Performance Analysis
# ═══════════════════════════════════════════════════════════════════════════════

class AIEvaluationRequest(PydanticBaseModel):
    n_cycles: int = 10  # Number of recent cycles to analyze
    backtest_days: int = 30  # Days for comparison backtest
    mode: str = "real"  # 'paper' | 'real' - which trades to analyze


@router.post("/{session_id}/ai-evaluate")
async def run_ai_evaluation(
    session_id: str,
    req: AIEvaluationRequest = AIEvaluationRequest(),
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Run AI evaluation on a live trading session.

    Compares recent N cycles of live trading with backtest results
    using the current strategy configuration.

    Returns AI-generated analysis and recommendations.
    """
    from ..models.live_trading import LiveBotSession, LiveAIEvaluation
    from ..core.live_ai_evaluation import LiveAIEvaluationService
    from datetime import datetime
    import uuid

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    # Verify session ownership (user-level: any of user's accounts)
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)

    try:
        # Initialize evaluation service (uses Claude CLI agent)
        service = LiveAIEvaluationService(db, user_id=ctx.user.id)

        # Run full evaluation
        is_paper = req.mode.lower() == Mode.PAPER
        result = await service.run_full_evaluation(
            session_id=session_id,
            symbol=session.symbol,
            strategy_name=session.strategy_name,
            strategy_config=session.strategy_config,
            n_cycles=req.n_cycles,
            backtest_days=req.backtest_days,
            evaluation_type="MANUAL",
            is_paper=is_paper
        )

        if result.get("status") == "failed":
            raise HTTPException(status_code=400, detail=result.get("error", "Evaluation failed"))

        # Save to database
        evaluation = LiveAIEvaluation(
            id=str(uuid.uuid4()),
            session_id=session_id,
            symbol=session.symbol,
            evaluation_type="MANUAL",
            is_paper=is_paper,
            trigger_cycle_count=req.n_cycles,
            analysis_start_time=datetime.fromisoformat(result["analysis_start_time"]) if result.get("analysis_start_time") else None,
            analysis_end_time=datetime.fromisoformat(result["analysis_end_time"]) if result.get("analysis_end_time") else None,
            cycles_analyzed=result.get("cycles_analyzed", 0),
            live_stats=result.get("live_stats"),
            backtest_stats=result.get("backtest_stats"),
            strategy_config=result.get("strategy_config"),
            comparison_data=result.get("comparison_data"),
            ai_model=result.get("ai_model"),
            ai_prompt=result.get("ai_prompt"),
            ai_response=result.get("ai_response"),
            evaluation_score=result.get("evaluation_score"),
            key_findings=result.get("key_findings"),
            recommendations=result.get("recommendations"),
            status="completed" if result.get("ai_response") else "failed",
            error_message=result.get("error_message"),
            completed_at=datetime.utcnow()
        )
        db.add(evaluation)

        # Save last used settings to session for auto-evaluation
        session.ai_eval_cycles = req.n_cycles
        session.ai_eval_backtest_days = req.backtest_days
        session.ai_eval_mode = req.mode

        db.commit()

        # Send Telegram notification with full details
        try:
            from ..core.telegram_service import send_telegram_notification
            comparison = result.get("comparison_data", {})
            live_stats = result.get("live_stats", {})
            backtest_stats = result.get("backtest_stats", {})
            key_findings = result.get("key_findings", {})

            await send_telegram_notification(
                db=db,
                user_id=ctx.user.id,
                notification_type="ai_eval",
                account_id=session.account_id,
                symbol=session.symbol,
                strategy_name=session.strategy_name,
                grade=comparison.get("overall_grade", "N/A"),
                cycles_analyzed=result.get("cycles_analyzed", 0),
                is_paper=is_paper,
                live_return=live_stats.get("total_return", 0),
                backtest_return=backtest_stats.get("total_return", 0),
                return_diff=comparison.get("return_diff", 0),
                action=key_findings.get("action"),
                key_reason=key_findings.get("main_issue"),
                ai_response=result.get("ai_response"),
                live_stats=live_stats,          # 라이브 통계 전체
                backtest_stats=backtest_stats,  # 백테스트 통계 전체
                comparison=comparison           # 비교 데이터 전체
            )
        except Exception as tg_err:
            logger.warning(f"Telegram notification failed: {tg_err}")

        return {
            "status": "success",
            "evaluation_id": evaluation.id,
            "mode": Mode.PAPER if is_paper else Mode.REAL,
            "grade": result.get("comparison_data", {}).get("overall_grade", "N/A"),
            "cycles_analyzed": result.get("cycles_analyzed", 0),
            "ai_response": result.get("ai_response"),
            "key_findings": result.get("key_findings"),
            "comparison": result.get("comparison_data"),
            "live_stats": result.get("live_stats"),
            "backtest_stats": result.get("backtest_stats"),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/ai-evaluations")
async def list_ai_evaluations(
    session_id: str,
    limit: int = 10,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    List AI evaluations for a session.
    """
    from ..models.live_trading import LiveBotSession, LiveAIEvaluation

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    # Verify session ownership (user-level)
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)

    evaluations = db.query(LiveAIEvaluation).filter(
        LiveAIEvaluation.session_id == session_id
    ).order_by(LiveAIEvaluation.created_at.desc()).limit(limit).all()

    return {
        "session_id": session_id,
        "total": len(evaluations),
        "data": [
            {
                "id": e.id,
                "evaluation_type": e.evaluation_type,
                "mode": Mode.PAPER if e.is_paper else Mode.REAL,
                "cycles_analyzed": e.cycles_analyzed,
                "grade": e.comparison_data.get("overall_grade") if e.comparison_data else None,
                "evaluation_score": e.evaluation_score,
                "key_findings": e.key_findings,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in evaluations
        ]
    }


@router.get("/ai-evaluations/{evaluation_id}")
async def get_ai_evaluation(
    evaluation_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Get detailed AI evaluation by ID.
    """
    from ..models.live_trading import LiveBotSession, LiveAIEvaluation

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    evaluation = db.query(LiveAIEvaluation).filter(
        LiveAIEvaluation.id == evaluation_id
    ).first()

    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Verify session ownership (user-level)
    if evaluation.session_id:
        await verify_session_ownership_by_user(evaluation.session_id, ctx.user_id, db)

    return {
        "id": evaluation.id,
        "session_id": evaluation.session_id,
        "symbol": evaluation.symbol,
        "evaluation_type": evaluation.evaluation_type,
        "mode": Mode.PAPER if evaluation.is_paper else Mode.REAL,
        "trigger_cycle_count": evaluation.trigger_cycle_count,
        "cycles_analyzed": evaluation.cycles_analyzed,
        "analysis_start_time": evaluation.analysis_start_time.isoformat() if evaluation.analysis_start_time else None,
        "analysis_end_time": evaluation.analysis_end_time.isoformat() if evaluation.analysis_end_time else None,
        "live_stats": evaluation.live_stats,
        "backtest_stats": evaluation.backtest_stats,
        "comparison_data": evaluation.comparison_data,
        "strategy_config": evaluation.strategy_config,
        "ai_model": evaluation.ai_model,
        "ai_response": evaluation.ai_response,
        "evaluation_score": evaluation.evaluation_score,
        "key_findings": evaluation.key_findings,
        "recommendations": evaluation.recommendations,
        "status": evaluation.status,
        "error_message": evaluation.error_message,
        "created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
        "completed_at": evaluation.completed_at.isoformat() if evaluation.completed_at else None,
    }


class AIEvalSettingsRequest(PydanticBaseModel):
    enabled: bool = False
    cycles: int = 10  # Evaluate every N cycles
    backtest_days: int = 30
    mode: str = "paper"  # 'paper' | 'real'


@router.get("/{session_id}/ai-eval-settings")
async def get_ai_eval_settings(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Get AI evaluation settings for a session.
    """
    from ..models.live_trading import LiveBotSession

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)

    return {
        "session_id": session_id,
        "enabled": session.ai_eval_enabled or False,
        "cycles": session.ai_eval_cycles or 10,
        "backtest_days": session.ai_eval_backtest_days or 30,
        "mode": session.ai_eval_mode or Mode.PAPER,
    }


@router.put("/{session_id}/ai-eval-settings")
async def update_ai_eval_settings(
    session_id: str,
    req: AIEvalSettingsRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Update AI evaluation settings for a session.
    These settings are used for automatic evaluation triggers.
    """
    from ..models.live_trading import LiveBotSession

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)

    # Update settings
    session.ai_eval_enabled = req.enabled
    session.ai_eval_cycles = req.cycles
    session.ai_eval_backtest_days = req.backtest_days
    session.ai_eval_mode = req.mode

    db.commit()

    return {
        "status": "success",
        "message": "AI evaluation settings updated",
        "settings": {
            "enabled": session.ai_eval_enabled,
            "cycles": session.ai_eval_cycles,
            "backtest_days": session.ai_eval_backtest_days,
            "mode": session.ai_eval_mode,
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AI Symbol Selection Settings
# ═══════════════════════════════════════════════════════════════════════════════

class AISymbolSettingsRequest(PydanticBaseModel):
    ai_symbol_mode: str = "static"  # "static" | "ai" | "reset"
    ai_search_conditions: Optional[str] = None
    ai_optimize_params: Optional[dict] = None  # {"params": {"leverage": [1,5,10], "position_side": ["long","short"]}}


@router.get("/{session_id}/ai-symbol-settings")
async def get_ai_symbol_settings(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """Get AI symbol selection settings for a session."""
    from ..models.live_trading import LiveBotSession

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)

    return {
        "session_id": session_id,
        "ai_symbol_mode": session.ai_symbol_mode or AiMode.STATIC,
        "ai_search_conditions": session.ai_search_conditions or "",
        "ai_optimize_params": session.ai_optimize_params,
    }


@router.put("/{session_id}/ai-symbol-settings")
async def update_ai_symbol_settings(
    session_id: str,
    req: AISymbolSettingsRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """Update AI symbol selection settings for a session."""
    from ..models.live_trading import LiveBotSession

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await verify_session_ownership_by_user(session_id, ctx.user_id, db)

    reset_performed = False

    if req.ai_symbol_mode == AiMode.RESET:
        # Reset: revert symbol to original profile symbol and set mode to static
        original = getattr(session, 'original_symbol', None)
        if original and original != session.symbol:
            old_symbol = session.symbol
            session.symbol = original
            cfg = dict(session.strategy_config or {})
            cfg['symbol'] = original
            orig_name = getattr(session, 'original_symbol_name', None)
            if orig_name:
                cfg['symbol_name'] = orig_name
            session.strategy_config = cfg
            reset_performed = True
            logger.info(f"[AISymbol] Reset: {old_symbol} -> {original} (session {session_id[:8]})")
        session.ai_symbol_mode = AiMode.STATIC
        session.ai_awaiting_cycle = False
    else:
        session.ai_symbol_mode = req.ai_symbol_mode
        # Only update search conditions when AI mode is active; preserve for static mode
        if req.ai_symbol_mode == AiMode.AI:
            session.ai_search_conditions = req.ai_search_conditions
            session.ai_optimize_params = req.ai_optimize_params
            # Reset awaiting flag so pipeline can trigger on resume
            session.ai_awaiting_cycle = False

    db.commit()

    result = {
        "status": "success",
        "message": "Symbol reset to original" if reset_performed else "AI symbol settings updated",
        "settings": {
            "ai_symbol_mode": session.ai_symbol_mode,
            "ai_search_conditions": session.ai_search_conditions,
            "ai_optimize_params": session.ai_optimize_params,
        }
    }
    if reset_performed:
        result["reset_symbol"] = session.symbol
        result["reset_symbol_name"] = getattr(session, 'original_symbol_name', None)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# AI Symbol Selection Progress
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/{session_id}/ai-symbol-progress")
async def get_ai_symbol_progress(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
):
    """Get AI symbol selection pipeline progress for a session."""
    from ..core.ai_symbol_selection import AISymbolSelectionService

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    service = AISymbolSelectionService.get_instance()
    progress = service.get_progress(session_id)

    if not progress:
        return {"session_id": session_id, "active": False, "stage": "idle", "message": ""}

    return {"session_id": session_id, **progress}


@router.get("/{session_id}/ai-symbol-history")
async def get_ai_symbol_history(
    session_id: str,
    limit: int = 20,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    """Get AI symbol selection history for a session."""
    from ..models.live_trading import AISymbolHistory

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    records = db.query(AISymbolHistory).filter(
        AISymbolHistory.session_id == session_id
    ).order_by(AISymbolHistory.created_at.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "group_id": r.group_id,
            "action": r.action,
            "old_symbol": r.old_symbol,
            "old_symbol_name": r.old_symbol_name,
            "new_symbol": r.new_symbol,
            "new_symbol_name": r.new_symbol_name,
            "search_conditions": r.search_conditions,
            "evaluation_reason": r.evaluation_reason,
            "backtest_results": r.backtest_results,
            "created_at": (r.created_at.isoformat() + "Z") if r.created_at else None,
        }
        for r in records
    ]


@router.get("/group/{group_id}/ai-symbol-history")
async def get_group_ai_symbol_history(
    group_id: str,
    limit: int = 30,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    """Get AI symbol selection history for all sessions in a group."""
    from ..models.live_trading import AISymbolHistory

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")

    records = db.query(AISymbolHistory).filter(
        AISymbolHistory.group_id == group_id
    ).order_by(AISymbolHistory.created_at.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "group_id": r.group_id,
            "action": r.action,
            "old_symbol": r.old_symbol,
            "old_symbol_name": r.old_symbol_name,
            "new_symbol": r.new_symbol,
            "new_symbol_name": r.new_symbol_name,
            "search_conditions": r.search_conditions,
            "evaluation_reason": r.evaluation_reason,
            "backtest_results": r.backtest_results,
            "created_at": (r.created_at.isoformat() + "Z") if r.created_at else None,
        }
        for r in records
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5: Strategy Profile API - Multi-Rank Session Templates
# ═══════════════════════════════════════════════════════════════════════════════

class StrategyProfileCreate(PydanticBaseModel):
    name: str
    description: Optional[str] = None
    strategy_name: str
    rank_configs: List[Dict[str, Any]]  # Array of rank configurations
    execution_mode: str = "parallel"
    rank_weights: Optional[Dict[str, float]] = None
    initial_capital: float = DEFAULT_INITIAL_CAPITAL
    is_paper: bool = True
    symbol_compare_settings: Optional[Dict[str, Any]] = None  # Symbol Compare 설정
    saved_symbols: Optional[List[Dict[str, Any]]] = None  # Target Asset 목록
    account_id: Optional[int] = None  # 연결된 거래 계좌 (거래소 자동 결정)


class StrategyProfileUpdate(PydanticBaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rank_configs: Optional[List[Dict[str, Any]]] = None
    execution_mode: Optional[str] = None
    rank_weights: Optional[Dict[str, float]] = None
    initial_capital: Optional[float] = None
    is_paper: Optional[bool] = None
    symbol_compare_settings: Optional[Dict[str, Any]] = None  # Symbol Compare 설정
    saved_symbols: Optional[List[Dict[str, Any]]] = None  # Target Asset 목록
    account_id: Optional[int] = None  # 연결된 거래 계좌


@router.get("/profiles")
async def list_strategy_profiles(
    strategy_name: str = "",
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    List all saved strategy profiles for the current user.

    Query params:
    - strategy_name: filter by strategy (optional)
    """
    from ..models.live_trading import StrategyProfile

    query = db.query(StrategyProfile).filter(
        StrategyProfile.user_id == ctx.user_id,
        StrategyProfile.is_active == True
    )

    if strategy_name:
        query = query.filter(StrategyProfile.strategy_name == strategy_name)

    profiles = query.order_by(StrategyProfile.updated_at.desc()).all()

    return {
        "total": len(profiles),
        "data": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "strategy_name": p.strategy_name,
                "rank_count": len(p.rank_configs) if p.rank_configs else 0,
                "execution_mode": p.execution_mode,
                "initial_capital": p.initial_capital,
                "is_paper": p.is_paper,
                "account_id": p.account_id,
                "saved_symbols": p.saved_symbols,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in profiles
        ]
    }


@router.post("/profiles")
async def create_strategy_profile(
    req: StrategyProfileCreate,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Save current integrated tab configuration as a reusable profile.
    """
    from ..models.live_trading import StrategyProfile
    import uuid

    # Validate rank_configs
    if not req.rank_configs or len(req.rank_configs) == 0:
        raise HTTPException(status_code=400, detail="At least one rank configuration is required")

    new_profile = StrategyProfile(
        id=str(uuid.uuid4()),
        user_id=ctx.user_id,
        name=req.name,
        description=req.description,
        strategy_name=req.strategy_name,
        rank_configs=req.rank_configs,
        execution_mode=req.execution_mode,
        rank_weights=req.rank_weights,
        initial_capital=req.initial_capital,
        is_paper=req.is_paper,
        symbol_compare_settings=req.symbol_compare_settings,
        saved_symbols=req.saved_symbols,
        account_id=req.account_id,
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)

    return {
        "status": "success",
        "message": f"Profile '{req.name}' saved",
        "data": {
            "id": new_profile.id,
            "name": new_profile.name,
            "rank_count": len(req.rank_configs),
            "created_at": new_profile.created_at.isoformat() if new_profile.created_at else None,
        }
    }


@router.get("/profiles/{profile_id}")
async def get_strategy_profile(
    profile_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Get a specific strategy profile with full configuration.
    """
    from ..models.live_trading import StrategyProfile

    profile = db.query(StrategyProfile).filter(
        StrategyProfile.id == profile_id,
        StrategyProfile.user_id == ctx.user_id,
        StrategyProfile.is_active == True
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "strategy_name": profile.strategy_name,
        "rank_configs": profile.rank_configs,
        "execution_mode": profile.execution_mode,
        "rank_weights": profile.rank_weights,
        "initial_capital": profile.initial_capital,
        "is_paper": profile.is_paper,
        "account_id": profile.account_id,
        "symbol_compare_settings": profile.symbol_compare_settings,
        "saved_symbols": profile.saved_symbols,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.put("/profiles/{profile_id}")
async def update_strategy_profile(
    profile_id: str,
    req: StrategyProfileUpdate,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Update an existing strategy profile.
    """
    from ..models.live_trading import StrategyProfile

    profile = db.query(StrategyProfile).filter(
        StrategyProfile.id == profile_id,
        StrategyProfile.user_id == ctx.user_id,
        StrategyProfile.is_active == True
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if req.name is not None:
        profile.name = req.name
    if req.description is not None:
        profile.description = req.description
    if req.rank_configs is not None:
        if len(req.rank_configs) == 0:
            raise HTTPException(status_code=400, detail="At least one rank configuration is required")
        profile.rank_configs = req.rank_configs
    if req.execution_mode is not None:
        profile.execution_mode = req.execution_mode
    if req.rank_weights is not None:
        profile.rank_weights = req.rank_weights
    if req.initial_capital is not None:
        profile.initial_capital = req.initial_capital
    if req.is_paper is not None:
        profile.is_paper = req.is_paper
    if req.symbol_compare_settings is not None:
        profile.symbol_compare_settings = req.symbol_compare_settings
    if req.saved_symbols is not None:
        profile.saved_symbols = req.saved_symbols
    if req.account_id is not None:
        profile.account_id = req.account_id

    db.commit()
    db.refresh(profile)

    return {
        "status": "success",
        "message": f"Profile '{profile.name}' updated",
        "data": {
            "id": profile.id,
            "name": profile.name,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }
    }


@router.delete("/profiles/{profile_id}")
async def delete_strategy_profile(
    profile_id: str,
    hard_delete: bool = False,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Delete a strategy profile (soft delete by default).
    """
    from ..models.live_trading import StrategyProfile

    profile = db.query(StrategyProfile).filter(
        StrategyProfile.id == profile_id,
        StrategyProfile.user_id == ctx.user_id
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if hard_delete:
        db.delete(profile)
        message = f"Profile '{profile.name}' permanently deleted"
    else:
        profile.is_active = False
        message = f"Profile '{profile.name}' archived"

    db.commit()

    return {"status": "success", "message": message}


# ============================================================================
# ExecutionEngine V2 — Signal API
# ============================================================================

@router.get("/session/{session_id}/signals")
async def get_session_signals(session_id: str, limit: int = 50, executed_only: bool = False, source: Optional[str] = None):
    """
    세션의 캡처된 시그널 목록 조회.
    engine_version=v2 세션에서만 데이터 반환.
    """
    engine = live_manager.engines.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Session not found or not running")

    if not engine._signal_context:
        return {"engine_version": "v1", "signals": [], "message": "v1 engine — no signal data"}

    signals = engine._signal_context.executed_signals if executed_only else engine._signal_context.signals
    if source:
        signals = [s for s in signals if s.source and s.source.startswith(source)]
    recent = signals[-limit:] if len(signals) > limit else signals

    return {
        "engine_version": "v2",
        "session_id": session_id,
        "total": len(signals),
        "showing": len(recent),
        "signals": [
            {
                "signal_id": s.signal_id,
                "side": s.side.value,
                "symbol": s.symbol,
                "quantity": s.quantity,
                "price": s.price,
                "order_type": s.order_type,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                "executed": s.executed,
                "exec_price": s.exec_price,
                "exec_quantity": s.exec_quantity,
                "decision": {
                    "action": s.decision.action.value,
                    "reason": s.decision.reason,
                    "filter_name": s.decision.filter_name,
                } if s.decision else None,
                "source": s.source,
                "metadata": s.metadata,
            }
            for s in recent
        ],
    }


@router.get("/session/{session_id}/engine-stats")
async def get_session_engine_stats(session_id: str):
    """
    세션의 ExecutionEngine 통계 조회.
    """
    engine = live_manager.engines.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Session not found or not running")

    if not engine._execution_engine:
        return {"engine_version": "v1", "message": "v1 engine — no execution stats"}

    return {
        "engine_version": "v2",
        "session_id": session_id,
        "signal_stats": engine._signal_context.get_signal_stats() if engine._signal_context else {},
        "engine_stats": engine._execution_engine.get_stats(),
    }


class FilterConfigRequest(BaseModel):
    filters: List[Dict[str, Any]]  # [{"type": "max_position_size", "max_quantity": 100}, ...]


@router.post("/session/{session_id}/filters")
async def configure_session_filters(session_id: str, request: FilterConfigRequest):
    """
    실행 중인 v2 세션의 필터 체인을 동적으로 설정.
    기존 필터를 교체합니다.

    지원 필터:
    - max_position_size: {"type": "max_position_size", "max_quantity": 100}
    - max_consecutive_loss: {"type": "max_consecutive_loss", "max_consecutive": 3}
    - time_restriction: {"type": "time_restriction", "start_hour": 9, "end_hour": 15}
    """
    engine = live_manager.engines.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Session not found or not running")

    if not engine._execution_engine:
        raise HTTPException(status_code=400, detail="v1 engine — cannot configure filters")

    from ..core.execution_engine import (
        FilterChainExecutor, PassthroughExecutor,
        MaxPositionSizeFilter, MaxConsecutiveLossFilter, TimeRestrictionFilter,
    )

    # Build new filter chain
    new_engine = FilterChainExecutor()
    applied = []

    for f_config in request.filters:
        f_type = f_config.get("type", "")
        if f_type == "max_position_size":
            new_engine.add_filter(MaxPositionSizeFilter(
                max_quantity=f_config.get("max_quantity", 100)
            ))
            applied.append(f_type)
        elif f_type == "max_consecutive_loss":
            new_engine.add_filter(MaxConsecutiveLossFilter(
                max_consecutive=f_config.get("max_consecutive", 3)
            ))
            applied.append(f_type)
        elif f_type == "time_restriction":
            new_engine.add_filter(TimeRestrictionFilter(
                start_hour=f_config.get("start_hour", 9),
                end_hour=f_config.get("end_hour", 15),
                start_minute=f_config.get("start_minute", 0),
                end_minute=f_config.get("end_minute", 20),
            ))
            applied.append(f_type)
        else:
            logger.warning(f"Unknown filter type: {f_type}")

    # Hot-swap engine (signal context holds reference)
    engine._execution_engine = new_engine
    if engine._signal_context:
        engine._signal_context._engine = new_engine

    return {
        "status": "success",
        "session_id": session_id,
        "filters_applied": applied,
        "engine_stats": new_engine.get_stats(),
    }


class SubmitSignalRequest(BaseModel):
    side: str  # "buy", "sell", "short", "close_position"
    symbol: Optional[str] = None  # None → use session's current symbol
    quantity: float = 0
    price: float = 0  # 0 = market price
    order_type: str = "market"
    source: str = "skill"  # must start with "skill"
    metadata: Optional[Dict[str, Any]] = None


@router.post("/session/{session_id}/submit-signal")
async def submit_signal(session_id: str, request: SubmitSignalRequest):
    """
    외부 소스(스킬 등)에서 시그널을 제출하여 ExecutionEngine을 통해 평가/실행.
    v2 엔진 필수.
    """
    engine = live_manager.engines.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Session not found or not running")

    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Session is not running")

    if not engine._signal_context:
        raise HTTPException(status_code=400, detail="v2 engine required for external signals")

    if not request.source.startswith("skill"):
        raise HTTPException(status_code=400, detail="source must start with 'skill'")

    symbol = request.symbol or engine.symbol
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    try:
        result = await engine.process_external_signal(
            side=request.side,
            symbol=symbol,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type,
            source=request.source,
            metadata=request.metadata,
        )
        return {
            "status": "success",
            "session_id": session_id,
            "symbol": symbol,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"submit_signal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SkillSymbolSwitchRequest(BaseModel):
    new_symbol: str
    new_symbol_name: Optional[str] = None
    optimized_params: Optional[Dict[str, Any]] = None
    source: str = "skill:symbol-select"
    reason: Optional[str] = None
    backtest_results: Optional[List[Dict[str, Any]]] = None


@router.post("/session/{session_id}/skill-symbol-switch")
async def skill_symbol_switch(session_id: str, request: SkillSymbolSwitchRequest):
    """
    외부 스킬에서 AI 종목 선정 결과를 적용하여 세션 종목을 전환.
    LiveManager.switch_session_symbol()을 호출하여 엔진 재초기화.
    """
    if not request.source.startswith("skill"):
        raise HTTPException(status_code=400, detail="source must start with 'skill'")

    engine = live_manager.engines.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Session not found or not running")

    old_symbol = engine.symbol

    if old_symbol == request.new_symbol and not request.optimized_params:
        return {
            "status": "kept",
            "session_id": session_id,
            "symbol": old_symbol,
            "message": "Same symbol, no change needed",
        }

    try:
        await live_manager.switch_session_symbol(
            session_id=session_id,
            new_symbol=request.new_symbol,
            new_symbol_name=request.new_symbol_name,
            optimized_params=request.optimized_params,
        )

        # Save AI symbol history if service available
        try:
            from ..core.ai_symbol_selection import AISymbolSelectionService
            ai_service = AISymbolSelectionService.get_instance()
            db = SessionLocal()
            try:
                sess = db.query(LiveBotSession).filter_by(id=session_id).first()
                group_id = sess.group_id if sess else None
            finally:
                db.close()

            action = "switched" if old_symbol != request.new_symbol else "kept"
            ai_service._save_history(
                session_id=session_id,
                group_id=group_id,
                action=action,
                old_symbol=old_symbol,
                new_symbol=request.new_symbol if action == "switched" else None,
                new_symbol_name=request.new_symbol_name,
                search_conditions=f"[{request.source}]",
                evaluation_reason=request.reason or f"Skill symbol switch: {old_symbol} → {request.new_symbol}",
                backtest_results=request.backtest_results or [],
            )
        except Exception as e:
            logger.warning(f"skill-symbol-switch: history save failed: {e}")

        return {
            "status": "switched" if old_symbol != request.new_symbol else "updated",
            "session_id": session_id,
            "old_symbol": old_symbol,
            "new_symbol": request.new_symbol,
            "optimized_params": request.optimized_params,
            "message": f"Symbol switched: {old_symbol} → {request.new_symbol}",
        }
    except Exception as e:
        logger.error(f"skill-symbol-switch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/candles")
async def get_session_candles(session_id: str, limit: int = 100):
    """
    세션의 히스토리 캔들 데이터 + 현재가 + 포지션 정보 제공.
    스킬이 기술 지표 분석에 사용.
    """
    engine = live_manager.engines.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Session not found or not running")

    candles = engine.get_history()
    recent = candles[-limit:] if len(candles) > limit else candles

    # Current price
    current_price = 0
    try:
        current_price = engine.context.get_current_price(engine.symbol)
    except Exception:
        pass

    # Holdings
    holdings = {}
    try:
        holdings = engine.context.holdings
    except Exception:
        pass

    interval = engine.strategy_config.get("interval", "1m") if engine.strategy_config else "1m"

    return {
        "session_id": session_id,
        "symbol": engine.symbol,
        "interval": interval,
        "candle_count": len(recent),
        "current_price": current_price,
        "holdings": holdings,
        "orders_enabled": engine.orders_enabled,
        "strategy_name": engine.strategy_name if hasattr(engine, 'strategy_name') else None,
        "strategy_config": engine.strategy_config if hasattr(engine, 'strategy_config') else {},
        "initial_capital": engine.context.initial_capital if hasattr(engine, 'context') else 0,
        "is_paper": engine.is_paper if hasattr(engine, 'is_paper') else True,
        "candles": recent,
    }


# =========================================================================
# Skill Monitor endpoints (no auth required)
# =========================================================================

@router.get("/monitor/sessions")
async def monitor_sessions():
    """
    모니터링 스킬 전용 — 인증 없이 모든 RUNNING 세션의 건강 상태 조회.
    """
    results = []
    for session_id, engine in live_manager.engines.items():
        if not engine.is_running:
            continue

        # Basic info
        info = {
            "session_id": session_id,
            "symbol": engine.symbol,
            "strategy_name": engine.strategy_name if hasattr(engine, 'strategy_name') else "?",
            "is_paper": engine.is_paper if hasattr(engine, 'is_paper') else True,
            "orders_enabled": engine.orders_enabled,
            "status": "RUNNING",
        }

        # Trade stats
        try:
            stats = engine.context.get_trade_stats(engine.symbol)
            info["total_return"] = stats.get("total_return", 0)
            info["win_rate"] = stats.get("win_rate", 0)
            info["max_drawdown"] = stats.get("max_drawdown", 0)
            info["total_cycles"] = stats.get("total_cycles", 0)
            info["sharpe_ratio"] = stats.get("sharpe_ratio", 0)
            info["profit_factor"] = stats.get("profit_factor", 0)
            info["avg_pnl"] = stats.get("avg_pnl", 0)
            info["realized_pnl"] = stats.get("realized_pnl", 0)
        except Exception:
            info["total_return"] = 0
            info["win_rate"] = 0
            info["max_drawdown"] = 0
            info["total_cycles"] = 0

        # Current price & equity
        try:
            info["current_price"] = engine.context.get_current_price(engine.symbol)
            info["equity"] = engine.context.get_total_equity()
            info["initial_capital"] = engine.context.initial_capital
        except Exception:
            pass

        results.append(info)

    return {"sessions": results, "count": len(results)}


@router.get("/monitor/goal/progress")
async def monitor_goal_progress(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Cron/skill 전용 — 인증 없이 12%/월 KPI 진행률 조회.
    account_id가 없으면 모든 계정 합산. localhost에서 cron이 호출.
    Auth 필요한 /goal/progress 와 동일한 집계 로직, 사용자 컨텍스트만 우회.
    """
    from datetime import datetime as _dt
    from sqlalchemy import func
    from ..models.live_trading import LiveTradeExecution, ExecutionStatus, LiveBotSession

    now = _dt.utcnow()
    month_start = _dt(now.year, now.month, 1)
    day_start = _dt(now.year, now.month, now.day)

    q = db.query(LiveBotSession)
    if account_id is not None:
        q = q.filter(LiveBotSession.account_id == account_id)
    sessions = q.all()

    if not sessions:
        return {
            "target_monthly_pct": GOAL_MONTHLY_RETURN_TARGET,
            "monthly_pnl_krw": 0.0,
            "monthly_return_pct": 0.0,
            "progress_pct": 0.0,
            "daily_pnl_krw": 0.0,
            "daily_return_pct": 0.0,
            "total_capital_base": 0.0,
            "session_count": 0,
            "sessions": [],
            "kill_switch": {
                "monthly_breach": False,
                "daily_breach": False,
                "breached_sessions": [],
            },
            "as_of": now.isoformat(),
        }

    session_ids = [s.id for s in sessions]
    capital_base = sum((s.initial_capital or 0.0) for s in sessions) or 0.0

    def _sum_pnl(start: _dt) -> float:
        v = db.query(func.coalesce(func.sum(LiveTradeExecution.realized_pnl), 0.0)).filter(
            LiveTradeExecution.session_id.in_(session_ids),
            LiveTradeExecution.status == ExecutionStatus.FILLED,
            LiveTradeExecution.signal_timestamp >= start,
        ).scalar()
        return float(v or 0.0)

    monthly_pnl = _sum_pnl(month_start)
    daily_pnl = _sum_pnl(day_start)
    monthly_return_pct = (monthly_pnl / capital_base * 100.0) if capital_base > 0 else 0.0
    daily_return_pct = (daily_pnl / capital_base * 100.0) if capital_base > 0 else 0.0
    progress_pct = (monthly_return_pct / GOAL_MONTHLY_RETURN_TARGET * 100.0) if GOAL_MONTHLY_RETURN_TARGET > 0 else 0.0

    per_session = (
        db.query(
            LiveTradeExecution.session_id,
            func.coalesce(func.sum(LiveTradeExecution.realized_pnl), 0.0).label("pnl"),
        )
        .filter(
            LiveTradeExecution.session_id.in_(session_ids),
            LiveTradeExecution.status == ExecutionStatus.FILLED,
        )
        .group_by(LiveTradeExecution.session_id)
        .all()
    )
    pnl_by_session = {sid: float(pnl or 0.0) for sid, pnl in per_session}

    session_rows = []
    breached_sessions = []
    for s in sessions:
        pnl = pnl_by_session.get(s.id, 0.0)
        ic = s.initial_capital or 0.0
        ret_pct = (pnl / ic * 100.0) if ic > 0 else 0.0
        breached = ret_pct <= KILL_SWITCH_SESSION_PCT
        if breached and s.status == "RUNNING":
            breached_sessions.append(s.id)
        session_rows.append({
            "session_id": s.id,
            "symbol": s.symbol,
            "status": s.status,
            "is_paper": s.is_paper,
            "account_id": s.account_id,
            "initial_capital": ic,
            "realized_pnl": pnl,
            "return_pct": ret_pct,
        })

    return {
        "target_monthly_pct": GOAL_MONTHLY_RETURN_TARGET,
        "monthly_pnl_krw": monthly_pnl,
        "monthly_return_pct": monthly_return_pct,
        "progress_pct": progress_pct,
        "daily_pnl_krw": daily_pnl,
        "daily_return_pct": daily_return_pct,
        "total_capital_base": capital_base,
        "session_count": len(sessions),
        "sessions": session_rows,
        "kill_switch": {
            "monthly_threshold_pct": KILL_SWITCH_MONTHLY_PCT,
            "session_threshold_pct": KILL_SWITCH_SESSION_PCT,
            "daily_threshold_pct": KILL_SWITCH_DAILY_PCT,
            "monthly_breach": monthly_return_pct <= KILL_SWITCH_MONTHLY_PCT,
            "daily_breach": daily_return_pct <= KILL_SWITCH_DAILY_PCT,
            "breached_sessions": breached_sessions,
        },
        "as_of": now.isoformat(),
    }


# =========================================================================
# Goal Progress — KPI tracking against 12%/month target
# =========================================================================

# Target return — system KPI (project_return_target.md)
GOAL_MONTHLY_RETURN_TARGET = 12.0  # %

# Kill switch thresholds (project_return_target.md, feedback_backwards_compatible_defaults.md)
KILL_SWITCH_MONTHLY_PCT = -10.0   # 월 누적 -10% → 모든 세션 정지
KILL_SWITCH_SESSION_PCT = -20.0   # 세션 -20% → 해당 세션 정지
KILL_SWITCH_DAILY_PCT = -5.0      # 일 -5% → 신규 주문 일시 차단


@router.get("/goal/progress")
async def get_goal_progress(
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context),
):
    """
    Return progress vs the 12%/month KPI target for the current account.

    Aggregates realized_pnl from FILLED LiveTradeExecution records grouped by:
      - This month (vs target)
      - Today
      - Per-session (life-time, since session start)

    Also surfaces kill-switch breach flags so callers (cron, UI, agents) can act.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func
    from ..models.live_trading import LiveTradeExecution, ExecutionStatus, LiveBotSession

    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account selected")

    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    day_start = datetime(now.year, now.month, now.day)

    # All sessions for this account (used for capital base + per-session breakdown)
    sessions = db.query(LiveBotSession).filter(
        LiveBotSession.account_id == ctx.account_id
    ).all()
    if not sessions:
        return {
            "target_monthly_pct": GOAL_MONTHLY_RETURN_TARGET,
            "monthly_pnl_krw": 0.0,
            "monthly_return_pct": 0.0,
            "progress_pct": 0.0,
            "daily_pnl_krw": 0.0,
            "daily_return_pct": 0.0,
            "total_capital_base": 0.0,
            "session_count": 0,
            "sessions": [],
            "kill_switch": {
                "monthly_breach": False,
                "daily_breach": False,
                "breached_sessions": [],
            },
            "as_of": now.isoformat(),
        }

    session_ids = [s.id for s in sessions]
    capital_base = sum((s.initial_capital or 0.0) for s in sessions) or 0.0

    # Helper: sum realized_pnl over a period
    def _sum_pnl(start: datetime) -> float:
        row = db.query(func.coalesce(func.sum(LiveTradeExecution.realized_pnl), 0.0)).filter(
            LiveTradeExecution.session_id.in_(session_ids),
            LiveTradeExecution.status == ExecutionStatus.FILLED,
            LiveTradeExecution.signal_timestamp >= start,
        ).scalar()
        return float(row or 0.0)

    monthly_pnl = _sum_pnl(month_start)
    daily_pnl = _sum_pnl(day_start)

    monthly_return_pct = (monthly_pnl / capital_base * 100.0) if capital_base > 0 else 0.0
    daily_return_pct = (daily_pnl / capital_base * 100.0) if capital_base > 0 else 0.0
    progress_pct = (monthly_return_pct / GOAL_MONTHLY_RETURN_TARGET * 100.0) if GOAL_MONTHLY_RETURN_TARGET > 0 else 0.0

    # Per-session lifetime PnL
    per_session = (
        db.query(
            LiveTradeExecution.session_id,
            func.coalesce(func.sum(LiveTradeExecution.realized_pnl), 0.0).label("pnl"),
        )
        .filter(
            LiveTradeExecution.session_id.in_(session_ids),
            LiveTradeExecution.status == ExecutionStatus.FILLED,
        )
        .group_by(LiveTradeExecution.session_id)
        .all()
    )
    pnl_by_session = {sid: float(pnl or 0.0) for sid, pnl in per_session}

    session_rows = []
    breached_sessions = []
    for s in sessions:
        pnl = pnl_by_session.get(s.id, 0.0)
        ic = s.initial_capital or 0.0
        ret_pct = (pnl / ic * 100.0) if ic > 0 else 0.0
        breached = ret_pct <= KILL_SWITCH_SESSION_PCT
        if breached and s.status == "RUNNING":
            breached_sessions.append(s.id)
        session_rows.append({
            "session_id": s.id,
            "symbol": s.symbol,
            "status": s.status,
            "is_paper": s.is_paper,
            "initial_capital": ic,
            "realized_pnl": pnl,
            "return_pct": ret_pct,
            "session_kill_switch_breached": breached,
        })

    return {
        "target_monthly_pct": GOAL_MONTHLY_RETURN_TARGET,
        "monthly_pnl_krw": monthly_pnl,
        "monthly_return_pct": monthly_return_pct,
        "progress_pct": progress_pct,
        "daily_pnl_krw": daily_pnl,
        "daily_return_pct": daily_return_pct,
        "total_capital_base": capital_base,
        "session_count": len(sessions),
        "sessions": session_rows,
        "kill_switch": {
            "monthly_threshold_pct": KILL_SWITCH_MONTHLY_PCT,
            "session_threshold_pct": KILL_SWITCH_SESSION_PCT,
            "daily_threshold_pct": KILL_SWITCH_DAILY_PCT,
            "monthly_breach": monthly_return_pct <= KILL_SWITCH_MONTHLY_PCT,
            "daily_breach": daily_return_pct <= KILL_SWITCH_DAILY_PCT,
            "breached_sessions": breached_sessions,
        },
        "as_of": now.isoformat(),
    }
