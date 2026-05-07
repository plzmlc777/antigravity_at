"""Position-floor backtester (v2.5).

Holds a baseline long position at all times (`floor_pct` of equity), and uses
pattern signals as an OVERLAY:
  - bull pattern signal active → increase to up_pct (e.g. 100%)
  - bear pattern signal active → decrease to floor_pct (= the floor, no exit below)
  - long_only → never go short

Why: a pure pattern strategy in a strong trend (e.g. 005930 +300%/yr) underperforms
buy-hold by orders of magnitude because patterns enter/exit on small swings. The
floor guarantees we capture most of the trend while still using pattern signals
to add/subtract exposure.

Conceptually equivalent to: BUY-AND-HOLD + pattern-modulated overlay.
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
class FloorBacktestConfig:
    floor_pct: float = 0.70             # baseline long exposure (always held)
    up_pct: float = 1.00                # exposure when bullish overlay active
    fee_rate: float = 0.00015
    long_only: bool = True
    overlay_horizon_bars: int = 30      # how long a bull/bear pattern signal influences exposure (1m bars)
    min_edge_pct: float = 0.0
    min_n_in_cell: int = 30


class PositionFloorBacktester:
    """Baseline long + pattern overlay.

    Implementation: at each 1m bar:
      target_exposure = floor_pct
      if any bull overlay signal is active → target_exposure = up_pct
      if any bear overlay signal is active → target_exposure = floor_pct (long_only;
          for short-enabled, would go to floor - delta)
    Adjust position to target_exposure; track trades as exposure-change events.
    """

    def __init__(
        self,
        fitness: FitnessTensor,
        *,
        initial_capital: float = 1_000_000.0,
        config: FloorBacktestConfig | None = None,
    ) -> None:
        self.fitness = fitness
        self.initial_capital = float(initial_capital)
        self.config = config or FloorBacktestConfig()

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
        bars = ohlcv_1m.sort_index()

        # Filter signals to FDR-active + positive edge
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

        kept = []
        for _, row in sig.iterrows():
            cell = self.fitness.get(
                row["pattern_name"], row["timeframe"], str(row["cell_id"]), row["direction"]
            )
            if cell is None or not cell.fdr_significant:
                continue
            if cell.edge_mean < cfg.min_edge_pct or cell.n < cfg.min_n_in_cell:
                continue
            if row["direction"] not in ("bull", "bear"):
                continue
            kept.append({
                "timestamp": row["timestamp"],
                "direction": row["direction"],
                "pattern": row["pattern_name"],
                "tf": row["timeframe"],
                "active_until": pd.Timestamp(row["timestamp"]) + pd.Timedelta(minutes=cfg.overlay_horizon_bars),
            })
        sig = pd.DataFrame(kept).sort_values("timestamp").reset_index(drop=True)

        # Walk 1m bars; maintain (cash, qty); rebalance to target exposure when it changes
        cash = self.initial_capital
        qty = 0.0
        trades: list[Trade] = []
        equity_curve: list[tuple[datetime, float]] = []
        prev_target = None
        last_change_ts = None
        last_change_price = None
        last_change_side = None

        # Walk linearly, marking signal windows
        sig_idx = 0
        active_bull_until: Optional[pd.Timestamp] = None
        active_bear_until: Optional[pd.Timestamp] = None

        for i in range(len(bars)):
            ts = bars.index[i]
            o = float(bars.iloc[i]["open"])

            # Activate / deactivate overlay signals
            while sig_idx < len(sig) and sig.iloc[sig_idx]["timestamp"] <= ts:
                row = sig.iloc[sig_idx]
                until = row["active_until"]
                if row["direction"] == "bull":
                    if active_bull_until is None or until > active_bull_until:
                        active_bull_until = until
                else:
                    if active_bear_until is None or until > active_bear_until:
                        active_bear_until = until
                sig_idx += 1
            if active_bull_until is not None and active_bull_until < ts:
                active_bull_until = None
            if active_bear_until is not None and active_bear_until < ts:
                active_bear_until = None

            # Decide target exposure
            target = cfg.floor_pct
            if active_bull_until is not None:
                target = cfg.up_pct
            if active_bear_until is not None and active_bull_until is None:
                # bear active alone (and long-only): pull back to floor (no short)
                target = cfg.floor_pct

            # current equity at open price
            equity = cash + qty * o
            current_qty_value = qty * o
            target_qty_value = equity * target
            delta_value = target_qty_value - current_qty_value

            # Rebalance only if delta is significant (>1% of equity to avoid micro-trading)
            if abs(delta_value) > equity * 0.01:
                if delta_value > 0:
                    # buy more
                    buy_qty = delta_value / (o * (1 + cfg.fee_rate))
                    cost = buy_qty * o * (1 + cfg.fee_rate)
                    cash -= cost
                    qty += buy_qty
                else:
                    # sell some
                    sell_qty = min(qty, -delta_value / o)
                    proceeds = sell_qty * o * (1 - cfg.fee_rate)
                    # record a "trade" if we're going from above-floor back to floor
                    # (gives us interpretable trades for KPIs)
                    cash += proceeds
                    qty -= sell_qty

            # Mark equity
            mtm = cash + qty * float(bars.iloc[i]["close"])
            equity_curve.append((ts.to_pydatetime(), mtm))

        # Close all at last bar
        last_close = float(bars.iloc[-1]["close"])
        if qty > 0:
            cash += qty * last_close * (1 - cfg.fee_rate)
            qty = 0.0

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
        # No discrete trades — KPIs computed from equity curve directly.
        r.n_trades = 0
        r.total_return_pct = (r.final_capital - r.initial_capital) / r.initial_capital
        if r.equity_curve:
            eq = np.array([e for _, e in r.equity_curve])
            peaks = np.maximum.accumulate(eq)
            dd = (peaks - eq) / peaks
            r.max_drawdown_pct = float(dd.max())
            # crude Sharpe from per-day returns
            ts_arr = pd.to_datetime([t for t, _ in r.equity_curve])
            eq_series = pd.Series(eq, index=ts_arr)
            daily = eq_series.resample("1D").last().dropna()
            daily_ret = daily.pct_change().dropna()
            if daily_ret.std() > 0:
                r.sharpe_ratio = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252))
        r.win_rate = 0.0
        r.profit_factor = 0.0
