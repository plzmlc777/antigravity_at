from pydantic import BaseModel, Field
from typing import Dict, List, Union, Any, Optional

class OptimizationRequest(BaseModel):
    symbol: str
    interval: str = "1m"
    days: int = 365
    from_date: Optional[str] = None
    initial_capital: float = 10000000
    # Parameter Search Space: { "key": [1, 2, 3], "other": ["a", "b"] }
    parameter_ranges: Dict[str, List[Union[str, int, float]]] 
    base_config: Dict[str, Any] = {} # Default/Fixed values

class OptimizationResultItem(BaseModel):
    rank: int
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
