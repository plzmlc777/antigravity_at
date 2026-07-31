"""Fetch semiconductor benchmark real data (Yahoo Finance, daily 5y).
SOX (Philadelphia Semiconductor Index) + KR semi leaders (Samsung, SK Hynix) + NVDA.
Saves runs/fx/semis_5y.csv
"""
import json, urllib.request, os
from datetime import datetime
import pandas as pd

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
UA = {"User-Agent": "Mozilla/5.0"}
TICKERS = {"SOX": "%5ESOX", "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "NVIDIA": "NVDA"}

def yahoo_daily(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
    r = d["chart"]["result"][0]
    ts = r["timestamp"]; cl = r["indicators"]["quote"][0]["close"]
    idx = [datetime.utcfromtimestamp(t).date() for t in ts]
    s = pd.Series(cl, index=pd.to_datetime(idx)).dropna()
    return s[~s.index.duplicated(keep="last")]

def main():
    cols = {}
    for name, tk in TICKERS.items():
        s = yahoo_daily(tk)
        cols[name] = s
        print(f"{name} ({tk}): {len(s)} pts {s.index.min().date()} -> {s.index.max().date()} last {s.iloc[-1]:,.2f}")
    df = pd.DataFrame(cols).sort_index()
    df.to_csv(os.path.join(OUTDIR, "semis_5y.csv"))

if __name__ == "__main__":
    main()
