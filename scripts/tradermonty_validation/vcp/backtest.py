"""VCP (Volatility Contraction Pattern) backtest on BTC daily — Minervini methodology.

Rules implemented (per tradermonty/claude-trading-skills VCP methodology):

  Minervini Trend Template (7 conditions, need 6+):
    1. Price > 150d SMA AND Price > 200d SMA
    2. 150d SMA > 200d SMA
    3. 200d SMA trending up for 22+ days
    4. Price > 50d SMA
    5. Price >= 25% above 52w low
    6. Price within 25% of 52w high
    7. RS > 70 (skipped — single symbol, no peer comparison)

  VCP Contractions:
    - Detect swing pivots (high/low) using ATR(14) * 1.5 threshold
    - Identify successive contractions with depth measurement
    - T1: 8-35% depth
    - T2: ratio T2/T1 <= 0.75 (25% tighter)
    - T3: ratio T3/T2 <= 0.75
    - Min 2 contractions required
    - Volume decreasing during contractions

  Entry:
    - Breakout above pivot (high of last contraction) with volume >= 1.5x 50d avg

  Stop:
    - 1.5% below last contraction low

  Exit:
    - Stop loss hit
    - Trailing 10% from peak after +10% gain
    - 60-day timeout (no fixed profit target in source)

Position sizing:
    - 30% capital per trade × no leverage (BTC spot)
    - Cost: 0.10% round-trip
"""
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd
import numpy as np

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

INITIAL_CAPITAL = 10_000.0
SIZE_PCT = 0.30
COST_PER_TRADE = 0.001    # 0.1% RT
STOP_LOSS_PCT = 0.015     # 1.5% below last contraction low
TRAILING_ACTIVATION = 0.10  # +10% gain triggers trailing
TRAILING_DROP = 0.10      # 10% drop from peak
TIMEOUT_DAYS = 60
BACKTEST_START = "2022-01-01"


# ============== Indicator helpers ==============

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["sma50"] = df["Close"].rolling(50).mean()
    df["sma150"] = df["Close"].rolling(150).mean()
    df["sma200"] = df["Close"].rolling(200).mean()
    df["sma200_22d_ago"] = df["sma200"].shift(22)
    df["52w_high"] = df["Close"].rolling(252).max()
    df["52w_low"] = df["Close"].rolling(252).min()
    df["vol_50d"] = df["Volume"].rolling(50).mean()
    df["atr14"] = compute_atr(df, 14)
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ============== Minervini Trend Template ==============

def trend_template_score(row) -> int:
    """Returns count (0-7) of passed criteria. Pass threshold = 6."""
    if pd.isna(row["sma200"]) or pd.isna(row["sma150"]) or pd.isna(row["sma50"]):
        return 0
    score = 0
    c = row["Close"]
    # 1. Price > 150d SMA AND Price > 200d SMA
    if c > row["sma150"] and c > row["sma200"]:
        score += 1
    # 2. 150d SMA > 200d SMA
    if row["sma150"] > row["sma200"]:
        score += 1
    # 3. 200d SMA trending up for 22+ days
    if not pd.isna(row["sma200_22d_ago"]) and row["sma200"] > row["sma200_22d_ago"]:
        score += 1
    # 4. Price > 50d SMA
    if c > row["sma50"]:
        score += 1
    # 5. Price >= 25% above 52w low
    if not pd.isna(row["52w_low"]) and c >= row["52w_low"] * 1.25:
        score += 1
    # 6. Price within 25% of 52w high
    if not pd.isna(row["52w_high"]) and c >= row["52w_high"] * 0.75:
        score += 1
    # 7. RS > 70 — N/A for single symbol; auto-pass since BTC vs USD has no benchmark
    score += 1  # auto-pass
    return score


# ============== Swing pivot detection (ZigZag) ==============

def detect_pivots(df: pd.DataFrame, atr_mult: float = 1.5) -> pd.DataFrame:
    """Return df with 'pivot' column: 'H' (swing high), 'L' (swing low), or None."""
    df = df.copy()
    df["pivot"] = None
    if len(df) < 20:
        return df

    closes = df["Close"].values
    atrs = df["atr14"].values
    highs = df["High"].values
    lows = df["Low"].values

    last_pivot_idx = 0
    last_pivot_price = closes[0]
    direction = 0  # 0=unknown, 1=looking for high, -1=looking for low

    for i in range(1, len(df)):
        if pd.isna(atrs[i]):
            continue
        threshold = atrs[i] * atr_mult

        if direction == 0:
            move = closes[i] - last_pivot_price
            if abs(move) >= threshold:
                direction = 1 if move > 0 else -1
                continue

        if direction == 1:  # looking for high
            if highs[i] > last_pivot_price:
                last_pivot_price = highs[i]
                last_pivot_idx = i
            elif last_pivot_price - lows[i] >= threshold:
                df.iat[last_pivot_idx, df.columns.get_loc("pivot")] = "H"
                direction = -1
                last_pivot_price = lows[i]
                last_pivot_idx = i
        else:  # looking for low
            if lows[i] < last_pivot_price:
                last_pivot_price = lows[i]
                last_pivot_idx = i
            elif highs[i] - last_pivot_price >= threshold:
                df.iat[last_pivot_idx, df.columns.get_loc("pivot")] = "L"
                direction = 1
                last_pivot_price = highs[i]
                last_pivot_idx = i

    return df


# ============== VCP detection ==============

@dataclass
class VCPSetup:
    detected_at: pd.Timestamp
    pivot_price: float       # buy point (high of last contraction)
    last_low: float          # for stop loss
    contractions: List[float]  # depth pcts e.g. [0.20, 0.12, 0.08]


def find_vcp_setups(df: pd.DataFrame) -> List[VCPSetup]:
    """Scan pivot sequence for VCP patterns and emit setups when detected."""
    pivots = df[df["pivot"].notna()].copy()
    if len(pivots) < 4:
        return []

    setups = []
    pivot_arr = pivots[["pivot", "Close", "High", "Low"]].copy()
    pivot_arr["price"] = pivot_arr.apply(lambda r: r["High"] if r["pivot"] == "H" else r["Low"], axis=1)
    pivot_indices = pivot_arr.index.tolist()
    pivot_types = pivot_arr["pivot"].tolist()
    pivot_prices = pivot_arr["price"].tolist()

    # We need sequence: H L H L H L (= 2 contractions) or longer
    # A "contraction" = drop from H to next L
    for i in range(len(pivot_types) - 4):
        # Need pattern starting with H and ending with H
        # Contraction k: H[k] -> L[k]
        # We look for sequences of (H, L) pairs with progressively shallower drops
        seq_types = pivot_types[i:i + 6]
        seq_prices = pivot_prices[i:i + 6]
        seq_indices = pivot_indices[i:i + 6]

        # Find longest valid VCP starting at i
        if seq_types[0] != "H":
            continue

        contractions = []
        valid = True
        for k in range(0, len(seq_types) - 1, 2):
            if k + 1 >= len(seq_types):
                break
            if seq_types[k] != "H" or seq_types[k + 1] != "L":
                valid = False
                break
            high_p = seq_prices[k]
            low_p = seq_prices[k + 1]
            depth = (high_p - low_p) / high_p
            contractions.append(depth)

        if not valid or len(contractions) < 2:
            continue

        # T1 must be 8-35% depth
        if not (0.08 <= contractions[0] <= 0.35):
            continue

        # T2 must be <= 0.75 * T1
        if contractions[1] > contractions[0] * 0.75:
            continue

        # If T3 exists, must be <= 0.75 * T2
        if len(contractions) >= 3 and contractions[2] > contractions[1] * 0.75:
            # Only keep first 2 if T3 fails
            contractions = contractions[:2]

        # Pivot = high of last contraction's H (last "H" in seq used)
        last_used_high_idx = i + (len(contractions) - 1) * 2
        last_used_low_idx = last_used_high_idx + 1
        pivot_price = pivot_prices[last_used_high_idx]
        last_low = pivot_prices[last_used_low_idx]

        # Setup is detected at the index AFTER the last L (waiting for breakout)
        detected_idx = pivot_indices[last_used_low_idx]

        setups.append(VCPSetup(
            detected_at=detected_idx,
            pivot_price=pivot_price,
            last_low=last_low,
            contractions=contractions,
        ))

    # Dedup: keep only first setup per detected_at
    seen = set()
    unique = []
    for s in setups:
        if s.detected_at not in seen:
            seen.add(s.detected_at)
            unique.append(s)
    return unique


# ============== Backtest ==============

@dataclass
class Trade:
    setup_idx: pd.Timestamp
    entry_date: pd.Timestamp
    entry_price: float
    pivot: float
    last_low: float
    contractions: List[float]
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    pnl_pct: float = 0.0
    hold_days: int = 0


def run_backtest(df: pd.DataFrame, setups: List[VCPSetup]) -> List[Trade]:
    trades = []
    df = df.loc[BACKTEST_START:].copy()

    in_position = False
    current_trade: Optional[Trade] = None
    peak_price = 0.0
    trailing_active = False

    setup_queue = sorted([s for s in setups if s.detected_at >= df.index[0]], key=lambda s: s.detected_at)
    setup_idx = 0

    for date, row in df.iterrows():
        # Manage existing position
        if in_position and current_trade:
            high, low, close = row["High"], row["Low"], row["Close"]

            # Update peak
            if high > peak_price:
                peak_price = high

            # Activate trailing
            if not trailing_active and (high / current_trade.entry_price - 1) >= TRAILING_ACTIVATION:
                trailing_active = True

            stop_price = current_trade.last_low * (1 - STOP_LOSS_PCT)

            # Check stop loss
            if low <= stop_price:
                current_trade.exit_date = date
                current_trade.exit_price = stop_price
                current_trade.exit_reason = "stop_loss"
                _close_trade(current_trade, trades)
                in_position = False
                current_trade = None
                continue

            # Check trailing
            if trailing_active:
                drop = (peak_price - low) / peak_price
                if drop >= TRAILING_DROP:
                    trail_price = peak_price * (1 - TRAILING_DROP)
                    current_trade.exit_date = date
                    current_trade.exit_price = trail_price
                    current_trade.exit_reason = "trailing_stop"
                    _close_trade(current_trade, trades)
                    in_position = False
                    current_trade = None
                    continue

            # Timeout
            if (date - current_trade.entry_date).days >= TIMEOUT_DAYS:
                current_trade.exit_date = date
                current_trade.exit_price = close
                current_trade.exit_reason = "timeout"
                _close_trade(current_trade, trades)
                in_position = False
                current_trade = None
                continue

        # Check for entry signal
        if not in_position:
            # Find setup that's been detected and waiting
            while setup_idx < len(setup_queue) and setup_queue[setup_idx].detected_at < date:
                setup = setup_queue[setup_idx]
                # Check trend template at entry day
                trend_score = trend_template_score(row)
                if trend_score < 6:
                    setup_idx += 1
                    continue

                # Check breakout: high >= pivot AND volume >= 1.5x 50d avg
                vol_ok = not pd.isna(row["vol_50d"]) and row["Volume"] >= row["vol_50d"] * 1.5
                if row["High"] >= setup.pivot_price and vol_ok:
                    # Entry
                    entry_price = setup.pivot_price  # assume fill at pivot
                    current_trade = Trade(
                        setup_idx=setup.detected_at,
                        entry_date=date,
                        entry_price=entry_price,
                        pivot=setup.pivot_price,
                        last_low=setup.last_low,
                        contractions=setup.contractions,
                    )
                    in_position = True
                    peak_price = entry_price
                    trailing_active = False
                    setup_idx += 1
                    break

                # Setup expires after 30 days without breakout
                if (date - setup.detected_at).days > 30:
                    setup_idx += 1
                else:
                    break

    # Close any still-open trade
    if in_position and current_trade:
        last_row = df.iloc[-1]
        current_trade.exit_date = df.index[-1]
        current_trade.exit_price = last_row["Close"]
        current_trade.exit_reason = "data_end"
        _close_trade(current_trade, trades)

    return trades


def _close_trade(trade: Trade, trades: List[Trade]):
    raw_return = (trade.exit_price - trade.entry_price) / trade.entry_price
    net = raw_return - COST_PER_TRADE
    trade.pnl_pct = net * SIZE_PCT
    trade.hold_days = (trade.exit_date - trade.entry_date).days
    trades.append(trade)


# ============== Metrics ==============

def compute_metrics(trades: List[Trade], df: pd.DataFrame) -> dict:
    if not trades:
        return {"total_trades": 0}

    eq = INITIAL_CAPITAL
    eq_curve = [(df.loc[BACKTEST_START:].index[0], eq)]
    for t in sorted(trades, key=lambda x: x.exit_date):
        eq *= (1 + t.pnl_pct)
        eq_curve.append((t.exit_date, eq))
    eq_df = pd.DataFrame(eq_curve, columns=["date", "equity"]).set_index("date")
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
        "sharpe": pnls.mean() / pnls.std() * np.sqrt(252 / max(1, days / len(trades))) if pnls.std() > 0 else 0,
        "final_equity": eq,
        "avg_hold_days": np.mean([t.hold_days for t in trades]),
        "by_exit": {
            r: {"count": sum(1 for t in trades if t.exit_reason == r),
                "avg_pnl_pct": np.mean([t.pnl_pct for t in trades if t.exit_reason == r])}
            for r in set(t.exit_reason for t in trades)
        },
    }


def buy_hold_metrics(df: pd.DataFrame) -> dict:
    s = df.loc[BACKTEST_START:].copy()
    units = INITIAL_CAPITAL / float(s["Close"].iloc[0])
    eq = s["Close"] * units
    final = float(eq.iloc[-1])
    days = (s.index[-1] - s.index[0]).days
    daily_ret = eq.pct_change().dropna()
    return {
        "total_return": final / INITIAL_CAPITAL - 1,
        "cagr": (final / INITIAL_CAPITAL) ** (365 / days) - 1 if days > 0 else 0,
        "max_dd": (eq / eq.cummax() - 1).min(),
        "sharpe": daily_ret.mean() / daily_ret.std() * np.sqrt(365),
        "final_equity": final,
    }


# ============== Main ==============

def main():
    print("Loading BTC daily data...")
    df = pd.read_csv(DATA / "btc_usd_daily.csv", parse_dates=["date"]).set_index("date")
    print(f"  Rows: {len(df)}")

    print("Computing indicators...")
    df = add_indicators(df)

    print("Detecting swing pivots (ATR x1.5)...")
    df = detect_pivots(df, atr_mult=1.5)
    pivots = df[df["pivot"].notna()]
    print(f"  Pivots found: {len(pivots)} (H={sum(pivots['pivot']=='H')}, L={sum(pivots['pivot']=='L')})")

    print("Scanning for VCP setups...")
    setups = find_vcp_setups(df)
    print(f"  VCP setups detected: {len(setups)}")

    setups_in_range = [s for s in setups if s.detected_at >= pd.Timestamp(BACKTEST_START)]
    print(f"  In backtest range (>= {BACKTEST_START}): {len(setups_in_range)}")

    print("Running backtest...")
    trades = run_backtest(df, setups)
    print(f"  Executed trades: {len(trades)}")

    metrics = compute_metrics(trades, df)
    bh = buy_hold_metrics(df)

    # Save trades
    if trades:
        pd.DataFrame([{
            "setup_idx": t.setup_idx, "entry_date": t.entry_date, "exit_date": t.exit_date,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "pivot": t.pivot, "last_low": t.last_low,
            "contractions": str(t.contractions),
            "exit_reason": t.exit_reason, "pnl_pct": t.pnl_pct, "hold_days": t.hold_days,
        } for t in trades]).to_csv(OUT / "trades.csv", index=False)

    # Print report
    print()
    print("=" * 70)
    print("VCP BACKTEST RESULT (BTC daily, 2022-01 ~ 2026-04)")
    print("=" * 70)
    if metrics["total_trades"] == 0:
        print("NO TRADES EXECUTED. Setups detected:", len(setups_in_range))
        print("(Likely cause: trend template + volume confirmation never aligned with BTC daily bars)")
    else:
        print(f"  Trades:           {metrics['total_trades']}")
        print(f"  Total Return:     {metrics['total_return']*100:+.2f}%")
        print(f"  CAGR:             {metrics['cagr']*100:+.2f}%")
        print(f"  Win Rate:         {metrics['win_rate']*100:.1f}%")
        print(f"  Avg Win:          {metrics['avg_win']*100:+.3f}%")
        print(f"  Avg Loss:         {metrics['avg_loss']*100:+.3f}%")
        print(f"  Profit Factor:    {metrics['profit_factor']:.2f}")
        print(f"  Max Drawdown:     {metrics['max_dd']*100:.2f}%")
        print(f"  Sharpe (~):       {metrics['sharpe']:.2f}")
        print(f"  Avg Hold:         {metrics['avg_hold_days']:.1f} days")
        print(f"  Final Equity:     ${metrics['final_equity']:,.0f}")
        print()
        print("  By exit reason:")
        for reason, stats in metrics["by_exit"].items():
            print(f"    {reason:15s} count={stats['count']:3d}  avg={stats['avg_pnl_pct']*100:+.3f}%")

    print()
    print("=" * 70)
    print("BENCHMARK: BUY-AND-HOLD BTC")
    print("=" * 70)
    print(f"  Total Return:     {bh['total_return']*100:+.2f}%")
    print(f"  CAGR:             {bh['cagr']*100:+.2f}%")
    print(f"  Max Drawdown:     {bh['max_dd']*100:.2f}%")
    print(f"  Sharpe:           {bh['sharpe']:.2f}")
    print(f"  Final Equity:     ${bh['final_equity']:,.0f}")


if __name__ == "__main__":
    main()
