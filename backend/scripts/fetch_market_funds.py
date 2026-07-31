"""Fetch KR market fund flows (증시자금추이, KOFIA FreeSIS STATSCU0100000060) — key-less.
Endpoint reverse-engineered via browser XHR capture.
Columns (dsGrid authoritative): TMPV1=date, TMPV2=투자자예탁금, TMPV3=장내파생상품 거래예수금,
TMPV4=대고객 RP매도잔고, TMPV5=위탁매매 미수금, TMPV6=반대매매금액, TMPV7=반대매매비중(%).
Amounts are in 백만원 -> converted to 조원. Saves runs/fx/market_funds_5y.csv
"""
import urllib.request, json, os, time
from datetime import date
import pandas as pd

# The KOFIA endpoint returns no Content-Length and closes with `Connection:
# close`, so urllib cannot tell a complete body from a truncated one. The
# server intermittently cuts the stream at exactly 32,120 bytes; measured
# 2026-07-31, 3 of 5 attempts returned the full 138KB / 1,225-row payload.
# A short read surfaces as JSONDecodeError, not a network error, so the parse
# is the completeness check. Same defect as fetch_market_credit.py.
MAX_TRIES = 10
RETRY_SLEEP_SEC = 2
MIN_ROWS = 100  # 5y of trading days is ~1,225; anything this small is a bad read

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
os.makedirs(OUTDIR, exist_ok=True)
URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"

MAP = {  # TMPV field -> (csv name, is_amount_조원)
    "TMPV2": ("투자자예탁금", True),
    "TMPV3": ("장내파생예수금", True),
    "TMPV4": ("대고객RP매도잔고", True),
    "TMPV5": ("위탁매매미수금", True),
    "TMPV6": ("반대매매금액", True),
    "TMPV7": ("반대매매비중", False),  # already %
}

def fetch(start, end):
    body = json.dumps({"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D",
                                     "tmpV45": start, "tmpV46": end,
                                     "OBJ_NM": "STATSCU0100000060BO"}}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "User-Agent": "Mozilla/5.0", "Content-Type": "application/json;charset=UTF-8",
        "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do?serviceId=STATSCU0100000060"})
    return fetch_with_retry(req)


def fetch_with_retry(req):
    """Return the parsed payload, retrying while the body arrives truncated."""
    last = ""
    for attempt in range(1, MAX_TRIES + 1):
        try:
            raw = urllib.request.urlopen(req, timeout=45).read()
        except Exception as exc:
            last = "request failed: %s" % exc
        else:
            try:
                d = json.loads(raw.decode())
            except json.JSONDecodeError:
                last = "truncated body (%d bytes)" % len(raw)
            else:
                rows = len(d.get("ds1", []))
                if rows >= MIN_ROWS:
                    if attempt > 1:
                        print("  recovered on attempt %d/%d" % (attempt, MAX_TRIES))
                    return d
                last = "only %d rows (< %d)" % (rows, MIN_ROWS)
        print("  retry %d/%d — %s" % (attempt, MAX_TRIES, last))
        if attempt < MAX_TRIES:
            time.sleep(RETRY_SLEEP_SEC)
    raise RuntimeError("KOFIA response never arrived complete in %d attempts — %s"
                       % (MAX_TRIES, last))

def main():
    today = date.today()
    start = f"{today.year-5}{today.month:02d}{today.day:02d}"
    end = f"{today.year}{today.month:02d}{today.day:02d}"
    d = fetch(start, end)
    rows = d.get("ds1", [])
    recs = {}
    for r in rows:
        dt = pd.to_datetime(str(r["TMPV1"]), format="%Y%m%d")
        rec = {}
        for f, (name, amt) in MAP.items():
            v = r.get(f)
            if v is None:
                continue
            rec[name] = round(v / 1e6, 4) if amt else v  # 백만원 -> 조원
        recs[dt] = rec
    df = pd.DataFrame.from_dict(recs, orient="index").sort_index()
    df.index.name = "date"
    df.to_csv(os.path.join(OUTDIR, "market_funds_5y.csv"))
    print(f"market_funds: {len(df)} rows {df.index.min().date()} -> {df.index.max().date()}")
    print(f"  투자자예탁금 last {df['투자자예탁금'].iloc[-1]:.1f}조 · 반대매매비중 last {df['반대매매비중'].iloc[-1]:.1f}%")

if __name__ == "__main__":
    main()
