from fastapi import APIRouter, Depends, HTTPException
from ..core.config import DEFAULT_EXCHANGE, DEFAULT_INITIAL_CAPITAL, DEFAULT_DAYS
from fastapi.responses import FileResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.strategy_info import StrategyInfo
from ..core.user_context import UserAccountContext, get_user_context
from .auth import get_current_user, get_optional_user
from ..models.user import User
import random
import time
import itertools
import functools
import csv
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from ..schemas.optimization import (
    OptimizationResultItem,
    HeavyOptimizationRequest, HeavyOptimizationStatus,
    ScoreWeights, RecalculateScoreRequest, RecalculateScoreResponse
)
from datetime import datetime

# CSV output directory
CSV_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "optimization_results")
os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)

import logging

logger = logging.getLogger("optimization")
logger.setLevel(logging.INFO)

# Removed file logging function in favor of direct print/file write in exception block


# ============================================================================
# UNIFIED CONFIG BUILDER - Single Source of Truth
# ============================================================================
def build_backtest_config(
    strategy_config: Dict[str, Any],
    symbol: str,
    interval: str,
    days: int,
    from_date: str,
    initial_capital: int,
    to_date: str = None
) -> Dict[str, Any]:
    """
    Builds a complete, normalized config for backtest execution.

    This function is the SINGLE SOURCE OF TRUTH for config building.
    Used by BOTH optimization and individual backtest to ensure consistency.

    Returns a new config dict with all required parameters.
    """
    config = strategy_config.copy()

    # 1. Symbol (required for data fetching)
    config['symbol'] = symbol

    # 2. Interval - use config value if present, otherwise use passed value
    config['interval'] = config.get('interval', interval)

    # 3. Request-level params - MUST be included for Select/Active to work correctly
    config['days'] = days
    config['from_date'] = from_date
    config['to_date'] = to_date
    config['initial_capital'] = initial_capital

    return config


def reconcile_days_with_dates(days: int, from_date: str, to_date: str) -> int:
    """
    Ensure `days` covers at least the from_date → to_date range.

    Problem: `days` controls the DB query window (start = to_date - days).
    If days < (to_date - from_date), data loading is shorter than the user's
    intended date range, and the from_date filter becomes a no-op.

    Fix: Auto-expand days when the explicit date range is larger.
    """
    if from_date and to_date:
        try:
            fd = datetime.strptime(str(from_date)[:10], "%Y-%m-%d")
            td = datetime.strptime(str(to_date)[:10], "%Y-%m-%d")
            range_days = (td - fd).days + 1
            if range_days > days:
                logger.info(f"[reconcile_days] days {days} → {range_days} (from_date={from_date}, to_date={to_date})")
                return range_days
        except (ValueError, TypeError):
            pass
    elif from_date:
        try:
            fd = datetime.strptime(str(from_date)[:10], "%Y-%m-%d")
            range_days = (datetime.utcnow() - fd).days + 1
            if range_days > days:
                logger.info(f"[reconcile_days] days {days} → {range_days} (from_date={from_date}, no to_date)")
                return range_days
        except (ValueError, TypeError):
            pass
    return days


# ============================================================================
# UNIFIED BACKTEST CORE - Single Source of Truth for ALL backtest operations
# ============================================================================
async def _run_unified_backtest(
    strategy_id: str,
    configs: List[Dict[str, Any]],  # List of normalized configs
    symbol: str,  # Global/fallback symbol
    interval: str,
    days: int,
    from_date: str,
    initial_capital: int,
    execution_mode: str = "single",  # "single", "parallel", "exclusive"
    to_date: str = None,
    optimize_mode: bool = False,  # True = skip chart/visualization data (optimization)
    exchange_name: str = DEFAULT_EXCHANGE  # Exchange for market data source
) -> Dict[str, Any]:
    """
    Unified backtest execution function.

    - "single": Single config backtest (individual rank tab)
    - "parallel": Multiple configs, each with equal capital split
    - "exclusive": Waterfall mode, winner takes all

    This is the SINGLE SOURCE OF TRUTH for all backtest operations.
    """
    from ..core.waterfall_engine import WaterfallBacktestEngine
    from ..core.strategy_registry import StrategyRegistry
    from ..services.market_data_factory import get_market_data_service

    # 1. Get Strategy Class from Registry
    strategy_class = StrategyRegistry.get_strategy_class(strategy_id)
    if not strategy_class:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_id}' not found. Available: {StrategyRegistry.list_strategies()}"
        )

    logger.info(f"[UNIFIED_BACKTEST] mode={execution_mode}, strategy={strategy_class.__name__}, configs={len(configs)}")

    # 2. Initialize Engine
    engine = WaterfallBacktestEngine(strategy_class, {}, exchange_name=exchange_name)

    # 3. Execute based on mode
    # Respect explicit execution_mode; only use len(configs)==1 shortcut for "single" mode
    # Reconcile days with from_date/to_date to prevent date range truncation
    days = reconcile_days_with_dates(days, from_date, to_date)

    if execution_mode == "single":
        # Single backtest - use run_single_backtest directly
        data_service = get_market_data_service(exchange_name)
        config = configs[0]
        rank_symbol = config.get('symbol', symbol)

        raw_feed = await data_service.get_candles(rank_symbol, interval=interval, days=days, to_date=to_date)
        if raw_feed:
            if from_date:
                raw_feed = [c for c in raw_feed if c['timestamp'] >= from_date]
            raw_feed.sort(key=lambda x: x['timestamp'])

        if not raw_feed:
            return {"error": "No data available for the specified parameters"}

        # Multi-symbol feed loading (CIO-015): if the strategy declares it
        # needs additional pair/hedge symbols via get_required_symbols(), fetch
        # their candles too and hand them to the engine as extra_feeds.
        # Legacy single-symbol strategies return [] and see no change.
        extra_feeds: Dict[str, List[Dict[str, Any]]] = {}
        try:
            extras = []
            if hasattr(strategy_class, 'get_required_symbols'):
                extras = strategy_class.get_required_symbols(config) or []
            for extra_sym in extras:
                if not extra_sym or extra_sym == rank_symbol or extra_sym in extra_feeds:
                    continue
                extra_raw = await data_service.get_candles(
                    extra_sym, interval=interval, days=days, to_date=to_date
                )
                if not extra_raw:
                    logger.warning(
                        f"[UNIFIED_BACKTEST] pair feed empty for {extra_sym}, "
                        f"strategy={strategy_id} — continuing without it"
                    )
                    continue
                if from_date:
                    extra_raw = [c for c in extra_raw if c['timestamp'] >= from_date]
                extra_raw.sort(key=lambda x: x['timestamp'])
                extra_feeds[extra_sym] = extra_raw
                logger.info(
                    f"[UNIFIED_BACKTEST] loaded pair feed {extra_sym}: "
                    f"{len(extra_raw)} candles for strategy={strategy_id}"
                )
        except Exception as e:
            logger.warning(
                f"[UNIFIED_BACKTEST] get_required_symbols failed for {strategy_id}: {e}"
            )
            extra_feeds = {}

        result = await engine.run_single_backtest(
            config=config,
            feed=raw_feed,
            initial_capital=initial_capital,
            symbol=rank_symbol,
            optimize_mode=optimize_mode,
            rank=1,
            extra_feeds=extra_feeds if extra_feeds else None,
        )
        result['strategy_id'] = strategy_id
        result['execution_mode'] = 'single'
        if extra_feeds:
            result['pair_symbols_loaded'] = list(extra_feeds.keys())

    elif execution_mode == "parallel":
        result = await engine.run_parallel(
            strategies_config=configs,
            global_symbol=symbol,
            duration_days=days,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            initial_capital=initial_capital,
            optimize_mode=optimize_mode,
            exchange_name=exchange_name
        )
        result['strategy_id'] = f"Integrated (Parallel Mode: Equal Split)"
        result['execution_mode'] = 'parallel'

    else:  # exclusive
        result = await engine.run_integrated(
            strategies_config=configs,
            global_symbol=symbol,
            duration_days=days,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            initial_capital=initial_capital,
            optimize_mode=optimize_mode,
            exchange_name=exchange_name
        )
        result['strategy_id'] = "Integrated (League Mode: Winner Takes All)"
        result['execution_mode'] = 'exclusive'

    return result


# Global Task Registry
HEAVY_OPTIMIZATION_TASKS: Dict[str, Dict[str, Any]] = {}  # For large-scale optimizations

import uuid
import multiprocessing
import atexit
import signal

# Track active ProcessPoolExecutors for cleanup on exit
_active_executors: list = []

def _cleanup_executors():
    """Kill all worker processes on main process exit (PM2 restart, etc.)."""
    for executor in list(_active_executors):
        try:
            # Access internal worker PIDs and kill them directly
            if hasattr(executor, '_processes'):
                for pid in list(executor._processes.keys()):
                    try:
                        os.kill(pid, signal.SIGKILL)
                        logger.info(f"Killed worker process {pid}")
                    except (ProcessLookupError, PermissionError):
                        pass
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning(f"Error during executor cleanup: {e}")
    _active_executors.clear()

atexit.register(_cleanup_executors)

def _signal_handler(signum, frame):
    """Handle SIGTERM (PM2 stop/restart) by cleaning up worker processes."""
    logger.info(f"Received signal {signum}, cleaning up worker processes...")
    _cleanup_executors()
    # Re-raise to allow normal shutdown
    raise SystemExit(0)

# Register SIGTERM handler (PM2 sends SIGTERM on restart)
try:
    signal.signal(signal.SIGTERM, _signal_handler)
except (OSError, ValueError):
    pass  # May fail in non-main thread


def _get_worker_count():
    """Determine worker count for parallel optimization.
    Uses cpu_count - 2 (reserve 2 cores for system/live trading), clamped to [2, 6].
    """
    cpu = os.cpu_count() or 4
    return max(2, min(6, cpu - 2))


def _process_optimization_result(config, res):
    """Process a single backtest result into OptimizationResultItem.
    Returns (OptimizationResultItem, error_msg_or_None).
    """
    if "error" in res:
        return None, str(res['error'])

    ret = float(str(res['total_return']).replace('%', '').replace(',', ''))
    wr = float(str(res['win_rate']).replace('%', ''))
    trades = int(res.get('total_cycles', 0))
    score = ret * (wr / 100.0)

    recent_10_wr = res.get("recent_10_win_rate", 0)
    if isinstance(recent_10_wr, str):
        recent_10_wr = float(recent_10_wr.replace('%', '')) if recent_10_wr != '-' else 0.0

    from ..core.stats_serializer import serialize_backtest_stats
    stats_obj = serialize_backtest_stats(res)
    stats_dict = stats_obj.model_dump()

    item = OptimizationResultItem(
        rank=0,
        symbol=config.get('symbol', ''),
        config=config,
        total_return=ret,
        win_rate=wr,
        recent_10_win_rate=recent_10_wr,
        total_cycles=trades,
        score=round(score, 2),
        max_drawdown=str(stats_obj.max_drawdown) if stats_obj.max_drawdown else "-",
        profit_factor=str(stats_obj.profit_factor) if stats_obj.profit_factor else "-",
        avg_pnl=str(stats_obj.avg_pnl) if stats_obj.avg_pnl else "-",
        sharpe_ratio=str(stats_obj.sharpe_ratio) if stats_obj.sharpe_ratio else "-",
        stability_score=str(stats_obj.stability_score) if stats_obj.stability_score else "-",
        acceleration_score=str(stats_obj.acceleration_score) if stats_obj.acceleration_score else "-",
        activity_rate=str(stats_obj.activity_rate) if stats_obj.activity_rate else "-",
        total_days=stats_obj.total_days,
        avg_holding_time=str(stats_obj.avg_holding_time) if stats_obj.avg_holding_time else "-",
        max_holding_time=str(stats_obj.max_holding_time) if stats_obj.max_holding_time else "-",
        min_holding_time=str(stats_obj.min_holding_time) if stats_obj.min_holding_time else "-",
        max_profit=str(stats_obj.max_profit) if stats_obj.max_profit else "-",
        max_loss=str(stats_obj.max_loss) if stats_obj.max_loss else "-",
        stats=stats_dict,
        metrics={}
    )
    return item, None


def _run_sync_in_process(strategy_cls, config, symbol, interval, days, from_date, initial_capital, to_date=None, exchange_name=DEFAULT_EXCHANGE):
    # Lower process priority so system/SSH processes remain responsive
    try:
        os.nice(10)
    except (OSError, AttributeError):
        pass  # Windows or permission error

    # Force close inherited DB connections to prevent SSL/OperationalError in worker process
    try:
        from ..db.session import engine
        engine.dispose()
    except Exception as e:
        print(f"Warning: Failed to dispose engine in worker: {e}")

    # Force reload modules to ensure latest code is used (worker process caching issue)
    # IMPORTANT: Reload order matters! base → martingale_base → strategies → registry
    # If base is reloaded without martingale_base, issubclass() checks break because
    # strategy classes inherit OLD BaseStrategy via unreloaded MartingaleBase.
    import sys
    import importlib

    # 1. Reload base classes in dependency order
    for base_mod in ['strategies.base', 'strategies.martingale_base']:
        if base_mod in sys.modules:
            try:
                importlib.reload(sys.modules[base_mod])
            except Exception:
                pass

    # 2. Reload ALL strategy modules (auto-discover, handles AI-generated strategies too)
    strategy_mods = [m for m in list(sys.modules.keys())
                     if m.startswith('strategies.') and m not in ('strategies.base', 'strategies.martingale_base')]
    for mod_name in strategy_mods:
        try:
            importlib.reload(sys.modules[mod_name])
        except Exception:
            pass

    # 3. Reload infrastructure modules
    for mod_name in ['app.core.strategy_registry', 'app.core.waterfall_engine', 'app.services.market_data', 'app.services.market_data_factory', 'app.services.binance_market_data']:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass

    import asyncio

    # IMPORTANT: After module reload, get FRESH strategy class from registry
    # The strategy_cls parameter is the OLD class reference from before reload
    from ..core.strategy_registry import StrategyRegistry
    strategy_id = config.get('strategy_id', 'dip_martingale')

    # create new loop for this process
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Use unified config builder (Single Source of Truth)
    print(f"[OPT_WORKER] symbol={symbol}, interval={interval}, days={days}, from_date={from_date}, to_date={to_date}")
    config = build_backtest_config(config, symbol, interval, days, from_date, initial_capital, to_date=to_date)
    actual_interval = config['interval']

    # Delegate to _run_unified_backtest (Single Source of Truth)
    # Use execution_mode="single" to ensure EXACT same code path as individual backtest
    # (Previously "exclusive" which routed to run_integrated() - functionally similar
    #  but not identical code path, causing potential result discrepancies)
    result = loop.run_until_complete(_run_unified_backtest(
        strategy_id=strategy_id,
        configs=[config],
        symbol=symbol,
        interval=actual_interval,
        days=days,
        from_date=from_date,
        initial_capital=initial_capital,
        execution_mode="single",
        to_date=to_date,
        optimize_mode=True,
        exchange_name=exchange_name
    ))

    return config, result


router = APIRouter()

@router.get("/debug-probe")
async def debug_probe():
    return {"status": "alive", "message": "Router is active"}

class IntegratedBacktestRequest(BaseModel):
    symbol: str = "TEST"
    interval: str = "1m"
    days: int = DEFAULT_DAYS
    from_date: Optional[str] = None
    initial_capital: int = DEFAULT_INITIAL_CAPITAL
    configs: List[Dict[str, Any]] = [] # Ordered list of configs
    exchange_name: str = DEFAULT_EXCHANGE  # Exchange for market data source (Kiwoom, Binance, etc.)

@router.post("/integrated/v2-backtest")
async def run_integrated_backtest(request: IntegratedBacktestRequest):
    try:
        from ..core.waterfall_engine import WaterfallBacktestEngine

        # Strategy class is resolved per-config inside run_integrated via StrategyRegistry
        # (each cfg can carry its own 'strategy_id' / 'strategy' field). The init class is a
        # placeholder fallback for configs that don't specify one.
        from strategies.base import BaseStrategy
        class MockStrategy(BaseStrategy):
             def initialize(self): pass
             def on_data(self, data): pass

        engine = WaterfallBacktestEngine(MockStrategy, {}, exchange_name=request.exchange_name)

        result = await engine.run_integrated(
            strategies_config=request.configs,
            global_symbol=request.symbol,
            interval=request.interval,
            duration_days=request.days,
            from_date=request.from_date,
            initial_capital=request.initial_capital,
            exchange_name=request.exchange_name,
        )
        
        return {
            "strategy_id": "integrated_waterfall",
            "total_return": result['total_return'],
            "win_rate": result['win_rate'],
            "recent_10_win_rate": result.get('recent_10_win_rate', 0),
            "max_drawdown": result['max_drawdown'],
            "total_cycles": result.get('total_cycles', 0),
            "avg_pnl": result.get('avg_pnl', "0%"),
            "max_profit": result.get('max_profit', "0%"),
            "max_loss": result.get('max_loss', "0%"),
            "profit_factor": result.get('profit_factor', "0.00"),
            "sharpe_ratio": result.get('sharpe_ratio', "0.00"),
            "activity_rate": result.get('activity_rate', "0%"),
            "total_days": result.get('total_days', 0),
            "avg_holding_time": result.get('avg_holding_time', "0m"),
            "max_holding_time": result.get('max_holding_time', "0m"),
            "min_holding_time": result.get('min_holding_time', "0m"),
            "decile_stats": result.get('decile_stats', []),
            "bucket_stats": result.get('bucket_stats', []),
            "stability_score": result.get('stability_score', "0.00"),
            "acceleration_score": result.get('acceleration_score', "0.00"),
            "chart_data": result['chart_data'],
            "ohlcv_data": result.get('ohlcv_data', []),
            "trades": result.get('trades', []),
            "matched_trades": result.get('matched_trades', []),
            "multi_ohlcv_data": result.get('multi_ohlcv_data', {}),
            "rank_stats_list": result.get('rank_stats_list', []),
            "logs": result.get('logs', [])
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
            "logs": ["CRASHED"]
        }

class Strategy(BaseModel):
    id: str
    name: str
    description: str
    code: Optional[str] = None
    tags: Optional[List[str]] = None
    detailed_description: Optional[str] = None
    parameter_schema: Optional[Dict[str, Any]] = None
    status: Optional[str] = "active"
    owner_id: Optional[int] = None
    is_public: Optional[bool] = False

    class Config:
        from_attributes = True

# Hardcoded strategies removed in favor of DB persistence.

@router.get("/list", response_model=List[Strategy])
async def list_strategies(
    status: Optional[str] = "active",
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    from ..core.strategy_registry import StrategyRegistry
    from sqlalchemy import or_

    # Auto-sync: ensure all discovered strategies exist in strategy_info
    registered = StrategyRegistry.list_strategies()
    existing_ids = {row[0] for row in db.query(StrategyInfo.id).all()}
    for sid in registered:
        if sid not in existing_ids:
            cls = StrategyRegistry.get_strategy_class(sid)
            if cls:
                doc = (cls.__doc__ or '').strip().split('\n')[0]
                name = cls.__name__.replace('Strategy', '').replace('_', ' ')
                db.add(StrategyInfo(id=sid, name=name, description=doc, status='active', is_public=True))
                logger.info(f"Auto-synced strategy_info: {sid}")
    db.commit()

    query = db.query(StrategyInfo)
    if status:
        query = query.filter(StrategyInfo.status == status)

    # Ownership filter: show public + own + ownerless (legacy)
    if current_user:
        query = query.filter(or_(
            StrategyInfo.is_public == True,
            StrategyInfo.owner_id == current_user.id,
            StrategyInfo.owner_id.is_(None),
        ))
    else:
        query = query.filter(or_(
            StrategyInfo.is_public == True,
            StrategyInfo.owner_id.is_(None),
        ))

    strats = query.all()
    result = []
    for s in strats:
        data = Strategy.from_orm(s)
        # Always prefer class schema (Single Source of Truth) over DB schema
        class_schema = StrategyRegistry.get_parameter_schema(s.id)
        if class_schema:
            data.parameter_schema = class_schema
        result.append(data)
    return result


class VisibilityUpdate(BaseModel):
    is_public: bool


@router.patch("/{strategy_id}/visibility")
async def toggle_strategy_visibility(
    strategy_id: str,
    body: VisibilityUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Toggle public/private visibility. Owner or admin can change."""
    strategy = db.query(StrategyInfo).filter(StrategyInfo.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    is_owner = strategy.owner_id is not None and strategy.owner_id == current_user.id
    is_admin = getattr(current_user, 'is_admin', False)
    if not (is_owner or is_admin or strategy.owner_id is None):
        raise HTTPException(status_code=403, detail="Only the owner can change visibility")
    if strategy.owner_id is None:
        strategy.owner_id = current_user.id
    strategy.is_public = body.is_public
    db.commit()
    return {"status": "ok", "strategy_id": strategy_id, "is_public": body.is_public}

@router.post("/generate")
async def generate_strategy_code(prompt: Dict[str, str]):
    # Mock AI Delay
    time.sleep(1.5)
    return {
        "id": f"ai_gen_{random.randint(1000, 9999)}",
        "name": "AI Generated Strategy",
        "description": f"Generated based on: {prompt.get('prompt')}",
        "code": f"# AI Generated Code for: {prompt.get('prompt')}\n\nclass MyStrategy(BaseStrategy):\n    def on_data(self, data):\n        # Logic derived from AI\n        if data.close > data.open * 1.05:\n            self.buy()",
        "tags": ["AI-Generated"]
    }



class BacktestRequest(BaseModel):
    symbol: str = "TEST"
    interval: str = "1m"
    days: int = DEFAULT_DAYS
    from_date: Optional[str] = None # Or start_date
    start_date: Optional[str] = None # Aliases
    to_date: Optional[str] = None  # End date (default: yesterday). Fixes date range for reproducible results.
    initial_capital: int = DEFAULT_INITIAL_CAPITAL
    config: Dict[str, Any] = {} # Nested config from frontend strategy selector
    exchange_name: str = DEFAULT_EXCHANGE  # Exchange for market data source (Kiwoom, Binance, etc.)

@router.post("/{strategy_id}/backtest")
async def run_mock_backtest(strategy_id: str, request: BacktestRequest):
    """
    Individual backtest endpoint.
    Uses _run_unified_backtest() for consistent behavior with integrated backtest.
    """
    start_date = request.start_date or request.from_date

    # Build normalized config (Single Source of Truth)
    config = build_backtest_config(
        request.config,
        symbol=request.symbol,
        interval=request.interval,
        days=request.days,
        from_date=start_date,
        initial_capital=request.initial_capital,
        to_date=request.to_date
    )

    logger.info(f"[BACKTEST] symbol={request.symbol}, interval={config['interval']}, days={request.days}, from_date={start_date}, to_date={request.to_date}")

    # Use unified backtest function (Single Source of Truth)
    result = await _run_unified_backtest(
        strategy_id=strategy_id,
        configs=[config],  # Single config wrapped in list
        symbol=request.symbol,
        interval=config['interval'],
        days=request.days,
        from_date=start_date,
        initial_capital=request.initial_capital,
        execution_mode="single",
        to_date=request.to_date,
        exchange_name=request.exchange_name
    )

    # Return standardized response
    return {
        "strategy_id": strategy_id,
        "total_return": result.get('total_return', 0),
        "win_rate": result.get('win_rate', 0),
        "recent_10_win_rate": result.get('recent_10_win_rate', 0),
        "max_drawdown": result.get('max_drawdown', 0),
        "total_cycles": result.get('total_cycles', 0),
        "avg_pnl": result.get('avg_pnl', "0%"),
        "max_profit": result.get('max_profit', "0%"),
        "max_loss": result.get('max_loss', "0%"),
        "profit_factor": result.get('profit_factor', "0.00"),
        "sharpe_ratio": result.get('sharpe_ratio', "0.00"),
        "activity_rate": result.get('activity_rate', "0%"),
        "total_days": result.get('total_days', 0),
        "avg_holding_time": result.get('avg_holding_time', "0m"),
        "max_holding_time": result.get('max_holding_time', "0m"),
        "min_holding_time": result.get('min_holding_time', "0m"),
        "decile_stats": result.get('decile_stats', []),
        "bucket_stats": result.get('bucket_stats', []),
        "stability_score": result.get('stability_score', "0.00"),
        "acceleration_score": result.get('acceleration_score', "0.00"),
        "chart_data": result.get('chart_data', []),
        "ohlcv_data": result.get('ohlcv_data', []),
        "trades": result.get('trades', []),
        "logs": result.get('logs', []),
        "rank_stats_list": result.get('rank_stats_list', [])
    }

# ============================================================================
# V2 SIGNAL-BASED BACKTEST (deprecated → v3으로 리다이렉트)
# ============================================================================

@router.post("/{strategy_id}/v2-backtest")
async def run_signal_backtest(strategy_id: str, request: BacktestRequest):
    """v2-backtest는 v3-backtest로 대체되었습니다. 호환성을 위해 v3로 위임."""
    return await run_intercepted_backtest(strategy_id, request)


# ============================================================================
# V3 SIGNAL-INTERCEPT BACKTEST (ExecutionEngine 검증용)
# ============================================================================

@router.post("/{strategy_id}/v3-backtest")
async def run_intercepted_backtest(strategy_id: str, request: BacktestRequest):
    """
    ExecutionEngine 기반 백테스트 (v3).
    SignalInterceptContext + PassthroughExecutor로 v1과 동일 결과 보장.
    추가로 ExecutionEngine 통계 + 시그널 데이터 반환.
    """
    from ..core.signal_context import SignalInterceptContext
    from ..core.execution_engine import PassthroughExecutor
    from ..core.waterfall_engine import WaterfallBacktestEngine, BacktestContext as WaterfallContext, is_futures_exchange
    from ..core.strategy_registry import StrategyRegistry
    from ..services.market_data_factory import get_market_data_service
    from ..core.data_schemas import EQUITY_VALUE_KEY

    strategy_class = StrategyRegistry.get_strategy_class(strategy_id)
    if not strategy_class:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_id}' not found."
        )

    start_date = request.start_date or request.from_date
    config = build_backtest_config(
        request.config,
        symbol=request.symbol,
        interval=request.interval,
        days=request.days,
        from_date=start_date,
        initial_capital=request.initial_capital,
        to_date=request.to_date
    )

    # 1. Fetch data
    exchange_name = request.exchange_name
    data_service = get_market_data_service(exchange_name)
    days = reconcile_days_with_dates(request.days, start_date, request.to_date)
    raw_feed = await data_service.get_candles(
        request.symbol, interval=config['interval'], days=days, to_date=request.to_date
    )
    if raw_feed:
        if start_date:
            raw_feed = [c for c in raw_feed if c['timestamp'] >= start_date]
        raw_feed.sort(key=lambda x: x['timestamp'])

    if not raw_feed:
        return {"error": "No data available"}

    # 2. Create real context (WaterfallBacktestContext)
    leverage = 1
    if is_futures_exchange(exchange_name):
        leverage = max(1, int(config.get('leverage', 1)))
    feeds = {request.symbol: raw_feed}
    real_context = WaterfallContext(
        feeds, initial_capital=request.initial_capital,
        primary_symbol=request.symbol, leverage=leverage
    )

    # 3. Wrap with SignalInterceptContext + PassthroughExecutor
    executor = PassthroughExecutor()
    context = SignalInterceptContext(real_context, executor)

    # 4. Create and run strategy
    p_config = config.copy()
    p_config['initial_capital'] = request.initial_capital
    p_config['symbol'] = request.symbol
    p_config['exchange_name'] = exchange_name

    strat = strategy_class(context, p_config)
    if hasattr(strat, 'initialize'):
        strat.initialize()

    for candle in raw_feed:
        real_context.current_timestamp = candle['timestamp']
        try:
            context.process_pending_orders(candle)
            strat.on_data(candle)
            context.update_equity()
        except Exception:
            pass

    # 5. Force liquidation at end
    long_positions = {}
    short_positions = {}
    for t in real_context.trades:
        sym = t['symbol']
        qty = t['quantity']
        if t['type'] == 'buy':
            long_positions[sym] = long_positions.get(sym, 0) + qty
        elif t['type'] == 'sell':
            long_positions[sym] = long_positions.get(sym, 0) - qty
        elif t['type'] == 'short':
            short_positions[sym] = short_positions.get(sym, 0) + qty
        elif t['type'] == 'close_short':
            short_positions[sym] = short_positions.get(sym, 0) - qty

    if raw_feed:
        close_price = raw_feed[-1]['close']
        for sym, net in long_positions.items():
            if net > 0:
                context.sell(sym, int(net), price=close_price,
                             metadata={"reason": "end_of_backtest_liquidation"})
                context.update_equity()
        for sym, net in short_positions.items():
            if net > 0:
                try:
                    context.close_position(sym, metadata={"reason": "end_of_backtest_liquidation"})
                except Exception:
                    context.buy(sym, int(net), price=close_price,
                                metadata={"reason": "end_of_backtest_liquidation"})
                context.update_equity()

    # 6. Calculate stats using WaterfallBacktestEngine._generate_stats
    engine = WaterfallBacktestEngine(strategy_class, {}, exchange_name=exchange_name)
    stats = engine._generate_stats(real_context, raw_feed)

    final_equity = real_context.equity_curve[-1][EQUITY_VALUE_KEY] if real_context.equity_curve else request.initial_capital

    return {
        "engine": "signal_v3",
        "strategy_id": strategy_id,
        "total_return": stats.get('total_return', 0),
        "win_rate": stats.get('win_rate', 0),
        "max_drawdown": stats.get('max_drawdown', 0),
        "total_cycles": stats.get('total_cycles', 0),
        "avg_pnl": stats.get('avg_pnl', "0%"),
        "max_profit": stats.get('max_profit', "0%"),
        "max_loss": stats.get('max_loss', "0%"),
        "profit_factor": stats.get('profit_factor', "0.00"),
        "sharpe_ratio": stats.get('sharpe_ratio', "0.00"),
        "activity_rate": stats.get('activity_rate', "0%"),
        "total_days": stats.get('total_days', 0),
        "avg_holding_time": stats.get('avg_holding_time', "0m"),
        "stability_score": stats.get('stability_score', "0.00"),
        "acceleration_score": stats.get('acceleration_score', "0.00"),
        "chart_data": stats.get('chart_data', []),
        "ohlcv_data": stats.get('ohlcv_data', []),
        "trades": stats.get('trades', []),
        "logs": stats.get('logs', []),
        # V3 전용: ExecutionEngine 통계 + 시그널 데이터
        "signal_stats": context.get_signal_stats(),
        "engine_stats": executor.get_stats(),
    }


# ============================================================================
# HEAVY OPTIMIZATION (Large-scale, 10K-100K+ combinations)
# ============================================================================

def _heavy_optimize_background_task(task_id: str, run_args: List, strategy_id: str, start_time: float, total_combos: int, tab_id: str = None, save_account_id: int = None, execution_mode: str = "standard"):
    """
    Background task for heavy optimization.
    Streams results directly to CSV to avoid memory issues.
    Supports 'standard' (sequential) and 'fast' (parallel ProcessPool) modes.
    """
    import heapq

    csv_filename = f"heavy_opt_{task_id}.csv"
    csv_filepath = os.path.join(CSV_OUTPUT_DIR, csv_filename)

    try:
        # Update status
        HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "running"
        HEAVY_OPTIMIZATION_TASKS[task_id]["progress_total"] = total_combos

        # Top 50 results (min-heap by score)
        top_results = []
        processed = 0
        failures = 0

        # CSV columns
        csv_columns = [
            'rank', 'symbol', 'score', 'total_return', 'win_rate', 'recent_10_win_rate', 'total_cycles',
            'max_drawdown', 'profit_factor', 'sharpe_ratio', 'avg_pnl',
            'stability_score', 'acceleration_score', 'activity_rate',
            'avg_holding_time', 'max_holding_time', 'min_holding_time',
            'max_profit', 'max_loss', 'total_days'
        ]
        config_keys = None

        def _process_heavy_result(config, res, writer, csvfile, seq_idx):
            """Process a single heavy optimization result: write CSV + update heap."""
            nonlocal config_keys, processed, failures, top_results

            if "error" in res:
                failures += 1
                return writer

            symbol = config.get('symbol', '')
            total_return = float(str(res.get('total_return', '0')).replace('%', '').replace(',', ''))
            win_rate = float(str(res.get('win_rate', '0')).replace('%', ''))
            total_cycles = int(res.get('total_cycles', 0))
            score = total_return * (win_rate / 100.0)

            recent_10_wr = res.get("recent_10_win_rate", 0)
            if isinstance(recent_10_wr, str):
                recent_10_wr = float(recent_10_wr.replace('%', '')) if recent_10_wr != '-' else 0.0

            row = {
                'rank': 0, 'symbol': symbol, 'score': round(score, 2),
                'total_return': total_return, 'win_rate': win_rate,
                'recent_10_win_rate': recent_10_wr, 'total_cycles': total_cycles,
                'max_drawdown': str(res.get('max_drawdown', '-')),
                'profit_factor': str(res.get('profit_factor', '-')),
                'sharpe_ratio': str(res.get('sharpe_ratio', '-')),
                'avg_pnl': str(res.get('avg_pnl', '-')),
                'stability_score': str(res.get('stability_score', '-')),
                'acceleration_score': str(res.get('acceleration_score', '-')),
                'activity_rate': str(res.get('activity_rate', '-')),
                'avg_holding_time': str(res.get('avg_holding_time', '-')),
                'max_holding_time': str(res.get('max_holding_time', '-')),
                'min_holding_time': str(res.get('min_holding_time', '-')),
                'max_profit': str(res.get('max_profit', '-')),
                'max_loss': str(res.get('max_loss', '-')),
                'total_days': int(res.get('total_days', 0)),
            }

            if writer is None:
                config_keys = [k for k in config.keys() if k not in ['symbol', 'strategy_id']]
                all_columns = csv_columns + [f"config_{k}" for k in config_keys]
                writer = csv.DictWriter(csvfile, fieldnames=all_columns)
                writer.writeheader()

            for k in config_keys:
                row[f"config_{k}"] = config.get(k, "")

            writer.writerow(row)
            csvfile.flush()

            result_entry = {
                'score': score, 'symbol': symbol,
                'total_return': total_return, 'win_rate': win_rate,
                'recent_10_win_rate': recent_10_wr, 'total_cycles': total_cycles,
                'max_drawdown': str(res.get('max_drawdown', '-')),
                'profit_factor': str(res.get('profit_factor', '-')),
                'sharpe_ratio': str(res.get('sharpe_ratio', '-')),
                'avg_pnl': str(res.get('avg_pnl', '-')),
                'stability_score': str(res.get('stability_score', '-')),
                'acceleration_score': str(res.get('acceleration_score', '-')),
                'activity_rate': str(res.get('activity_rate', '-')),
                'avg_holding_time': str(res.get('avg_holding_time', '-')),
                'max_holding_time': str(res.get('max_holding_time', '-')),
                'min_holding_time': str(res.get('min_holding_time', '-')),
                'max_profit': str(res.get('max_profit', '-')),
                'max_loss': str(res.get('max_loss', '-')),
                'total_days': int(res.get('total_days', 0)),
                'config': {k: config.get(k) for k in config_keys} if config_keys else {}
            }

            if len(top_results) < 50:
                heapq.heappush(top_results, (score, seq_idx, result_entry))
            elif score > top_results[0][0]:
                heapq.heapreplace(top_results, (score, seq_idx, result_entry))

            processed += 1
            return writer

        def _update_heavy_progress(completed_count):
            elapsed = time.time() - start_time
            avg_time = elapsed / completed_count if completed_count > 0 else 0
            remaining = avg_time * (total_combos - completed_count)

            HEAVY_OPTIMIZATION_TASKS[task_id]["progress_current"] = completed_count
            HEAVY_OPTIMIZATION_TASKS[task_id]["elapsed_seconds"] = elapsed
            HEAVY_OPTIMIZATION_TASKS[task_id]["estimated_remaining_seconds"] = remaining

            mode_tag = " [parallel]" if execution_mode == "fast" else ""
            HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Processing ({completed_count}/{total_combos}){mode_tag}..."

            if completed_count % 10 == 0:
                sorted_top = sorted([t[2] for t in top_results], key=lambda x: x['score'], reverse=True)
                HEAVY_OPTIMIZATION_TASKS[task_id]["top_results"] = sorted_top

        # Open CSV file for streaming write
        with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = None

            if execution_mode == "fast":
                # ===== PARALLEL EXECUTION =====
                worker_count = _get_worker_count()
                logger.info(f"[HEAVY PARALLEL] Running {total_combos} with {worker_count} workers (spawn)")
                HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Starting parallel execution ({worker_count} workers)..."

                ctx = multiprocessing.get_context('spawn')
                completed_count = 0

                executor = ProcessPoolExecutor(
                    max_workers=worker_count, mp_context=ctx,
                    max_tasks_per_child=1  # Restart workers after each task to prevent memory leak
                )
                _active_executors.append(executor)
                try:
                    # Batch submission to avoid holding all futures in memory
                    batch_size = worker_count * 2
                    args_iter = iter(enumerate(run_args))
                    active_futures = {}
                    iter_finished = False

                    def _submit_heavy_batch():
                        nonlocal iter_finished
                        while len(active_futures) < batch_size and not iter_finished:
                            try:
                                i, args = next(args_iter)
                                future = executor.submit(_run_sync_in_process, *args)
                                active_futures[future] = i
                            except StopIteration:
                                iter_finished = True
                                break

                    _submit_heavy_batch()

                    while active_futures:
                        if HEAVY_OPTIMIZATION_TASKS[task_id].get("cancel_requested"):
                            for f in active_futures:
                                f.cancel()
                            HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "cancelled"
                            HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Cancelled at {completed_count}/{total_combos}"
                            break

                        done_futures = set()
                        for future in as_completed(active_futures):
                            done_futures.add(future)
                            completed_count += 1
                            idx = active_futures[future]

                            try:
                                config, res = future.result()
                                writer = _process_heavy_result(config, res, writer, csvfile, idx)
                            except Exception as e:
                                failures += 1
                                logger.warning(f"Heavy opt future {idx} failed: {e}")

                            _update_heavy_progress(completed_count)
                            _submit_heavy_batch()
                            break  # Process one at a time to submit new work

                        for f in done_futures:
                            del active_futures[f]

                finally:
                    executor.shutdown(wait=True)
                    if executor in _active_executors:
                        _active_executors.remove(executor)

            else:
                # ===== SEQUENTIAL EXECUTION =====
                for i, args in enumerate(run_args):
                    if HEAVY_OPTIMIZATION_TASKS[task_id].get("cancel_requested"):
                        logger.info(f"Heavy optimization {task_id} cancellation requested at {i}/{total_combos}")
                        HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "cancelled"
                        HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Cancelled at {i}/{total_combos}"
                        break

                    if i % 5 == 0:
                        time.sleep(0.01)

                    try:
                        config, res = _run_sync_in_process(*args)
                        writer = _process_heavy_result(config, res, writer, csvfile, i)
                    except Exception as e:
                        failures += 1
                        logger.warning(f"Heavy opt iteration {i} failed: {e}")

                    _update_heavy_progress(i + 1)

        # Finalize
        elapsed = time.time() - start_time
        file_size = os.path.getsize(csv_filepath) if os.path.exists(csv_filepath) else 0

        sorted_top = sorted([t[2] for t in top_results], key=lambda x: x['score'], reverse=True)

        if HEAVY_OPTIMIZATION_TASKS[task_id]["status"] != "cancelled":
            HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "completed"
            elapsed_str = f"{elapsed:.1f}s" if elapsed < 60 else f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
            HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Completed: {processed} results, {failures} failures (Elapsed: {elapsed_str})"

        HEAVY_OPTIMIZATION_TASKS[task_id]["csv_file"] = csv_filename
        HEAVY_OPTIMIZATION_TASKS[task_id]["file_size_bytes"] = file_size
        HEAVY_OPTIMIZATION_TASKS[task_id]["top_results"] = sorted_top
        HEAVY_OPTIMIZATION_TASKS[task_id]["progress_current"] = total_combos
        HEAVY_OPTIMIZATION_TASKS[task_id]["elapsed_seconds"] = elapsed

        logger.info(f"Heavy optimization {task_id} completed: {processed} results in {elapsed:.1f}s")

        # Server-side auto-save to DB (same as regular optimization)
        if tab_id and HEAVY_OPTIMIZATION_TASKS[task_id]["status"] == "completed":
            try:
                from ..db.session import SessionLocal
                from ..models.strategy_result import StrategyAnalysisResult
                db = SessionLocal()
                try:
                    # Format top 50 results for DB storage using centralized serializer
                    from ..core.stats_serializer import serialize_backtest_stats

                    def format_result_item(idx: int, r: dict) -> dict:
                        """Format single optimization result with standardized stats."""
                        stats = serialize_backtest_stats(r)
                        stats_dict = stats.model_dump()
                        return {
                            "rank": idx + 1,
                            "symbol": r.get("symbol", ""),
                            "config": r.get("config", {}),
                            "score": r.get("score", 0),
                            # Single source of truth for all stats
                            "stats": stats_dict,
                            # Essential top-level fields for quick access
                            "total_return": stats.total_return,
                            "win_rate": stats.win_rate,
                            "total_cycles": stats.total_cycles,
                        }

                    result_data = {
                        "strategy_id": strategy_id,
                        "best_config": sorted_top[0]["config"] if sorted_top else {},
                        "results": [format_result_item(idx, r) for idx, r in enumerate(sorted_top)],
                        "total_combinations": total_combos,
                        "elapsed_time": elapsed,
                        "status": "completed"
                    }

                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    stmt = pg_insert(StrategyAnalysisResult).values(
                        tab_id=tab_id,
                        result_type="optimization",
                        account_id=save_account_id,
                        data=result_data,
                    ).on_conflict_do_update(
                        constraint="strategy_results_pkey",
                        set_=dict(data=result_data, account_id=save_account_id),
                    )
                    db.execute(stmt)
                    db.commit()
                    logger.info(f"[Heavy Optimization] Auto-saved {len(sorted_top)} results to DB (tab_id={tab_id})")
                finally:
                    db.close()
            except Exception as save_err:
                logger.error(f"[Heavy Optimization] Failed to auto-save to DB: {save_err}")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Heavy optimization {task_id} failed: {e}\n{tb}")
        HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "failed"
        HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = str(e)


@router.post("/heavy-optimize/{strategy_id}")
async def start_heavy_optimization(strategy_id: str, request: HeavyOptimizationRequest, ctx: UserAccountContext = Depends(get_user_context)):
    """
    Start a large-scale optimization (10K-100K+ combinations).
    Results are streamed directly to CSV file.
    """
    start_time = time.time()

    # Get strategy class
    from ..core.strategy_registry import StrategyRegistry
    strategy_class = StrategyRegistry.get_strategy_class(strategy_id)

    if not strategy_class:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    # Generate combinations
    symbols = request.symbols
    if not symbols:
        raise HTTPException(status_code=400, detail="At least one symbol is required")

    keys = list(request.parameter_ranges.keys())
    values = list(request.parameter_ranges.values())
    param_combinations = list(itertools.product(*values))

    total_combinations = len(symbols) * len(param_combinations)

    if total_combinations < 1:
        raise HTTPException(status_code=400, detail="No combinations to run")

    logger.info(f"[Heavy Optimize] Starting {total_combinations} combinations ({len(symbols)} symbols x {len(param_combinations)} params)")

    # Prepare run args
    base_config = request.base_config.copy()
    run_args = []

    for symbol in symbols:
        for combo in param_combinations:
            current_config = base_config.copy()
            current_config['strategy_id'] = strategy_id
            current_config['symbol'] = symbol
            for i, key in enumerate(keys):
                current_config[key] = combo[i]

            run_args.append((
                strategy_class,
                current_config,
                symbol,
                request.interval,
                request.days,
                request.from_date,
                request.initial_capital,
                request.to_date,
                request.exchange_name
            ))

    # Create task
    task_id = str(uuid.uuid4())
    started_at = datetime.now().isoformat()

    HEAVY_OPTIMIZATION_TASKS[task_id] = {
        "task_id": task_id,
        "status": "initializing",
        "progress_current": 0,
        "progress_total": total_combinations,
        "message": "Initializing...",
        "started_at": started_at,
        "elapsed_seconds": 0,
        "estimated_remaining_seconds": None,
        "csv_file": None,
        "file_size_bytes": None,
        "top_results": [],
        "strategy_id": strategy_id,
        "symbols": symbols,
        "tab_id": request.tab_id,
        "tab_key": request.tab_key
    }

    # Start background task
    import asyncio
    loop = asyncio.get_running_loop()
    save_tab_id = request.tab_id
    save_acct_id = request.save_account_id or (ctx.account_id if ctx.has_active_account else None)
    loop.run_in_executor(
        None,
        _heavy_optimize_background_task,
        task_id,
        run_args,
        strategy_id,
        start_time,
        total_combinations,
        save_tab_id,
        save_acct_id,
        request.execution_mode
    )

    return {
        "task_id": task_id,
        "status": "running",
        "total_combinations": total_combinations,
        "message": f"Started heavy optimization with {total_combinations} combinations"
    }


@router.get("/heavy-optimize/status/{task_id}", response_model=HeavyOptimizationStatus)
async def get_heavy_optimization_status(task_id: str):
    """Get status of a heavy optimization task."""
    task = HEAVY_OPTIMIZATION_TASKS.get(task_id)

    if not task:
        return HeavyOptimizationStatus(
            task_id=task_id,
            status="not_found",
            progress_current=0,
            progress_total=0,
            progress_percent=0,
            message="Task not found"
        )

    progress_total = task.get("progress_total", 1)
    progress_current = task.get("progress_current", 0)
    progress_percent = (progress_current / progress_total * 100) if progress_total > 0 else 0

    return HeavyOptimizationStatus(
        task_id=task_id,
        status=task["status"],
        progress_current=progress_current,
        progress_total=progress_total,
        progress_percent=round(progress_percent, 2),
        message=task.get("message", ""),
        started_at=task.get("started_at"),
        elapsed_seconds=task.get("elapsed_seconds"),
        estimated_remaining_seconds=task.get("estimated_remaining_seconds"),
        csv_file=task.get("csv_file"),
        file_size_bytes=task.get("file_size_bytes"),
        top_results=task.get("top_results"),
        tab_id=task.get("tab_id"),
        tab_key=task.get("tab_key")
    )


@router.post("/heavy-optimize/cancel/{task_id}")
async def cancel_heavy_optimization(task_id: str):
    """Cancel a running heavy optimization task."""
    task = HEAVY_OPTIMIZATION_TASKS.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] not in ("initializing", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task with status: {task['status']}")

    HEAVY_OPTIMIZATION_TASKS[task_id]["cancel_requested"] = True
    return {"message": "Cancellation requested", "task_id": task_id}


@router.get("/heavy-optimize/download/{task_id}")
async def download_heavy_optimization_csv(task_id: str):
    """Download the heavy optimization results CSV file."""
    task = HEAVY_OPTIMIZATION_TASKS.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    csv_filename = task.get("csv_file")
    if not csv_filename:
        raise HTTPException(status_code=404, detail="CSV file not available yet")

    csv_filepath = os.path.join(CSV_OUTPUT_DIR, csv_filename)

    if not os.path.exists(csv_filepath):
        raise HTTPException(status_code=404, detail="CSV file not found on disk")

    return FileResponse(
        path=csv_filepath,
        filename=csv_filename,
        media_type="text/csv"
    )


@router.get("/heavy-optimize/list")
async def list_heavy_optimization_tasks(tab_ids: Optional[str] = None):
    """List heavy optimization tasks, optionally filtered by tab_ids (comma-separated)."""
    tasks = []
    for task_id, task in HEAVY_OPTIMIZATION_TASKS.items():
        if tab_ids:
            tab_id_set = set(tab_ids.split(","))
            if task.get("tab_id") not in tab_id_set:
                continue
        tasks.append({
            "task_id": task_id,
            "status": task.get("status"),
            "progress_percent": round(task.get("progress_current", 0) / max(task.get("progress_total", 1), 1) * 100, 2),
            "strategy_id": task.get("strategy_id"),
            "symbols": task.get("symbols", []),
            "started_at": task.get("started_at"),
            "csv_file": task.get("csv_file"),
            "tab_id": task.get("tab_id"),
            "tab_key": task.get("tab_key")
        })
    return {"tasks": tasks}


# ============================================================================
# WEIGHTED SCORE RECALCULATION - Apply custom weights to full CSV results
# ============================================================================

def _parse_numeric(value, default=0.0):
    """Safely parse a numeric value from string/number."""
    if value is None or value == '-' or value == '':
        return default
    try:
        return float(str(value).replace('%', '').replace(',', ''))
    except (ValueError, TypeError):
        return default


def _calculate_weighted_score(row: dict, weights: ScoreWeights) -> float:
    """
    Calculate weighted score using the formula:
    Base: (Return × Sharpe × Stability × CycleAvgPnL × ...) / MDD
    With weights applied as power exponents

    If weight is 0, that factor is excluded (treated as 1.0)
    """
    # Parse all metrics (all stats are now cycle-based for martingale strategies)
    ret = _parse_numeric(row.get('total_return', 0))
    sharpe = _parse_numeric(row.get('sharpe_ratio', 0))
    stability = _parse_numeric(row.get('stability_score', 0))
    mdd = abs(_parse_numeric(row.get('max_drawdown', 0)))
    wr = _parse_numeric(row.get('win_rate', 0))  # Cycle win rate
    recent_10 = _parse_numeric(row.get('recent_10_win_rate', 0))  # Recent 10 cycles win rate
    pf = _parse_numeric(row.get('profit_factor', 0))
    accel = _parse_numeric(row.get('acceleration_score', 0))
    trades = _parse_numeric(row.get('total_cycles', 0))  # = Cycle count
    activity = _parse_numeric(row.get('activity_rate', 0))
    avg_pnl = _parse_numeric(row.get('avg_pnl', 0))  # Cycle avg PnL (in %)

    # Skip invalid data (negative return or zero MDD/Sharpe)
    if ret <= 0:
        return 0.0
    if mdd == 0:
        mdd = 0.01  # Prevent division by zero
    if sharpe <= 0:
        sharpe = 0.01  # Prevent negative sharpe issues
    if stability <= 0:
        stability = 0.01  # Prevent zero stability

    # Calculate numerator components (higher is better)
    numerator = 1.0

    # Primary weights
    if weights.return_weight > 0:
        ret_normalized = min(ret / 100.0, 10.0)  # Cap at 1000%
        numerator *= pow(max(ret_normalized, 0.01), weights.return_weight)

    if weights.sharpe_weight > 0:
        sharpe_normalized = min(sharpe, 5.0)  # Cap at 5
        numerator *= pow(max(sharpe_normalized, 0.01), weights.sharpe_weight)

    if weights.stability_weight > 0:
        numerator *= pow(max(stability, 0.01), weights.stability_weight)

    if weights.avg_pnl_weight > 0:
        # AvgPnL: per-cycle avg profit percentage (cycle-based)
        # Normalize: 1% avg pnl = 1.0
        avg_pnl_normalized = 1.0 + avg_pnl
        numerator *= pow(max(avg_pnl_normalized, 0.01), weights.avg_pnl_weight)

    # Secondary weights
    if weights.win_rate_weight > 0:
        wr_normalized = wr / 100.0  # Convert to 0-1
        numerator *= pow(max(wr_normalized, 0.01), weights.win_rate_weight)

    if weights.recent_10_weight > 0:
        # Recent 10 win rate: momentum indicator (fallback to overall win rate if null)
        recent_10_val = recent_10 if recent_10 > 0 else wr
        recent_10_normalized = recent_10_val / 100.0  # Convert to 0-1
        numerator *= pow(max(recent_10_normalized, 0.01), weights.recent_10_weight)

    if weights.profit_factor_weight > 0:
        pf_normalized = min(pf, 10.0)  # Cap at 10
        numerator *= pow(max(pf_normalized, 0.01), weights.profit_factor_weight)

    if weights.accel_weight > 0:
        # Accel: positive is good, negative is bad
        accel_factor = 1.0 + (accel / 100.0)  # Range: 0-2
        numerator *= pow(max(accel_factor, 0.01), weights.accel_weight)

    if weights.trades_weight > 0:
        # Trades = Cycle count for martingale strategies
        trades_normalized = min(trades / 50.0, 5.0)  # Normalize: 50 cycles = 1.0
        numerator *= pow(max(trades_normalized, 0.01), weights.trades_weight)

    if weights.activity_weight > 0:
        activity_normalized = activity / 100.0  # Convert to 0-1
        numerator *= pow(max(activity_normalized, 0.01), weights.activity_weight)

    # Calculate denominator (penalty - higher is worse)
    denominator = 1.0

    if weights.mdd_weight > 0:
        mdd_normalized = mdd / 100.0  # Convert to 0-1 scale
        denominator *= pow(max(mdd_normalized, 0.01), weights.mdd_weight)

    return numerator / denominator if denominator > 0 else 0.0


@router.post("/recalculate-scores", response_model=RecalculateScoreResponse)
async def recalculate_scores(request: RecalculateScoreRequest):
    """
    Recalculate optimization scores with custom weights from the full CSV file.

    This reads the entire CSV (all combinations), applies new weighted scoring formula,
    and returns the new top N results sorted by the new score.

    Weights:
    - return_weight: Power exponent for return (default: 1.0)
    - sharpe_weight: Power exponent for Sharpe ratio (default: 1.2)
    - stability_weight: Power exponent for stability score (default: 1.0)
    - mdd_weight: Power exponent for MDD penalty (default: 1.5)
    - win_rate_weight: Power exponent for win rate (default: 0.0 = excluded)
    - accel_weight: Power exponent for acceleration (default: 0.0 = excluded)

    Set weight to 0 to exclude that metric from the calculation.
    """
    task_id = request.task_id

    # Try to find CSV file from heavy optimization tasks
    csv_filename = None

    # Check heavy optimization tasks
    if task_id in HEAVY_OPTIMIZATION_TASKS:
        csv_filename = HEAVY_OPTIMIZATION_TASKS[task_id].get("csv_file")

    # Try standard naming convention as fallback
    if not csv_filename:
        # Try both naming patterns
        for pattern in [f"optimization_{task_id}.csv", f"heavy_opt_{task_id}.csv"]:
            potential_path = os.path.join(CSV_OUTPUT_DIR, pattern)
            if os.path.exists(potential_path):
                csv_filename = pattern
                break

    if not csv_filename:
        raise HTTPException(status_code=404, detail=f"CSV file not found for task_id: {task_id}")

    csv_filepath = os.path.join(CSV_OUTPUT_DIR, csv_filename)

    if not os.path.exists(csv_filepath):
        raise HTTPException(status_code=404, detail=f"CSV file not found on disk: {csv_filename}")

    logger.info(f"[Recalculate] Reading CSV: {csv_filepath}")

    # Read all rows from CSV
    try:
        with open(csv_filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read CSV: {str(e)}")

    total_rows = len(rows)
    logger.info(f"[Recalculate] Loaded {total_rows} rows, applying weights: {request.weights}")

    # Calculate new scores for all rows
    scored_rows = []
    for row in rows:
        new_score = _calculate_weighted_score(row, request.weights)
        if new_score > 0:  # Skip invalid entries
            scored_rows.append((new_score, row))

    # Sort by new score (descending) and take top N
    scored_rows.sort(key=lambda x: x[0], reverse=True)
    top_rows = scored_rows[:request.top_n]

    # Convert to OptimizationResultItem format
    results = []
    for rank, (new_score, row) in enumerate(top_rows, 1):
        # Extract config columns (prefixed with 'config_')
        config = {}
        for key, value in row.items():
            if key.startswith('config_'):
                config_key = key[7:]  # Remove 'config_' prefix
                config[config_key] = value

        results.append(OptimizationResultItem(
            rank=rank,
            symbol=row.get('symbol', ''),
            config=config,
            total_return=_parse_numeric(row.get('total_return', 0)),
            win_rate=_parse_numeric(row.get('win_rate', 0)),
            recent_10_win_rate=_parse_numeric(row.get('recent_10_win_rate', 0)),
            total_cycles=int(_parse_numeric(row.get('total_cycles', 0))),
            score=round(new_score, 4),
            max_drawdown=str(row.get('max_drawdown', '-')),
            profit_factor=str(row.get('profit_factor', '-')),
            sharpe_ratio=str(row.get('sharpe_ratio', '-')),
            avg_pnl=str(row.get('avg_pnl', '-')),
            stability_score=str(row.get('stability_score', '-')),
            acceleration_score=str(row.get('acceleration_score', '-')),
            activity_rate=str(row.get('activity_rate', '-')),
            total_days=int(_parse_numeric(row.get('total_days', 0))),
            avg_holding_time=str(row.get('avg_holding_time', '-')),
            max_holding_time=str(row.get('max_holding_time', '-')),
            min_holding_time=str(row.get('min_holding_time', '-')),
            max_profit=str(row.get('max_profit', '-')),
            max_loss=str(row.get('max_loss', '-')),
            metrics={
                'recent_10_win_rate': _parse_numeric(row.get('recent_10_win_rate', 0)),
                'max_drawdown': row.get('max_drawdown', '-'),
                'profit_factor': row.get('profit_factor', '-'),
                'sharpe_ratio': row.get('sharpe_ratio', '-'),
                'avg_pnl': row.get('avg_pnl', '-'),
                'stability_score': row.get('stability_score', '-'),
                'acceleration_score': row.get('acceleration_score', '-'),
            }
        ))

    logger.info(f"[Recalculate] Returning top {len(results)} results (from {len(scored_rows)} valid entries)")

    return RecalculateScoreResponse(
        task_id=task_id,
        total_rows=total_rows,
        weights_applied=request.weights,
        results=results
    )


# --- Integrated Backtest Logic ---

class IntegratedConfig(BaseModel):
    id: str
    rank: int
    config: Dict[str, Any]
    strategy_id: str
    symbol: str

class IntegratedBacktestRequest(BaseModel):
    configs: List[IntegratedConfig]
    symbol: str # Primary/Global symbol (fallback)
    interval: str
    days: int
    from_date: Optional[str] = None
    to_date: Optional[str] = None  # End date (default: yesterday). Fixes date range for reproducible results.
    initial_capital: float
    execution_mode: str = "exclusive"  # 'exclusive' (waterfall) or 'parallel' (equal split)
    exchange_name: str = DEFAULT_EXCHANGE  # Exchange for market data source (Kiwoom, Binance, etc.)

@router.post("/integrated-backtest")
async def run_integrated_backtest(request: IntegratedBacktestRequest):
    """
    Integrated backtest endpoint for multiple strategies.
    Uses _run_unified_backtest() for consistent behavior with individual backtest.
    """
    import traceback

    try:
        if not request.configs:
            return {"error": "No strategies provided"}

        # Prepare Strategy Configs - USE SAME NORMALIZATION AS INDIVIDUAL BACKTEST
        num_ranks = len(request.configs)

        # Capital allocation based on execution mode
        if request.execution_mode == "parallel":
            per_rank_capital = int(request.initial_capital) // num_ranks
        else:
            per_rank_capital = int(request.initial_capital)

        # Normalize all configs
        strategies_config = []
        for c in request.configs:
            rank_symbol = c.config.get('symbol') or c.symbol or request.symbol
            normalized_config = build_backtest_config(
                c.config,
                symbol=rank_symbol,
                interval=request.interval,
                days=request.days,
                from_date=request.from_date,
                initial_capital=per_rank_capital,
                to_date=request.to_date
            )
            strategies_config.append(normalized_config)

        actual_interval = strategies_config[0].get('interval', request.interval)
        strategy_id = request.configs[0].strategy_id if request.configs else "time_momentum"

        logger.info(f"[INTEGRATED] mode={request.execution_mode}, strategy={strategy_id}, ranks={num_ranks}")

        # Use unified backtest function (Single Source of Truth)
        result = await _run_unified_backtest(
            strategy_id=strategy_id,
            configs=strategies_config,
            symbol=request.symbol,
            interval=actual_interval,
            days=request.days,
            from_date=request.from_date,
            initial_capital=int(request.initial_capital),
            execution_mode=request.execution_mode,
            to_date=request.to_date,
            exchange_name=request.exchange_name
        )

        return result

    except Exception as e:
        logger.error(f"[INTEGRATED] Error: {str(e)}")
        logger.error(f"[INTEGRATED] Traceback: {traceback.format_exc()}")
        raise

