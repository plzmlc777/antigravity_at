"""지정 종목·구간의 ohlcv_1m 결손을 거래소 원본으로 채운다.

⚠ 절대 삭제하지 않는다. `INSERT ... ON CONFLICT DO NOTHING` 만 쓴다.
   (2026-08-20 --bulk 전량삭제 사고 때문에 삭제 경로를 아예 두지 않는다.)
"""
import sys, io, json, time, urllib.request, urllib.parse
from datetime import datetime, timezone
sys.path.insert(0, "/home/mint/auto_trading/backend")
import pandas as pd
from sqlalchemy import text
from app.db.session import engine

SYM = sys.argv[1]
A, B = sys.argv[2], sys.argv[3]
REST = "https://fapi.binance.com/fapi/v1/klines"

st = int(pd.Timestamp(A, tz="UTC").timestamp() * 1000)
et = int(pd.Timestamp(B, tz="UTC").timestamp() * 1000)
rows, cur = [], st
while cur < et:
    q = urllib.parse.urlencode({"symbol": SYM, "interval": "1m",
                                "startTime": cur, "endTime": et, "limit": 1000})
    d = json.load(urllib.request.urlopen(f"{REST}?{q}", timeout=30))
    if not d:
        break
    rows += d
    cur = int(d[-1][0]) + 60_000
    time.sleep(0.12)
print(f"{SYM} 거래소 {len(rows):,}봉 수집 ({A} ~ {B})")

with engine.connect() as c:
    before = c.execute(text("select count(*) from ohlcv_1m where symbol=:s "
                            "and ts>=:a and ts<:b"),
                       {"s": SYM, "a": A, "b": B}).scalar()
print(f"DB 현재 {before:,}봉 · 결손 {len(rows)-before:,}봉")

buf = io.StringIO()
for k in rows:
    t = datetime.fromtimestamp(int(k[0]) / 1000, timezone.utc).replace(tzinfo=None)
    buf.write(f"{SYM}\t{t.isoformat(sep=' ')}\t{k[1]}\t{k[2]}\t{k[3]}\t{k[4]}\t{k[5]}\n")
buf.seek(0)

raw = engine.raw_connection()
cur_ = raw.cursor()
cur_.execute("""CREATE TEMP TABLE _fill_1m
                (symbol text, ts timestamp, open double precision,
                 high double precision, low double precision,
                 close double precision, volume double precision)
                ON COMMIT DROP""")
cur_.copy_expert("COPY _fill_1m FROM STDIN", buf)
cur_.execute("""INSERT INTO ohlcv_1m (symbol, ts, open, high, low, close, volume)
                SELECT symbol, ts, open, high, low, close, volume FROM _fill_1m
                ON CONFLICT (symbol, ts) DO NOTHING""")
n = cur_.rowcount or 0
raw.commit(); cur_.close()

with engine.connect() as c:
    after = c.execute(text("select count(*) from ohlcv_1m where symbol=:s "
                           "and ts>=:a and ts<:b"),
                      {"s": SYM, "a": A, "b": B}).scalar()
print(f"삽입 {n:,}행 → DB {after:,}봉 · 남은 결손 {len(rows)-after:,}봉")
