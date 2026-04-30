"""Plot VCP equity curve vs Buy-and-Hold."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "output"

INITIAL = 10000.0
SIZE_PCT = 0.30


def main():
    spot = pd.read_csv(DATA / "btc_usd_daily.csv", parse_dates=["date"]).set_index("date").loc["2022-01-01":]
    trades = pd.read_csv(OUT / "trades.csv", parse_dates=["entry_date", "exit_date"])

    # VCP equity (compound)
    eq = INITIAL
    eq_pts = [(spot.index[0], eq)]
    for _, t in trades.sort_values("exit_date").iterrows():
        eq *= (1 + t["pnl_pct"])
        eq_pts.append((t["exit_date"], eq))
    vcp_eq = pd.DataFrame(eq_pts, columns=["date", "equity"]).set_index("date")

    # Forward-fill VCP equity to daily
    vcp_daily = vcp_eq.reindex(spot.index, method="ffill").fillna(INITIAL)

    # B&H equity
    bh_units = INITIAL / float(spot["Close"].iloc[0])
    bh_eq = spot["Close"] * bh_units

    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True,
                              gridspec_kw={"height_ratios": [3, 1]})

    # Equity curves
    axes[0].plot(vcp_daily.index, vcp_daily["equity"], label="VCP Strategy", color="steelblue", linewidth=1.8)
    axes[0].plot(bh_eq.index, bh_eq.values, label="Buy-and-Hold BTC", color="orange", linewidth=1.2, alpha=0.75)
    axes[0].axhline(INITIAL, color="gray", linestyle="--", alpha=0.4, label="Initial $10K")
    # Mark trade entries/exits
    for _, t in trades.iterrows():
        color = "green" if t["pnl_pct"] > 0 else "red"
        axes[0].axvspan(t["entry_date"], t["exit_date"], alpha=0.15, color=color)
    axes[0].set_ylabel("Equity ($)")
    axes[0].set_title("VCP (Volatility Contraction Pattern) — BTC Daily 2022-2026")
    axes[0].legend(loc="upper left")
    axes[0].grid(True, alpha=0.3)

    # Drawdown comparison
    vcp_dd = (vcp_daily["equity"] / vcp_daily["equity"].cummax() - 1) * 100
    bh_dd = (bh_eq / bh_eq.cummax() - 1) * 100
    axes[1].fill_between(vcp_dd.index, vcp_dd, 0, color="steelblue", alpha=0.4, label="VCP DD")
    axes[1].fill_between(bh_dd.index, bh_dd, 0, color="orange", alpha=0.3, label="B&H DD")
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].set_xlabel("Date")
    axes[1].legend(loc="lower left")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT / "vcp_chart.png", dpi=110)
    print(f"Saved: {OUT / 'vcp_chart.png'}")


if __name__ == "__main__":
    main()
