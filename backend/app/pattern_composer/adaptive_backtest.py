"""Regime-adaptive composer (v5).

Switches between two modes based on the prevailing 1d regime:

  - macro_trending_up + positive momentum  →  HOLD mode (just be long; buy-hold style)
  - everything else                        →  DEFENSIVE mode (pattern-based exit/re-entry)

Rationale (from sweep findings):
  - Defensive timing crushes buy-hold on bear/sideways stocks (001210: -30% BH → +125%)
  - Defensive timing destroys buy-hold on bull stocks (005930: +304% BH → +13%)
  - Therefore: hold during macro uptrends, defensive otherwise.
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
class AdaptiveConfig:
    pressure_window_min: int = 60 * 24
    exit_threshold: int = 3
    enter_threshold: int = 0
    min_n_in_cell: int = 20
    fee_rate: float = 0.00015
    use_negative_edge_cells: bool = True
    # macro regime gating: which 1d regimes activate "hold" mode (no defensive exits)
    hold_trends: tuple[str, ...] = ("trending_up",)
    hold_momentums: tuple[str, ...] = ("positive",)
    # if 1d regime hasn't warmed up yet, default to defensive mode (safer)
    fallback_when_warmup: str = "defensive"


class RegimeAdaptiveBacktester:
    def __init__(
        self,
        fitness: FitnessTensor,
        *,
        initial_capital: float = 1_000_000.0,
        config: AdaptiveConfig | None = None,
    ) -> None:
        self.fitness = fitness
        self.initial_capital = float(initial_capital)
        self.config = config or AdaptiveConfig()

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

        # bear-pressure events (same as defensive)
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
            if cell is None or not cell.fdr_significant or cell.n < cfg.min_n_in_cell:
                continue
            is_bear = (row["direction"] == "bear" and cell.edge_mean > 0) or (
                cfg.use_negative_edge_cells and cell.edge_mean < 0
            )
            if is_bear:
                bear_events.append(pd.Timestamp(row["timestamp"]))
        be_arr = np.array([t.value for t in sorted(bear_events)])

        # Forward-fill 1d regime onto 1m index
        rdf_1d = regime_by_tf.get("1d", pd.DataFrame())
        if len(rdf_1d) > 0:
            rdf_1d = rdf_1d.copy()
            rdf_1d.index = pd.to_datetime(rdf_1d.index)
            mapped = rdf_1d.reindex(bars.index, method="ffill")
            macro_trend = mapped["trend"].fillna("sideways").to_numpy()
            macro_momentum = mapped["momentum"].fillna("neutral").to_numpy()
            macro_warmup = mapped["is_warmup"].fillna(True).to_numpy()
        else:
            n = len(bars)
            macro_trend = np.array(["sideways"] * n, dtype=object)
            macro_momentum = np.array(["neutral"] * n, dtype=object)
            macro_warmup = np.array([True] * n)

        cash = self.initial_capital
        qty = 0.0
        equity_curve: list[tuple[datetime, float]] = []
        trades: list[Trade] = []
        in_market = False
        entry_ts: Optional[pd.Timestamp] = None
        entry_price = 0.0

        # initial entry long
        first_open = float(bars.iloc[0]["open"])
        qty = (cash * 0.99) / (first_open * (1 + cfg.fee_rate))
        cash -= qty * first_open * (1 + cfg.fee_rate)
        in_market = True
        entry_ts = bars.index[0]
        entry_price = first_open

        win_ns = pd.Timedelta(minutes=cfg.pressure_window_min).value
        ts_arr = bars.index.to_numpy(dtype="datetime64[ns]").view("int64")

        for i in range(len(bars)):
            ts_ns = ts_arr[i]
            close = float(bars.iloc[i]["close"])
            o = float(bars.iloc[i]["open"])

            # Macro mode: hold or defensive?
            is_warmup = bool(macro_warmup[i])
            if is_warmup:
                mode_is_hold = (cfg.fallback_when_warmup == "hold")
            else:
                mode_is_hold = (
                    macro_trend[i] in cfg.hold_trends
                    and macro_momentum[i] in cfg.hold_momentums
                )

            if mode_is_hold:
                # In hold mode: just stay long. Re-enter if not in market.
                if not in_market:
                    qty_buy = (cash * 0.99) / (o * (1 + cfg.fee_rate))
                    if qty_buy > 0:
                        cash -= qty_buy * o * (1 + cfg.fee_rate)
                        qty = qty_buy
                        in_market = True
                        entry_ts = bars.index[i]
                        entry_price = o
            else:
                # Defensive mode: bear pressure-driven exit
                lo = ts_ns - win_ns
                count = int(np.searchsorted(be_arr, ts_ns, side="right")
                            - np.searchsorted(be_arr, lo, side="left"))
                if in_market and count >= cfg.exit_threshold:
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
                        contributing_patterns=("adaptive_defensive_exit",),
                    ))
                    qty = 0.0
                    in_market = False
                elif (not in_market) and count <= cfg.enter_threshold:
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
                contributing_patterns=("adaptive_eod",),
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
