"""
symbol_score.py - SINGLE SOURCE OF TRUTH for AI Symbol Selection Scoring

Reliability-weighted composite score used by the AI symbol selection pipeline:
  base_score  = (return% × 0.7) + (win_rate% × 0.15)
  reliability = function of trade count (1~2: 0.3~0.4, 3~4: 0.55~0.7,
                5~9: 0.76~1.0, 10+: 1.0~1.2 bonus capped at 30)
  score       = base_score × reliability

Used by:
- backend ai_symbol_selection.AISymbolSelector._calculate_score (live pipeline)
- skill at-symbol-select/scripts/scoring.py (CLI thin wrapper)

Both paths must produce identical scores. Modify only here.
"""

from typing import Any, Dict, List


def calculate_score(total_return: float, win_rate: float, total_cycles: int) -> float:
    """Reliability-weighted composite score for AI symbol selection.

    Args:
        total_return: Total return in percent (e.g., 5.43)
        win_rate:     Win rate in percent (e.g., 62.7)
        total_cycles: Number of completed trade cycles

    Returns:
        Composite score (higher = better). Returns -inf when total_cycles == 0.
    """
    if total_cycles == 0:
        return float("-inf")

    # Base score: return-dominant + win_rate as tiebreaker
    # Return already reflects leverage (equity-based), so weight it heavily
    base_score = (total_return * 0.7) + (win_rate * 0.15)

    # Reliability multiplier based on trade count
    if total_cycles <= 2:
        reliability = 0.2 + (total_cycles * 0.1)              # 0.3 ~ 0.4
    elif total_cycles <= 4:
        reliability = 0.4 + ((total_cycles - 2) * 0.15)       # 0.55 ~ 0.7
    elif total_cycles <= 9:
        reliability = 0.7 + ((total_cycles - 4) * 0.06)       # 0.76 ~ 1.0
    else:
        reliability = 1.0 + (min(total_cycles, 30) - 10) * 0.01  # 1.0 ~ 1.2 bonus

    return base_score * reliability


def _coerce_pct(value: Any) -> float:
    """Parse a percentage value that may be a number or a string like '5.43%' or '5,432'."""
    return float(str(value).replace("%", "").replace(",", ""))


def calculate_score_from_result(result: Dict[str, Any]) -> float:
    """Convenience: extract (total_return, win_rate, total_cycles) from a backtest
    result dict and compute the score. Used by both backend and skill."""
    total_return = _coerce_pct(result.get("total_return", 0))
    win_rate = _coerce_pct(result.get("win_rate", 0))
    total_cycles = int(result.get("total_cycles", 0))
    return calculate_score(total_return, win_rate, total_cycles)


def score_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add a 'score' field to each backtest result and return the list sorted descending."""
    scored = []
    for r in results:
        entry = dict(r)
        entry["score"] = round(calculate_score_from_result(r), 4)
        scored.append(entry)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
