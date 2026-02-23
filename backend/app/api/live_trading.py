from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..core.live_manager import live_manager
from ..db.session import get_db
from ..core.user_context import UserAccountContext, get_user_context
from ..core.config import DEFAULT_INITIAL_CAPITAL

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

class StopAllRequest(BaseModel):
    force: bool = False

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

    # Check if session is already in memory
    if session_id in live_manager.engines:
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
        # Delete related AI evaluations first
        deleted_evals = db.query(LiveAIEvaluation).filter(
            LiveAIEvaluation.session_id == session_id
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
            "deleted_ai_evaluations": deleted_evals
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

    # Source 3: Profile-level saved_symbols (if profile_id available)
    profile_ids = list({sess.profile_id for sess in sessions if sess.profile_id})
    if profile_ids:
        from ..models.live_trading import StrategyProfile
        profiles = db.query(StrategyProfile.id, StrategyProfile.saved_symbols).filter(
            StrategyProfile.id.in_(profile_ids)
        ).all()
        for p in profiles:
            if p.saved_symbols:
                for sym in p.saved_symbols:
                    if sym.get("code") and sym.get("name") and sym["code"] not in symbol_name_map:
                        symbol_name_map[sym["code"]] = sym["name"]

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
            "symbol_name": symbol_name_map.get(sess.symbol, sess.symbol),
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
            "strategy_config": sess.strategy_config,  # Full config for UI display
            **engine_info
        })

    return results


@router.get("/accumulated-stats")
async def get_accumulated_stats(
    symbols: str = "",
    strategy_name: str = "",
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

        # Build query - filter by user's account
        query = db.query(LiveTradeExecution).join(LiveBotSession).filter(
            LiveTradeExecution.status == ExecutionStatus.FILLED,
            LiveBotSession.account_id == ctx.account_id
        )

        # If strategy_name is provided, filter by sessions with that strategy
        if strategy_name:
            query = query.filter(LiveBotSession.strategy_name == strategy_name)

        if symbol_list:
            query = query.filter(LiveTradeExecution.symbol.in_(symbol_list))

        executions = query.order_by(LiveTradeExecution.signal_timestamp).all()

        # Group by symbol and mode, track per-cycle PnLs and durations
        stats_by_symbol = {}
        for ex in executions:
            sym = ex.symbol
            if sym not in stats_by_symbol:
                stats_by_symbol[sym] = {
                    "paper": {
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
                    "real": {
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
            key = "paper" if is_paper else "real"
            s = stats_by_symbol[sym][key]
            s["trades"] += 1
            qty = ex.filled_quantity or 0.0
            price = ex.executed_price or 0.0

            # Track trade date for activity rate
            if ex.signal_timestamp:
                s["trade_dates"].add(ex.signal_timestamp.date())

            if ex.signal_type == "BUY":
                s["buys"] += 1
                # Track first BUY time for cycle duration
                if s["first_buy_time"] is None:
                    s["first_buy_time"] = ex.signal_timestamp
                s["buy_queue"].append({"qty": qty, "price": price, "timestamp": ex.signal_timestamp})
            elif ex.signal_type == "SELL":
                s["sells"] += 1
                # Match with buys (FIFO) to calculate cycle PnL
                sell_qty = qty
                sell_value = qty * price
                buy_cost = 0.0
                matched_qty = 0.0

                while sell_qty > 0 and s["buy_queue"]:
                    buy = s["buy_queue"][0]
                    match_qty = min(sell_qty, buy["qty"])
                    buy_cost += match_qty * buy["price"]
                    matched_qty += match_qty
                    sell_qty -= match_qty
                    buy["qty"] -= match_qty
                    if buy["qty"] <= 0:
                        s["buy_queue"].pop(0)

                if matched_qty > 0:
                    cycle_pnl = (price * matched_qty) - buy_cost
                    s["cycle_pnls"].append(cycle_pnl)
                    s["cycle_entry_costs"].append(buy_cost)

                    # Calculate cycle PnL percentage
                    cycle_pnl_pct = (cycle_pnl / buy_cost * 100) if buy_cost > 0 else 0
                    s["cycle_pnl_pcts"].append(cycle_pnl_pct)

                    # Track cumulative PnL for max drawdown calculation
                    prev_cum = s["cumulative_pnls"][-1] if s["cumulative_pnls"] else 0
                    s["cumulative_pnls"].append(prev_cum + cycle_pnl)

                    # Calculate cycle duration (first BUY to SELL)
                    if s["first_buy_time"] and ex.signal_timestamp:
                        duration_mins = (ex.signal_timestamp - s["first_buy_time"]).total_seconds() / 60
                        s["cycle_durations"].append(duration_mins)

                # Reset first_buy_time if no more buys in queue (cycle complete)
                if not s["buy_queue"]:
                    s["first_buy_time"] = None

        # Calculate final stats
        import statistics as stat_module
        result = {}
        for sym, modes in stats_by_symbol.items():
            result[sym] = {"paper": {}, "real": {}}
            for key in ["paper", "real"]:
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
                    "total_trades": cycles,  # = cycle count
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
        is_paper = mode.lower() == "paper"

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

            if ex.signal_type == "BUY":
                groups[config_hash]["buys"].append({"qty": qty, "price": price})
            elif ex.signal_type == "SELL":
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
                "total_trades": len(data["buys"]) + len(data["sells"]),
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
            if ex.signal_type == "BUY":
                buys.append({"qty": qty, "price": price})
            elif ex.signal_type == "SELL":
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
                "total_trades": len(matching_trades),
                "win_rate": round((wins / cycles) * 100, 1),
                "total_pnl": round(total_pnl, 0),
                "avg_pnl": round(total_pnl / cycles, 0),
                "max_pnl": round(max(cycle_pnls), 0),
                "min_pnl": round(min(cycle_pnls), 0),
            }
        else:
            stats = {
                "cycles": 0,
                "total_trades": len(matching_trades),
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
        # Initialize service with user_id to load API key from database
        service = LiveAIEvaluationService(db, user_id=ctx.user.id)

        # Run full evaluation
        is_paper = req.mode.lower() == "paper"
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
            "mode": "paper" if is_paper else "real",
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
                "mode": "paper" if e.is_paper else "real",
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
        "mode": "paper" if evaluation.is_paper else "real",
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
        "mode": session.ai_eval_mode or "paper",
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
