"""Defensive-timing backtester (v4).

Treats patterns as a RISK SWITCH rather than an alpha source:
  - Default: 100% long (buy-and-hold base case)
  - Compute rolling "bear pressure" from FDR-active negative-edge signals
    AND bear-direction positive-edge cells:
       count of bear/negative signals in past `pressure_window_min` minutes
  - If bear pressure > threshold → exit to cash
  - When pressure drops back below threshold → re-enter long

The hope: patterns can predict drawdowns even when they can't predict alpha.
By dodging the 25% drawdown of 005930 (Mar-Apr 2026), we'd outperform buy-hold.
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
class DefensiveConfig:
    pressure_window_min: int = 60 * 24       # 1 trading day in minutes
    enter_threshold: int = 0                 # default: enter (low/no bear pressure)
    exit_threshold: int = 5                   # exit when ≥ N bear pressure events recently
    min_n_in_cell: int = 20
    fee_rate: float = 0.00015
    use_neutral_signals_as_risk: bool = False  # neutral vol_climax can also be risk warning
    use_negative_edge_cells: bool = True       # cells with edge < 0 are real bear signals
    require_fdr: bool = True


class DefensiveTimingBacktester:
    """Buy-hold by default; exit when pattern-based bear pressure spikes."""

    def __init__(
        self,
        fitness: FitnessTensor,
        *,
        initial_capital: float = 1_000_000.0,
        config: DefensiveConfig | None = None,
    ) -> None:
        self.fitness = fitness
        self.initial_capital = float(initial_capital)
        self.config = config or DefensiveConfig()

    def run(
        self,
        *,
        symbol: str,
        ohlcv_1m: pd.DataFrame,
        signals_df: pd.DataFrame,
        regime_by_tf: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        cfg = self.config
        bars = ohlcv_1m.sort_index()

        # Build "bear pressure events": signals whose fitness cell is bear-active
        # OR whose fitness cell has negative edge (mean-reversion warning)
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

        bear_events: list[pd.Timestamp] = []
        for _, row in sig.iterrows():
            cell = self.fitness.get(
                row["pattern_name"], row["timeframe"], str(row["cell_id"]), row["direction"]
            )
            if cell is None:
                continue
            if cfg.require_fdr and not cell.fdr_significant:
                continue
            if cell.n < cfg.min_n_in_cell:
                continue
            is_bear_signal = (
                row["direction"] == "bear" and cell.edge_mean > 0
            ) or (
                cfg.use_negative_edge_cells and cell.edge_mean < 0
            ) or (
                cfg.use_neutral_signals_as_risk and row["direction"] == "neutral"
            )
            if is_bear_signal:
                bear_events.append(pd.Timestamp(row["timestamp"]))

        bear_events_sorted = sorted(bear_events)
        be_arr = np.array([t.value for t in bear_events_sorted])

        # Walk 1m bars; maintain (cash, qty); rebalance on threshold cross
        cash = self.initial_capital
        qty = 0.0
        equity_curve: list[tuple[datetime, float]] = []
        trades: list[Trade] = []
        in_market = False
        entry_ts: Optional[pd.Timestamp] = None
        entry_price = 0.0

        win_ns = pd.Timedelta(minutes=cfg.pressure_window_min).value
        ts_arr = bars.index.to_numpy(dtype="datetime64[ns]").view("int64")

        # initial entry: long
        first_open = float(bars.iloc[0]["open"])
        qty = (cash * 0.99) / (first_open * (1 + cfg.fee_rate))
        cash -= qty * first_open * (1 + cfg.fee_rate)
        in_market = True
        entry_ts = bars.index[0]
        entry_price = first_open

        for i in range(len(bars)):
            ts_ns = ts_arr[i]
            close = float(bars.iloc[i]["close"])
            o = float(bars.iloc[i]["open"])

            # bear pressure in [ts - window, ts]
            lo = ts_ns - win_ns
            count = int(np.searchsorted(be_arr, ts_ns, side="right") - np.searchsorted(be_arr, lo, side="left"))

            # State machine
            if in_market and count >= cfg.exit_threshold:
                # exit
                proceeds = qty * o * (1 - cfg.fee_rate)
                cost_basis = qty * entry_price * (1 + cfg.fee_rate)
                cash += proceeds
                trades.append(Trade(
                    entry_ts=entry_ts.to_pydatetime() if hasattr(entry_ts, "to_pydatetime") else entry_ts,
                    exit_ts=bars.index[i].to_pydatetime() if hasattr(bars.index[i], "to_pydatetime") else bars.index[i],
                    side="long",
                    entry_price=entry_price, exit_price=o, qty=qty,
                    return_pct=(proceeds - cost_basis) / cost_basis,
                    exit_reason="opposite_signal",
                    entry_score=0.0,
                    contributing_patterns=("defensive_exit",),
                ))
                qty = 0.0
                in_market = False
            elif (not in_market) and count <= cfg.enter_threshold:
                # re-enter
                qty_buy = (cash * 0.99) / (o * (1 + cfg.fee_rate))
                if qty_buy > 0:
                    cash -= qty_buy * o * (1 + cfg.fee_rate)
                    qty = qty_buy
                    in_market = True
                    entry_ts = bars.index[i]
                    entry_price = o

            mtm = cash + qty * close
            equity_curve.append((bars.index[i].to_pydatetime() if hasattr(bars.index[i], "to_pydatetime") else bars.index[i], mtm))

        # close at last bar
        if in_market:
            last_close = float(bars.iloc[-1]["close"])
            proceeds = qty * last_close * (1 - cfg.fee_rate)
            cost_basis = qty * entry_price * (1 + cfg.fee_rate)
            cash += proceeds
            trades.append(Trade(
                entry_ts=entry_ts.to_pydatetime() if hasattr(entry_ts, "to_pydatetime") else entry_ts,
                exit_ts=bars.index[-1].to_pydatetime() if hasattr(bars.index[-1], "to_pydatetime") else bars.index[-1],
                side="long",
                entry_price=entry_price, exit_price=last_close, qty=qty,
                return_pct=(proceeds - cost_basis) / cost_basis,
                exit_reason="eod",
                entry_score=0.0,
                contributing_patterns=("defensive_eod",),
            ))

        result = BacktestResult(
            symbol=symbol,
            start=bars.index[0].to_pydatetime(),
            end=bars.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=cash,
            trades=trades,
            equity_curve=equity_curve,
        )
        self._compute_kpis(result)
        return result

    def _compute_kpis(self, r: BacktestResult) -> None:
        n = len(r.trades)
        r.n_trades = n
        r.total_return_pct = (r.final_capital - r.initial_capital) / r.initial_capital
        if r.equity_curve:
            eq = np.array([e for _, e in r.equity_curve])
            peaks = np.maximum.accumulate(eq)
            dd = (peaks - eq) / peaks
            r.max_drawdown_pct = float(dd.max())
        if n:
            rets = np.array([t.return_pct for t in r.trades])
            r.win_rate = float((rets > 0).mean())
            wins = rets[rets > 0]; losses = rets[rets <= 0]
            r.avg_win_pct = float(wins.mean()) if len(wins) else 0.0
            r.avg_loss_pct = float(losses.mean()) if len(losses) else 0.0
            gw = float(wins.sum()); gl = -float(losses.sum())
            r.profit_factor = (gw / gl) if gl > 0 else float("inf") if gw > 0 else 0.0
            ts_arr = pd.to_datetime([t for t, _ in r.equity_curve])
            eq_series = pd.Series([e for _, e in r.equity_curve], index=ts_arr)
            daily = eq_series.resample("1D").last().dropna()
            dret = daily.pct_change().dropna()
            if dret.std() > 0:
                r.sharpe_ratio = float(dret.mean() / dret.std() * np.sqrt(252))
        counts: dict[str, int] = {}
        for t in r.trades:
            counts[t.exit_reason] = counts.get(t.exit_reason, 0) + 1
        r.exit_reason_counts = counts
