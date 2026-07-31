"""Lean FX collector (Naver market index) -> fx_krw_5y.csv. No matplotlib (cron-friendly).
USD/CNY/EUR/JPY vs KRW, daily close, ~5y.
"""
import json, time, os
from datetime import datetime, timedelta
import urllib.request
import pandas as pd

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
os.makedirs(OUTDIR, exist_ok=True)
CODES = {"USD/KRW": "FX_USDKRW", "CNY/KRW": "FX_CNYKRW",
         "EUR/KRW": "FX_EURKRW", "JPY/KRW (per 100)": "FX_JPYKRW"}
UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://m.stock.naver.com/front-api/marketIndex/prices?category=exchange&reutersCode={code}&page={page}&pageSize=10"

def fetch_series(code, min_date):
    rows, page = {}, 1
    while True:
        url = BASE.format(code=code, page=page)
        ok = False
        for _ in range(4):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    d = json.loads(resp.read().decode())
                res = d.get("result")
                if not res:
                    return rows
                for r in res:
                    rows[r["localTradedAt"]] = float(r["closePrice"].replace(",", ""))
                ok = True
                break
            except Exception:
                time.sleep(0.4)
        if not ok:
            return rows
        if min(rows) <= min_date:
            return rows
        page += 1
        time.sleep(0.05)

def main():
    today = datetime.now()
    d5 = (today - timedelta(days=365 * 5 + 5)).strftime("%Y-%m-%d")
    series = {}
    for name, code in CODES.items():
        s = pd.Series(fetch_series(code, d5))
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        series[name] = s[s.index >= pd.to_datetime(d5)]
        print(f"{name}: {len(series[name])} pts")
    df = pd.DataFrame(series).sort_index()
    df.to_csv(os.path.join(OUTDIR, "fx_krw_5y.csv"))
    print(f"fx_krw_5y: {len(df)} rows -> {df.index.max().date()}")

if __name__ == "__main__":
    main()
