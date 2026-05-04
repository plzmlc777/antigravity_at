"""
TradingPolicy ABC — turns model predictions into trade actions.

Policies are STATELESS w.r.t. predictions: each call sees current prediction +
position state and returns an action. The Backtester owns the state.

Concrete policies provided:
  - LongOnlyThresholdPolicy: enter long when pred > entry_threshold,
    exit on SL/TP/time-stop.
  - LongShortThresholdPolicy: same + symmetric short side.

Extending: implement `decide(...)` for richer behavior (Kelly sizing,
volatility-targeting, regime-conditional, pyramiding, etc.).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np


ActionKind = Literal[
    "enter_long", "enter_short", "exit", "hold",
]


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    sl_price: float | None = None
    tp_price: float | None = None
    note: str = ""

    @classmethod
    def hold(cls) -> "Action":
        return cls(kind="hold")

    @classmethod
    def exit_(cls, note: str = "") -> "Action":
        return cls(kind="exit", note=note)


@dataclass
class PolicyContext:
    """State passed to TradingPolicy.decide()."""
    timestamp: datetime
    prediction: float          # composer output for this bar (NaN if not predicted yet)
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    in_position: bool
    side: Literal["long", "short", "flat"]
    entry_price: float = 0.0
    bars_held: int = 0


class TradingPolicy(ABC):
    @abstractmethod
    def decide(self, ctx: PolicyContext) -> Action:
        raise NotImplementedError


# ─────────────────────────────────────── concrete policies ───


class LongOnlyThresholdPolicy(TradingPolicy):
    """Enter long when prediction > entry_threshold; exit on SL/TP/time."""

    def __init__(
        self,
        *,
        entry_threshold: float = 0.005,
        sl_pct: float = 0.04,
        tp_pct: float = 0.10,
        max_hold_bars: int = 5,
    ) -> None:
        self.entry_threshold = float(entry_threshold)
        self.sl_pct = float(sl_pct)
        self.tp_pct = float(tp_pct)
        self.max_hold_bars = int(max_hold_bars)

    def decide(self, c: PolicyContext) -> Action:
        if c.in_position and c.side == "long":
            # exits checked by Backtester via SL/TP price levels (set at entry)
            # but we also support time-stop here
            if c.bars_held >= self.max_hold_bars:
                return Action.exit_("time")
            return Action.hold()
        if c.in_position and c.side == "short":
            return Action.exit_("policy_no_short")
        if not c.in_position and not np.isnan(c.prediction):
            if c.prediction > self.entry_threshold:
                sl = c.open_price * (1 - self.sl_pct)
                tp = c.open_price * (1 + self.tp_pct)
                return Action(kind="enter_long", sl_price=sl, tp_price=tp)
        return Action.hold()


class LongShortThresholdPolicy(TradingPolicy):
    """Symmetric long+short policy."""

    def __init__(
        self,
        *,
        entry_threshold: float = 0.005,
        sl_pct: float = 0.04,
        tp_pct: float = 0.10,
        max_hold_bars: int = 5,
    ) -> None:
        self.entry_threshold = float(entry_threshold)
        self.sl_pct = float(sl_pct)
        self.tp_pct = float(tp_pct)
        self.max_hold_bars = int(max_hold_bars)

    def decide(self, c: PolicyContext) -> Action:
        if c.in_position:
            if c.bars_held >= self.max_hold_bars:
                return Action.exit_("time")
            return Action.hold()
        if not np.isnan(c.prediction):
            if c.prediction > self.entry_threshold:
                return Action(
                    kind="enter_long",
                    sl_price=c.open_price * (1 - self.sl_pct),
                    tp_price=c.open_price * (1 + self.tp_pct),
                )
            if c.prediction < -self.entry_threshold:
                return Action(
                    kind="enter_short",
                    sl_price=c.open_price * (1 + self.sl_pct),
                    tp_price=c.open_price * (1 - self.tp_pct),
                )
        return Action.hold()


class FundingReversalPolicy(TradingPolicy):
    """Mean-reversal policy designed for funding-rate z-score signals.

    Combine with `NegationPassthroughComposer` (prediction = -z):
      - prediction > +entry_threshold (z << -entry_threshold) → enter LONG
      - prediction < -entry_threshold (z >> +entry_threshold) → enter SHORT
      - exit when |prediction| < exit_threshold (z near 0 — mean reverted)
      - timeout after max_hold_bars
      - SL via sl_pct (no TP — exit-at-mean handles take-profit naturally).
    """

    def __init__(
        self,
        *,
        entry_threshold: float = 2.5,
        exit_threshold: float = 0.5,
        sl_pct: float = 0.03,
        max_hold_bars: int = 7,
    ) -> None:
        self.entry_threshold = float(entry_threshold)
        self.exit_threshold = float(exit_threshold)
        self.sl_pct = float(sl_pct)
        self.max_hold_bars = int(max_hold_bars)

    def decide(self, c: PolicyContext) -> Action:
        if c.in_position:
            if c.bars_held >= self.max_hold_bars:
                return Action.exit_("time")
            # mean-reversion exit: prediction (= -z) approaching 0 → spread closed
            if not np.isnan(c.prediction) and abs(c.prediction) < self.exit_threshold:
                return Action.exit_("mean")
            return Action.hold()
        if not np.isnan(c.prediction):
            if c.prediction > self.entry_threshold:
                # tp sentinel: 100x entry — effectively unreachable (mean-reversal
                # exits via z-near-zero before any tp would matter)
                return Action(
                    kind="enter_long",
                    sl_price=c.open_price * (1 - self.sl_pct),
                    tp_price=c.open_price * 100.0,
                )
            if c.prediction < -self.entry_threshold:
                # tp sentinel: 0 — short never triggers (low > 0 always)
                return Action(
                    kind="enter_short",
                    sl_price=c.open_price * (1 + self.sl_pct),
                    tp_price=0.0,
                )
        return Action.hold()
