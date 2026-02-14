from pydantic import BaseModel, Field
from typing import Dict, List, Union, Any, Optional

class OptimizationRequest(BaseModel):
    symbol: str
    symbols: Optional[List[str]] = None  # Multi-symbol cross-optimization
    interval: str = "1m"
    days: int = 365  # Default 1 year, max 730 (2 years)
    from_date: Optional[str] = None
    to_date: Optional[str] = None  # End date (default: yesterday). Fixes date range for reproducible results.
    initial_capital: float = 10000000
    # Parameter Search Space: { "key": [1, 2, 3], "other": ["a", "b"] }
    parameter_ranges: Dict[str, List[Union[str, int, float]]]
    base_config: Dict[str, Any] = {} # Default/Fixed values
    # Server-side auto-save: tab UUID for persisting results to DB on completion
    save_to_tab_id: Optional[str] = None
    save_account_id: Optional[int] = None
    execution_mode: str = "standard"  # "standard" (sequential) or "fast" (parallel ProcessPool)

class OptimizationResultItem(BaseModel):
    rank: int
    symbol: Optional[str] = None  # Which symbol this result belongs to (cross-optimization)
    config: Dict[str, Any]
    total_return: float
    win_rate: float
    recent_10_win_rate: Optional[float] = None  # Recent 10 cycles win rate
    total_trades: int
    score: float
    # Detailed Metrics (Explicitly added to avoid stripping)
    max_drawdown: Optional[str] = None
    profit_factor: Optional[str] = None
    sharpe_ratio: Optional[str] = None
    avg_pnl: Optional[str] = None
    stability_score: Optional[str] = None
    acceleration_score: Optional[str] = None
    activity_rate: Optional[str] = None
    total_days: Optional[int] = 0
    avg_holding_time: Optional[str] = None  # Cycle-based: avg cycle duration (minutes)
    max_holding_time: Optional[str] = None  # Cycle-based: max cycle duration (minutes)
    min_holding_time: Optional[str] = None  # Cycle-based: min cycle duration (minutes)
    max_profit: Optional[str] = None
    max_loss: Optional[str] = None
    # Single source of truth for all stats (used by frontend normalizeStats)
    stats: Dict[str, Any] = {}
    # Legacy field - kept empty for backward compatibility
    metrics: Dict[str, Any] = {}

class OptimizationResponse(BaseModel):
    strategy_id: str
    best_config: Dict[str, Any]
    results: List[OptimizationResultItem]
    failures: List[str] = [] # Debugging info
    total_combinations: int
    elapsed_time: float
    # Async Fields
    task_id: Optional[str] = None
    status: Optional[str] = "completed" # completed, running, failed

class OptimizationStatus(BaseModel):
    task_id: str
    status: str
    progress_current: int
    progress_total: int
    message: str
    result: Optional[OptimizationResponse] = None
    csv_file: Optional[str] = None  # CSV filename for full results download
    partial_results: Optional[List[OptimizationResultItem]] = None  # Top N results so far (during running)


# Heavy Optimization (Large-scale, CSV streaming)
class HeavyOptimizationRequest(BaseModel):
    """Request for large-scale optimization (10K-100K+ combinations)"""
    symbols: List[str]  # Multiple symbols required
    interval: str = "1m"
    days: int = 365
    from_date: Optional[str] = None
    to_date: Optional[str] = None  # End date (default: yesterday). Fixes date range for reproducible results.
    initial_capital: float = 10000000
    parameter_ranges: Dict[str, List[Union[str, int, float]]]
    base_config: Dict[str, Any] = {}
    strategy_id: str = "DipMartingaleStrategy"
    # Server-side auto-save: tab UUID for persisting results to DB on completion
    save_to_tab_id: Optional[str] = None
    save_account_id: Optional[int] = None
    profile_id: Optional[str] = None  # Profile UUID for task recovery across browsers
    tab_key: Optional[str] = None  # Tab identifier (e.g. "0", "-3") for per-tab tracking
    execution_mode: str = "standard"  # "standard" (sequential) or "fast" (parallel ProcessPool)


class HeavyOptimizationStatus(BaseModel):
    """Status for heavy optimization task"""
    task_id: str
    status: str  # pending, running, completed, failed, cancelled
    progress_current: int
    progress_total: int
    progress_percent: float
    message: str
    started_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    estimated_remaining_seconds: Optional[float] = None
    csv_file: Optional[str] = None  # Available when completed
    file_size_bytes: Optional[int] = None
    top_results: Optional[List[Dict[str, Any]]] = None  # Top 10 results so far
    profile_id: Optional[str] = None  # Profile UUID for task association
    tab_key: Optional[str] = None  # Tab identifier for per-tab tracking


class ScoreWeights(BaseModel):
    """Weights for score calculation formula: (Return^w × Sharpe^w × Stability^w × AvgPnL^w) / MDD^w

    Note: All metrics are now cycle-based for martingale strategies.
    - total_trades = number of completed cycles
    - win_rate = profitable cycles / total cycles
    - avg_pnl = average PnL per cycle
    """
    # Primary weights (important)
    return_weight: float = 1.0     # Return weight (0 = exclude)
    sharpe_weight: float = 1.2     # Sharpe ratio weight (0 = exclude)
    stability_weight: float = 1.0  # Stability score weight (0 = exclude)
    mdd_weight: float = 1.5        # Max drawdown penalty weight (0 = no penalty)
    avg_pnl_weight: float = 1.0    # Avg PnL per cycle weight (0 = exclude)
    # Secondary weights (optional, default 0)
    win_rate_weight: float = 0.0   # Win rate weight (cycle-based)
    recent_10_weight: float = 0.0  # Recent 10 cycles win rate weight (momentum indicator)
    profit_factor_weight: float = 0.0  # Profit factor weight
    accel_weight: float = 0.0      # Acceleration weight
    trades_weight: float = 0.0     # Total trades weight (= cycle count for martingale)
    activity_weight: float = 0.0   # Activity rate weight

    class Config:
        json_schema_extra = {
            "example": {
                "return_weight": 1.0,
                "sharpe_weight": 1.2,
                "stability_weight": 1.0,
                "mdd_weight": 1.5,
                "avg_pnl_weight": 1.0,
                "win_rate_weight": 0.0,
                "recent_10_weight": 0.0,
                "profit_factor_weight": 0.0,
                "accel_weight": 0.0,
                "trades_weight": 0.0,
                "activity_weight": 0.0
            }
        }


class RecalculateScoreRequest(BaseModel):
    """Request to recalculate scores with custom weights from full CSV"""
    task_id: str  # Original optimization task_id to find CSV file
    weights: ScoreWeights
    top_n: int = 50  # Number of top results to return


class RecalculateScoreResponse(BaseModel):
    """Response with recalculated top N results"""
    task_id: str
    total_rows: int
    weights_applied: ScoreWeights
    results: List[OptimizationResultItem]
