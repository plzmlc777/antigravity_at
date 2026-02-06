from pydantic import BaseModel, Field
from typing import Dict, List, Union, Any, Optional

class OptimizationRequest(BaseModel):
    symbol: str
    symbols: Optional[List[str]] = None  # Multi-symbol cross-optimization
    interval: str = "1m"
    days: int = 365  # Default 1 year, max 730 (2 years)
    from_date: Optional[str] = None
    initial_capital: float = 10000000
    # Parameter Search Space: { "key": [1, 2, 3], "other": ["a", "b"] }
    parameter_ranges: Dict[str, List[Union[str, int, float]]]
    base_config: Dict[str, Any] = {} # Default/Fixed values
    # Server-side auto-save: tab UUID for persisting results to DB on completion
    save_to_tab_id: Optional[str] = None
    save_account_id: Optional[int] = None

class OptimizationResultItem(BaseModel):
    rank: int
    symbol: Optional[str] = None  # Which symbol this result belongs to (cross-optimization)
    config: Dict[str, Any]
    total_return: float
    win_rate: float
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
    avg_holding_time: Optional[str] = None
    max_profit: Optional[str] = None
    max_loss: Optional[str] = None
    cycle_count: Optional[int] = None  # Martingale cycle count
    cycle_avg_pnl: Optional[float] = None  # Avg PnL per cycle
    cycle_avg_hold: Optional[float] = None  # Avg holding time per cycle (minutes)
    cycle_max_hold: Optional[float] = None  # Max holding time per cycle (minutes)
    cycle_min_hold: Optional[float] = None  # Min holding time per cycle (minutes)
    metrics: Dict[str, Any] = {} # For any extra fields

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
