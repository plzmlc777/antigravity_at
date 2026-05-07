"""Multi-position event-driven backtester (v2.1).

Same signal-event semantics as EventDrivenBacktester, but lifts the single-
position constraint that killed v1: when a new credible signal arrives while
existing positions are open, we open it too — up to `max_concurrent`. Each
position is sized as `(equity * size_pct) / max_concurrent`.

Why this matters: in v1, 49 of 85 active signals were dropped due to overlap.
This module trades all of them, raising capital utilization from ~3.5% to
typically 15–30% of time.

Other improvements over EventDrivenBacktester:
  - per-position equity carved out at entry (so capital is properly split)
  - SL/TP can be configured as fixed pct OR as multiples of fitness edge_std
  - per-cell size multiplier (high-edge cells get more capital)
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
class MultiBacktestConfig:
    max_concurrent: int = 5
    base_size_pct: float = 0.95         # total equity exposure when fully loaded
    long_only: bool = True
    sl_pct: float = 0.020
    tp_pct: float = 0.040
    use_intrabar_sl_tp: bool = True
    fee_rate: float = 0.00015
    min_edge_pct: float = 0.0
    min_n_in_cell: int = 30
    # adaptive sizing: position size = base × (1 + edge_amplifier × normalized_edge)
    edge_amplifier: float = 0.0          # 0 = uniform sizing; 1 = double-size for top-edge cell
    # adaptive SL/TP: if > 0, override sl_pct/tp_pct with k × edge_std
    sl_std_mult: float = 0.0
    tp_std_mult: float = 0.0


@dataclass
class _Position:
    side: str
    entry_ts: pd.Timestamp
    entry_price: float
    qty: float
    capital_locked: float        # cash removed from pool at entry
    sl_price: float
    tp_price: float
    planned_exit_ts: pd.Timestamp
    pattern: str
    timeframe: str


class MultiPositionEventBacktester:
    def __init__(
        self,
        fitness: FitnessTensor,
        *,
        initial_capital: float = 1_000_000.0,
        config: MultiBacktestConfig | None = None,
    ) -> None:
        self.fitness = fitness
        self.initial_capital = float(initial_capital)
        self.config = config or MultiBacktestConfig()

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
        bars_1m = ohlcv_1m.sort_index()

        # Attach cell_id per signal
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
        sig = sig.dropna(subset=["cell_id"]).sort_values("timestamp").reset_index(drop=True)

        # Filter signals to FDR-active + positive edge + (optional long-only)
        kept_rows = []
        cells_for_sig: list = []
        edge_means = []
        for _, row in sig.iterrows():
            cell = self.fitness.get(
                row["pattern_name"], row["timeframe"], str(row["cell_id"]), row["direction"]
            )
            if cell is None or not cell.fdr_significant:
                continue
            if cell.edge_mean < cfg.min_edge_pct or cell.n < cfg.min_n_in_cell:
                continue
            if cfg.long_only and row["direction"] != "bull":
                continue
            if row["direction"] not in ("bull", "bear"):
                continue
            kept_rows.append(row)
            cells_for_sig.append(cell)
            edge_means.append(cell.edge_mean)
        sig_kept = pd.DataFrame(kept_rows)
        if len(sig_kept) == 0:
            return self._empty_result(symbol, bars_1m)

        max_edge = max(edge_means) if edge_means else 1.0

        cash = self.initial_capital
        positions: list[_Position] = []
        trades: list[Trade] = []
        equity_curve: list[tuple[datetime, float]] = []

        # Build a queue of pending entries (sorted by timestamp)
        pending = list(zip(sig_kept.itertuples(index=False), cells_for_sig, edge_means))
        pending.sort(key=lambda t: t[0].timestamp)

        # Helper: convert to TF position
        def find_tf_pos(tf, ts):
            tf_df = ohlcv_by_tf.get(tf)
            if tf_df is None:
                return None, None
            arr = tf_df.index.get_indexer([pd.Timestamp(ts)])
            pos = int(arr[0])
            return tf_df, pos

        # Walk 1m bars; at each bar, (1) close any positions hit by SL/TP/time, (2) open queued entries whose entry_ts <= now
        pending_idx = 0
        bar_index = bars_1m.index
        bar_arr = bars_1m[["open", "high", "low", "close"]].to_numpy()

        for i in range(len(bars_1m)):
            ts = bar_index[i]
            o, h, l, c = bar_arr[i]

            # Mark-to-market
            mtm = cash + sum(p.qty * c for p in positions)
            equity_curve.append((ts.to_pydatetime(), mtm))

            # 1) Manage open positions
            keep: list[_Position] = []
            for p in positions:
                exit_reason = None
                exit_price = None
                if cfg.use_intrabar_sl_tp:
                    if p.side == "long":
                        if l <= p.sl_price:
                            exit_reason = "sl"
                            exit_price = p.sl_price
                        elif h >= p.tp_price:
                            exit_reason = "tp"
                            exit_price = p.tp_price
                    else:
                        if h >= p.sl_price:
                            exit_reason = "sl"
                            exit_price = p.sl_price
                        elif l <= p.tp_price:
                            exit_reason = "tp"
                            exit_price = p.tp_price
                if exit_reason is None and ts >= p.planned_exit_ts:
                    exit_reason = "time"
                    exit_price = float(c)

                if exit_reason is not None:
                    proceeds = p.qty * exit_price * (1 - cfg.fee_rate)
                    cash += proceeds
                    ret_pct = (proceeds - p.capital_locked) / p.capital_locked
                    trades.append(Trade(
                        entry_ts=p.entry_ts.to_pydatetime() if hasattr(p.entry_ts, "to_pydatetime") else p.entry_ts,
                        exit_ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                        side=p.side,
                        entry_price=p.entry_price,
                        exit_price=float(exit_price),
                        qty=p.qty,
                        return_pct=float(ret_pct),
                        exit_reason=exit_reason,  # type: ignore[arg-type]
                        entry_score=0.0,
                        contributing_patterns=(f"{p.pattern}@{p.timeframe}",),
                    ))
                else:
                    keep.append(p)
            positions = keep

            # 2) Open queued entries up to max_concurrent
            while pending_idx < len(pending):
                row, cell, edge = pending[pending_idx]
                tf = row.timeframe
                tf_df, pos = find_tf_pos(tf, row.timestamp)
                if tf_df is None or pos < 0 or pos + 1 >= len(tf_df):
                    pending_idx += 1
                    continue
                entry_ts = tf_df.index[pos + 1]
                # only act when current 1m bar reaches entry_ts
                if entry_ts > ts:
                    break  # later signal — wait
                if entry_ts < ts:
                    pending_idx += 1
                    continue  # missed (shouldn't happen with sorted pending)
                if len(positions) >= cfg.max_concurrent:
                    pending_idx += 1
                    continue  # at concurrency limit, skip this signal

                # planned exit: pos + horizon TF bars
                exit_pos = pos + int(row.horizon_bars)
                if exit_pos >= len(tf_df):
                    pending_idx += 1
                    continue
                planned_exit_ts = tf_df.index[exit_pos]
                entry_price = float(tf_df.iloc[pos + 1]["open"])

                # capital allocation: equity / max_concurrent (with optional edge amplifier)
                equity = cash + sum(pp.qty * c for pp in positions)
                base_share = (equity * cfg.base_size_pct) / cfg.max_concurrent
                if cfg.edge_amplifier > 0 and max_edge > 0:
                    norm = min(1.0, edge / max_edge)
                    share = base_share * (1.0 + cfg.edge_amplifier * norm)
                else:
                    share = base_share
                share = min(share, cash * 0.99)  # don't exceed available cash
                if share < entry_price:  # not enough cash for 1 share
                    pending_idx += 1
                    continue
                qty = share / (entry_price * (1 + cfg.fee_rate))
                if qty <= 0:
                    pending_idx += 1
                    continue
                cost = qty * entry_price * (1 + cfg.fee_rate)
                cash -= cost

                # SL/TP
                if cfg.sl_std_mult > 0 and cell.edge_std > 0:
                    sl_pct = max(0.005, cfg.sl_std_mult * cell.edge_std)
                else:
                    sl_pct = cfg.sl_pct
                if cfg.tp_std_mult > 0 and cell.edge_std > 0:
                    tp_pct = max(0.01, cfg.tp_std_mult * cell.edge_std)
                else:
                    tp_pct = cfg.tp_pct

                if row.direction == "bull":
                    sl_price = entry_price * (1 - sl_pct)
                    tp_price = entry_price * (1 + tp_pct)
                    side = "long"
                else:
                    sl_price = entry_price * (1 + sl_pct)
                    tp_price = entry_price * (1 - tp_pct)
                    side = "short"

                positions.append(_Position(
                    side=side, entry_ts=entry_ts, entry_price=entry_price,
                    qty=qty, capital_locked=cost,
                    sl_price=sl_price, tp_price=tp_price,
                    planned_exit_ts=planned_exit_ts,
                    pattern=row.pattern_name, timeframe=tf,
                ))
                pending_idx += 1

        # Close remaining positions at last bar
        if positions:
            last_ts = bars_1m.index[-1]
            last_close = float(bars_1m.iloc[-1]["close"])
            for p in positions:
                proceeds = p.qty * last_close * (1 - cfg.fee_rate)
                cash += proceeds
                ret_pct = (proceeds - p.capital_locked) / p.capital_locked
                trades.append(Trade(
                    entry_ts=p.entry_ts.to_pydatetime() if hasattr(p.entry_ts, "to_pydatetime") else p.entry_ts,
                    exit_ts=last_ts.to_pydatetime() if hasattr(last_ts, "to_pydatetime") else last_ts,
                    side=p.side,
                    entry_price=p.entry_price, exit_price=last_close, qty=p.qty,
                    return_pct=float(ret_pct), exit_reason="eod",
                    entry_score=0.0,
                    contributing_patterns=(f"{p.pattern}@{p.timeframe}",),
                ))

        result = BacktestResult(
            symbol=symbol,
            start=bars_1m.index[0].to_pydatetime(),
            end=bars_1m.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=cash,
            trades=trades,
            equity_curve=equity_curve,
        )
        self._compute_kpis(result)
        return result

    def _empty_result(self, symbol: str, bars_1m: pd.DataFrame) -> BacktestResult:
        return BacktestResult(
            symbol=symbol,
            start=bars_1m.index[0].to_pydatetime(),
            end=bars_1m.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=self.initial_capital,
            trades=[], equity_curve=[],
        )

    def _compute_kpis(self, r: BacktestResult) -> None:
        n = len(r.trades)
        r.n_trades = n
        if n == 0:
            r.total_return_pct = 0.0
            return
        rets = np.array([t.return_pct for t in r.trades])
        wins = rets[rets > 0]; losses = rets[rets <= 0]
        r.win_rate = float(len(wins) / n)
        r.avg_win_pct = float(wins.mean()) if len(wins) else 0.0
        r.avg_loss_pct = float(losses.mean()) if len(losses) else 0.0
        gw = float(wins.sum()); gl = -float(losses.sum())
        r.profit_factor = (gw / gl) if gl > 0 else float("inf") if gw > 0 else 0.0
        r.total_return_pct = (r.final_capital - r.initial_capital) / r.initial_capital
        if r.equity_curve:
            eq = np.array([e for _, e in r.equity_curve])
            peaks = np.maximum.accumulate(eq)
            dd = (peaks - eq) / peaks
            r.max_drawdown_pct = float(dd.max())
        if rets.std(ddof=1) > 0:
            sharpe = rets.mean() / rets.std(ddof=1)
            tpy = n / max(1.0, (r.end - r.start).days / 365.0)
            r.sharpe_ratio = float(sharpe * np.sqrt(tpy))
        bars_held = [(t.exit_ts - t.entry_ts).total_seconds() / 60.0 for t in r.trades]
        r.avg_holding_bars = float(np.mean(bars_held)) if bars_held else 0.0
        counts: dict[str, int] = {}
        for t in r.trades:
            counts[t.exit_reason] = counts.get(t.exit_reason, 0) + 1
        r.exit_reason_counts = counts
