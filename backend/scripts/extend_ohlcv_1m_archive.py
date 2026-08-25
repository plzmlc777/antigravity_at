"""`ohlcv_1m` 을 **과거로 확장** — 바이낸스 공개 아카이브 (무료·키 불필요).

`repair_ohlcv_1m.py` 와 같은 방식이되 구간·유니버스·속도를 **인자로** 받는다.
그 스크립트는 2026-08-20 소실 복구 전용이라 창이 소스에 박혀 있었다.

⚠ 절대 삭제하지 않는다
    임시 테이블에 COPY 한 뒤 `INSERT ... ON CONFLICT DO NOTHING` 으로 옮긴다.
    이미 있는 행은 그대로 두고 없는 것만 채운다. 중간에 죽어도 안전하고,
    같은 명령을 다시 돌려도 무해하다(재개 가능).

    2026-08-20 에 `collect_ohlcv_hourly.py --tf 1m --bulk` 를 돌렸다가
    175종목 9,184만 행을 잃었다. 그 안의 bulk_copy() 는 **구간과 무관하게
    종목 전체를 지운다**. 확장·복구는 반드시 이 경로로 한다.

⚠ 실거래와 같은 서버에서 돈다
    기본이 **직렬 + 파일마다 쉼**이다. 워커를 늘리지 마라. `--sleep` 으로
    더 느리게 만들 수는 있어도 빠르게 만들 수단은 일부러 두지 않았다.

사용:
  python3 -m scripts.extend_ohlcv_1m_archive \
      --universe configs/rsi_paper_universe.txt \
      --from 2022-08-17 --to 2024-08-16 --sleep 0.5
  # 점검만 (내려받지 않고 대상만 센다)
  python3 -m scripts.extend_ohlcv_1m_archive --universe … --from … --to … --dry-run
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text                                    # noqa: E402

from app.db.session import engine                              # noqa: E402

log = logging.getLogger("extend_1m")
BASE = "https://data.binance.vision/data/futures/um"
TF = "1m"

DDL = """CREATE TEMP TABLE IF NOT EXISTS _stage_1m
         (symbol text, ts timestamp, open double precision, high double precision,
          low double precision, close double precision, volume double precision)
         ON COMMIT DROP"""
MOVE = """INSERT INTO ohlcv_1m (symbol, ts, open, high, low, close, volume)
          SELECT symbol, ts, open, high, low, close, volume FROM _stage_1m
          ON CONFLICT (symbol, ts) DO NOTHING"""


def _fetch(url: str, sleep: float) -> list | None:
    """월/일 zip 하나. 없으면 None (상장 전이면 정상적으로 없다)."""
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            blob = r.read()
    except urllib.error.HTTPError:
        return None
    except Exception as e:                                     # noqa: BLE001
        log.debug("내려받기 실패 %s: %s", url, e)
        return None
    finally:
        if sleep:
            time.sleep(sleep)                                  # 서버·거래소 배려
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as f:
            for line in io.TextIOWrapper(f, "utf-8"):
                p = line.strip().split(",")
                if not p or not p[0] or p[0][0].isalpha():      # 헤더 행
                    continue
                out.append((int(p[0]), p[1], p[2], p[3], p[4], p[5]))
    return out


def months(d0: date, d1: date):
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_range(sym: str, d0: date, d1: date, sleep: float) -> list:
    rows = []
    for y, m in months(d0, d1):
        r = _fetch(f"{BASE}/monthly/klines/{sym}/{TF}/{sym}-{TF}-{y}-{m:02d}.zip", sleep)
        if r:
            rows += r
    # ⚠ 월별 파일은 **달이 끝나야** 올라온다. 끝 달이 진행 중이면 일별로 보완.
    if (d1.year, d1.month) == (date.today().year, date.today().month):
        d = date(d1.year, d1.month, 1)
        while d <= d1:
            r = _fetch(f"{BASE}/daily/klines/{sym}/{TF}/{sym}-{TF}-{d.isoformat()}.zip",
                       sleep)
            if r:
                rows += r
            d += timedelta(days=1)
    lo = int(datetime(d0.year, d0.month, d0.day,
                      tzinfo=timezone.utc).timestamp() * 1000)
    hi = int(datetime(d1.year, d1.month, d1.day, 23, 59,
                      tzinfo=timezone.utc).timestamp() * 1000)
    return [r for r in rows if lo <= r[0] <= hi]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="", help="종목 목록 파일 (한 줄에 하나)")
    p.add_argument("--symbols", default="", help="쉼표 구분 (universe 보다 우선)")
    p.add_argument("--from", dest="d_from", required=True, help="YYYY-MM-DD 포함")
    p.add_argument("--to", dest="d_to", required=True, help="YYYY-MM-DD 포함")
    p.add_argument("--sleep", type=float, default=0.5,
                   help="파일마다 쉬는 초. 실거래와 같은 서버라 기본이 느리다")
    p.add_argument("--dry-run", action="store_true",
                   help="내려받지 않고 대상 종목·기존 행수만 센다")
    p.add_argument("--skip-covered", type=int, default=0,
                   help="이 구간에 이미 N행 이상 있으면 건너뛴다 (0=항상 시도)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    d0 = date.fromisoformat(a.d_from)
    d1 = date.fromisoformat(a.d_to)
    if d1 < d0:
        raise SystemExit("--to 가 --from 보다 앞이다")

    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    elif a.universe:
        syms = [s.strip().upper() for s in Path(a.universe).read_text().split()
                if s.strip()]
    else:
        raise SystemExit("--universe 또는 --symbols 중 하나는 필요하다")

    with engine.connect() as c:
        have = {s: c.execute(text("select count(*) from ohlcv_1m "
                                  "where symbol=:s and ts>=:a and ts<=:b"),
                             {"s": s, "a": d0, "b": d1}).scalar() for s in syms}
    todo = [s for s in syms if have[s] <= a.skip_covered]
    log.info("구간 %s ~ %s · 종목 %d · 대상 %d (기존 %s행 이하)",
             d0, d1, len(syms), len(todo), f"{a.skip_covered:,}")
    log.info("이미 채워진 종목 %d · 그 구간 총 %s행",
             len(syms) - len(todo), f"{sum(have.values()):,}")
    if a.dry_run:
        for s in todo[:20]:
            log.info("  대상 %s (기존 %s행)", s, f"{have[s]:,}")
        n_month = sum(1 for _ in months(d0, d1))
        log.info("점검만 — 내려받을 파일 최대 %s개 (%d종목 × %d달), "
                 "쉼 %.1f초면 최소 %.1f시간",
                 f"{len(todo)*n_month:,}", len(todo), n_month, a.sleep,
                 len(todo) * n_month * a.sleep / 3600)
        return 0

    raw = engine.raw_connection()
    t0, done, ins, empty = time.time(), 0, 0, 0
    for i, s in enumerate(todo, 1):
        try:
            rows = fetch_range(s, d0, d1, a.sleep)
        except Exception as e:                                 # noqa: BLE001
            log.warning("  ✗ %s 내려받기 예외: %s", s, e)
            continue
        if not rows:
            empty += 1                                         # 상장 전이면 정상
            continue
        buf = io.StringIO()
        for ts, o, h, l, c_, v in rows:
            t = datetime.fromtimestamp(ts / 1000, timezone.utc).replace(tzinfo=None)
            buf.write(f"{s}\t{t.isoformat(sep=' ')}\t{o}\t{h}\t{l}\t{c_}\t{v}\n")
        buf.seek(0)
        cur = raw.cursor()
        try:
            cur.execute(DDL)
            cur.copy_expert("COPY _stage_1m FROM STDIN", buf)
            cur.execute(MOVE)
            ins += cur.rowcount or 0
            raw.commit()
        except Exception as e:                                 # noqa: BLE001
            raw.rollback()
            log.warning("  ✗ %s 적재 실패: %s", s, e)
        finally:
            cur.close()
        done += 1
        if i % 5 == 0 or i == len(todo):
            el = time.time() - t0
            log.info("[%d/%d] %s · 삽입 %s행 · %.0f분 경과 · 남은 %.0f분",
                     i, len(todo), s, f"{ins:,}", el / 60,
                     (len(todo) - i) * el / i / 60)
    log.info("확장 완료 — 적재 %d종목 · 아카이브 없음 %d · %s행 · %.0f분",
             done, empty, f"{ins:,}", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
