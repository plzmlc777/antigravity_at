"""Backtester — walks 1m bars, applies a DynamicPatternComposer, simulates
single-position long-only (KR equities) trading, and reports KPIs.

Design:
  - Pre-compute the "active signals" set at every 1m bar by expanding each
    signal across its horizon span on its own TF, then mapping back to 1m.
  - Walk 1m bars: when flat, ask composer for entry; when in position, manage
    exits (SL / TP / time stop / opposite signal).
  - Trade-by-trade equity curve.

Look-ahead safety:
  - A signal emitted at bar t (TF close) is only considered active for the
    NEXT 1m bar onward (not the same bar that emitted it). This matches the
    "trade on next bar's open" convention used during fitness learning.
  - Entry executes at the next bar's open, not the current bar's close.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from app.pattern_fitness.types import FitnessTensor
from app.pattern_scanner.types import TF_TO_PANDAS_FREQ

from .composer import ComposerConfig, DynamicPatternComposer
from .types import BacktestResult, ComposerDecision, Trade

logger = logging.getLogger(__name__)


def _tf_to_minutes(tf: str) -> int:
    """Convert TF string to minute count for horizon expansion on the 1m grid."""
    return {
        "1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 60 * 24,
    }[tf]


@dataclass
class _PositionState:
    side: str           # "long" | "short"
    entry_ts: datetime
    entry_price: float
    qty: float
    bars_held: int = 0
    entry_score: float = 0.0
    contributing: tuple[str, ...] = ()
    sl_price: float = 0.0
    tp_price: float = 0.0


class Backtester:
    """Drive a DynamicPatternComposer over historical 1m bars."""

    def __init__(
        self,
        composer: DynamicPatternComposer,
        *,
        initial_capital: float = 1_000_000.0,
        size_pct: float = 0.95,
        fee_rate: float = 0.00015,  # KR side default (very rough; not commission-tuned)
    ) -> None:
        self.composer = composer
        self.initial_capital = float(initial_capital)
        self.size_pct = float(size_pct)
        self.fee_rate = float(fee_rate)

    # ─────────────────────────────────────── helpers

    def _build_active_signal_index(
        self,
        signals_df: pd.DataFrame,
        regime_by_tf: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """Attach cell_id (regime at signal emit) and per-signal expiry timestamp.

        Returns a frame ready for fast time-window lookup."""
        if len(signals_df) == 0:
            return signals_df.copy()
        df = signals_df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # attach cell_id per TF (reindex regime DF onto signal timestamps)
        df["cell_id"] = pd.NA
        for tf, group_idx in df.groupby("timeframe").groups.items():
            if tf not in regime_by_tf:
                continue
            rdf = regime_by_tf[tf]
            sub = df.loc[group_idx]
            mapped = rdf.reindex(sub["timestamp"].values)
            df.loc[sub.index, "cell_id"] = mapped["cell_id"].values

        # per-signal expiry on 1m grid
        def _expiry(row):
            tf_min = _tf_to_minutes(row["timeframe"])
            return row["timestamp"] + timedelta(minutes=tf_min * int(row["horizon_bars"]))

        df["expiry_ts"] = df.apply(_expiry, axis=1)
        # signals become "active" 1 minute after emission (next-bar entry rule)
        df["active_from"] = df["timestamp"] + pd.Timedelta(minutes=1)
        return df.sort_values("active_from").reset_index(drop=True)

    def _active_at(self, signals_df: pd.DataFrame, ts: pd.Timestamp) -> pd.DataFrame:
        """Slice the active signals at moment ts."""
        return signals_df[(signals_df["active_from"] <= ts) & (signals_df["expiry_ts"] >= ts)]

    # ─────────────────────────────────────── main loop

    def run(
        self,
        *,
        symbol: str,
        ohlcv_1m: pd.DataFrame,
        signals_df: pd.DataFrame,
        regime_by_tf: dict[str, pd.DataFrame],
        eval_freq_minutes: int = 5,
    ) -> BacktestResult:
        """Walk 1m bars, evaluate composer every `eval_freq_minutes`, simulate trades."""
        cfg = self.composer.config

        bars = ohlcv_1m.copy()
        bars.index = pd.to_datetime(bars.index)
        bars = bars.sort_index()

        sig = self._build_active_signal_index(signals_df, regime_by_tf)

        capital = self.initial_capital
        position: Optional[_PositionState] = None
        equity_curve: list[tuple[datetime, float]] = []
        trades: list[Trade] = []
        cooldown_until: Optional[pd.Timestamp] = None

        eval_step = max(1, int(eval_freq_minutes))
        for i in range(len(bars)):
            ts = bars.index[i]
            row = bars.iloc[i]
            price = float(row["open"])  # entry/exit at open

            # mark-to-market: cash + qty*current_price (cash already had
            # qty*entry_price*(1+fee) deducted at entry).
            mtm = capital
            if position is not None:
                mtm = capital + position.qty * price
            equity_curve.append((ts.to_pydatetime(), mtm))

            # exit checks first (priority: SL/TP intrabar, then time-stop, then opposite signal)
            if position is not None:
                # intrabar high/low check using current bar's high/low
                bar_high = float(row["high"])
                bar_low = float(row["low"])
                exit_reason = None
                exit_price = price

                if position.side == "long":
                    if bar_low <= position.sl_price:
                        exit_reason = "sl"
                        exit_price = position.sl_price
                    elif bar_high >= position.tp_price:
                        exit_reason = "tp"
                        exit_price = position.tp_price

                if exit_reason is None and position.bars_held >= cfg.time_stop_bars:
                    exit_reason = "time"
                    exit_price = price

                if exit_reason is None and (i % eval_step == 0):
                    active = self._active_at(sig, ts)
                    decision = self.composer.compose(timestamp=ts, active_signals=active)
                    if self.composer.should_exit(decision.ensemble_score, position.side):
                        exit_reason = "opposite_signal"
                        exit_price = price

                if exit_reason:
                    pnl_pct, capital = self._close_position(
                        position, exit_price, capital, exit_reason, ts, trades
                    )
                    cooldown_until = ts + pd.Timedelta(minutes=cfg.cooldown_bars)
                    position = None
                else:
                    position.bars_held += 1
                    continue

            # entry checks
            if position is None and (cooldown_until is None or ts >= cooldown_until):
                if i % eval_step != 0:
                    continue
                active = self._active_at(sig, ts)
                if len(active) == 0:
                    continue
                decision = self.composer.compose(timestamp=ts, active_signals=active)
                if decision.action == "enter_long":
                    sl = price * (1 - cfg.sl_pct)
                    tp = price * (1 + cfg.tp_pct)
                    qty = (capital * self.size_pct) / (price * (1 + self.fee_rate))
                    qty = max(0.0, qty)
                    if qty > 0:
                        position = _PositionState(
                            side="long",
                            entry_ts=ts.to_pydatetime(),
                            entry_price=price,
                            qty=qty,
                            entry_score=decision.ensemble_score,
                            contributing=decision.contributing_patterns,
                            sl_price=sl,
                            tp_price=tp,
                        )
                        capital -= qty * price * (1 + self.fee_rate)

        # close any open position at last bar (EOD)
        if position is not None:
            last_ts = bars.index[-1]
            last_price = float(bars.iloc[-1]["close"])
            _, capital = self._close_position(position, last_price, capital, "eod", last_ts, trades)

        result = BacktestResult(
            symbol=symbol,
            start=bars.index[0].to_pydatetime(),
            end=bars.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=capital,
            trades=trades,
            equity_curve=equity_curve,
        )
        self._compute_kpis(result)
        return result

    # ─────────────────────────────────────── exit helper

    def _close_position(
        self,
        pos: _PositionState,
        exit_price: float,
        capital: float,
        reason: str,
        ts: pd.Timestamp,
        trades: list[Trade],
    ) -> tuple[float, float]:
        gross = pos.qty * exit_price
        fee = gross * self.fee_rate
        capital += gross - fee
        if pos.side == "long":
            ret = (exit_price - pos.entry_price) / pos.entry_price - 2 * self.fee_rate
        else:
            ret = (pos.entry_price - exit_price) / pos.entry_price - 2 * self.fee_rate
        trades.append(Trade(
            entry_ts=pos.entry_ts,
            exit_ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty=pos.qty,
            return_pct=ret,
            exit_reason=reason,  # type: ignore[arg-type]
            entry_score=pos.entry_score,
            contributing_patterns=pos.contributing,
        ))
        return ret, capital

    # ─────────────────────────────────────── KPIs

    def _compute_kpis(self, r: BacktestResult) -> None:
        n = len(r.trades)
        r.n_trades = n
        if n == 0:
            r.total_return_pct = (r.final_capital - r.initial_capital) / r.initial_capital
            return

        rets = np.array([t.return_pct for t in r.trades])
        wins = rets[rets > 0]
        losses = rets[rets <= 0]

        r.win_rate = float(len(wins) / n) if n else 0.0
        r.avg_win_pct = float(wins.mean()) if len(wins) else 0.0
        r.avg_loss_pct = float(losses.mean()) if len(losses) else 0.0
        gross_win = float(wins.sum())
        gross_loss = -float(losses.sum())
        r.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
        r.total_return_pct = (r.final_capital - r.initial_capital) / r.initial_capital

        # max drawdown on equity curve
        if r.equity_curve:
            equity = np.array([e for _, e in r.equity_curve])
            peaks = np.maximum.accumulate(equity)
            dd = (peaks - equity) / peaks
            r.max_drawdown_pct = float(dd.max())
        else:
            r.max_drawdown_pct = 0.0

        # crude Sharpe on per-trade returns (annualized assuming ~250 days)
        if rets.std(ddof=1) > 0:
            sharpe = rets.mean() / rets.std(ddof=1)
            # rough annualization: scale by sqrt(trades_per_year)
            trades_per_year = n / max(1.0, (r.end - r.start).days / 365.0)
            r.sharpe_ratio = float(sharpe * np.sqrt(trades_per_year))
        else:
            r.sharpe_ratio = 0.0

        bars_held = []
        for t in r.trades:
            delta = (t.exit_ts - t.entry_ts).total_seconds() / 60.0
            bars_held.append(delta)
        r.avg_holding_bars = float(np.mean(bars_held)) if bars_held else 0.0

        counts: dict[str, int] = {}
        for t in r.trades:
            counts[t.exit_reason] = counts.get(t.exit_reason, 0) + 1
        r.exit_reason_counts = counts
