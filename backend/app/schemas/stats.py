"""
Centralized statistics schema for backtest and optimization results.
Single source of truth for all stat field definitions and types.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class BacktestStats(BaseModel):
    """
    Common statistics schema for backtest/optimization results.
    All numeric fields use consistent float/int types.
    """
    # === Core Performance ===
    total_return: float = Field(default=0.0, description="Total return percentage")
    win_rate: float = Field(default=0.0, description="Win rate percentage (0-100)")
    recent_10_win_rate: Optional[float] = Field(default=None, description="Win rate of last 10 trades/cycles")
    total_cycles: int = Field(default=0, description="Total number of trades or cycles")
    total_days: int = Field(default=0, description="Total trading days in backtest period")

    # === Risk Metrics ===
    max_drawdown: float = Field(default=0.0, description="Maximum drawdown percentage (negative)")
    sharpe_ratio: float = Field(default=0.0, description="Sharpe ratio")
    profit_factor: float = Field(default=0.0, description="Profit factor (gross profit / gross loss)")

    # === PnL Details ===
    avg_pnl: float = Field(default=0.0, description="Average PnL per trade/cycle")
    max_profit: float = Field(default=0.0, description="Maximum single profit")
    max_loss: float = Field(default=0.0, description="Maximum single loss (negative)")

    # === Time Metrics ===
    avg_holding_time: Optional[int] = Field(default=None, description="Average holding time in minutes")
    max_holding_time: Optional[int] = Field(default=None, description="Maximum holding time in minutes")
    min_holding_time: Optional[int] = Field(default=None, description="Minimum holding time in minutes")

    # === Quality Scores ===
    stability_score: float = Field(default=0.0, description="Stability score (0-1)")
    acceleration_score: float = Field(default=0.0, description="Acceleration/momentum score")
    activity_rate: float = Field(default=0.0, description="Activity rate percentage")

    # === Cycle Metrics (for martingale strategies) ===
    cycle_count: Optional[int] = Field(default=None, description="Number of completed cycles")
    cycle_avg_pnl: Optional[float] = Field(default=None, description="Average PnL per cycle")
    cycle_avg_hold: Optional[int] = Field(default=None, description="Average cycle duration in minutes")
    cycle_max_hold: Optional[int] = Field(default=None, description="Maximum cycle duration in minutes")
    cycle_min_hold: Optional[int] = Field(default=None, description="Minimum cycle duration in minutes")

    class Config:
        # Allow extra fields for forward compatibility
        extra = "ignore"


class OptimizationResultItem(BaseModel):
    """Single optimization result with rank, config, and stats."""
    rank: int = Field(description="Ranking position (1 = best)")
    score: float = Field(description="Optimization score")
    symbol: Optional[str] = Field(default=None, description="Symbol code (for cross-optimization)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Parameter configuration")
    stats: BacktestStats = Field(description="Backtest statistics for this config")

    # Legacy compatibility: also expose top-level stat fields
    @property
    def total_return(self) -> float:
        return self.stats.total_return

    @property
    def win_rate(self) -> float:
        return self.stats.win_rate


class OptimizationResult(BaseModel):
    """Complete optimization result with multiple configs."""
    strategy_id: str
    best_config: Dict[str, Any]
    total_combinations: int
    elapsed_time: float
    status: str = "completed"
    task_id: Optional[str] = None
    results: List[OptimizationResultItem] = Field(default_factory=list)
    failures: List[str] = Field(default_factory=list)


# === Field Definitions for Frontend Sync ===
# This list defines the canonical order and properties of stat fields
STAT_FIELD_DEFINITIONS = [
    # (key, label, format, decimals, category)
    ("total_return", "Return", "pct", 2, "core"),
    ("profit_factor", "PF", "num", 2, "core"),
    ("win_rate", "Win Rate", "pct", 1, "core"),
    ("recent_10_win_rate", "Recent 10", "pct", 1, "core"),
    ("sharpe_ratio", "Sharpe", "num", 2, "core"),
    ("total_cycles", "Cycles", "int", 0, "activity"),
    ("stability_score", "Stability", "num", 3, "quality"),
    ("acceleration_score", "Accel", "num", 3, "quality"),
    ("activity_rate", "Activity", "pct", 1, "activity"),
    ("avg_pnl", "Avg PnL", "pct", 2, "pnl"),
    ("avg_holding_time", "Avg Hold", "time", 0, "time"),
    ("max_holding_time", "Max Hold", "time", 0, "time"),
    ("min_holding_time", "Min Hold", "time", 0, "time"),
    ("max_profit", "Max Profit", "pct", 2, "pnl"),
    ("max_loss", "Max Loss", "pct", 2, "pnl"),
    ("max_drawdown", "Max DD", "pct", 2, "risk"),
]
