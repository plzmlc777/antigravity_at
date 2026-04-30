"""Breakout Trade Planner backtest — Minervini-style breakout execution on VCP setups.

Per tradermonty/claude-trading-skills breakout-trade-planner rules:

  Reuses VCP setup detection (Minervini Trend Template + contractions)

  Differences from pure VCP backtest:
    - Entry zone: pivot ~ pivot + 2% (max chase)
    - Stop: 1.0% below last contraction low (tighter than VCP's 1.5%)
    - Exit: 2R profit target (Risk × 2) — fixed, no trailing
    - Time stop: 60-day timeout

  Risk = entry_price - stop_price
  Target = entry_price + 2 * Risk
"""
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
import sys

# Reuse VCP detection code
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vcp"))
from backtest import (  # type: ignore
    add_indicators, detect_pivots, find_vcp_setups, trend_template_score,
    VCPSetup, INITIAL_CAPITAL, SIZE_PCT, COST_PER_TRADE,
)

import pandas as pd
import numpy as np

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

STOP_BUFFER_PCT = 0.010      # 1.0% below last contraction low
MAX_CHASE_PCT = 0.020        # 2% above pivot — won't enter beyond
PROFIT_R_MULTIPLE = 2.0      # 2R target
TIMEOUT_DAYS = 60
BACKTEST_START = "2022-01-01"


@dataclass
class Trade:
    setup_idx: pd.Timestamp
    entry_date: pd.Timestamp
    entry_price: float
    pivot: float
    last_low: float
    stop_price: float
    target_price: float
    contractions: list
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    pnl_pct: float = 0.0
    hold_days: int = 0
    r_multiple: float = 0.0


def run_backtest(df: pd.DataFrame, setups: List[VCPSetup]) -> List[Trade]:
    trades = []
    df = df.loc[BACKTEST_START:].copy()
    in_position = False
    current: Optional[Trade] = None

    queue = sorted([s for s in setups if s.detected_at >= df.index[0]], key=lambda s: s.detected_at)
    qi = 0

    for date, row in df.iterrows():
        # Manage open position
        if in_position and current:
            high, low, close = row["High"], row["Low"], row["Close"]

            # Stop loss
            if low <= current.stop_price:
                current.exit_date = date
                current.exit_price = current.stop_price
                current.exit_reason = "stop_loss"
                _close(current, trades)
                in_position = False
                current = None
                continue

            # Profit target (2R)
            if high >= current.target_price:
                current.exit_date = date
                current.exit_price = current.target_price
                current.exit_reason = "target_2r"
                _close(current, trades)
                in_position = False
                current = None
                continue

            # Timeout
            if (date - current.entry_date).days >= TIMEOUT_DAYS:
                current.exit_date = date
                current.exit_price = close
                current.exit_reason = "timeout"
                _close(current, trades)
                in_position = False
                current = None
                continue

        # Entry scan
        if not in_position:
            while qi < len(queue) and queue[qi].detected_at < date:
                setup = queue[qi]

                # Trend template at entry day
                if trend_template_score(row) < 6:
                    qi += 1
                    continue

                # Volume confirmation: 1.5x 50d avg
                vol_ok = (not pd.isna(row["vol_50d"])) and row["Volume"] >= row["vol_50d"] * 1.5
                # Breakout: high crossed pivot during the day
                broke = row["High"] >= setup.pivot_price
                # Chase limit: open price not more than 2% above pivot (avoid late entry)
                chase_ok = row["Open"] <= setup.pivot_price * (1 + MAX_CHASE_PCT)

                if broke and vol_ok and chase_ok:
                    entry = setup.pivot_price
                    stop = setup.last_low * (1 - STOP_BUFFER_PCT)
                    risk = entry - stop
                    if risk <= 0:
                        qi += 1
                        continue
                    target = entry + risk * PROFIT_R_MULTIPLE

                    current = Trade(
                        setup_idx=setup.detected_at,
                        entry_date=date,
                        entry_price=entry,
                        pivot=setup.pivot_price,
                        last_low=setup.last_low,
                        stop_price=stop,
                        target_price=target,
                        contractions=setup.contractions,
                    )
                    in_position = True
                    qi += 1
                    break

                # Setup expires after 30d
                if (date - setup.detected_at).days > 30:
                    qi += 1
                else:
                    break

    if in_position and current:
        last = df.iloc[-1]
        current.exit_date = df.index[-1]
        current.exit_price = float(last["Close"])
        current.exit_reason = "data_end"
        _close(current, trades)

    return trades


def _close(t: Trade, trades: List[Trade]):
    raw = (t.exit_price - t.entry_price) / t.entry_price
    net = raw - COST_PER_TRADE
    t.pnl_pct = net * SIZE_PCT
    t.hold_days = (t.exit_date - t.entry_date).days
    risk = t.entry_price - t.stop_price
    t.r_multiple = (t.exit_price - t.entry_price) / risk if risk > 0 else 0
    trades.append(t)


def metrics(trades: List[Trade], df: pd.DataFrame) -> dict:
    if not trades:
        return {"total_trades": 0}
    eq = INITIAL_CAPITAL
    eq_pts = [(df.loc[BACKTEST_START:].index[0], eq)]
    for t in sorted(trades, key=lambda x: x.exit_date):
        eq *= (1 + t.pnl_pct)
        eq_pts.append((t.exit_date, eq))
    eq_df = pd.DataFrame(eq_pts, columns=["date", "equity"]).set_index("date")
    eq_df["dd"] = eq_df["equity"] / eq_df["equity"].cummax() - 1
    pnls = pd.Series([t.pnl_pct for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    days = (eq_df.index[-1] - eq_df.index[0]).days
    return {
        "total_trades": len(trades),
        "total_return": eq / INITIAL_CAPITAL - 1,
        "cagr": (eq / INITIAL_CAPITAL) ** (365 / days) - 1 if days > 0 else 0,
        "win_rate": (pnls > 0).mean(),
        "avg_win": wins.mean() if len(wins) else 0,
        "avg_loss": losses.mean() if len(losses) else 0,
        "profit_factor": abs(wins.sum() / losses.sum()) if len(losses) else float("inf"),
        "max_dd": eq_df["dd"].min(),
        "avg_r": np.mean([t.r_multiple for t in trades]),
        "final_equity": eq,
        "avg_hold": np.mean([t.hold_days for t in trades]),
        "by_exit": {r: {"count": sum(1 for t in trades if t.exit_reason == r),
                        "avg_pnl_pct": np.mean([t.pnl_pct for t in trades if t.exit_reason == r]),
                        "avg_r": np.mean([t.r_multiple for t in trades if t.exit_reason == r])}
                    for r in set(t.exit_reason for t in trades)},
    }


def buy_hold(df: pd.DataFrame) -> dict:
    s = df.loc[BACKTEST_START:].copy()
    units = INITIAL_CAPITAL / float(s["Close"].iloc[0])
    eq = s["Close"] * units
    days = (s.index[-1] - s.index[0]).days
    return {
        "total_return": float(eq.iloc[-1]) / INITIAL_CAPITAL - 1,
        "cagr": (float(eq.iloc[-1]) / INITIAL_CAPITAL) ** (365 / days) - 1 if days > 0 else 0,
        "max_dd": float((eq / eq.cummax() - 1).min()),
        "final_equity": float(eq.iloc[-1]),
    }


def main():
    print("Loading BTC daily...")
    df = pd.read_csv(DATA / "btc_usd_daily.csv", parse_dates=["date"]).set_index("date")
    df = add_indicators(df)
    df = detect_pivots(df, atr_mult=1.5)
    setups = find_vcp_setups(df)
    in_range = [s for s in setups if s.detected_at >= pd.Timestamp(BACKTEST_START)]
    print(f"  VCP setups in range: {len(in_range)}")

    trades = run_backtest(df, setups)
    print(f"  Trades: {len(trades)}")

    if trades:
        pd.DataFrame([{
            "setup_idx": t.setup_idx, "entry_date": t.entry_date, "exit_date": t.exit_date,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "stop_price": t.stop_price, "target_price": t.target_price,
            "exit_reason": t.exit_reason, "pnl_pct": t.pnl_pct, "hold_days": t.hold_days,
            "r_multiple": t.r_multiple,
        } for t in trades]).to_csv(OUT / "trades.csv", index=False)

    m = metrics(trades, df)
    bh = buy_hold(df)

    print()
    print("=" * 70)
    print("BREAKOUT TRADE PLANNER — BACKTEST (BTC daily, 2022-2026)")
    print("=" * 70)
    print("  Rule variant: stop=1% below low, target=2R, max chase=2%")
    print()
    if m["total_trades"] == 0:
        print("  NO TRADES.")
    else:
        print(f"  Trades:           {m['total_trades']}")
        print(f"  Total Return:     {m['total_return']*100:+.2f}%")
        print(f"  CAGR:             {m['cagr']*100:+.2f}%")
        print(f"  Win Rate:         {m['win_rate']*100:.1f}%")
        print(f"  Avg Win:          {m['avg_win']*100:+.3f}%")
        print(f"  Avg Loss:         {m['avg_loss']*100:+.3f}%")
        print(f"  Profit Factor:    {m['profit_factor']:.2f}")
        print(f"  Avg R-multiple:   {m['avg_r']:+.2f}")
        print(f"  Max Drawdown:     {m['max_dd']*100:.2f}%")
        print(f"  Avg Hold:         {m['avg_hold']:.1f} days")
        print(f"  Final Equity:     ${m['final_equity']:,.0f}")
        print()
        print("  By exit reason:")
        for r, st in m["by_exit"].items():
            print(f"    {r:12s}  count={st['count']:3d}  avg={st['avg_pnl_pct']*100:+.3f}%  avg_R={st['avg_r']:+.2f}")
    print()
    print("=" * 70)
    print("BENCHMARK: BUY-AND-HOLD")
    print("=" * 70)
    print(f"  Total Return:     {bh['total_return']*100:+.2f}%")
    print(f"  CAGR:             {bh['cagr']*100:+.2f}%")
    print(f"  Max Drawdown:     {bh['max_dd']*100:.2f}%")
    print(f"  Final Equity:     ${bh['final_equity']:,.0f}")


if __name__ == "__main__":
    main()
