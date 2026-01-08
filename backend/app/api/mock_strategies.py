from fastapi import APIRouter
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
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

    import asyncio
    from ..core.backtest_engine import BacktestEngine
    
    engine = BacktestEngine(strategy_cls, config)
    # create new loop for this process
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    result = loop.run_until_complete(engine.run(
        symbol=symbol, 
        interval=interval, 
        duration_days=days, 
        from_date=from_date,
        initial_capital=initial_capital
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
        
        # Use max_workers=4
        with ProcessPoolExecutor(max_workers=4) as executor:
            # We want to iterate as they complete to update progress?
            # executor.map returns iterator.
            # zip(*run_args) unzips
            
            # NOTE: list(executor.map(...)) blocks until all are done.
            # To get progress, we use enumerate on the iterator or submit individually and use as_completed.
            # For simplicity with map, we can't get granular progress easily unless we chunk it or wrap the iterator.
            # Let's switch to submit + as_completed for progress updates.
            from concurrent.futures import as_completed
            
            futures = [executor.submit(_run_sync_in_process, *args) for args in run_args]
            
            for i, future in enumerate(as_completed(futures)):
                try:
                    config, res = future.result()
                    
                    if "error" in res:
                        err_msg = str(res['error'])
                        if len(failures) < 10:
                             failures.append(f"Config failed: {err_msg}")
                        # logger.error(f"Config failed: {err_msg}")
                    else:
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
                                "total_days": res.get("total_days", 0)
                            }
                        ))
                except Exception as e:
                    logger.error(f"Future Result Error: {e}")
                    failures.append(str(e))
                
                # Check for Cancellation
                if OPTIMIZATION_TASKS[task_id].get("cancel_requested"):
                    logger.info(f"Task {task_id} cancellation requested. Stopping executor.")
                    executor.shutdown(wait=False, cancel_futures=True)
                    OPTIMIZATION_TASKS[task_id]["status"] = "cancelled"
                    OPTIMIZATION_TASKS[task_id]["message"] = "Cancelled by user"
                    # Break loop
                    break
                
                # Update Progress
                OPTIMIZATION_TASKS[task_id]["progress_current"] = i + 1
        
        # Finished
        results.sort(key=lambda x: x.score, reverse=True)
        for i, item in enumerate(results):
            item.rank = i + 1
            
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
            "chart_data": result['chart_data'],
            "ohlcv_data": result.get('ohlcv_data', []),
            "trades": result.get('trades', []),
            "matched_trades": result.get('matched_trades', []),
            "multi_ohlcv_data": result.get('multi_ohlcv_data', {}),
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

MOCK_STRATEGIES = [
    Strategy(
        id="time_momentum",
        name="Time Momentum (User Req)",
        description="Wait Delay -> Check % Jump -> Buy -> Trailing Stop",
        code="[Real Engine] Logic implemented in backend/strategies/time_momentum.py",
        tags=["Momentum", "Timed Entry"]
    ),
    Strategy(
        id="rsi_strategy",
        name="RSI Swing Master",
        description="Buys when RSI < 30 and Sells when RSI > 70. Classic mean reversion.",
        code="def on_data(self, data):\n    if rsi < 30:\n        order.buy()\n    elif rsi > 70:\n        order.sell()",
        tags=["Mean Reversion", "Technical"]
    ),
    Strategy(
        id="golden_cross",
        name="MA Golden Cross",
        description="Buys when 20MA crosses above 60MA. Captures strong trends.",
        code="def on_data(self, data):\n    if ma20 > ma60 and prev_ma20 <= prev_ma60:\n        order.buy()",
        tags=["Trend Following", "Moving Average"]
    ),
    Strategy(
        id="volatility_breakout",
        name="Volatility Breakout",
        description="Larry Williams' volatility breakout strategy.",
        code="def on_data(self, data):\n    if current_price > target_price:\n        order.buy()",
        tags=["Breakout", "Intraday"]
    )
]

@router.get("/list", response_model=List[Strategy])
async def list_strategies():
    return MOCK_STRATEGIES

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
    from ..core.backtest_engine import BacktestEngine
    
    # Select Strategy Class
    strategy_class = None
    
    # Use nested config as the strategy config
    config = request.config
    
    # Also inject root-level params into config if needed (or keep separate)
    # Strategy might need start_date? Usually not, just "on_data".
    
    if strategy_id == "time_momentum":
        from ..strategies.time_momentum import TimeMomentumStrategy
        strategy_class = TimeMomentumStrategy
    else:
        # Fallback for others (or use a Default)
        from ..strategies.base import BaseStrategy
        class MockStrategy(BaseStrategy):
             def initialize(self): pass
             def on_data(self, data): pass
        strategy_class = MockStrategy

    # Run Engine
    # Initialize engine with Strategy Class and Strategy Config
    engine = BacktestEngine(strategy_class, config)
    
    # Run
    # Pass initial_capital to run() or set it before running?
    # BacktestEngine needs to support initial_capital argument in run() or init.
    # We will pass it to run().
    
    start_date = request.start_date or request.from_date
    
    result = await engine.run(
        symbol=request.symbol, 
        interval=request.interval,
        duration_days=request.days, 
        from_date=start_date,
        initial_capital=request.initial_capital
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
        "total_days": result.get('total_days', 0), # Expose total_days
        "avg_holding_time": result.get('avg_holding_time', "0m"),
        "decile_stats": result.get('decile_stats', []),
        "stability_score": result.get('stability_score', "0.00"),
        "acceleration_score": result.get('acceleration_score', "0.00"),
        "chart_data": result['chart_data'],
        "ohlcv_data": result.get('ohlcv_data', []),
        "trades": result.get('trades', []),
        "logs": result['logs']
    }

@router.post("/{strategy_id}/optimize", response_model=OptimizationResponse)
async def optimize_strategy(strategy_id: str, request: OptimizationRequest):
    start_time = time.time()
    
    # 1. Select Strategy Class
    strategy_class = None
    if strategy_id == "time_momentum":
        from ..strategies.time_momentum import TimeMomentumStrategy
        strategy_class = TimeMomentumStrategy
    else:
        # Optimization only supported for TimeMomentum for now or generic?
        # Fallback to generic if possible, but we need class logic.
        from ..strategies.base import BaseStrategy
        class MockStrategy(BaseStrategy):
             def initialize(self): pass
             def on_data(self, data): pass
        strategy_class = MockStrategy

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
    for combo in combinations:
        # Merge combo into config
        current_config = base_config.copy()
        for i, key in enumerate(keys):
            current_config[key] = combo[i]
            
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

@router.post("/integrated-backtest")
async def run_integrated_backtest(request: IntegratedBacktestRequest):
    # Full League Mode Implementation
    from ..core.waterfall_engine import WaterfallBacktestEngine
    from ..strategies.time_momentum import TimeMomentumStrategy
    
    if not request.configs:
        return {"error": "No strategies provided"}
        
    # Prepare Strategy Configs
    # Convert Pydantic models to dicts
    strategies_config = [c.config for c in request.configs]
    
    # Ensure symbols are set fallback
    for i, cfg in enumerate(strategies_config):
        if 'symbol' not in cfg:
            cfg['symbol'] = request.configs[i].symbol or request.symbol

    engine = WaterfallBacktestEngine(TimeMomentumStrategy, {})
    
    # Run Integrated League
    result = await engine.run_integrated(
        strategies_config=strategies_config,
        global_symbol=request.symbol, # Fallback global symbol
        duration_days=request.days,
        from_date=request.from_date,
        interval=request.interval,
        initial_capital=int(request.initial_capital)
    )
    
    result['strategy_id'] = "Integrated (League Mode: Winner Takes All)"
    return result

