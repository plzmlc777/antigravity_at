from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..core.live_manager import live_manager
from ..db.session import get_db
from ..core.user_context import UserAccountContext, get_user_context

router = APIRouter()

class LiveBotStartRequest(BaseModel):
    symbol: str
    strategy_name: str = "time_momentum"
    strategy_config: Dict[str, Any] = {}
    initial_capital: float = 10000000
    is_paper: bool = True

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
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Start a new Live Trading Session.
    Note: Call /live/stop-all first if starting multiple sessions to prevent duplicates.
    """
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account selected")

    try:
        config = req.dict()
        config["account_id"] = ctx.account_id  # 계좌 ID 추가
        session_id = await live_manager.start_session(config)
        return {"status": "success", "session_id": session_id, "message": "Live Session Started"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

async def verify_session_ownership(session_id: str, account_id: int, db: Session) -> bool:
    """Verify that the session belongs to the user's account"""
    from ..models.live_trading import LiveBotSession
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.account_id != account_id:
        raise HTTPException(status_code=403, detail="Session does not belong to your account")
    return True

@router.get("/check-position")
async def check_session_positions(
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Check if any running session for this account has an open position.
    Used by frontend to decide whether to show stop confirmation or position warning.
    """
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account selected")

    from ..models.live_trading import LiveBotSession, SessionStatus
    from ..db.session import SessionLocal
    db = SessionLocal()
    try:
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
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")
    await verify_session_ownership(session_id, ctx.account_id, db)
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

class ToggleOrdersRequest(BaseModel):
    enabled: bool

@router.post("/toggle-orders/{session_id}")
async def toggle_orders(
    session_id: str,
    req: ToggleOrdersRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")
    await verify_session_ownership(session_id, ctx.account_id, db)
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
    Note: We reuse ToggleOrdersRequest (Boolean enabled) where enabled=True means Paper Mode?
    Actually, let's be explicit. enabled=True means is_paper=True.
    """
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")
    await verify_session_ownership(session_id, ctx.account_id, db)
    try:
        await live_manager.toggle_mode(session_id, req.enabled)
        return {"status": "success", "is_paper": req.enabled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/liquidate/{session_id}")
async def liquidate_session(
    session_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db)
):
    """
    Emergency: Market Sell all positions and pause trading.
    """
    if not ctx.has_active_account:
        raise HTTPException(status_code=400, detail="No active account")
    await verify_session_ownership(session_id, ctx.account_id, db)
    try:
        await live_manager.liquidate_session(session_id)
        return {"status": "success", "message": "Liquidation order sent and trading paused."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_live_status(ctx: UserAccountContext = Depends(get_user_context)):
    """
    Get status of active Live Sessions for current user's account.
    """
    return await live_manager.get_status(account_id=ctx.account_id)

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
                        "cycle_pnls": [],  # Per-cycle PnL list
                        "cycle_durations": [],  # Per-cycle duration in minutes
                        "first_buy_time": None,  # First BUY timestamp in current cycle
                    },
                    "real": {
                        "trades": 0, "buys": 0, "sells": 0,
                        "buy_queue": [],
                        "cycle_pnls": [],
                        "cycle_durations": [],
                        "first_buy_time": None,
                    },
                }

            is_paper = ex.is_paper if ex.is_paper is not None else True
            key = "paper" if is_paper else "real"
            s = stats_by_symbol[sym][key]
            s["trades"] += 1
            qty = ex.filled_quantity or 0.0
            price = ex.executed_price or 0.0

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

                    # Calculate cycle duration (first BUY to SELL)
                    if s["first_buy_time"] and ex.signal_timestamp:
                        duration_mins = (ex.signal_timestamp - s["first_buy_time"]).total_seconds() / 60
                        s["cycle_durations"].append(duration_mins)

                # Reset first_buy_time if no more buys in queue (cycle complete)
                if not s["buy_queue"]:
                    s["first_buy_time"] = None

        # Calculate final stats
        result = {}
        for sym, modes in stats_by_symbol.items():
            result[sym] = {"paper": {}, "real": {}}
            for key in ["paper", "real"]:
                s = modes[key]
                cycle_pnls = s["cycle_pnls"]
                cycles = len(cycle_pnls)

                cycle_durations = s["cycle_durations"]

                if cycles > 0:
                    total_pnl = sum(cycle_pnls)
                    wins = sum(1 for p in cycle_pnls if p > 0)
                    win_rate = (wins / cycles) * 100

                    # Recent 10 cycles
                    recent_10 = cycle_pnls[-10:] if cycles >= 10 else cycle_pnls
                    recent_wins = sum(1 for p in recent_10 if p > 0)
                    recent_win_rate = (recent_wins / len(recent_10)) * 100 if recent_10 else 0

                    # Max, Min, Avg PnL
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

                    # Calculate percentage (based on average buy cost)
                    total_buy_cost = sum(p["price"] * p["qty"] for p in s.get("buy_queue", [])) if s.get("buy_queue") else 0
                    # Use total sold value for percentage calculation
                    if cycles > 0 and total_pnl != 0:
                        # Approximate: use average cycle cost
                        avg_cycle_cost = abs(total_pnl / cycles) * 10  # rough estimate
                        pnl_pct = (total_pnl / (total_pnl + avg_cycle_cost)) * 100 if avg_cycle_cost else 0
                    else:
                        pnl_pct = 0
                else:
                    total_pnl = 0
                    win_rate = 0
                    recent_win_rate = 0
                    max_pnl = 0
                    min_pnl = 0
                    avg_pnl = 0
                    pnl_pct = 0
                    avg_holding_time = None
                    max_holding_time = None
                    min_holding_time = None

                result[sym][key] = {
                    "trades": s["trades"],
                    "buys": s["buys"],
                    "sells": s["sells"],
                    "cycles": cycles,
                    "realized_pnl": round(total_pnl, 0),
                    "realized_pnl_pct": round(pnl_pct, 2),
                    "win_rate": round(win_rate, 1),
                    "recent_10_win_rate": round(recent_win_rate, 1),
                    "max_pnl": round(max_pnl, 0),
                    "min_pnl": round(min_pnl, 0),
                    "avg_pnl": round(avg_pnl, 0),
                    # Holding time stats (in minutes, null if no data)
                    "avg_holding_time": round(avg_holding_time) if avg_holding_time is not None else None,
                    "max_holding_time": round(max_holding_time) if max_holding_time is not None else None,
                    "min_holding_time": round(min_holding_time) if min_holding_time is not None else None,
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

MAX_VERSIONS_PER_RANK = 10  # Maximum versions per strategy_id + symbol combination

class ParameterVersionUpdate(PydanticBaseModel):
    version_name: Optional[str] = None
    description: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


@router.get("/parameter-versions")
async def list_parameter_versions(strategy_id: str = "", symbol: str = "", include_inactive: bool = False):
    """
    List all saved parameter versions.

    Query params:
    - strategy_id: filter by strategy (e.g., "dip_martingale")
    - symbol: filter by symbol (optional)
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

        if symbol:
            query = query.filter(StrategyParameterVersion.symbol == symbol)

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
    Maximum 10 versions per strategy_id + symbol combination.
    """
    from ..db.session import SessionLocal
    from ..models.live_trading import StrategyParameterVersion
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

        # Check 10 version limit
        if len(existing_versions) >= MAX_VERSIONS_PER_RANK:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {MAX_VERSIONS_PER_RANK} versions allowed per strategy+symbol. Delete old versions first."
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

        return {
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
