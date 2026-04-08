"""
data_schemas.py - SINGLE SOURCE OF TRUTH for Data Point Schemas

Centralizes key names used in equity curve, chart data, etc.
Prevents key mismatch bugs (e.g., "timestamp" vs "date") across engines.

Used by:
- waterfall_engine.py (WaterfallBacktestContext.update_equity, run_parallel combined curve, _calc_mdd)

Frontend counterpart: EQUITY_DATE_KEY in chartConfig.js
"""

# --- Equity Curve Point Schema ---
EQUITY_DATE_KEY = "date"
EQUITY_VALUE_KEY = "equity"


def make_equity_point(date_str: str, equity_value) -> dict:
    """Create a single equity curve data point with consistent keys.

    Args:
        date_str: Date/time string (e.g., "2025-01-27 09:30")
        equity_value: Equity value (int or float)

    Returns:
        dict with standardized keys: {"date": ..., "equity": ...}
    """
    return {
        EQUITY_DATE_KEY: date_str,
        EQUITY_VALUE_KEY: int(equity_value),
    }
