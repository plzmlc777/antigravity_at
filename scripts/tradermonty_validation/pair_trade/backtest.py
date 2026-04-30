"""Pair Trading backtest — BTC/ETH cointegration + z-score mean reversion.

Per tradermonty/claude-trading-skills pair-trade-screener rules:

  Cointegration test:
    - ADF on residuals (Engle-Granger)
    - p < 0.05 to enter pair as tradable
    - Re-test in rolling window

  Spread definition:
    - Spread = log(BTC) - β × log(ETH)
    - β from rolling OLS over 90-day window

  Entry:
    - z-score < -2.0 → LONG spread (long BTC, short ETH)
    - z-score > +2.0 → SHORT spread (short BTC, long ETH)

  Exit:
    - z-score crosses 0 (mean reversion) → close
    - |z| > 3.0 → stop loss (extreme divergence)
    - 90 days timeout

  Position sizing:
    - $5,000 long leg + $5,000 × β short leg (market neutral)
    - Effective capital used: 50% (long leg). Short leg margin separate.

  Costs:
    - 0.10% RT per leg → 0.20% total RT (4 trades per round trip — open long, open short, close both)
"""
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

INITIAL_CAPITAL = 10_000.0
LONG_LEG_DOLLARS = 5_000.0     # $5K long leg, $5K × β short leg
COST_PER_LEG_RT = 0.001        # 0.1% per leg per direction
ROLLING_WINDOW = 90
ENTRY_Z = 2.0
EXIT_Z = 0.0
STOP_Z = 3.0
TIMEOUT_DAYS = 90
COINT_PVAL_THRESHOLD = 0.05
BACKTEST_START = "2022-01-01"


@dataclass
class Trade:
    direction: str          # "long_spread" or "short_spread"
    entry_date: pd.Timestamp
    exit_date: Optional[pd.Timestamp] = None
    entry_z: float = 0.0
    exit_z: float = 0.0
    entry_btc: float = 0.0
    entry_eth: float = 0.0
    exit_btc: float = 0.0
    exit_eth: float = 0.0
    entry_beta: float = 0.0
    exit_reason: str = ""
    pnl_btc_leg: float = 0.0   # $ on BTC leg
    pnl_eth_leg: float = 0.0
    pnl_total: float = 0.0
    pnl_pct: float = 0.0       # vs initial capital
    hold_days: int = 0


def load() -> pd.DataFrame:
    btc = pd.read_csv(DATA / "btc_daily.csv", parse_dates=["date"]).set_index("date")
    eth = pd.read_csv(DATA / "eth_daily.csv", parse_dates=["date"]).set_index("date")
    df = pd.DataFrame({
        "btc_close": btc["Close"],
        "eth_close": eth["Close"],
    }).dropna()
    df["log_btc"] = np.log(df["btc_close"])
    df["log_eth"] = np.log(df["eth_close"])
    return df


def rolling_beta_and_spread(df: pd.DataFrame, window: int = 90) -> pd.DataFrame:
    """Compute rolling β and spread = log_btc - β * log_eth."""
    df = df.copy()
    betas = []
    spreads = []
    for i in range(len(df)):
        if i < window:
            betas.append(np.nan)
            spreads.append(np.nan)
            continue
        x = df["log_eth"].iloc[i - window:i].values
        y = df["log_btc"].iloc[i - window:i].values
        # OLS: y = a + b*x → β = cov(x,y)/var(x)
        b = np.cov(x, y, ddof=0)[0, 1] / np.var(x, ddof=0)
        a = y.mean() - b * x.mean()
        # Current spread (using current bar)
        spread_now = df["log_btc"].iloc[i] - (a + b * df["log_eth"].iloc[i])
        betas.append(b)
        spreads.append(spread_now)
    df["beta"] = betas
    df["spread"] = spreads
    df["spread_mean"] = df["spread"].rolling(window).mean()
    df["spread_std"] = df["spread"].rolling(window).std()
    df["zscore"] = (df["spread"] - df["spread_mean"]) / df["spread_std"]
    return df


def rolling_cointegration_pvalue(df: pd.DataFrame, window: int = 90) -> pd.Series:
    """Run rolling ADF test on the spread."""
    pvals = [np.nan] * len(df)
    for i in range(window * 2, len(df)):
        spreads = df["spread"].iloc[i - window:i].dropna()
        if len(spreads) < window * 0.8:
            continue
        try:
            adf_result = adfuller(spreads, autolag="AIC")
            pvals[i] = adf_result[1]
        except Exception:
            pvals[i] = np.nan
    return pd.Series(pvals, index=df.index)


def run_backtest(df: pd.DataFrame) -> List[Trade]:
    trades: List[Trade] = []
    df = df.loc[BACKTEST_START:].copy()
    in_position = False
    current: Optional[Trade] = None

    for date, row in df.iterrows():
        z = row["zscore"]
        coint_p = row["coint_pval"]
        beta = row["beta"]

        if pd.isna(z) or pd.isna(beta):
            continue

        # Manage open position
        if in_position and current:
            stop_hit = abs(z) > STOP_Z
            mean_revert = (
                (current.direction == "long_spread" and z >= EXIT_Z)
                or (current.direction == "short_spread" and z <= EXIT_Z)
            )
            timeout_hit = (date - current.entry_date).days >= TIMEOUT_DAYS

            if stop_hit or mean_revert or timeout_hit:
                current.exit_date = date
                current.exit_z = z
                current.exit_btc = row["btc_close"]
                current.exit_eth = row["eth_close"]
                current.exit_reason = (
                    "stop_loss" if stop_hit else
                    "mean_revert" if mean_revert else
                    "timeout"
                )

                # PnL calc (market-neutral pair)
                # Long spread = LONG BTC ($5K), SHORT ETH ($5K × entry_beta)
                # Short spread = SHORT BTC, LONG ETH
                btc_units = LONG_LEG_DOLLARS / current.entry_btc
                eth_units = (LONG_LEG_DOLLARS * current.entry_beta) / current.entry_eth
                btc_ret = (current.exit_btc - current.entry_btc) / current.entry_btc
                eth_ret = (current.exit_eth - current.entry_eth) / current.entry_eth

                if current.direction == "long_spread":
                    pnl_btc = btc_ret * LONG_LEG_DOLLARS
                    pnl_eth = -eth_ret * (LONG_LEG_DOLLARS * current.entry_beta)
                else:
                    pnl_btc = -btc_ret * LONG_LEG_DOLLARS
                    pnl_eth = eth_ret * (LONG_LEG_DOLLARS * current.entry_beta)

                # Costs: 4 fills (open both, close both)
                total_notional = LONG_LEG_DOLLARS + LONG_LEG_DOLLARS * current.entry_beta
                cost = total_notional * COST_PER_LEG_RT
                current.pnl_btc_leg = pnl_btc
                current.pnl_eth_leg = pnl_eth
                current.pnl_total = pnl_btc + pnl_eth - cost
                current.pnl_pct = current.pnl_total / INITIAL_CAPITAL
                current.hold_days = (current.exit_date - current.entry_date).days
                trades.append(current)
                in_position = False
                current = None
                continue

        # Entry scan
        if not in_position:
            # Cointegration filter
            if pd.isna(coint_p) or coint_p >= COINT_PVAL_THRESHOLD:
                continue

            if z <= -ENTRY_Z:
                # Long spread: long BTC, short ETH
                current = Trade(
                    direction="long_spread", entry_date=date, entry_z=z,
                    entry_btc=row["btc_close"], entry_eth=row["eth_close"],
                    entry_beta=beta,
                )
                in_position = True
            elif z >= ENTRY_Z:
                current = Trade(
                    direction="short_spread", entry_date=date, entry_z=z,
                    entry_btc=row["btc_close"], entry_eth=row["eth_close"],
                    entry_beta=beta,
                )
                in_position = True

    # Close any open trade at end
    if in_position and current:
        last = df.iloc[-1]
        current.exit_date = df.index[-1]
        current.exit_z = last["zscore"]
        current.exit_btc = last["btc_close"]
        current.exit_eth = last["eth_close"]
        btc_ret = (current.exit_btc - current.entry_btc) / current.entry_btc
        eth_ret = (current.exit_eth - current.entry_eth) / current.entry_eth
        if current.direction == "long_spread":
            pnl_btc = btc_ret * LONG_LEG_DOLLARS
            pnl_eth = -eth_ret * (LONG_LEG_DOLLARS * current.entry_beta)
        else:
            pnl_btc = -btc_ret * LONG_LEG_DOLLARS
            pnl_eth = eth_ret * (LONG_LEG_DOLLARS * current.entry_beta)
        cost = (LONG_LEG_DOLLARS + LONG_LEG_DOLLARS * current.entry_beta) * COST_PER_LEG_RT
        current.pnl_btc_leg = pnl_btc
        current.pnl_eth_leg = pnl_eth
        current.pnl_total = pnl_btc + pnl_eth - cost
        current.pnl_pct = current.pnl_total / INITIAL_CAPITAL
        current.hold_days = (current.exit_date - current.entry_date).days
        current.exit_reason = "data_end"
        trades.append(current)

    return trades


def metrics(trades: List[Trade], df: pd.DataFrame) -> dict:
    if not trades:
        return {"total_trades": 0}
    eq = INITIAL_CAPITAL
    pts = [(df.loc[BACKTEST_START:].index[0], eq)]
    for t in sorted(trades, key=lambda x: x.exit_date):
        eq += t.pnl_total
        pts.append((t.exit_date, eq))
    eq_df = pd.DataFrame(pts, columns=["date", "equity"]).set_index("date")
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
        "avg_hold": np.mean([t.hold_days for t in trades]),
        "final_equity": eq,
        "by_exit": {r: {"count": sum(1 for t in trades if t.exit_reason == r),
                        "avg_pnl_pct": np.mean([t.pnl_pct for t in trades if t.exit_reason == r])}
                    for r in set(t.exit_reason for t in trades)},
        "by_direction": {d: {"count": sum(1 for t in trades if t.direction == d),
                              "win_rate": np.mean([t.pnl_pct > 0 for t in trades if t.direction == d]),
                              "avg_pnl_pct": np.mean([t.pnl_pct for t in trades if t.direction == d])}
                          for d in set(t.direction for t in trades)},
    }


def main():
    print("Loading BTC + ETH data...")
    df = load()
    print(f"  Common days: {len(df)}")

    print("Computing rolling β + spread + z-score (90d window)...")
    df = rolling_beta_and_spread(df, ROLLING_WINDOW)

    print("Running rolling cointegration test (ADF)...")
    df["coint_pval"] = rolling_cointegration_pvalue(df, ROLLING_WINDOW)
    coint_pass_pct = (df["coint_pval"] < COINT_PVAL_THRESHOLD).mean() * 100
    print(f"  Cointegrated days (p<0.05): {coint_pass_pct:.1f}% of all days")

    print("Running backtest...")
    trades = run_backtest(df)
    print(f"  Trades: {len(trades)}")

    if trades:
        pd.DataFrame([{
            "direction": t.direction,
            "entry_date": t.entry_date, "exit_date": t.exit_date,
            "entry_z": t.entry_z, "exit_z": t.exit_z,
            "entry_btc": t.entry_btc, "entry_eth": t.entry_eth,
            "exit_btc": t.exit_btc, "exit_eth": t.exit_eth,
            "entry_beta": t.entry_beta,
            "exit_reason": t.exit_reason,
            "pnl_btc_leg": t.pnl_btc_leg, "pnl_eth_leg": t.pnl_eth_leg,
            "pnl_total": t.pnl_total, "pnl_pct": t.pnl_pct, "hold_days": t.hold_days,
        } for t in trades]).to_csv(OUT / "trades.csv", index=False)

    df_save = df.loc[BACKTEST_START:][["btc_close", "eth_close", "beta", "spread", "zscore", "coint_pval"]]
    df_save.to_csv(OUT / "spread_zscore.csv")

    m = metrics(trades, df)
    print()
    print("=" * 70)
    print("PAIR TRADE — BTC/ETH BACKTEST (2022-2026)")
    print("=" * 70)
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
        print(f"  Max Drawdown:     {m['max_dd']*100:.2f}%")
        print(f"  Avg Hold:         {m['avg_hold']:.1f} days")
        print(f"  Final Equity:     ${m['final_equity']:,.0f}")
        print()
        print("  By exit reason:")
        for r, st in m["by_exit"].items():
            print(f"    {r:14s}  count={st['count']:3d}  avg={st['avg_pnl_pct']*100:+.3f}%")
        print()
        print("  By direction:")
        for d, st in m["by_direction"].items():
            print(f"    {d:14s}  count={st['count']:3d}  win={st['win_rate']*100:5.1f}%  avg={st['avg_pnl_pct']*100:+.3f}%")


if __name__ == "__main__":
    main()
