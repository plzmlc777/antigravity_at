"""Shared dataclasses for the composer + backtester."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


DecisionAction = Literal["enter_long", "enter_short", "exit", "hold"]


@dataclass(frozen=True)
class ComposerDecision:
    """One bar's composer output."""
    timestamp: datetime
    action: DecisionAction
    ensemble_score: float           # net (bull_total - bear_total), magnitude indicates conviction
    bull_weight: float              # sum of trusted bull signal contributions
    bear_weight: float
    neutral_weight: float
    n_active_signals: int           # how many signals contributed
    n_trusted_signals: int          # how many had FDR-active fitness cells
    contributing_patterns: tuple[str, ...] = ()  # for interpretability logs
    suggested_target: float | None = None
    suggested_stop: float | None = None
    note: str = ""


@dataclass(frozen=True)
class Trade:
    """One round-trip in the backtest."""
    entry_ts: datetime
    exit_ts: datetime
    side: Literal["long", "short"]
    entry_price: float
    exit_price: float
    qty: float
    return_pct: float               # signed pct of capital invested
    exit_reason: Literal["tp", "sl", "time", "opposite_signal", "eod"]
    entry_score: float              # ensemble_score at entry
    contributing_patterns: tuple[str, ...] = ()


@dataclass
class BacktestResult:
    symbol: str
    start: datetime
    end: datetime
    initial_capital: float
    final_capital: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)

    # KPIs (filled by Backtester.compute_kpis())
    n_trades: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    avg_holding_bars: float = 0.0
    exit_reason_counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"Backtest — {self.symbol}\n"
            f"  window         : {self.start} → {self.end}\n"
            f"  capital        : {self.initial_capital:,.0f} → {self.final_capital:,.0f}\n"
            f"  total return   : {self.total_return_pct*100:+.2f}%\n"
            f"  trades         : {self.n_trades}\n"
            f"  win rate       : {self.win_rate*100:.1f}%\n"
            f"  avg win/loss   : {self.avg_win_pct*100:+.2f}% / {self.avg_loss_pct*100:+.2f}%\n"
            f"  profit factor  : {self.profit_factor:.2f}\n"
            f"  max drawdown   : {self.max_drawdown_pct*100:.2f}%\n"
            f"  sharpe         : {self.sharpe_ratio:.2f}\n"
            f"  avg holding    : {self.avg_holding_bars:.1f} bars\n"
            f"  exit reasons   : {self.exit_reason_counts}"
        )
