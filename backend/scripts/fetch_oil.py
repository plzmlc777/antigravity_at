"""Fetch energy real data for the 유가 tab.
- WTI(CL=F)/Brent(BZ=F)/Natural gas(NG=F): Yahoo Finance daily 5y.
- Dubai crude: World Bank Pink Sheet monthly ($/bbl) — KR's crude import benchmark.
Saves runs/fx/oil_daily_5y.csv + runs/fx/dubai_monthly_5y.csv
"""
import json, urllib.request, io, os
from datetime import datetime
import pandas as pd

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
UA = {"User-Agent": "Mozilla/5.0"}
YF = {"WTI": "CL=F", "Brent": "BZ=F", "천연가스": "NG=F"}
WB_FALLBACK = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"

def wb_monthly_url():
    import re
    try:
        html = urllib.request.urlopen(urllib.request.Request(
            "https://www.worldbank.org/en/research/commodity-markets", headers=UA), timeout=25).read().decode("utf-8", "ignore")
        m = re.findall(r"https://thedocs\.worldbank\.org/[^\"' ]*CMO-Historical-Data-Monthly\.xlsx", html)
        return m[0] if m else WB_FALLBACK
    except Exception:
        return WB_FALLBACK

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
    for name, tk in YF.items():
        s = yahoo_daily(tk)
        cols[name] = s
        print(f"{name} ({tk}): {len(s)} pts last {s.iloc[-1]:.2f}")
    pd.DataFrame(cols).sort_index().to_csv(os.path.join(OUTDIR, "oil_daily_5y.csv"))

    raw = urllib.request.urlopen(urllib.request.Request(wb_monthly_url(), headers=UA), timeout=45).read()
    df = pd.read_excel(io.BytesIO(raw), sheet_name="Monthly Prices", header=4)
    df = df.rename(columns={df.columns[0]: "date"})
    d = df[["date", "Crude oil, Dubai"]].rename(columns={"Crude oil, Dubai": "두바이유"})
    d = d[d["date"].astype(str).str.match(r"\d{4}M\d{2}")].copy()
    d["date"] = pd.to_datetime(d["date"].astype(str).str.replace("M", "-") + "-01")
    d = d.set_index("date").sort_index()
    d = d[d.index >= pd.Timestamp("2021-06-01")].astype(float)
    d.to_csv(os.path.join(OUTDIR, "dubai_monthly_5y.csv"))
    print(f"두바이유 (WB monthly): {len(d)} pts last {d['두바이유'].iloc[-1]:.1f}")

if __name__ == "__main__":
    main()
