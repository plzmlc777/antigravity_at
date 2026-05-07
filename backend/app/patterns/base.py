"""
Pattern Library — Base classes.

Design principles (from pattern_strategy_master.json):
1. A detector is a PURE FUNCTION: ohlcv DataFrame -> list[PatternSignal].
2. No trading logic in detectors (no SL/TP/sizing/order placement).
3. No look-ahead leak: PatternSignal.timestamp is the earliest moment the pattern
   could have been detected (current bar close). Trading happens on next bar open.
4. Confidence is normalized to [0, 1]. 1.0 = textbook example.
5. Suggested target/stop are *prices*, not pct. Composer decides whether to use them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal

import pandas as pd


PatternDirection = Literal["bull", "bear", "neutral"]
PatternCategory = Literal["chart", "candle", "indicator", "volume"]

REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class PatternSignal:
    """A single pattern detection event.

    timestamp:
        Bar timestamp at which this pattern became detectable. Trading must wait
        until the NEXT bar's open (handled by composer). Detector itself just
        reports the moment of detection.

    direction:
        bull / bear / neutral. Reversal patterns at tops are bear, at bottoms bull.

    confidence:
        0.0~1.0. Calibrated per-detector — a 0.7 from one detector is roughly
        comparable to 0.7 from another in terms of "textbook-likeness".

    suggested_target / suggested_stop:
        Optional price levels suggested by the pattern itself (e.g. H&S target =
        head height projected from neckline). Composer may override.

    horizon_bars:
        Expected validity window in BARS of the detector's source timeframe.
        Composer uses this for time-stop logic.

    metadata:
        Pattern-specific extra info. Free-form dict for diagnostics/logging.
        Examples: {"cup_depth_pct": 0.22, "neckline_price": 71200, "n_peaks": 3}.
    """
    pattern_name: str
    timestamp: datetime
    direction: PatternDirection
    confidence: float
    horizon_bars: int
    suggested_target: float | None = None
    suggested_stop: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"PatternSignal.confidence must be in [0,1], got {self.confidence}"
            )
        if self.horizon_bars < 1:
            raise ValueError(
                f"PatternSignal.horizon_bars must be >=1, got {self.horizon_bars}"
            )
        if self.direction not in ("bull", "bear", "neutral"):
            raise ValueError(f"Invalid direction: {self.direction}")


class PatternDetector(ABC):
    """Abstract base class for all pattern detectors.

    Subclasses must define:
        - name (ClassVar[str])         : unique identifier (snake_case)
        - category (ClassVar[...])     : chart | candle | indicator | volume
        - min_bars (ClassVar[int])     : minimum bar count required
        - detect(ohlcv) -> list[...]   : detection logic

    Optional:
        - applicable_timeframes        : tuple of timeframes (e.g. ("15m","1h","4h","1d"))
                                          where this detector is meaningful. None = all.
                                          Scanner uses this to skip detectors at TFs
                                          where they have no real-world meaning
                                          (e.g. Cup&Handle on 1m is nonsense).
    """

    name: ClassVar[str] = ""
    category: ClassVar[PatternCategory] = "chart"
    min_bars: ClassVar[int] = 10
    applicable_timeframes: ClassVar[tuple[str, ...] | None] = None

    @classmethod
    def fully_qualified_name(cls) -> str:
        """Stable identifier for fitness tensor keys: 'category/name'."""
        return f"{cls.category}/{cls.name}"

    @staticmethod
    def _validate_ohlcv(ohlcv: pd.DataFrame) -> None:
        missing = [c for c in REQUIRED_OHLCV_COLUMNS if c not in ohlcv.columns]
        if missing:
            raise ValueError(
                f"OHLCV DataFrame missing required columns: {missing}. "
                f"Got: {list(ohlcv.columns)}"
            )
        if not isinstance(ohlcv.index, pd.DatetimeIndex):
            raise ValueError(
                "OHLCV must be indexed by DatetimeIndex (use df.set_index('timestamp'))."
            )

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = dict(self.default_params())
        if params:
            self.params.update(params)

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        """Override to expose tunable parameters."""
        return {}

    def detect(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        """Run detection. Subclasses override _detect_impl, not this."""
        if len(ohlcv) < self.min_bars:
            return []
        self._validate_ohlcv(ohlcv)
        return self._detect_impl(ohlcv)

    @abstractmethod
    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        """Implement detection here. ohlcv is guaranteed to have required columns
        and DatetimeIndex, and len >= min_bars."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.fully_qualified_name()})>"
