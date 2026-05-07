"""Type definitions for the Pattern Scanner.

The Signal Tensor is represented as a flat pandas DataFrame (parquet-friendly,
analytics-friendly) rather than a nested dict. Each row is one signal emission.

ScannedSignal extends PatternSignal with (symbol, timeframe) so the composer
knows where each signal came from across the (pattern × TF × symbol) cube.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.patterns.base import PatternDirection, PatternSignal


# Standard timeframes scanned by default.  Order matters for ordinal logic
# (lower-index = finer granularity).
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d")


# Pandas resample-style aliases.  Keep in sync with SUPPORTED_TIMEFRAMES.
TF_TO_PANDAS_FREQ: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "60min",
    "4h": "240min",
    "1d": "1D",
}


@dataclass(frozen=True)
class ScannedSignal:
    """Signal emitted by a detector at a specific (symbol, timeframe).

    `metadata` is a free-form dict from the detector. It will be stored as a
    JSON-encoded string when persisted to parquet (because parquet handles
    string columns better than nested dict columns across versions).
    """
    symbol: str
    timeframe: str
    pattern_name: str
    timestamp: datetime
    direction: PatternDirection
    confidence: float
    horizon_bars: int
    suggested_target: float | None = None
    suggested_stop: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_pattern_signal(
        cls, sig: PatternSignal, *, symbol: str, timeframe: str
    ) -> "ScannedSignal":
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            pattern_name=sig.pattern_name,
            timestamp=sig.timestamp,
            direction=sig.direction,
            confidence=sig.confidence,
            horizon_bars=sig.horizon_bars,
            suggested_target=sig.suggested_target,
            suggested_stop=sig.suggested_stop,
            metadata=dict(sig.metadata),
        )

    def to_row(self) -> dict[str, Any]:
        """Flat dict suitable for DataFrame construction."""
        d = asdict(self)
        # metadata kept as dict; conversion to JSON string done at persist time
        return d


def signal_tensor_columns() -> list[str]:
    """Stable column order for the Signal Tensor DataFrame."""
    return [
        "symbol",
        "timeframe",
        "pattern_name",
        "timestamp",
        "direction",
        "confidence",
        "horizon_bars",
        "suggested_target",
        "suggested_stop",
        "metadata",
    ]
