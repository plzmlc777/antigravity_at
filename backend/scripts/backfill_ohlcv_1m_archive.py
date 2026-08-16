"""`ohlcv` 1분봉 구멍 메우기 — 바이낸스 공개 아카이브 (무료·키 불필요).

## 왜 (2026-08-16)

    알트 13종목  2021-01 ~ 현재 · 각 **295만 행**
    **BTCUSDT   2026-03-29 ~ 현재 · 정확히 200,000 행**
    ETHUSDT     2026-03-27 ~ · 정확히 200,000 행

BTC·ETH **만** 4.5개월치다. 200,000 = 138.9일치로 딱 떨어지는 걸 보면 어느
시점에 지워지고 그 뒤로만 채워진 것이다(활성 절단 잡은 없다 — 확인함).

⚠ **BTC 를 트리거로 쓰는 모든 패러다임이 조용히 4.5개월짜리로 돌아간다.**
   R-5 시드 `btc_rv_highvol` 이 정확히 여기 걸렸다 — BTC 30분 RV 가 핵심
   트리거인데 원장에 4.5개월뿐이라 긴 창을 못 만든다.
   `ohlcv_daily` 의 BTC·ETH 구멍(2026-08-15 복구)도 **이 구멍에서 유도된
   증상**이었다. 이번이 뿌리다.

## 방식

    완결된 달  monthly/klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip
    당월       daily/klines/<SYM>/1m/<SYM>-1m-YYYY-MM-DD.zip
               (⚠ 월별 파일은 **달이 끝나야** 올라온다 — 당월을 월별로만
                받으면 조용히 최근이 빠진다)

⚠ 기존 행은 덮지 않는다 — `ON CONFLICT (symbol, time_frame, timestamp)
  DO NOTHING`. 라이브 수집분이 우선이다.

⚠ 대량 삽입을 쓴다 — 540만 행을 한 줄씩 넣으면 30분이 넘는다.
  `execute_values` 로 배치 삽입한다.

사용:
  python3 -m scripts.backfill_ohlcv_1m_archive --symbols BTCUSDT,ETHUSDT \
      --from 2021-01-01
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bf1m")

MONTHLY = "https://data.binance.vision/data/futures/um/monthly/klines"
DAILY = "https://data.binance.vision/data/futures/um/daily/klines"
BATCH = 20_000


def parse(blob: bytes) -> list[tuple]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        txt = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    out = []
    for r in csv.reader(io.StringIO(txt)):
        if not r or not r[0].strip().isdigit():
            continue                       # 헤더가 있는 달이 있다
        try:
            ts = int(r[0])
            if ts > 10**14:                # 마이크로초로 주는 달이 있다
                ts //= 1000
            out.append((datetime.fromtimestamp(ts / 1000, timezone.utc
                                               ).replace(tzinfo=None),
                        float(r[1]), float(r[2]), float(r[3]), float(r[4]),
                        float(r[5])))
        except (ValueError, IndexError):
            continue
    return out


def fetch(url: str) -> list[tuple]:
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return parse(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    except Exception as exc:
        log.warning("%s: %s", url.rsplit("/", 1)[-1], exc)
        return []


def main() -> int:
    p = argparse.ArgumentParser(description="ohlcv 1분봉 아카이브 백필")
    p.add_argument("--symbols", required=True, help="쉼표 구분")
    p.add_argument("--from", dest="d_from", default="2021-01-01")
    p.add_argument("--to", dest="d_to", default="")
    a = p.parse_args()

    from sqlalchemy import text
    from psycopg2.extras import execute_values

    from app.db.session import engine

    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    d0 = datetime.fromisoformat(a.d_from).date()
    d1 = datetime.fromisoformat(a.d_to).date() if a.d_to else date.today()

    # 완결된 달 목록 + 당월 일별
    months, y, m = [], d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        if (y, m) != (d1.year, d1.month):
            months.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    cur_days = [date(d1.year, d1.month, x) for x in range(1, d1.day + 1)]
    cur_days = [x for x in cur_days if x >= d0]
    log.info("대상 %s · 월별 %d개 + 당월 일별 %d개", syms, len(months), len(cur_days))

    raw = engine.raw_connection()
    total, t0 = 0, time.time()
    try:
        cur = raw.cursor()
        for sym in syms:
            n_sym = 0
            jobs = ([(MONTHLY, f"{sym}/1m/{sym}-1m-{yy}-{mm:02d}.zip")
                     for yy, mm in months]
                    + [(DAILY, f"{sym}/1m/{sym}-1m-{dd.isoformat()}.zip")
                       for dd in cur_days])
            for i, (base, path) in enumerate(jobs, 1):
                rows = fetch(f"{base}/{path}")
                if not rows:
                    continue
                buf = [(sym, ts, "1m", o, h, l, c, v)
                       for ts, o, h, l, c, v in rows]
                for k in range(0, len(buf), BATCH):
                    execute_values(cur,
                                   "INSERT INTO ohlcv (symbol, timestamp, "
                                   "time_frame, open, high, low, close, volume, "
                                   "created_at) VALUES %s "
                                   "ON CONFLICT (symbol, time_frame, timestamp) "
                                   "DO NOTHING",
                                   buf[k:k + BATCH],
                                   template="(%s,%s,%s,%s,%s,%s,%s,%s,now())",
                                   page_size=BATCH)
                    n_sym += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                raw.commit()
                if i % 12 == 0:
                    log.info("  %s [%d/%d] 누적 신규 %s (%.0f초)",
                             sym, i, len(jobs), f"{n_sym:,}", time.time() - t0)
            total += n_sym
            log.info("%s 완료 — 신규 %s행", sym, f"{n_sym:,}")
    finally:
        raw.close()

    print("=" * 76)
    with engine.connect() as c:
        for sym in syms:
            n, lo, hi = c.execute(text(
                "SELECT count(*), min(timestamp), max(timestamp) FROM ohlcv "
                "WHERE symbol=:s AND time_frame='1m'"), {"s": sym}).one()
            print(f"  {sym:<10} {n:>10,}행 · {lo} ~ {hi}")
    print(f"  신규 {total:,}행 · {time.time()-t0:.0f}초")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
