from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.strategy_info import StrategyInfo
import random
import time
import itertools
import functools
from concurrent.futures import ProcessPoolExecutor
from ..schemas.optimization import OptimizationRequest, OptimizationResponse, OptimizationResultItem, OptimizationStatus

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
    initial_capital: int
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
    config['initial_capital'] = initial_capital

    return config


# Global Task Registry
OPTIMIZATION_TASKS: Dict[str, Dict[str, Any]] = {}

import uuid

# Helper for Parallel Execution
# Must be top-level for pickling
def _run_backtest_wrapper(args):
    strategy_cls, config, symbol, interval, days, from_date, initial_capital = args
    from ..core.backtest_engine import BacktestEngine
    
    # Initialize implementation of run
    engine = BacktestEngine(strategy_cls, config)
    try:
        # Run simplified backtest (we don't need charts for optimization, just metrics)
        # But BacktestEngine.run might be heavy. 
        # Ideally, we should add a 'lite' mode to run() to skip chart generation.
        # For now, we just run it.
        result = engine.run_sync( # Assuming valid sync method or using asyncio.run in wrapper if needed.
             # Wait, engine.run is async? 
             # If engine.run is async, we can't easily call it from ProcessPool without new event loop.
             # Let's check imports. BacktestEngine is usually sync or has sync wrapper?
             # Based on previous usage: result = await engine.run(...)
             # If it's async, we should use ThreadPool or run_in_executor with loop.
             # BUT Backtest is CPU bound.
             # We should probably run it synchronously in the process.
             # Let's assume we can call the core logic synchronously or use asyncio.run(engine.run(...))
             symbol, interval, days, from_date, initial_capital
        )
        return config, result
    except Exception as e:
        return config, {"error": str(e)}

def _run_sync_in_process(strategy_cls, config, symbol, interval, days, from_date, initial_capital):
    # Force close inherited DB connections to prevent SSL/OperationalError in worker process
    try:
        from ..db.session import engine
        engine.dispose()
    except Exception as e:
        print(f"Warning: Failed to dispose engine in worker: {e}")

    # Force reload modules to ensure latest code is used (worker process caching issue)
    import sys
    import importlib
    modules_to_reload = [
        'app.strategies.base',
        'app.strategies.dip_martingale',
        'app.strategies.time_momentum',
        'app.core.strategy_registry',
        'app.core.waterfall_engine',
        'app.services.market_data'
    ]
    for mod_name in modules_to_reload:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass  # Continue if reload fails

    import asyncio
    # [MIGRATION] Use WaterfallBacktestEngine for consistent logic (Unified, Standard MDD, StockOrder)
    from ..core.waterfall_engine import WaterfallBacktestEngine

    # IMPORTANT: After module reload, get FRESH strategy class from registry
    # The strategy_cls parameter is the OLD class reference from before reload
    from ..core.strategy_registry import StrategyRegistry
    strategy_id = config.get('strategy_id', 'dip_martingale')
    fresh_strategy_cls = StrategyRegistry.get_strategy_class(strategy_id) or strategy_cls

    # Initialize Engine with Unified Logic (using fresh class)
    engine = WaterfallBacktestEngine(fresh_strategy_cls, config)
    
    # create new loop for this process
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    # Use unified config builder (Single Source of Truth)
    config = build_backtest_config(config, symbol, interval, days, from_date, initial_capital)
    actual_interval = config['interval']

    result = loop.run_until_complete(engine.run_integrated(
        strategies_config=[config],
        global_symbol=symbol,
        interval=actual_interval,
        duration_days=days,
        from_date=from_date,
        initial_capital=initial_capital,
        optimize_mode=True
    ))

    return config, result

def _optimize_background_task(task_id: str, run_args: List, strategy_id: str, start_time: float, total_combos: int):
    """
    Background wrapper that runs the sync process pool and updates Global Status.
    """
    try:
        results = []
        failures = []
        
        # Update Status to Running
        OPTIMIZATION_TASKS[task_id]["status"] = "running"
        OPTIMIZATION_TASKS[task_id]["progress_total"] = total_combos
        
        # TEMPORARY: Sequential execution to fix ProcessPoolExecutor module caching issue
        logger.info(f"[TEMP] Running {total_combos} combinations sequentially (no multiprocessing)")

        for i, args in enumerate(run_args):
            try:
                config, res = _run_sync_in_process(*args)

                if "error" in res:
                    err_msg = str(res['error'])
                    if len(failures) < 10:
                         failures.append(f"Config failed: {err_msg}")
                else:
                    # Update Status Message
                    if 'perf_log' in res:
                         OPTIMIZATION_TASKS[task_id]["message"] = f"Processing ({i+1}/{total_combos})... {res['perf_log']}"

                    # Calculate Score
                    ret = float(str(res['total_return']).replace('%', '').replace(',', ''))
                    wr = float(str(res['win_rate']).replace('%', ''))
                    trades = int(res.get('total_trades', 0))

                    score = ret * (wr / 100.0)

                    results.append(OptimizationResultItem(
                        rank=0,
                        config=config,
                        total_return=ret,
                        win_rate=wr,
                        total_trades=trades,
                        score=round(score, 2),
                        # Explicit Top-Level Promoted Fields
                        max_drawdown=str(res.get("max_drawdown", "-")),
                        profit_factor=str(res.get("profit_factor", "-")),
                        avg_pnl=str(res.get("avg_pnl", "-")),
                        sharpe_ratio=str(res.get("sharpe_ratio", "-")),
                        avg_holding_time=str(res.get("avg_holding_time", "-")),
                        stability_score=str(res.get("stability_score", "-")),
                        acceleration_score=str(res.get("acceleration_score", "-")),
                        activity_rate=str(res.get("activity_rate", "-")),
                        total_days=int(res.get("total_days", 0)),
                        max_profit=str(res.get("max_profit", "-")),
                        max_loss=str(res.get("max_loss", "-")),
                        cycle_count=res.get("cycle_count"),
                        cycle_avg_pnl=res.get("cycle_avg_pnl"),
                        cycle_avg_hold=res.get("cycle_avg_hold"),
                        cycle_max_hold=res.get("cycle_max_hold"),
                        cycle_min_hold=res.get("cycle_min_hold"),
                        metrics={
                            # Frontend relies on 'metrics' spread, so we must populate these!
                            "max_drawdown": res.get("max_drawdown", "-"),
                            "profit_factor": res.get("profit_factor", "-"),
                            "avg_pnl": res.get("avg_pnl", "-"),
                            "sharpe_ratio": res.get("sharpe_ratio", "-"),
                            "avg_holding_time": res.get("avg_holding_time", "-"),
                            "stability_score": res.get("stability_score", "-"),
                            "acceleration_score": res.get("acceleration_score", "-"),
                            "activity_rate": res.get("activity_rate", "-"),
                            "total_days": res.get("total_days", 0),
                            "max_profit": res.get("max_profit", "-"),
                            "max_loss": res.get("max_loss", "-"),
                            "cycle_count": res.get("cycle_count"),
                            "cycle_avg_pnl": res.get("cycle_avg_pnl"),
                            "cycle_avg_hold": res.get("cycle_avg_hold"),
                            "cycle_max_hold": res.get("cycle_max_hold"),
                            "cycle_min_hold": res.get("cycle_min_hold")
                        }
                    ))
            except Exception as e:
                logger.error(f"Result Error: {e}")
                failures.append(str(e))

            # Update Progress
            OPTIMIZATION_TASKS[task_id]["progress_current"] = i + 1

            # Check for Cancellation
            if OPTIMIZATION_TASKS[task_id].get("cancel_requested"):
                logger.info(f"Task {task_id} cancellation requested.")
                OPTIMIZATION_TASKS[task_id]["status"] = "cancelled"
                OPTIMIZATION_TASKS[task_id]["message"] = "Cancelled by user"
                break
        
        # Finished - Sort by score and assign ranks
        results.sort(key=lambda x: x.score, reverse=True)

        # Use model_copy to properly update rank (Pydantic v2 safe)
        ranked_results = []
        for i, item in enumerate(results):
            ranked_item = item.model_copy(update={"rank": i + 1})
            ranked_results.append(ranked_item)
        results = ranked_results

        execution_time = time.time() - start_time
        
        # Determine final status
        final_status = "completed"
        if OPTIMIZATION_TASKS[task_id].get("cancel_requested"):
             final_status = "cancelled"
        
        response = OptimizationResponse(
            strategy_id=strategy_id,
            best_config=results[0].config if results else {},
            results=results[:50],
            failures=failures,
            total_combinations=total_combos,
            elapsed_time=execution_time,
            task_id=task_id,
            status=final_status
        )
        
        OPTIMIZATION_TASKS[task_id]["status"] = final_status
        OPTIMIZATION_TASKS[task_id]["result"] = response
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        msg = f"CRITICAL FAILURE: {e}\n{tb}"
        
        # Log to stdout for Docker/Shell capture
        print(f"\n[OPTIMIZATION ERROR] {msg}\n", flush=True)
        
        # Log to simple file
        try:
            with open("optimization_crash.log", "a") as f:
                f.write(f"{time.ctime()}\n{msg}\n")
        except:
            pass

        logger.error(f"Background Task Failed: {e}")
        OPTIMIZATION_TASKS[task_id]["status"] = "failed"
        OPTIMIZATION_TASKS[task_id]["message"] = str(e)

# Removed old _optimize_sync_wrapper as it is replaced by _optimize_background_task logic


router = APIRouter()

@router.get("/debug-probe")
async def debug_probe():
    return {"status": "alive", "message": "Router is active"}

class IntegratedBacktestRequest(BaseModel):
    symbol: str = "TEST"
    interval: str = "1m"
    days: int = 365
    from_date: Optional[str] = None
    initial_capital: int = 10000000
    configs: List[Dict[str, Any]] = [] # Ordered list of configs

@router.post("/integrated/v2-backtest")
async def run_integrated_backtest(request: IntegratedBacktestRequest):
    try:
        from ..core.backtest_engine import BacktestEngine
        from ..core.integrated_backtest_engine import IntegratedBacktestEngine
        
        # Initialize Engine (Mock strategy class just to satisfy init, logic is in run_integrated)
        from ..strategies.base import BaseStrategy
        class MockStrategy(BaseStrategy):
             def initialize(self): pass
             def on_data(self, data): pass
        
        engine = IntegratedBacktestEngine(MockStrategy, {}) # Use Subclass for Integrated Mode
        
        result = await engine.run_integrated_simulation(
            strategies_config=request.configs,
            symbol=request.symbol,
            interval=request.interval,
            duration_days=request.days,
            from_date=request.from_date,
            initial_capital=request.initial_capital
        )
        
        return {
            "strategy_id": "integrated_waterfall",
            "total_return": result['total_return'],
            "win_rate": result['win_rate'],
            "max_drawdown": result['max_drawdown'],
            "total_trades": result.get('total_trades', 0),
            "avg_pnl": result.get('avg_pnl', "0%"),
            "max_profit": result.get('max_profit', "0%"),
            "max_loss": result.get('max_loss', "0%"),
            "profit_factor": result.get('profit_factor', "0.00"),
            "sharpe_ratio": result.get('sharpe_ratio', "0.00"),
            "activity_rate": result.get('activity_rate', "0%"),
            "total_days": result.get('total_days', 0),
            "avg_holding_time": result.get('avg_holding_time', "0m"),
            "decile_stats": result.get('decile_stats', []),
            "stability_score": result.get('stability_score', "0.00"),
            "acceleration_score": result.get('acceleration_score', "0.00"),
            "cycle_count": result.get('cycle_count'),
            "cycle_avg_pnl": result.get('cycle_avg_pnl'),
            "cycle_avg_hold": result.get('cycle_avg_hold'),
            "cycle_max_hold": result.get('cycle_max_hold'),
            "cycle_min_hold": result.get('cycle_min_hold'),
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
    code: str
    tags: List[str]
    detailed_description: Optional[str] = None
    parameter_schema: Optional[Dict[str, Any]] = None  # UI parameter configuration

    class Config:
        from_attributes = True

# Hardcoded strategies removed in favor of DB persistence.

@router.get("/list", response_model=List[Strategy])
async def list_strategies(db: Session = Depends(get_db)):
    from ..core.strategy_registry import StrategyRegistry
    strats = db.query(StrategyInfo).all()
    result = []
    for s in strats:
        data = Strategy.from_orm(s)
        if not data.parameter_schema:
            class_schema = StrategyRegistry.get_parameter_schema(s.id)
            if class_schema:
                data.parameter_schema = class_schema
        result.append(data)
    return result

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
    days: int = 365
    from_date: Optional[str] = None # Or start_date
    start_date: Optional[str] = None # Aliases
    initial_capital: int = 10000000
    config: Dict[str, Any] = {} # Nested config from frontend strategy selector

@router.post("/{strategy_id}/backtest")
async def run_mock_backtest(strategy_id: str, request: BacktestRequest):
    # [FIX 2026-01-26] Force reload strategy modules to ensure latest code is used
    # This fixes the issue where backtest uses cached (old) code while optimization uses fresh code
    import sys
    import importlib

    # Reload strategy modules in CORRECT ORDER (base class first, then implementations, then registry)
    strategy_modules_to_reload = [
        'app.strategies.base',           # 1. Base class first
        'app.strategies.dip_martingale', # 2. Strategy implementations
        'app.strategies.time_momentum',
        'app.core.strategy_registry',    # 3. Registry (imports strategies)
        'app.core.waterfall_engine',     # 4. Engine (uses registry)
    ]

    for mod_name in strategy_modules_to_reload:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass  # Silently continue if reload fails

    # [MIGRATION] Use WaterfallBacktestEngine for consistent logic with Integrated Tab
    from ..core.waterfall_engine import WaterfallBacktestEngine

    # Select Strategy Class from Registry (now with fresh imports)
    from ..core.strategy_registry import StrategyRegistry
    strategy_class = StrategyRegistry.get_strategy_class(strategy_id)

    if not strategy_class:
        # Fallback for others (or raise 404)
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found in registry.")

    # Select Strategy Config
    raw_config = request.config
    start_date = request.start_date or request.from_date

    # Use unified config builder (Single Source of Truth - same as optimization)
    config = build_backtest_config(
        raw_config,
        symbol=request.symbol,
        interval=request.interval,
        days=request.days,
        from_date=start_date,
        initial_capital=request.initial_capital
    )
    actual_interval = config['interval']

    # Initialize Engine
    engine = WaterfallBacktestEngine(strategy_class, config)

    # DEBUG: Log all parameters for comparison with optimization
    logger.info(f"[BACKTEST] symbol={request.symbol}, interval={actual_interval}, days={request.days}, from_date={start_date}, initial_capital={request.initial_capital}")
    logger.info(f"[BACKTEST] config={config}")

    # *** SINGLE SOURCE OF TRUTH ***
    # Use run_single_backtest() - same function used by parallel mode
    # This ensures individual backtest results EXACTLY match parallel mode rank results

    # 1. Fetch Data
    from ..services.market_data import MarketDataService
    data_service = MarketDataService()
    raw_feed = await data_service.get_candles(request.symbol, interval=actual_interval, days=request.days)
    if raw_feed:
        if start_date:
            raw_feed = [c for c in raw_feed if c['timestamp'] >= start_date]
        raw_feed.sort(key=lambda x: x['timestamp'])

    if not raw_feed:
        return {"error": "No data available for the specified parameters"}

    # 2. Run Single Backtest (SAME function as parallel mode uses)
    result = await engine.run_single_backtest(
        config=config,
        feed=raw_feed,
        initial_capital=request.initial_capital,
        symbol=request.symbol,
        optimize_mode=False,  # Include chart_data for visualization
        rank=1
    ) 
    
    return {
        "strategy_id": strategy_id,
        "total_return": result['total_return'],
        "win_rate": result['win_rate'],
        "max_drawdown": result['max_drawdown'],
        "total_trades": result.get('total_trades', 0),
        "avg_pnl": result.get('avg_pnl', "0%"),
        "max_profit": result.get('max_profit', "0%"),
        "max_loss": result.get('max_loss', "0%"),
        "profit_factor": result.get('profit_factor', "0.00"),
        "sharpe_ratio": result.get('sharpe_ratio', "0.00"),
        "activity_rate": result.get('activity_rate', "0%"),
        "total_days": result.get('total_days', 0),
        "avg_holding_time": result.get('avg_holding_time', "0m"),
        "decile_stats": result.get('decile_stats', []),
        "stability_score": result.get('stability_score', "0.00"),
        "acceleration_score": result.get('acceleration_score', "0.00"),
        "cycle_count": result.get('cycle_count'),
        "cycle_avg_pnl": result.get('cycle_avg_pnl'),
        "cycle_avg_hold": result.get('cycle_avg_hold'),
        "cycle_max_hold": result.get('cycle_max_hold'),
        "cycle_min_hold": result.get('cycle_min_hold'),
        "chart_data": result['chart_data'],
        "ohlcv_data": result.get('ohlcv_data', []),
        "trades": result.get('trades', []),
        "logs": result.get('logs', []),
        "rank_stats_list": result.get('rank_stats_list', [])
    }

@router.post("/{strategy_id}/optimize", response_model=OptimizationResponse)
async def optimize_strategy(strategy_id: str, request: OptimizationRequest):
    start_time = time.time()
    
    # 1. Select Strategy Class from Registry
    from ..core.strategy_registry import StrategyRegistry
    strategy_class = StrategyRegistry.get_strategy_class(strategy_id)
    
    if not strategy_class:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found for optimization.")

    # 2. Generate Cartesian Product
    keys = list(request.parameter_ranges.keys())
    values = list(request.parameter_ranges.values())
    combinations = list(itertools.product(*values))
    
    # Limit max combinations to avoid DOS
    if len(combinations) > 500:
         # raise HTTPException(status_code=400, detail="Too many combinations. Max 500.")
         combinations = combinations[:500] 

    logger.info(f"[Optimization] Running {len(combinations)} combinations for {strategy_id}")

    # 3. Prepare Tasks
    tasks = []
    base_config = request.base_config.copy()
    
    run_args = []
    for idx, combo in enumerate(combinations):
        # Merge combo into config
        current_config = base_config.copy()
        current_config['strategy_id'] = strategy_id  # Required for fresh class lookup after module reload
        for i, key in enumerate(keys):
            current_config[key] = combo[i]

        # Debug: Log first few combinations
        if idx < 5:
            logger.info(f"[DEBUG] Combo {idx}: interval={current_config.get('interval', 'NOT_SET')}, request.interval={request.interval}")

        run_args.append((
            strategy_class,
            current_config,
            request.symbol,
            request.interval,
            request.days,
            request.from_date,
            request.initial_capital
        ))

    # 4. Async Execution (Fire and Forget)
    task_id = str(uuid.uuid4())
    
    OPTIMIZATION_TASKS[task_id] = {
        "status": "initializing",
        "progress_current": 0,
        "progress_total": len(combinations),
        "message": "Initializing...",
        "result": None,
        "task_id": task_id
    }
    
    # Run in Thread (to allow Thread to manage ProcessPool and updates)
    import asyncio
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, 
        _optimize_background_task, 
        task_id, 
        run_args, 
        strategy_id, 
        start_time, 
        len(combinations)
    )
    
    # Return Immediate Response
    return OptimizationResponse(
        strategy_id=strategy_id,
        best_config={},
        results=[],
        failures=[],
        total_combinations=len(combinations),
        elapsed_time=0,
        task_id=task_id,
        status="running"
    )

@router.get("/optimize/status/{task_id}", response_model=OptimizationStatus)
async def get_optimization_status(task_id: str):
    from ..schemas.optimization import OptimizationStatus
    task = OPTIMIZATION_TASKS.get(task_id)
    if not task:
        # Fallback for invalid ID
        return OptimizationStatus(
            task_id=task_id,
            status="not_found",
            progress_current=0,
            progress_total=0,
            message="Task not found"
        )
        
    return OptimizationStatus(
        task_id=task_id,
        status=task["status"],
        progress_current=task.get("progress_current", 0),
        progress_total=task.get("progress_total", 0),
        message=task.get("message", ""),
        result=task.get("result")
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
    initial_capital: float
    execution_mode: str = "exclusive"  # 'exclusive' (waterfall) or 'parallel' (equal split)

@router.post("/integrated-backtest")
async def run_integrated_backtest(request: IntegratedBacktestRequest):
    # Full League Mode Implementation
    import traceback
    from ..core.waterfall_engine import WaterfallBacktestEngine
    from ..strategies.time_momentum import TimeMomentumStrategy
    from ..strategies.dip_martingale import DipMartingaleStrategy

    try:
        if not request.configs:
            return {"error": "No strategies provided"}

        # Prepare Strategy Configs - USE SAME NORMALIZATION AS INDIVIDUAL BACKTEST
        # This ensures parallel mode results match individual rank backtests
        num_ranks = len(request.configs)

        # For parallel mode: frontend sends totalCapital = rank1Capital * num_ranks
        # So per-rank capital = initial_capital / num_ranks
        # For exclusive mode: frontend sends rank1Capital (no multiplication)
        if request.execution_mode == "parallel":
            per_rank_capital = int(request.initial_capital) // num_ranks
        else:
            per_rank_capital = int(request.initial_capital)

        strategies_config = []
        for i, c in enumerate(request.configs):
            # Get the rank's symbol (from config or fallback)
            rank_symbol = c.config.get('symbol') or c.symbol or request.symbol

            # Apply same normalization as individual backtest (build_backtest_config)
            normalized_config = build_backtest_config(
                c.config,
                symbol=rank_symbol,
                interval=request.interval,  # Global interval for data consistency
                days=request.days,
                from_date=request.from_date,
                initial_capital=per_rank_capital  # Use per-rank capital (same as individual backtest)
            )
            strategies_config.append(normalized_config)

        # Use NORMALIZED config's interval (same as individual backtest)
        # All ranks should have the same interval after normalization
        actual_interval = strategies_config[0].get('interval', request.interval)

        # DEBUG: Log configs being passed to engine
        logger.warning(f"[INTEGRATED] execution_mode={request.execution_mode}")
        logger.warning(f"[INTEGRATED] request.interval={request.interval}, actual_interval={actual_interval}")
        logger.warning(f"[INTEGRATED] days={request.days}, from_date={request.from_date}")
        logger.warning(f"[INTEGRATED] initial_capital={request.initial_capital} (total from frontend)")
        logger.warning(f"[INTEGRATED] per_rank_capital={per_rank_capital} (each rank gets this - same as individual backtest)")
        for idx, cfg in enumerate(strategies_config):
            logger.warning(f"[INTEGRATED] Rank {idx+1} config keys: {list(cfg.keys())}")
            # Print key DipMartingale params
            logger.warning(f"[INTEGRATED] Rank {idx+1} symbol={cfg.get('symbol')}, interval={cfg.get('interval')}, initial_capital={cfg.get('initial_capital')}")
            logger.warning(f"[INTEGRATED] Rank {idx+1} dip_percent={cfg.get('dip_percent')}, trailing_start={cfg.get('trailing_start_percent')}, max_levels={cfg.get('max_levels')}")

        # Determine strategy class based on first config's strategy_id
        strategy_id = request.configs[0].strategy_id if request.configs else "time_momentum"
        strategy_class = TimeMomentumStrategy
        if "dip" in strategy_id.lower() or "martingale" in strategy_id.lower():
            strategy_class = DipMartingaleStrategy

        engine = WaterfallBacktestEngine(strategy_class, {})

        # Parallel Mode: Equal capital split across all ranks
        if request.execution_mode == "parallel":
            result = await engine.run_parallel(
                strategies_config=strategies_config,
                global_symbol=request.symbol,
                duration_days=request.days,
                from_date=request.from_date,
                interval=actual_interval,  # Use config's interval (same as individual backtest)
                initial_capital=int(request.initial_capital)
            )
            result['strategy_id'] = f"Integrated (Parallel Mode: Equal Split)"
            result['execution_mode'] = 'parallel'
        else:
            # Exclusive Mode: Waterfall/League - Winner Takes All
            result = await engine.run_integrated(
                strategies_config=strategies_config,
                global_symbol=request.symbol,
                duration_days=request.days,
                from_date=request.from_date,
                interval=actual_interval,  # Use config's interval (same as individual backtest)
                initial_capital=int(request.initial_capital)
            )
            result['strategy_id'] = "Integrated (League Mode: Winner Takes All)"
            result['execution_mode'] = 'exclusive'

        return result
    except Exception as e:
        logger.error(f"[INTEGRATED] Error: {str(e)}")
        logger.error(f"[INTEGRATED] Traceback: {traceback.format_exc()}")
        raise

