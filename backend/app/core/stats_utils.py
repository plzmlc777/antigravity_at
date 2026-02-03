"""
stats_utils.py - SINGLE SOURCE OF TRUTH for Stability/Acceleration Calculations

Used by:
- waterfall_engine.py
- backtest_engine.py

N-Bucket based stability calculation (default N=12)
- Divides trades into N equal groups by count (not by time/month)
- More consistent across different backtest periods
"""

from typing import List, Dict, Any
from datetime import datetime
import numpy as np
from scipy import stats as scipy_stats


# Default number of buckets for stability calculation
DEFAULT_N_BUCKETS = 12


def calc_stability_stats(trades: List[Dict], n_buckets: int = DEFAULT_N_BUCKETS) -> Dict[str, Any]:
    """
    Calculate stability and acceleration scores using N-bucket approach.

    Args:
        trades: List of completed trades with 'time', 'pnl', 'pnl_percent' fields
        n_buckets: Number of buckets to divide trades into (default: 12)

    Returns:
        {
            "stability_score": float (0-1, R² of cumulative PnL curve),
            "acceleration_score": float (recent slope / overall slope),
            "bucket_stats": List of per-bucket stats for UI display
        }
    """
    if not trades or len(trades) == 0:
        return {
            "stability_score": 0.0,
            "acceleration_score": 1.0,
            "bucket_stats": []
        }

    # Parse timestamp helper
    def parse_ts(t):
        if isinstance(t, datetime):
            return t
        return datetime.fromisoformat(t)

    # Sort trades by time
    sorted_trades = sorted(trades, key=lambda t: parse_ts(t['time']))
    total_trades = len(sorted_trades)

    # If fewer trades than buckets, use trade count as bucket count
    actual_buckets = min(n_buckets, total_trades)

    if actual_buckets < 2:
        # Not enough data for meaningful stability calculation
        total_pnl = sum(t.get('pnl_percent', 0) for t in sorted_trades) * 100
        return {
            "stability_score": 0.0,
            "acceleration_score": 1.0,
            "bucket_stats": [{
                "block": "Q1",
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
                "win_rate": round(len([t for t in sorted_trades if t.get('pnl', 0) > 0]) / total_trades * 100, 1) if total_trades > 0 else 0,
                "count": total_trades
            }]
        }

    # Divide trades into N buckets (equal count per bucket)
    bucket_size = total_trades // actual_buckets
    remainder = total_trades % actual_buckets

    bucket_stats = []
    start_idx = 0

    for i in range(actual_buckets):
        # Distribute remainder across first buckets
        extra = 1 if i < remainder else 0
        end_idx = start_idx + bucket_size + extra

        chunk = sorted_trades[start_idx:end_idx]

        if chunk:
            total_pnl = sum(t.get('pnl_percent', 0) for t in chunk) * 100
            avg_pnl = total_pnl / len(chunk)
            wins = len([t for t in chunk if t.get('pnl', 0) > 0])
            win_rate = wins / len(chunk) * 100

            # Get date range for label
            first_date = parse_ts(chunk[0]['time']).strftime("%m/%d")
            last_date = parse_ts(chunk[-1]['time']).strftime("%m/%d")
            date_label = f"{first_date}-{last_date}"
        else:
            total_pnl = 0.0
            avg_pnl = 0.0
            win_rate = 0.0
            date_label = f"Q{i+1}"

        bucket_stats.append({
            "block": f"Q{i+1}",
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
            "win_rate": round(win_rate, 1),
            "date_range": date_label,
            "count": len(chunk)
        })

        start_idx = end_idx

    # Calculate Stability Score (R² of cumulative PnL)
    try:
        pnl_values = [s['total_pnl'] for s in bucket_stats]
        cumulative = np.cumsum(pnl_values)

        x = np.arange(len(cumulative))
        slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, cumulative)

        stability_score = r_value ** 2 if len(cumulative) > 1 else 0.0

        # Calculate Acceleration Score (recent slope / overall slope)
        # Recent = Last 25% of buckets (min 3)
        n_recent = max(3, int(len(cumulative) * 0.25))

        if len(cumulative) >= 6:  # Need enough data for meaningful acceleration
            recent_cum = cumulative[-n_recent:]
            x_recent = np.arange(len(recent_cum))
            slope_recent, _, _, _, _ = scipy_stats.linregress(x_recent, recent_cum)

            if abs(slope) > 0.0001:
                acceleration_score = slope_recent / slope
            else:
                acceleration_score = 0.0
        else:
            acceleration_score = 1.0  # Neutral if not enough data

    except Exception as e:
        print(f"[stats_utils] Error calculating stability: {e}")
        stability_score = 0.0
        acceleration_score = 1.0

    return {
        "stability_score": round(stability_score, 4),
        "acceleration_score": round(acceleration_score, 4),
        "bucket_stats": bucket_stats
    }
