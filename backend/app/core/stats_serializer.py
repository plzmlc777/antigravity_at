"""
Centralized statistics serialization utilities.
Converts raw backtest engine results to standardized BacktestStats schema.
"""
from typing import Any, Dict, Optional, Union
from ..schemas.stats import BacktestStats, OptimizationResultItem


def _to_float(value: Any, default: float = 0.0) -> float:
    """Convert various types to float."""
    if value is None or value == "-" or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove % and , from string
        cleaned = value.replace("%", "").replace(",", "").strip()
        if cleaned == "-" or cleaned == "":
            return default
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Convert various types to int."""
    if value is None or value == "-" or value == "":
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned == "-" or cleaned == "":
            return default
        try:
            return int(float(cleaned))
        except ValueError:
            return default
    return default


def serialize_backtest_stats(raw: Dict[str, Any]) -> BacktestStats:
    """
    Convert raw backtest engine result to standardized BacktestStats.

    Args:
        raw: Raw result dict from waterfall_engine or optimization

    Returns:
        BacktestStats with consistent types
    """
    return BacktestStats(
        # Core Performance
        total_return=_to_float(raw.get("total_return")),
        win_rate=_to_float(raw.get("win_rate")),
        recent_10_win_rate=_to_float(raw.get("recent_10_win_rate")) if raw.get("recent_10_win_rate") is not None else None,
        total_trades=_to_int(raw.get("total_trades"), 0) or 0,
        total_days=_to_int(raw.get("total_days"), 0) or 0,

        # Risk Metrics
        max_drawdown=_to_float(raw.get("max_drawdown")),
        sharpe_ratio=_to_float(raw.get("sharpe_ratio")),
        profit_factor=_to_float(raw.get("profit_factor")),

        # PnL Details
        avg_pnl=_to_float(raw.get("avg_pnl")),
        max_profit=_to_float(raw.get("max_profit")),
        max_loss=_to_float(raw.get("max_loss")),

        # Time Metrics
        avg_holding_time=_to_int(raw.get("avg_holding_time")),
        max_holding_time=_to_int(raw.get("max_holding_time")),
        min_holding_time=_to_int(raw.get("min_holding_time")),

        # Quality Scores
        stability_score=_to_float(raw.get("stability_score")),
        acceleration_score=_to_float(raw.get("acceleration_score")),
        activity_rate=_to_float(raw.get("activity_rate")),

        # Cycle Metrics (martingale)
        cycle_count=_to_int(raw.get("cycle_count")),
        cycle_avg_pnl=_to_float(raw.get("cycle_avg_pnl")) if raw.get("cycle_avg_pnl") is not None else None,
        cycle_avg_hold=_to_int(raw.get("cycle_avg_hold")),
        cycle_max_hold=_to_int(raw.get("cycle_max_hold")),
        cycle_min_hold=_to_int(raw.get("cycle_min_hold")),
    )


def serialize_optimization_result_item(
    rank: int,
    score: float,
    config: Dict[str, Any],
    raw_stats: Dict[str, Any],
    symbol: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create optimization result item with standardized stats.

    Returns dict format for JSON serialization (DB storage).
    """
    stats = serialize_backtest_stats(raw_stats)

    return {
        "rank": rank,
        "score": round(score, 4),
        "symbol": symbol or "",
        "config": config,
        "stats": stats.model_dump(),
        # Legacy compatibility: also include top-level fields
        "total_return": stats.total_return,
        "win_rate": stats.win_rate,
        "recent_10_win_rate": stats.recent_10_win_rate,
        "total_trades": stats.total_trades,
    }


def stats_to_legacy_format(stats: BacktestStats) -> Dict[str, Any]:
    """
    Convert BacktestStats to legacy format with string values.
    For backward compatibility with existing frontend code.
    """
    return {
        "total_return": stats.total_return,
        "win_rate": stats.win_rate,
        "recent_10_win_rate": stats.recent_10_win_rate,
        "total_trades": stats.total_trades,
        "total_days": stats.total_days,
        "max_drawdown": str(stats.max_drawdown) if stats.max_drawdown else "-",
        "sharpe_ratio": str(stats.sharpe_ratio) if stats.sharpe_ratio else "-",
        "profit_factor": str(stats.profit_factor) if stats.profit_factor else "-",
        "avg_pnl": str(stats.avg_pnl) if stats.avg_pnl else "-",
        "max_profit": str(stats.max_profit) if stats.max_profit else "-",
        "max_loss": str(stats.max_loss) if stats.max_loss else "-",
        "avg_holding_time": str(stats.avg_holding_time) if stats.avg_holding_time else "-",
        "max_holding_time": str(stats.max_holding_time) if stats.max_holding_time else "-",
        "min_holding_time": str(stats.min_holding_time) if stats.min_holding_time else "-",
        "stability_score": str(stats.stability_score) if stats.stability_score else "-",
        "acceleration_score": str(stats.acceleration_score) if stats.acceleration_score else "-",
        "activity_rate": str(stats.activity_rate) if stats.activity_rate else "-",
        "cycle_count": stats.cycle_count,
        "cycle_avg_pnl": stats.cycle_avg_pnl,
        "cycle_avg_hold": stats.cycle_avg_hold,
        "cycle_max_hold": stats.cycle_max_hold,
        "cycle_min_hold": stats.cycle_min_hold,
    }


def merge_stats_with_metrics(stats: BacktestStats) -> Dict[str, Any]:
    """
    Create result dict with both top-level stats and metrics sub-object.
    For backward compatibility with existing optimization result format.
    """
    stats_dict = stats.model_dump()

    return {
        # Top-level (legacy format)
        **stats_to_legacy_format(stats),
        # New unified stats object
        "stats": stats_dict,
        # Legacy metrics object (deprecated, for backward compat)
        "metrics": stats_dict,
    }
