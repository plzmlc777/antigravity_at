"""ohlcv_1m 소실 구간 복구 — **삭제 없이** 채운다.

⚠ 무슨 일이 있었나 (2026-08-20)
    `collect_ohlcv_hourly.py --tf 1m --bulk --from ... --to ...` 을 돌렸다.
    그 안의 bulk_copy() 는 **구간과 무관하게 종목 전체를 지운다**:

        cur.execute(f"DELETE FROM {table} WHERE symbol = %s", (sym,))

    삭제는 전체, 삽입은 지정 구간이라 **기존 1년치가 사라졌다.**
    실행 전에 소스를 안 읽은 것이 원인이다.

⚠ 이 스크립트는 절대 삭제하지 않는다
    임시 테이블에 COPY 한 뒤 `INSERT ... ON CONFLICT DO NOTHING` 으로 옮긴다.
    이미 있는 행은 그대로 두고 없는 것만 채운다. 중간에 죽어도 안전하다.
"""
import sys, io, time, zipfile, urllib.request, urllib.error
from datetime import date, datetime, timezone, timedelta
sys.path.insert(0, '.')
from app.db.session import engine
from sqlalchemy import text

BASE = "https://data.binance.vision/data/futures/um"
TF = "1m"
WANT_FROM = date(2025, 8, 17)      # 소실된 구간
WANT_TO   = date(2026, 8, 16)

def _fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            blob = r.read()
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as f:
            for line in io.TextIOWrapper(f, "utf-8"):
                p = line.strip().split(",")
                if not p or not p[0] or p[0][0].isalpha():
                    continue
                out.append((int(p[0]), p[1], p[2], p[3], p[4], p[5]))
    return out

def fetch_range(sym, d0, d1):
    rows, y, m = [], d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        r = _fetch(f"{BASE}/monthly/klines/{sym}/{TF}/{sym}-{TF}-{y}-{m:02d}.zip")
        if r: rows += r
        m += 1
        if m == 13: y, m = y + 1, 1
    # 이번 달은 일별로 보완
    d = date(d1.year, d1.month, 1)
    while d <= d1:
        r = _fetch(f"{BASE}/daily/klines/{sym}/{TF}/{sym}-{TF}-{d.isoformat()}.zip")
        if r: rows += r
        d += timedelta(days=1)
    lo = int(datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc).timestamp()*1000)
    hi = int(datetime(d1.year, d1.month, d1.day, 23, 59, tzinfo=timezone.utc).timestamp()*1000)
    return [r for r in rows if lo <= r[0] <= hi]

DDL = """CREATE TEMP TABLE IF NOT EXISTS _stage_1m
         (symbol text, ts timestamp, open double precision, high double precision,
          low double precision, close double precision, volume double precision)
         ON COMMIT DROP"""
MOVE = """INSERT INTO ohlcv_1m (symbol, ts, open, high, low, close, volume)
          SELECT symbol, ts, open, high, low, close, volume FROM _stage_1m
          ON CONFLICT (symbol, ts) DO NOTHING"""

uni = [s.strip() for s in open('configs/rsi_paper_universe.txt').read().split() if s.strip()]
raw = engine.raw_connection()
need = []
with engine.connect() as c:
    for s in uni:
        n = c.execute(text("select count(*) from ohlcv_1m where symbol=:s and ts>=:a"),
                      {"s": s, "a": WANT_FROM}).scalar()
        if n < 500000:
            need.append((s, n))
print(f"복구 대상 {len(need)}종목 (최근 1년 행수 50만 미만)")
t0, done, ins = time.time(), 0, 0
for i, (s, have) in enumerate(need, 1):
    rows = fetch_range(s, WANT_FROM, WANT_TO)
    if not rows:
        print(f"  ✗ {s} 아카이브 없음"); continue
    buf = io.StringIO()
    for ts, o, h, l, c_, v in rows:
        t = datetime.fromtimestamp(ts/1000, timezone.utc).replace(tzinfo=None)
        buf.write(f"{s}\t{t.isoformat(sep=' ')}\t{o}\t{h}\t{l}\t{c_}\t{v}\n")
    buf.seek(0)
    cur = raw.cursor()
    cur.execute(DDL)
    cur.copy_expert("COPY _stage_1m FROM STDIN", buf)
    cur.execute(MOVE)
    ins += cur.rowcount or 0
    raw.commit(); cur.close()
    done += 1
    if i % 10 == 0:
        el = time.time()-t0
        print(f"  [{i}/{len(need)}] {s} · 삽입 {ins:,}행 · {el:.0f}초 · "
              f"남은 {(len(need)-i)*el/i/60:.0f}분")
print(f"복구 완료 {done}/{len(need)}종목 · {ins:,}행 · {time.time()-t0:.0f}초")
