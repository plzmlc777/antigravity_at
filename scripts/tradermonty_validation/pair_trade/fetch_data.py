"""Fetch BTC-USD + ETH-USD daily 2020-2026 for pair trading."""
from pathlib import Path
import pandas as pd
import yfinance as yf

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)


def fetch(symbol: str, name: str) -> pd.DataFrame:
    df = yf.download(symbol, start="2020-01-01", end="2026-04-30", interval="1d", progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "date"
    out = OUT / f"{name}_daily.csv"
    df.to_csv(out)
    print(f"  {symbol:10s} → {out.name}  ({len(df)} rows)")
    return df


def main():
    btc = fetch("BTC-USD", "btc")
    eth = fetch("ETH-USD", "eth")
    common = btc.index.intersection(eth.index)
    print(f"\n  Common dates: {len(common)} ({common.min().date()} → {common.max().date()})")


if __name__ == "__main__":
    main()
