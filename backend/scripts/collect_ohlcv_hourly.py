"""시간봉 수집 — 바이낸스 공개 아카이브 (무료·키 불필요).

⚠ 당월은 월별 파일이 없다
    `monthly/klines/<SYM>/1h/<SYM>-1h-YYYY-MM.zip` 은 **달이 끝나야** 올라온다.
    당월치를 월별로만 받으면 조용히 최근 데이터가 빠진다(DOSUSDT 2026-08 실측
    404). 완결된 달은 월별, 당월은 **일별**로 받는다.

⚠ 기존 행은 덮지 않는다
    `ON CONFLICT DO NOTHING`. 1분봉에서 유도한 행이 이미 있으면 그쪽이 원본에
    가까우므로 우선한다.

기본 대상은 **신상저격수 코호트**다 — 상장일 ~ +35일. 전 종목 3.6년을 받으면
1,100만 행이라 지금 필요하지 않다.

사용:
  python3 -m scripts.collect_ohlcv_hourly --cohort --since 2025-01-01
  python3 -m scripts.collect_ohlcv_hourly --symbols BTCUSDT --from 2025-01-01 --to 2026-08-15
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ohlcv_1h")

BASE = "https://data.binance.vision/data/futures/um"
LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
WORKERS = 8
COHORT_DAYS = 35          # 상장일 + 35일 (보유 30일 + 여유)


def _fetch(url: str) -> list[list] | None:
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception as exc:
        log.warning("%s: %s", url.rsplit("/", 1)[-1], exc)
        return None
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    out = []
    for r in csv.reader(io.StringIO(text)):
        if not r or not r[0].strip().isdigit():
            continue                       # 헤더가 있는 달이 있다
        try:
            ts = int(r[0])
            if ts > 10**14:                # 마이크로초로 주는 달이 있다
                ts //= 1000
            out.append([ts, float(r[1]), float(r[2]), float(r[3]),
                        float(r[4]), float(r[5])])
        except (ValueError, IndexError):
            continue
    return out


def month_file(sym: str, y: int, m: int) -> list[list] | None:
    return _fetch(f"{BASE}/monthly/klines/{sym}/1h/{sym}-1h-{y}-{m:02d}.zip")


def day_file(sym: str, d: date) -> list[list] | None:
    return _fetch(f"{BASE}/daily/klines/{sym}/1h/{sym}-1h-{d.isoformat()}.zip")


def fetch_range(sym: str, d0: date, d1: date) -> list[list]:
    """완결된 달은 월별, 당월은 일별로. 순서 상관없이 모아서 정렬한다."""
    today = date.today()
    cur_ym = (today.year, today.month)
    jobs: list = []
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        if (y, m) == cur_ym:
            cur = max(d0, date(y, m, 1))
            while cur <= min(d1, today):
                jobs.append(("d", cur))
                cur += timedelta(days=1)
        else:
            jobs.append(("m", (y, m)))
        m += 1
        if m > 12:
            y, m = y + 1, 1

    def one(job):
        kind, arg = job
        return month_file(sym, *arg) if kind == "m" else day_file(sym, arg)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        chunks = list(ex.map(one, jobs))
    rows = [r for c in chunks if c for r in c]
    # 경계에서 겹칠 수 있다 — 타임스탬프로 중복 제거
    seen, uniq = set(), []
    for r in sorted(rows, key=lambda x: x[0]):
        if r[0] in seen:
            continue
        seen.add(r[0])
        uniq.append(r)
    lo = datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc).timestamp() * 1000
    hi = (datetime(d1.year, d1.month, d1.day, tzinfo=timezone.utc)
          + timedelta(days=1)).timestamp() * 1000
    return [r for r in uniq if lo <= r[0] < hi]


def main() -> int:
    p = argparse.ArgumentParser(description="시간봉 수집")
    p.add_argument("--cohort", action="store_true",
                   help="신상저격수 코호트 (상장일 ~ +35일)")
    p.add_argument("--since", default="2025-01-01", help="코호트 상장일 하한")
    p.add_argument("--symbols", default="", help="쉼표 구분 (--cohort 대신)")
    p.add_argument("--from", dest="d_from", default="")
    p.add_argument("--to", dest="d_to", default="")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine

    targets: list[tuple[str, date, date]] = []
    if a.cohort:
        listings = json.loads(LISTINGS.read_text())
        for s, meta in sorted(listings.items()):
            if not isinstance(meta, dict) or not meta.get("onboard_date"):
                continue
            d = meta["onboard_date"]
            if d < a.since:
                continue
            ld = datetime.strptime(d, "%Y-%m-%d").date()
            targets.append((s, ld, min(ld + timedelta(days=COHORT_DAYS),
                                       date.today())))
    else:
        if not (a.symbols and a.d_from and a.d_to):
            raise SystemExit("--cohort 또는 (--symbols --from --to) 가 필요하다")
        d0 = datetime.fromisoformat(a.d_from).date()
        d1 = datetime.fromisoformat(a.d_to).date()
        targets = [(s.strip().upper(), d0, d1)
                   for s in a.symbols.split(",") if s.strip()]
    if a.limit:
        targets = targets[:a.limit]
    log.info("대상 %d종목", len(targets))

    total, miss, t0 = 0, 0, time.time()
    with engine.connect() as conn:
        for i, (sym, d0, d1) in enumerate(targets, 1):
            try:
                rows = fetch_range(sym, d0, d1)
            except Exception as exc:
                log.warning("[%d/%d] %s 실패: %s", i, len(targets), sym, exc)
                continue
            if not rows:
                miss += 1
                continue
            new = 0
            for ts, o, h, l, c, v in rows:
                res = conn.execute(text(
                    "INSERT INTO ohlcv_hourly "
                    "(symbol, ts, open, high, low, close, volume, built_at) "
                    "VALUES (:s, :t, :o, :h, :l, :c, :v, now()) "
                    "ON CONFLICT (symbol, ts) DO NOTHING"),
                    {"s": sym,
                     "t": datetime.fromtimestamp(ts / 1000, timezone.utc
                                                 ).replace(tzinfo=None),
                     "o": o, "h": h, "l": l, "c": c, "v": v})
                new += res.rowcount or 0
            conn.commit()
            total += new
            if i % 10 == 0 or new:
                log.info("[%d/%d] %s — 아카이브 %d봉 · 신규 %d · 누적 %s",
                         i, len(targets), sym, len(rows), new, f"{total:,}")

    print("=" * 76)
    with engine.connect() as c:
        n, s, t_lo, t_hi = c.execute(text(
            "SELECT count(*), count(distinct symbol), min(ts), max(ts) "
            "FROM ohlcv_hourly")).one()
        print(f"  ohlcv_hourly  {n:>9,}행 · 종목 {s:>4} · {t_lo} ~ {t_hi}")
    print(f"  신규 {total:,}행 · 아카이브 없음 {miss}종목 · {time.time()-t0:.0f}초")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
