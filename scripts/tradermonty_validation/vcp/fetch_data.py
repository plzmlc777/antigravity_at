"""Fetch BTC-USD daily data 2020-2026 (need 200+ days history before backtest start)."""
from pathlib import Path
import pandas as pd
import yfinance as yf

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)


def main():
    # Fetch 6+ years to ensure 200-day SMA is valid from 2022-01
    df = yf.download("BTC-USD", start="2020-01-01", end="2026-04-30", interval="1d", progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "date"
    out = OUT / "btc_usd_daily.csv"
    df.to_csv(out)
    print(f"Saved: {out}")
    print(f"  Rows: {len(df)}")
    print(f"  Range: {df.index.min().date()} → {df.index.max().date()}")
    print(f"  First valid 200d SMA: row {200} = {df.index[200].date()}")


if __name__ == "__main__":
    main()
