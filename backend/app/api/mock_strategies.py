from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..models.strategy_info import StrategyInfo
from ..core.user_context import UserAccountContext, get_user_context
import random
import time
import itertools
import functools
import csv
import os
from concurrent.futures import ProcessPoolExecutor
from ..schemas.optimization import (
    OptimizationRequest, OptimizationResponse, OptimizationResultItem, OptimizationStatus,
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
    to_date: str = None
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
    from ..services.market_data import MarketDataService

    # 1. Get Strategy Class from Registry
    strategy_class = StrategyRegistry.get_strategy_class(strategy_id)
    if not strategy_class:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_id}' not found. Available: {StrategyRegistry.list_strategies()}"
        )

    logger.info(f"[UNIFIED_BACKTEST] mode={execution_mode}, strategy={strategy_class.__name__}, configs={len(configs)}")

    # 2. Initialize Engine
    engine = WaterfallBacktestEngine(strategy_class, {})

    # 3. Execute based on mode
    if execution_mode == "single" or len(configs) == 1:
        # Single backtest - use run_single_backtest directly
        data_service = MarketDataService()
        config = configs[0]
        rank_symbol = config.get('symbol', symbol)

        raw_feed = await data_service.get_candles(rank_symbol, interval=interval, days=days, to_date=to_date)
        if raw_feed:
            if from_date:
                raw_feed = [c for c in raw_feed if c['timestamp'] >= from_date]
            raw_feed.sort(key=lambda x: x['timestamp'])

        if not raw_feed:
            return {"error": "No data available for the specified parameters"}

        result = await engine.run_single_backtest(
            config=config,
            feed=raw_feed,
            initial_capital=initial_capital,
            symbol=rank_symbol,
            optimize_mode=False,
            rank=1
        )
        result['strategy_id'] = strategy_id
        result['execution_mode'] = 'single'

    elif execution_mode == "parallel":
        result = await engine.run_parallel(
            strategies_config=configs,
            global_symbol=symbol,
            duration_days=days,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            initial_capital=initial_capital
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
            initial_capital=initial_capital
        )
        result['strategy_id'] = "Integrated (League Mode: Winner Takes All)"
        result['execution_mode'] = 'exclusive'

    return result


# Global Task Registry
OPTIMIZATION_TASKS: Dict[str, Dict[str, Any]] = {}
HEAVY_OPTIMIZATION_TASKS: Dict[str, Dict[str, Any]] = {}  # For large-scale optimizations

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

def _run_sync_in_process(strategy_cls, config, symbol, interval, days, from_date, initial_capital, to_date=None):
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
    print(f"[OPT_WORKER] symbol={symbol}, interval={interval}, days={days}, from_date={from_date}, to_date={to_date}")
    config = build_backtest_config(config, symbol, interval, days, from_date, initial_capital, to_date=to_date)
    actual_interval = config['interval']

    result = loop.run_until_complete(engine.run_integrated(
        strategies_config=[config],
        global_symbol=symbol,
        interval=actual_interval,
        duration_days=days,
        from_date=from_date,
        to_date=to_date,
        initial_capital=initial_capital,
        optimize_mode=True
    ))

    return config, result

def _optimize_background_task(task_id: str, run_args: List, strategy_id: str, start_time: float, total_combos: int, save_to_tab_id: str = None, save_account_id: int = None):
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
                         sym_tag = f" [{config.get('symbol', '')}]" if config.get('symbol') else ""
                         OPTIMIZATION_TASKS[task_id]["message"] = f"Processing ({i+1}/{total_combos}){sym_tag}... {res['perf_log']}"

                    # Calculate Score
                    ret = float(str(res['total_return']).replace('%', '').replace(',', ''))
                    wr = float(str(res['win_rate']).replace('%', ''))
                    trades = int(res.get('total_trades', 0))

                    score = ret * (wr / 100.0)

                    # Extract recent_10_win_rate as float
                    recent_10_wr = res.get("recent_10_win_rate", 0)
                    if isinstance(recent_10_wr, str):
                        recent_10_wr = float(recent_10_wr.replace('%', '')) if recent_10_wr != '-' else 0.0

                    # Use centralized serializer for consistent stats
                    from ..core.stats_serializer import serialize_backtest_stats
                    stats_obj = serialize_backtest_stats(res)
                    stats_dict = stats_obj.model_dump()

                    results.append(OptimizationResultItem(
                        rank=0,
                        symbol=config.get('symbol', ''),
                        config=config,
                        total_return=ret,
                        win_rate=wr,
                        recent_10_win_rate=recent_10_wr,
                        total_trades=trades,
                        score=round(score, 2),
                        # Top-level fields for backward compatibility (string format)
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
                        # Single source of truth (frontend normalizeStats checks stats first)
                        stats=stats_dict,
                        metrics={}  # Empty - deprecated
                    ))
            except Exception as e:
                logger.error(f"Result Error: {e}")
                failures.append(str(e))

            # Update Progress
            OPTIMIZATION_TASKS[task_id]["progress_current"] = i + 1

            # Update partial results every 10 items (for live preview)
            if len(results) > 0 and (i + 1) % 10 == 0:
                # Sort current results and take top 20 for preview
                sorted_partial = sorted(results, key=lambda x: x.score, reverse=True)[:20]
                # Assign temporary ranks
                partial_with_ranks = []
                for idx, item in enumerate(sorted_partial):
                    partial_with_ranks.append(item.model_copy(update={"rank": idx + 1}))
                OPTIMIZATION_TASKS[task_id]["partial_results"] = partial_with_ranks

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

        # Write ALL results to CSV file
        csv_filename = f"optimization_{task_id}.csv"
        csv_filepath = os.path.join(CSV_OUTPUT_DIR, csv_filename)
        try:
            with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                if results:
                    # Define CSV columns (symbol included for cross-optimization)
                    csv_columns = [
                        'rank', 'symbol', 'score', 'total_return', 'win_rate', 'recent_10_win_rate', 'total_trades',
                        'max_drawdown', 'profit_factor', 'sharpe_ratio', 'avg_pnl',
                        'stability_score', 'acceleration_score', 'activity_rate',
                        'avg_holding_time', 'max_holding_time', 'min_holding_time',
                        'max_profit', 'max_loss', 'total_days'
                    ]
                    # Add config keys from first result
                    config_keys = list(results[0].config.keys())
                    all_columns = csv_columns + [f"config_{k}" for k in config_keys]

                    writer = csv.DictWriter(csvfile, fieldnames=all_columns)
                    writer.writeheader()

                    for item in results:
                        row = {
                            'rank': item.rank,
                            'symbol': item.symbol or '',
                            'score': item.score,
                            'total_return': item.total_return,
                            'win_rate': item.win_rate,
                            'recent_10_win_rate': item.recent_10_win_rate or 0,
                            'total_trades': item.total_trades,
                            'max_drawdown': item.max_drawdown,
                            'profit_factor': item.profit_factor,
                            'sharpe_ratio': item.sharpe_ratio,
                            'avg_pnl': item.avg_pnl,
                            'stability_score': item.stability_score,
                            'acceleration_score': item.acceleration_score,
                            'activity_rate': item.activity_rate,
                            'avg_holding_time': item.avg_holding_time,
                            'max_holding_time': item.max_holding_time,
                            'min_holding_time': item.min_holding_time,
                            'max_profit': item.max_profit,
                            'max_loss': item.max_loss,
                            'total_days': item.total_days,
                        }
                        # Add config values
                        for k in config_keys:
                            row[f"config_{k}"] = item.config.get(k, "")
                        writer.writerow(row)

            OPTIMIZATION_TASKS[task_id]["csv_file"] = csv_filename
            logger.info(f"[CSV] Saved {len(results)} results to {csv_filepath}")
        except Exception as csv_err:
            logger.error(f"[CSV] Failed to save CSV: {csv_err}")

        execution_time = time.time() - start_time
        
        # Determine final status
        final_status = "completed"
        if OPTIMIZATION_TASKS[task_id].get("cancel_requested"):
             final_status = "cancelled"
        
        response = OptimizationResponse(
            strategy_id=strategy_id,
            best_config=results[0].config if results else {},
            results=results[:200],
            failures=failures,
            total_combinations=total_combos,
            elapsed_time=execution_time,
            task_id=task_id,
            status=final_status
        )
        
        OPTIMIZATION_TASKS[task_id]["status"] = final_status
        OPTIMIZATION_TASKS[task_id]["result"] = response

        # Server-side auto-save to DB (independent of frontend polling)
        if save_to_tab_id and final_status == "completed":
            try:
                from ..db.session import SessionLocal
                from ..models.strategy_result import StrategyAnalysisResult
                db = SessionLocal()
                try:
                    result_data = response.model_dump() if hasattr(response, 'model_dump') else response.dict()
                    db_obj = db.query(StrategyAnalysisResult).filter(
                        StrategyAnalysisResult.tab_id == save_to_tab_id,
                        StrategyAnalysisResult.result_type == "optimization",
                        StrategyAnalysisResult.account_id == save_account_id
                    ).first()
                    if db_obj:
                        db_obj.data = result_data
                    else:
                        db_obj = StrategyAnalysisResult(
                            tab_id=save_to_tab_id,
                            result_type="optimization",
                            account_id=save_account_id,
                            data=result_data
                        )
                        db.add(db_obj)
                    db.commit()
                    logger.info(f"[Optimization] Auto-saved results to DB (tab_id={save_to_tab_id})")
                finally:
                    db.close()
            except Exception as save_err:
                logger.error(f"[Optimization] Failed to auto-save to DB: {save_err}")

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
            "recent_10_win_rate": result.get('recent_10_win_rate', 0),
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
    to_date: Optional[str] = None  # End date (default: yesterday). Fixes date range for reproducible results.
    initial_capital: int = 10000000
    config: Dict[str, Any] = {} # Nested config from frontend strategy selector

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
        to_date=request.to_date
    )

    # Return standardized response
    return {
        "strategy_id": strategy_id,
        "total_return": result.get('total_return', 0),
        "win_rate": result.get('win_rate', 0),
        "recent_10_win_rate": result.get('recent_10_win_rate', 0),
        "max_drawdown": result.get('max_drawdown', 0),
        "total_trades": result.get('total_trades', 0),
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

@router.post("/{strategy_id}/optimize", response_model=OptimizationResponse)
async def optimize_strategy(strategy_id: str, request: OptimizationRequest, ctx: UserAccountContext = Depends(get_user_context)):
    start_time = time.time()
    
    # 1. Select Strategy Class from Registry
    from ..core.strategy_registry import StrategyRegistry
    strategy_class = StrategyRegistry.get_strategy_class(strategy_id)
    
    if not strategy_class:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found for optimization.")

    # 2. Generate Cartesian Product (with optional multi-symbol cross-optimization)
    symbols = request.symbols if request.symbols else [request.symbol]
    keys = list(request.parameter_ranges.keys())
    values = list(request.parameter_ranges.values())
    param_combinations = list(itertools.product(*values))

    # No limit - user can stop manually via cancel button if needed
    # Accurate optimization results are more important than speed
    total_combinations = len(symbols) * len(param_combinations)
    logger.info(f"[Optimization] Running {total_combinations} combinations ({len(symbols)} symbols x {len(param_combinations)} params) for {strategy_id}, to_date={request.to_date}, days={request.days}, from_date={request.from_date}")

    # 3. Prepare Tasks
    tasks = []
    base_config = request.base_config.copy()

    run_args = []
    for symbol in symbols:
        for idx, combo in enumerate(param_combinations):
            # Merge combo into config
            current_config = base_config.copy()
            current_config['strategy_id'] = strategy_id  # Required for fresh class lookup after module reload
            current_config['symbol'] = symbol  # Override symbol for cross-optimization
            for i, key in enumerate(keys):
                current_config[key] = combo[i]

            # Debug: Log first few combinations
            if len(run_args) < 5:
                logger.info(f"[DEBUG] Combo {len(run_args)}: symbol={symbol}, interval={current_config.get('interval', 'NOT_SET')}")

            run_args.append((
                strategy_class,
                current_config,
                symbol,
                request.interval,
                request.days,
                request.from_date,
                request.initial_capital,
                request.to_date
            ))

    # 4. Async Execution (Fire and Forget)
    task_id = str(uuid.uuid4())

    OPTIMIZATION_TASKS[task_id] = {
        "status": "initializing",
        "progress_current": 0,
        "progress_total": total_combinations,
        "message": "Initializing...",
        "result": None,
        "task_id": task_id
    }

    # Run in Thread (to allow Thread to manage ProcessPool and updates)
    import asyncio
    loop = asyncio.get_running_loop()
    save_tab_id = request.save_to_tab_id
    save_acct_id = ctx.account_id if ctx.has_active_account else None
    loop.run_in_executor(
        None,
        _optimize_background_task,
        task_id,
        run_args,
        strategy_id,
        start_time,
        total_combinations,
        save_tab_id,
        save_acct_id
    )

    # Return Immediate Response
    return OptimizationResponse(
        strategy_id=strategy_id,
        best_config={},
        results=[],
        failures=[],
        total_combinations=total_combinations,
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

    # Build response first
    response = OptimizationStatus(
        task_id=task_id,
        status=task["status"],
        progress_current=task.get("progress_current", 0),
        progress_total=task.get("progress_total", 0),
        message=task.get("message", ""),
        result=task.get("result"),
        csv_file=task.get("csv_file"),
        partial_results=task.get("partial_results") if task["status"] == "running" else None
    )

    # Memory cleanup: Delete completed/failed/cancelled tasks after returning result
    # Frontend saves to DB, so we don't need to keep it in memory
    if task["status"] in ("completed", "failed", "cancelled") and task.get("result"):
        del OPTIMIZATION_TASKS[task_id]
        logger.info(f"[Memory Cleanup] Deleted optimization task {task_id} from memory after result delivery")

    return response


@router.get("/optimize/download/{task_id}")
async def download_optimization_csv(task_id: str):
    """
    Download the full optimization results as a CSV file.
    The file contains ALL results, not just the top 200.
    """
    csv_filename = f"optimization_{task_id}.csv"
    csv_filepath = os.path.join(CSV_OUTPUT_DIR, csv_filename)

    if not os.path.exists(csv_filepath):
        raise HTTPException(status_code=404, detail="CSV file not found. Optimization may still be running or task_id is invalid.")

    return FileResponse(
        path=csv_filepath,
        filename=csv_filename,
        media_type="text/csv"
    )


# ============================================================================
# HEAVY OPTIMIZATION (Large-scale, 10K-100K+ combinations)
# ============================================================================

def _heavy_optimize_background_task(task_id: str, run_args: List, strategy_id: str, start_time: float, total_combos: int, save_to_tab_id: str = None, save_account_id: int = None):
    """
    Background task for heavy optimization.
    Streams results directly to CSV to avoid memory issues.
    """
    import heapq

    csv_filename = f"heavy_opt_{task_id}.csv"
    csv_filepath = os.path.join(CSV_OUTPUT_DIR, csv_filename)

    try:
        # Update status
        HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "running"
        HEAVY_OPTIMIZATION_TASKS[task_id]["progress_total"] = total_combos

        # Top 10 results (min-heap by score, keep top 10)
        top_results = []
        processed = 0
        failures = 0

        # CSV columns
        csv_columns = [
            'rank', 'symbol', 'score', 'total_return', 'win_rate', 'recent_10_win_rate', 'total_trades',
            'max_drawdown', 'profit_factor', 'sharpe_ratio', 'avg_pnl',
            'stability_score', 'acceleration_score', 'activity_rate',
            'avg_holding_time', 'max_holding_time', 'min_holding_time',
            'max_profit', 'max_loss', 'total_days'
        ]
        config_keys = None

        # Open CSV file for streaming write
        with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = None

            for i, args in enumerate(run_args):
                # Check for cancellation
                if HEAVY_OPTIMIZATION_TASKS[task_id].get("cancel_requested"):
                    logger.info(f"Heavy optimization {task_id} cancellation requested at {i}/{total_combos}")
                    HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "cancelled"
                    HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Cancelled at {i}/{total_combos}"
                    break

                try:
                    config, res = _run_sync_in_process(*args)

                    if "error" in res:
                        failures += 1
                        continue

                    # Extract metrics - SAME as regular optimization (directly from res)
                    symbol = config.get('symbol', '')

                    # Parse total_return and win_rate (same as regular optimization)
                    total_return = float(str(res.get('total_return', '0')).replace('%', '').replace(',', ''))
                    win_rate = float(str(res.get('win_rate', '0')).replace('%', ''))
                    total_trades = int(res.get('total_trades', 0))

                    # Calculate score (same formula as regular optimization)
                    score = total_return * (win_rate / 100.0)

                    # Extract recent_10_win_rate
                    recent_10_wr = res.get("recent_10_win_rate", 0)
                    if isinstance(recent_10_wr, str):
                        recent_10_wr = float(recent_10_wr.replace('%', '')) if recent_10_wr != '-' else 0.0

                    # Build row data (same fields as regular optimization CSV)
                    row = {
                        'rank': 0,  # Will be updated later
                        'symbol': symbol,
                        'score': round(score, 2),
                        'total_return': total_return,
                        'win_rate': win_rate,
                        'recent_10_win_rate': recent_10_wr,
                        'total_trades': total_trades,
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

                    # Initialize CSV writer with config keys from first result
                    if writer is None:
                        config_keys = [k for k in config.keys() if k not in ['symbol', 'strategy_id']]
                        all_columns = csv_columns + [f"config_{k}" for k in config_keys]
                        writer = csv.DictWriter(csvfile, fieldnames=all_columns)
                        writer.writeheader()

                    # Add config values to row
                    for k in config_keys:
                        row[f"config_{k}"] = config.get(k, "")

                    # Write row to CSV
                    writer.writerow(row)
                    csvfile.flush()  # Ensure data is written

                    # Update top 10 (min-heap)
                    # Include all metrics (same as regular optimization for consistency)
                    result_entry = {
                        'score': score,
                        'symbol': symbol,
                        'total_return': total_return,
                        'win_rate': win_rate,
                        'recent_10_win_rate': recent_10_wr,
                        'total_trades': total_trades,
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
                        heapq.heappush(top_results, (score, i, result_entry))
                    elif score > top_results[0][0]:
                        heapq.heapreplace(top_results, (score, i, result_entry))

                    processed += 1

                except Exception as e:
                    failures += 1
                    logger.warning(f"Heavy opt iteration {i} failed: {e}")

                # Update progress
                elapsed = time.time() - start_time
                avg_time_per_combo = elapsed / (i + 1)
                remaining = avg_time_per_combo * (total_combos - i - 1)

                HEAVY_OPTIMIZATION_TASKS[task_id]["progress_current"] = i + 1
                HEAVY_OPTIMIZATION_TASKS[task_id]["elapsed_seconds"] = elapsed
                HEAVY_OPTIMIZATION_TASKS[task_id]["estimated_remaining_seconds"] = remaining
                HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Processing ({i+1}/{total_combos})..."

                # Update top results every 10 iterations (for real-time partial display)
                if (i + 1) % 10 == 0:
                    sorted_top = sorted([t[2] for t in top_results], key=lambda x: x['score'], reverse=True)
                    HEAVY_OPTIMIZATION_TASKS[task_id]["top_results"] = sorted_top

        # Finalize
        elapsed = time.time() - start_time
        file_size = os.path.getsize(csv_filepath) if os.path.exists(csv_filepath) else 0

        sorted_top = sorted([t[2] for t in top_results], key=lambda x: x['score'], reverse=True)

        if HEAVY_OPTIMIZATION_TASKS[task_id]["status"] != "cancelled":
            HEAVY_OPTIMIZATION_TASKS[task_id]["status"] = "completed"
            HEAVY_OPTIMIZATION_TASKS[task_id]["message"] = f"Completed: {processed} results, {failures} failures"

        HEAVY_OPTIMIZATION_TASKS[task_id]["csv_file"] = csv_filename
        HEAVY_OPTIMIZATION_TASKS[task_id]["file_size_bytes"] = file_size
        HEAVY_OPTIMIZATION_TASKS[task_id]["top_results"] = sorted_top
        HEAVY_OPTIMIZATION_TASKS[task_id]["progress_current"] = total_combos
        HEAVY_OPTIMIZATION_TASKS[task_id]["elapsed_seconds"] = elapsed

        logger.info(f"Heavy optimization {task_id} completed: {processed} results in {elapsed:.1f}s")

        # Server-side auto-save to DB (same as regular optimization)
        if save_to_tab_id and HEAVY_OPTIMIZATION_TASKS[task_id]["status"] == "completed":
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
                            "total_trades": stats.total_trades,
                        }

                    result_data = {
                        "strategy_id": strategy_id,
                        "best_config": sorted_top[0]["config"] if sorted_top else {},
                        "results": [format_result_item(idx, r) for idx, r in enumerate(sorted_top)],
                        "total_combinations": total_combos,
                        "elapsed_time": elapsed,
                        "status": "completed"
                    }

                    db_obj = db.query(StrategyAnalysisResult).filter(
                        StrategyAnalysisResult.tab_id == save_to_tab_id,
                        StrategyAnalysisResult.result_type == "optimization",
                        StrategyAnalysisResult.account_id == save_account_id
                    ).first()
                    if db_obj:
                        db_obj.data = result_data
                    else:
                        db_obj = StrategyAnalysisResult(
                            tab_id=save_to_tab_id,
                            result_type="optimization",
                            account_id=save_account_id,
                            data=result_data
                        )
                        db.add(db_obj)
                    db.commit()
                    logger.info(f"[Heavy Optimization] Auto-saved {len(sorted_top)} results to DB (tab_id={save_to_tab_id})")
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
                request.to_date
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
        "symbols": symbols
    }

    # Start background task
    import asyncio
    loop = asyncio.get_running_loop()
    save_tab_id = request.save_to_tab_id
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
        save_acct_id
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
        top_results=task.get("top_results")
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
async def list_heavy_optimization_tasks():
    """List all heavy optimization tasks (for recovery after refresh)."""
    tasks = []
    for task_id, task in HEAVY_OPTIMIZATION_TASKS.items():
        tasks.append({
            "task_id": task_id,
            "status": task.get("status"),
            "progress_percent": round(task.get("progress_current", 0) / max(task.get("progress_total", 1), 1) * 100, 2),
            "strategy_id": task.get("strategy_id"),
            "symbols": task.get("symbols", []),
            "started_at": task.get("started_at"),
            "csv_file": task.get("csv_file")
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
    trades = _parse_numeric(row.get('total_trades', 0))  # = Cycle count
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

    # Try to find CSV file from both regular and heavy optimization tasks
    csv_filename = None

    # Check regular optimization tasks first
    if task_id in OPTIMIZATION_TASKS:
        csv_filename = OPTIMIZATION_TASKS[task_id].get("csv_file")

    # Check heavy optimization tasks
    if not csv_filename and task_id in HEAVY_OPTIMIZATION_TASKS:
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
            total_trades=int(_parse_numeric(row.get('total_trades', 0))),
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
            to_date=request.to_date
        )

        return result

    except Exception as e:
        logger.error(f"[INTEGRATED] Error: {str(e)}")
        logger.error(f"[INTEGRATED] Traceback: {traceback.format_exc()}")
        raise

