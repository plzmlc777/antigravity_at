"""Fetch KR margin/credit balances (신용공여 잔고 추이, KOFIA FreeSIS STATSCU0100000070) — key-less.
Same reverse-engineered endpoint as fetch_market_funds. Columns (dsGrid leaves, ORDER_SEQ):
TMPV1=date, TMPV2=신용거래융자 전체, TMPV3=유가증권(코스피), TMPV4=코스닥,
TMPV5~7=신용거래대주(전체/유가/코스닥), TMPV8=청약자금대출, TMPV9=예탁증권 담보융자.
Amounts 백만원 -> 조원. Saves runs/fx/market_credit_5y.csv
"""
import urllib.request, json, os, time
from datetime import date
import pandas as pd

# The KOFIA endpoint returns no Content-Length and closes with `Connection:
# close`, so urllib cannot tell a complete body from a truncated one. The
# server intermittently cuts the stream at exactly 32,120 bytes; measured
# 2026-07-31, only 2 of 5 attempts returned the full 170KB / 1,225-row payload
# (the failure is not size-related — a 3-year window succeeded at 100KB while
# a 1-year window truncated). Prior behaviour: JSONDecodeError -> the pipeline
# logged "keeping last-good CSV" and the dashboard silently scored ETF regime
# with 신용융자 data that was days stale.
MAX_TRIES = 10
RETRY_SLEEP_SEC = 2
MIN_ROWS = 100  # 5y of trading days is ~1,225; anything this small is a bad read

OUTDIR = os.environ.get("DASH_OUTDIR", "/home/hcpark/antigravity/backend/runs/fx")
URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
MAP = {"TMPV2": "신용융자", "TMPV3": "신용융자_코스피", "TMPV4": "신용융자_코스닥",
       "TMPV9": "예탁증권담보융자"}

def fetch_with_retry(req):
    """Return the parsed payload, retrying while the body arrives truncated.

    A short read raises JSONDecodeError rather than a network error, so the
    parse itself is the completeness check. MIN_ROWS additionally rejects a
    body that parses but is obviously partial.
    """
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
    body = json.dumps({"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D",
                                    "tmpV45": start, "tmpV46": end,
                                    "OBJ_NM": "STATSCU0100000070BO"}}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "User-Agent": "Mozilla/5.0", "Content-Type": "application/json;charset=UTF-8",
        "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do?serviceId=STATSCU0100000070"})
    d = fetch_with_retry(req)
    recs = {}
    for r in d.get("ds1", []):
        dt = pd.to_datetime(str(r["TMPV1"]), format="%Y%m%d")
        recs[dt] = {name: round(r[f] / 1e6, 4) for f, name in MAP.items() if r.get(f) is not None}
    df = pd.DataFrame.from_dict(recs, orient="index").sort_index()
    df.index.name = "date"
    df.to_csv(os.path.join(OUTDIR, "market_credit_5y.csv"))
    print(f"market_credit: {len(df)} rows {df.index.min().date()} -> {df.index.max().date()}")
    print(f"  신용융자 last {df['신용융자'].iloc[-1]:.1f}조 (코스피 {df['신용융자_코스피'].iloc[-1]:.1f} + 코스닥 {df['신용융자_코스닥'].iloc[-1]:.1f})")

if __name__ == "__main__":
    main()
