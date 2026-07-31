"""Fetch global dry-bulk freight index (KDCI = KOBC Dry Bulk Index) — key-less, gov source.
KOBC (한국해양진흥공사) publishes KDCI daily with vessel-class sub-indices. This is the real
freight index analog to BDI (Baltic Exchange's BDI itself has no free/no-key daily feed).
Endpoint: POST /ebz/shippinginfo/kdci/gridList.do with sDay/eDay (YYYY-MM-DD) -> HTML table
(Date, KDCI, CAPE, PANAMAX, SUPRAMAX, HANDY). Saves runs/fx/freight_5y.csv
"""
import urllib.request, urllib.parse, re, os
from datetime import date
import pandas as pd

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
URL = "https://kobc.or.kr/ebz/shippinginfo/kdci/gridList.do?mId=0301000000"
COLS = ["date", "건화물종합", "케이프", "파나막스", "수프라막스", "핸디"]

def main():
    today = date.today()
    sDay = f"{today.year-5}-{today.month:02d}-{today.day:02d}"
    eDay = today.strftime("%Y-%m-%d")
    data = urllib.parse.urlencode({"page": 1, "sDay": sDay, "eDay": eDay,
                                   "mId": "0301000000", "siteCode": "shippinginfo"}).encode()
    req = urllib.request.Request(URL, data=data, headers={
        "User-Agent": "Mozilla/5.0", "Referer": URL,
        "Content-Type": "application/x-www-form-urlencoded"})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
    recs = {}
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).replace(",", "").strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if cells and re.match(r"20\d\d-\d\d-\d\d", cells[0]) and len(cells) >= 6:
            dt = pd.to_datetime(cells[0])
            recs[dt] = {COLS[i]: float(cells[i]) for i in range(1, 6) if cells[i]}
    df = pd.DataFrame.from_dict(recs, orient="index").sort_index()
    df.index.name = "date"
    if len(df) < 100:
        raise SystemExit(f"KDCI fetch too few rows ({len(df)}) — endpoint may have changed")
    df.to_csv(os.path.join(OUTDIR, "freight_5y.csv"))
    print(f"freight (KDCI): {len(df)} rows {df.index.min().date()} -> {df.index.max().date()} · KDCI last {df['건화물종합'].iloc[-1]:,.0f}")

if __name__ == "__main__":
    main()
