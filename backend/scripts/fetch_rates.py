"""Fetch major-country central bank policy rates (BIS WS_CBPOL, daily) — key-less.
Includes majors + Russia/Brazil/India + Southeast Asia (ID/TH/MY/PH).
BIS SDMX: https://stats.bis.org/api/v1/data/BIS,WS_CBPOL,1.0/D.<codes>?format=csv
Saves runs/fx/rates_5y.csv (daily, ffilled step-function rates in %).
"""
import urllib.request, csv, io, os
from datetime import date
import pandas as pd

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
# BIS REF_AREA code -> Korean name (order = display order)
AREAS = [("US", "미국"), ("XM", "유로존"), ("JP", "일본"), ("CN", "중국"),
         ("KR", "한국"), ("GB", "영국"), ("RU", "러시아"), ("BR", "브라질"),
         ("IN", "인도"), ("ID", "인도네시아"), ("TH", "태국"),
         ("MY", "말레이시아"), ("PH", "필리핀")]

def main():
    today = date.today()
    start = f"{today.year-5}-{today.month:02d}-01"
    codes = "+".join(a for a, _ in AREAS)
    url = (f"https://stats.bis.org/api/v1/data/BIS,WS_CBPOL,1.0/D.{codes}"
           f"?format=csv&startPeriod={start}")
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                 timeout=60).read().decode("utf-8", "ignore")
    rd = csv.DictReader(io.StringIO(raw))
    recs = {}  # (date, area) -> value
    for row in rd:
        v = row.get("OBS_VALUE", "")
        try:
            fv = float(v)
        except ValueError:
            continue
        recs[(row["TIME_PERIOD"], row["REF_AREA"])] = fv
    s = pd.Series(recs)
    if s.empty:
        raise SystemExit("BIS rates fetch empty — endpoint may have changed")
    df = s.unstack()  # rows=date, cols=area
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    # daily business range + forward-fill step-function rates
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full).ffill()
    df = df.rename(columns={a: kr for a, kr in AREAS})
    df = df[[kr for _, kr in AREAS if kr in df.columns]]
    df.index.name = "date"
    df.to_csv(os.path.join(OUTDIR, "rates_5y.csv"))
    latest = df.iloc[-1]
    print(f"rates: {len(df)} rows {df.index.min().date()} -> {df.index.max().date()}")
    print("  " + " · ".join(f"{k} {latest[k]:.2f}%" for k in df.columns))

if __name__ == "__main__":
    main()
