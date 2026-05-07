"""Event-driven backtester — fires one trade per FDR-active signal.

This complements the continuous-ensemble Backtester with the simpler
trade-per-signal model that exactly matches how the FitnessTensor was learned.

Semantics:
  1. For each signal whose (pattern, tf, regime, direction) is FDR-significant
     with positive edge_mean:
       - entry: NEXT TF bar's open after signal emission
       - exit:  TF bar at signal_position + horizon_bars (close)
       - SL:    intra-holding-period 1m bar low/high crosses configured pct
       - TP:    intra-holding-period 1m bar high/low crosses configured pct
  2. Multiple overlapping signals: take only the next non-overlapping one
     (single-position model — KR equity reality).

Why this exists in addition to the continuous Backtester:
The FitnessTensor was learned with "close[t+h] / close[t] - 1" on each signal's
own TF DataFrame. The continuous ensemble Backtester used wall-clock horizons,
which mis-mapped TF-bar counts (especially for KR equities with lunch break +
overnight gaps). This module respects TF-bar timing exactly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from app.pattern_fitness.types import FitnessTensor

from .types import BacktestResult, Trade

logger = logging.getLogger(__name__)


@dataclass
class EventBacktestConfig:
    """Per-trade behavior."""
    sl_pct: float = 0.020         # 2% stop-loss within holding window
    tp_pct: float = 0.040         # 4% take-profit within holding window
    use_intrabar_sl_tp: bool = True
    fee_rate: float = 0.00015
    size_pct: float = 0.95
    long_only: bool = True
    min_edge_pct: float = 0.0      # only trade signals whose fitness cell edge >= this
    min_n_in_cell: int = 30        # safety floor


class EventDrivenBacktester:
    def __init__(
        self,
        fitness: FitnessTensor,
        *,
        initial_capital: float = 1_000_000.0,
        config: EventBacktestConfig | None = None,
    ) -> None:
        self.fitness = fitness
        self.initial_capital = float(initial_capital)
        self.config = config or EventBacktestConfig()

    def run(
        self,
        *,
        symbol: str,
        ohlcv_1m: pd.DataFrame,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        signals_df: pd.DataFrame,
        regime_by_tf: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        cfg = self.config

        # Attach cell_id per signal (regime at signal time on its TF)
        sig = signals_df.copy()
        sig["timestamp"] = pd.to_datetime(sig["timestamp"])
        sig["cell_id"] = pd.NA
        for tf, gidx in sig.groupby("timeframe").groups.items():
            if tf not in regime_by_tf:
                continue
            rdf = regime_by_tf[tf]
            sub = sig.loc[gidx]
            mapped = rdf.reindex(sub["timestamp"].values)
            sig.loc[sub.index, "cell_id"] = mapped["cell_id"].values
        sig = sig.dropna(subset=["cell_id"])

        # Filter to active + positive-edge directional signals
        def _trustable(row):
            if cfg.long_only and row["direction"] != "bull":
                return False
            if row["direction"] not in ("bull", "bear"):
                return False
            cell = self.fitness.get(
                row["pattern_name"], row["timeframe"], str(row["cell_id"]), row["direction"]
            )
            if cell is None:
                return False
            if not cell.fdr_significant:
                return False
            if cell.edge_mean < cfg.min_edge_pct:
                return False
            if cell.n < cfg.min_n_in_cell:
                return False
            return True

        sig = sig[sig.apply(_trustable, axis=1)].sort_values("timestamp").reset_index(drop=True)

        bars_1m = ohlcv_1m.sort_index()

        capital = self.initial_capital
        trades: list[Trade] = []
        equity_curve: list[tuple[datetime, float]] = []
        position_open_until: Optional[pd.Timestamp] = None  # don't take new trades until this passes

        for i, row in sig.iterrows():
            tf = row["timeframe"]
            ts = row["timestamp"]
            tf_df = ohlcv_by_tf.get(tf)
            if tf_df is None or len(tf_df) == 0:
                continue
            pos_idx = tf_df.index.get_indexer([ts])
            pos = int(pos_idx[0])
            if pos < 0 or pos + 1 >= len(tf_df):
                continue
            exit_pos = pos + int(row["horizon_bars"])
            if exit_pos >= len(tf_df):
                continue

            entry_ts = tf_df.index[pos + 1]
            planned_exit_ts = tf_df.index[exit_pos]

            # skip overlapping with previous open trade
            if position_open_until is not None and entry_ts < position_open_until:
                continue

            entry_price = float(tf_df.iloc[pos + 1]["open"])
            qty = (capital * cfg.size_pct) / (entry_price * (1 + cfg.fee_rate))
            if qty <= 0:
                continue

            sl_price = entry_price * (1 - cfg.sl_pct) if row["direction"] == "bull" else entry_price * (1 + cfg.sl_pct)
            tp_price = entry_price * (1 + cfg.tp_pct) if row["direction"] == "bull" else entry_price * (1 - cfg.tp_pct)

            # walk the 1m bars between entry_ts and planned_exit_ts; check intrabar SL/TP
            window = bars_1m.loc[(bars_1m.index >= entry_ts) & (bars_1m.index <= planned_exit_ts)]
            exit_price = float(tf_df.iloc[exit_pos]["close"])
            exit_ts = planned_exit_ts
            exit_reason = "time"
            if cfg.use_intrabar_sl_tp and len(window):
                for ts_w, b in window.iterrows():
                    if row["direction"] == "bull":
                        if b["low"] <= sl_price:
                            exit_price, exit_ts, exit_reason = sl_price, ts_w, "sl"
                            break
                        if b["high"] >= tp_price:
                            exit_price, exit_ts, exit_reason = tp_price, ts_w, "tp"
                            break
                    else:
                        if b["high"] >= sl_price:
                            exit_price, exit_ts, exit_reason = sl_price, ts_w, "sl"
                            break
                        if b["low"] <= tp_price:
                            exit_price, exit_ts, exit_reason = tp_price, ts_w, "tp"
                            break

            # compute pnl
            entry_cash = qty * entry_price * (1 + cfg.fee_rate)
            exit_cash = qty * exit_price * (1 - cfg.fee_rate)
            capital_before = capital
            capital = capital - entry_cash + exit_cash
            ret = (capital - capital_before) / capital_before

            trades.append(Trade(
                entry_ts=entry_ts.to_pydatetime() if hasattr(entry_ts, "to_pydatetime") else entry_ts,
                exit_ts=exit_ts.to_pydatetime() if hasattr(exit_ts, "to_pydatetime") else exit_ts,
                side=("long" if row["direction"] == "bull" else "short"),
                entry_price=entry_price,
                exit_price=exit_price,
                qty=qty,
                return_pct=ret,
                exit_reason=exit_reason,  # type: ignore[arg-type]
                entry_score=0.0,
                contributing_patterns=(f"{row['pattern_name']}@{tf}",),
            ))
            position_open_until = exit_ts
            # equity sample at exit
            equity_curve.append((exit_ts.to_pydatetime() if hasattr(exit_ts, "to_pydatetime") else exit_ts, capital))

        result = BacktestResult(
            symbol=symbol,
            start=bars_1m.index[0].to_pydatetime(),
            end=bars_1m.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=capital,
            trades=trades,
            equity_curve=equity_curve,
        )
        self._compute_kpis(result)
        return result

    def _compute_kpis(self, r: BacktestResult) -> None:
        n = len(r.trades)
        r.n_trades = n
        if n == 0:
            r.total_return_pct = 0.0
            return
        rets = np.array([t.return_pct for t in r.trades])
        wins = rets[rets > 0]
        losses = rets[rets <= 0]
        r.win_rate = float(len(wins) / n)
        r.avg_win_pct = float(wins.mean()) if len(wins) else 0.0
        r.avg_loss_pct = float(losses.mean()) if len(losses) else 0.0
        gross_win = float(wins.sum())
        gross_loss = -float(losses.sum())
        r.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
        r.total_return_pct = (r.final_capital - r.initial_capital) / r.initial_capital
        if r.equity_curve:
            equity = np.array([e for _, e in r.equity_curve])
            peaks = np.maximum.accumulate(equity)
            dd = (peaks - equity) / peaks
            r.max_drawdown_pct = float(dd.max())
        if rets.std(ddof=1) > 0:
            sharpe = rets.mean() / rets.std(ddof=1)
            trades_per_year = n / max(1.0, (r.end - r.start).days / 365.0)
            r.sharpe_ratio = float(sharpe * np.sqrt(trades_per_year))
        bars_held = [(t.exit_ts - t.entry_ts).total_seconds() / 60.0 for t in r.trades]
        r.avg_holding_bars = float(np.mean(bars_held)) if bars_held else 0.0
        counts: dict[str, int] = {}
        for t in r.trades:
            counts[t.exit_reason] = counts.get(t.exit_reason, 0) + 1
        r.exit_reason_counts = counts
