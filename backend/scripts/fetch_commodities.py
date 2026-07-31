"""Fetch commodity real data for the market dashboard.
- Gold/Silver/Copper: Yahoo Finance futures daily (GC=F/SI=F/HG=F), 5y.
- Fertilizer: World Bank Pink Sheet monthly (Urea/DAP/Potassium chloride), 5y.
Saves CSVs into runs/fx/.
"""
import json, urllib.request, io, os
from datetime import date, datetime
import pandas as pd

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
os.makedirs(OUTDIR, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}

YF = {"Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F"}

def wb_monthly_url():
    """Resolve the current World Bank Pink Sheet monthly xlsx (hash changes each edition)."""
    import re
    fallback = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
    try:
        html = urllib.request.urlopen(urllib.request.Request(
            "https://www.worldbank.org/en/research/commodity-markets", headers=UA), timeout=25).read().decode("utf-8", "ignore")
        m = re.findall(r"https://thedocs\.worldbank\.org/[^\"' ]*CMO-Historical-Data-Monthly\.xlsx", html)
        return m[0] if m else fallback
    except Exception:
        return fallback

def yahoo_daily(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
    r = d["chart"]["result"][0]
    ts = r["timestamp"]; cl = r["indicators"]["quote"][0]["close"]
    idx = [datetime.utcfromtimestamp(t).date() for t in ts]
    s = pd.Series(cl, index=pd.to_datetime(idx)).dropna()
    s = s[~s.index.duplicated(keep="last")]
    return s

def main():
    # --- metals (daily) ---
    cols = {}
    for name, tk in YF.items():
        s = yahoo_daily(tk)
        cols[name] = s
        print(f"{name} ({tk}): {len(s)} pts {s.index.min().date()} -> {s.index.max().date()} last {s.iloc[-1]:.2f}")
    metals = pd.DataFrame(cols).sort_index()
    metals.to_csv(os.path.join(OUTDIR, "commodities_daily_5y.csv"))

    # --- fertilizer (monthly, World Bank Pink Sheet) ---
    raw = urllib.request.urlopen(urllib.request.Request(wb_monthly_url(), headers=UA), timeout=45).read()
    df = pd.read_excel(io.BytesIO(raw), sheet_name="Monthly Prices", header=4)
    df = df.rename(columns={df.columns[0]: "date"})
    keep = {"Urea ": "Urea", "DAP": "DAP", "Potassium chloride **": "Potash"}
    d = df[["date"] + list(keep)].rename(columns=keep)
    d = d[d["date"].astype(str).str.match(r"\d{4}M\d{2}")].copy()
    d["date"] = pd.to_datetime(d["date"].astype(str).str.replace("M", "-") + "-01")
    d = d.set_index("date").sort_index()
    d = d[d.index >= pd.Timestamp("2021-06-01")].astype(float)
    d.to_csv(os.path.join(OUTDIR, "fertilizer_monthly_5y.csv"))
    print(f"Fertilizer (WB monthly): {len(d)} pts {d.index.min().date()} -> {d.index.max().date()} Urea last {d['Urea'].iloc[-1]:.1f}")

if __name__ == "__main__":
    main()
