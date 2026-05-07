"""
SignalSource ABC — every feature provider implements this single interface.

A SignalSource takes raw data (the parts it cares about) plus an evaluation
DatetimeIndex and returns a DataFrame of features at those timestamps.

Output contract:
  - Index == eval_index (DatetimeIndex), one row per evaluation moment
  - All column names are prefixed with `self.feature_prefix` (e.g. "pat_", "flow_")
    to avoid collisions across sources
  - Cells must be numeric (or NaN) — composers will fill NaN with 0.0 by default
  - No look-ahead: feature at time t must be derivable from data up to time t

A Pipeline holds a list of sources, calls `build_features(...)` on each, and
concatenates the column blocks into a single feature matrix.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd


@dataclass
class SourceContext:
    """Bundle of raw inputs that a SignalSource may consume.

    Sources only use the fields they care about. Extra fields (e.g., a NewsSource
    won't use ohlcv_1m) are simply ignored.
    """
    symbol: str
    eval_freq_minutes: int                       # 1 / 5 / 15 / 60 / 240 / 1440
    ohlcv_1m: pd.DataFrame | None = None
    ohlcv_eval: pd.DataFrame | None = None       # resampled to eval frequency
    ohlcv_by_tf: dict[str, pd.DataFrame] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)


def source_feature_prefix(name: str) -> str:
    """Standard prefix from source name; "pattern" → "pat_", "kr_flow" → "flow_" etc.
    Convention: lowercase short prefix + underscore."""
    return f"{name.lower()}_"


class SignalSource(ABC):
    """Abstract base for any feature-producing module.

    Required class attributes:
      - name: str           — short identifier ("pattern", "kr_flow", "binance_micro", ...)
      - feature_prefix: str — column-name prefix (must match `source_feature_prefix(name)`
                              by default, but subclasses may override).

    Optional:
      - requires: tuple of SourceContext field names that must be present.
                  Pipeline checks these before invocation.
    """

    name: ClassVar[str] = ""
    feature_prefix: ClassVar[str] = ""
    requires: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        # Auto-derive feature_prefix from name when not explicitly set on
        # THIS class. Checking cls.__dict__ (not the inherited attribute) means
        # a subclass overriding only `name` gets its own prefix rather than
        # silently inheriting the parent's — preventing column-collision bugs.
        if cls.name and "feature_prefix" not in cls.__dict__:
            cls.feature_prefix = source_feature_prefix(cls.name)

    @abstractmethod
    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        """Return DataFrame indexed by eval timestamps with prefixed columns.

        It is the source's responsibility to:
          1. Validate `ctx.requires` are present (else raise ValueError).
          2. Compute features look-ahead-safely.
          3. Prefix all output columns with `self.feature_prefix`.
        """
        raise NotImplementedError

    # ----- helpers for subclasses -----

    def _require(self, ctx: SourceContext, *fields: str) -> None:
        for f in fields:
            v = getattr(ctx, f, None)
            if v is None or (isinstance(v, (pd.DataFrame, pd.Series, dict)) and len(v) == 0):
                raise ValueError(f"{self.__class__.__name__}: required ctx.{f} is empty/None")

    def _prefixed(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out.columns = [
            c if c.startswith(self.feature_prefix) else f"{self.feature_prefix}{c}"
            for c in out.columns
        ]
        return out

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r}, prefix={self.feature_prefix!r})>"
