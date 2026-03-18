"""
OHLCV Gap Detection Utility
- Detects gaps (missing candle data) in OHLCV time series
- Supports both 24/7 markets (Binance crypto) and session-based markets (Kiwoom Korean stocks)
- Returns gap intervals [(gap_start, gap_end), ...] for targeted backfill
"""

from datetime import datetime, timedelta, time as dt_time
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Korean stock market trading hours
KR_MARKET_OPEN = dt_time(9, 0)
KR_MARKET_CLOSE = dt_time(15, 30)

# Gap detection thresholds (multiples of expected interval)
# e.g., for 1m candles, a gap > 5 minutes triggers detection
GAP_THRESHOLD_MULTIPLIER = 5


def detect_gaps(
    candles: list,
    interval: str = "1m",
    is_24h_market: bool = True,
) -> List[Tuple[datetime, datetime]]:
    """
    Detect gaps in candle data by checking timestamp continuity.

    Args:
        candles: List of OHLCV ORM objects with .timestamp attribute
        interval: Candle interval (e.g., "1m", "5m", "1h")
        is_24h_market: True for crypto (24/7), False for Korean stocks (09:00-15:30)

    Returns:
        List of (gap_start, gap_end) tuples where data is missing.
        gap_start = last known candle timestamp before gap
        gap_end = first known candle timestamp after gap
    """
    if len(candles) < 2:
        return []

    interval_minutes = _parse_interval_minutes(interval)
    max_gap_seconds = interval_minutes * 60 * GAP_THRESHOLD_MULTIPLIER

    gaps = []
    for i in range(1, len(candles)):
        prev_ts = candles[i - 1].timestamp
        curr_ts = candles[i].timestamp
        diff_seconds = (curr_ts - prev_ts).total_seconds()

        if diff_seconds <= max_gap_seconds:
            continue

        if not is_24h_market:
            # Korean stocks: skip overnight gaps (market close → next market open)
            if _is_overnight_gap(prev_ts, curr_ts):
                continue

        gaps.append((prev_ts, curr_ts))

    if gaps:
        total_missing = sum(
            (end - start).total_seconds() / 60 for start, end in gaps
        )
        logger.warning(
            f"[GapDetector] Found {len(gaps)} gap(s) in data. "
            f"~{int(total_missing)} minutes missing. "
            f"Largest: {max((e - s).total_seconds() / 3600 for s, e in gaps):.1f}h"
        )

    return gaps


def _is_overnight_gap(prev_ts: datetime, curr_ts: datetime) -> bool:
    """
    Check if the gap between two timestamps is an expected inter-session gap
    for Korean stock market.

    Returns True (= not a real gap) for these cases:
    1. Normal overnight: Fri 15:29 → Mon 09:00 (weekend)
    2. Holiday gap: Wed 15:29 → Fri 09:00 (Thu holiday)
    3. Mid-day cutoff: Tue 11:30 → Thu 09:01 (data stopped mid-session,
       resumed after holiday — still an inter-day gap, not intra-day)
    4. Partial last day: Tue 14:00 → Thu 09:05 (early stop)

    Returns False (= real gap, needs backfill) ONLY when:
    - Both timestamps are on the SAME calendar day AND within trading hours
      e.g., 10:05 → 10:30 on the same day with > threshold gap
    """
    # Same calendar day = intra-day gap = real gap that needs filling
    if prev_ts.date() == curr_ts.date():
        return False

    # Different calendar days: this is an inter-session gap (overnight/weekend/holiday).
    # Regardless of what time prev or curr is, if they're on different days,
    # it's expected market closure. No public holiday calendar needed.
    #
    # Edge case: prev at 09:30 Tue, curr at 14:00 Thu
    # → This means Tue had partial data + Wed was holiday + Thu partial data.
    # → The gap is between sessions, not within a session. Not a real gap.
    return True


def _parse_interval_minutes(interval: str) -> int:
    """Parse interval string to minutes."""
    interval = interval.lower().strip()
    if interval.endswith("m"):
        return int(interval[:-1])
    elif interval.endswith("h"):
        return int(interval[:-1]) * 60
    elif interval == "1d":
        return 1440
    return 1  # default to 1 minute
