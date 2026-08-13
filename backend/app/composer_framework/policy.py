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

from .rules import FULL_FRACTION, MARKET_OPEN, FillRule, SizingRule


ActionKind = Literal[
    "enter_long", "enter_short", "exit", "hold",
]


@dataclass(frozen=True)
class Action:
    """정책이 정본에 내리는 지시.

    2026-08-13 확장 — 네 필드가 늘었다. **전부 기본값이 현행 동작과 같다.**
    기존 정책은 한 줄도 바꾸지 않아도 되고, 골든/파리티가 그대로 통과하는 것이
    행동 변경 0 의 증거다.
    """

    kind: ActionKind
    sl_price: float | None = None
    tp_price: float | None = None
    # 얼마나 들어가는가 / 어떻게 체결되는가 — 전략마다 실제로 달라지는 두 축을
    # 다형 규칙으로 뺐다(rules.py). 정본은 호출만 하고 분기하지 않는다.
    sizing: SizingRule = FULL_FRACTION      # 기본 = 설정 상한 전량 (현행)
    fill: FillRule = MARKET_OPEN            # 기본 = 그 바 시가 시장가 (현행)
    # 청산 비율 — 보유 수량 대비. 1.0 = 전량(현행).
    # 0 < exit_frac < 1 이면 부분 청산이고, 남은 수량은 진입가·보유바수를 잇는다.
    exit_frac: float = 1.0
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


class LifecycleDecayEarlyExitPolicy(TradingPolicy):
    """Lifecycle short paradigm with vol-cliff-gated early exit.

    Pair with `bn_lifecycle_decay_early_exit` source (or any source that
    emits prediction ∈ {-1.0, +1.0}). Unlike LongShortThresholdPolicy this
    policy EVALUATES the prediction even while in position — a +exit_signal
    triggers an early flat-out.

    State machine:
      flat  + prediction <= -entry_threshold     → enter_short
      short + prediction >= +exit_signal_thresh  → exit (decay invalidated)
      short + bars_held >= max_hold_bars         → exit (time stop)
      else                                       → hold

    Long-side intentionally disabled — the lifecycle paradigm only shorts.
    A persistent +signal after exit (source emits +1.0 across the entire
    post-checkday window) is benign: flat + positive prediction does NOT
    trigger any long entry.
    """

    def __init__(
        self,
        *,
        entry_threshold: float = 0.5,
        exit_signal_threshold: float = 0.5,
        sl_pct: float = 0.50,
        tp_pct: float = 1.0,
        max_hold_bars: int = 30,
    ) -> None:
        self.entry_threshold = float(entry_threshold)
        self.exit_signal_threshold = float(exit_signal_threshold)
        self.sl_pct = float(sl_pct)
        self.tp_pct = float(tp_pct)
        self.max_hold_bars = int(max_hold_bars)

    def decide(self, c: PolicyContext) -> Action:
        if c.in_position and c.side == "short":
            if c.bars_held >= self.max_hold_bars:
                return Action.exit_("time")
            if not np.isnan(c.prediction) and c.prediction >= self.exit_signal_threshold:
                return Action.exit_("vol_cliff_invalidated")
            return Action.hold()
        if c.in_position and c.side == "long":
            return Action.exit_("policy_no_long")
        if not c.in_position and not np.isnan(c.prediction):
            if c.prediction <= -self.entry_threshold:
                return Action(
                    kind="enter_short",
                    sl_price=c.open_price * (1 + self.sl_pct),
                    tp_price=c.open_price * (1 - self.tp_pct) if self.tp_pct < 1.0 else 0.0,
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
