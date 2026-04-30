"""Plot Breakout vs VCP vs B&H comparison."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "output"
VCP_OUT = ROOT.parent / "vcp" / "output"
INITIAL = 10000.0


def main():
    spot = pd.read_csv(DATA / "btc_usd_daily.csv", parse_dates=["date"]).set_index("date").loc["2022-01-01":]

    bo_trades = pd.read_csv(OUT / "trades.csv", parse_dates=["entry_date", "exit_date"])
    vcp_trades = pd.read_csv(VCP_OUT / "trades.csv", parse_dates=["entry_date", "exit_date"])

    def equity_curve(trades_df):
        eq = INITIAL
        pts = [(spot.index[0], eq)]
        for _, t in trades_df.sort_values("exit_date").iterrows():
            eq *= (1 + t["pnl_pct"])
            pts.append((t["exit_date"], eq))
        df = pd.DataFrame(pts, columns=["date", "equity"]).set_index("date")
        return df.reindex(spot.index, method="ffill").fillna(INITIAL)

    bo_eq = equity_curve(bo_trades)
    vcp_eq = equity_curve(vcp_trades)
    bh_units = INITIAL / float(spot["Close"].iloc[0])
    bh_eq = spot["Close"] * bh_units

    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

    axes[0].plot(vcp_eq.index, vcp_eq["equity"], label="VCP (trailing stop)", color="steelblue", linewidth=1.6)
    axes[0].plot(bo_eq.index, bo_eq["equity"], label="Breakout (2R target)", color="green", linewidth=1.6)
    axes[0].plot(bh_eq.index, bh_eq.values, label="Buy-and-Hold BTC", color="orange", linewidth=1.2, alpha=0.75)
    axes[0].axhline(INITIAL, color="gray", linestyle="--", alpha=0.4)
    axes[0].set_ylabel("Equity ($)")
    axes[0].set_title("VCP vs Breakout vs Buy-and-Hold (BTC daily, 2022-2026)")
    axes[0].legend(loc="upper left")
    axes[0].grid(True, alpha=0.3)

    for label, eq, color in [("VCP", vcp_eq["equity"], "steelblue"),
                              ("Breakout", bo_eq["equity"], "green"),
                              ("B&H", bh_eq, "orange")]:
        dd = (eq / eq.cummax() - 1) * 100
        axes[1].plot(dd.index, dd, label=label, color=color, linewidth=1)
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].set_xlabel("Date")
    axes[1].legend(loc="lower left")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT / "breakout_vs_vcp_vs_bh.png", dpi=110)
    print(f"Saved: {OUT / 'breakout_vs_vcp_vs_bh.png'}")


if __name__ == "__main__":
    main()
