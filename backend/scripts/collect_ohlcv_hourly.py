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
# ⚠ 아카이브는 **T+1** 이다 — 오늘·어제 봉이 없다. 라이브 사이클에는 못 쓴다.
#   그래서 최근 구간만 REST klines 로 받는 `--live` 모드를 둔다.
#   같은 데이터원이라 값은 일치한다(2026-08-15 실측: REST vs 아카이브 500/500).
REST = "https://fapi.binance.com/fapi/v1/klines"
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


def rest_recent(sym: str, hours: int) -> list[list]:
    """최근 N시간 1h 봉을 REST 로. 아카이브 지연을 메운다.

    ⚠ **마지막 봉은 미완성**이다. 그대로 넣으면 진행 중인 시간의 고가·저가·
      종가가 확정값처럼 저장된다. 마감된 봉만 남긴다.
    """
    import urllib.parse
    end = int(time.time() * 1000)
    start = end - hours * TF_MS[TF]
    out: list[list] = []
    cur = start
    while cur < end:
        q = urllib.parse.urlencode({"symbol": sym, "interval": TF,
                                    "startTime": cur, "limit": 1000})
        try:
            with urllib.request.urlopen(f"{REST}?{q}", timeout=60) as r:
                data = json.load(r)
        except Exception as exc:
            log.warning("%s REST 실패: %s", sym, exc)
            break
        if not data:
            break
        for k in data:
            try:
                out.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                            float(k[4]), float(k[5])])
            except (ValueError, IndexError):
                continue
        nxt = int(data[-1][0]) + TF_MS[TF]
        if nxt <= cur:
            break
        cur = nxt
        if len(data) < 1000:
            break
    # 마감된 봉만 — 봉 시작 + 1시간 <= 현재
    now_ms = int(time.time() * 1000)
    return [r for r in out if r[0] + TF_MS[TF] <= now_ms]


# ⚠ 시간대는 **파라미터**다. 예전엔 "1h" 가 여섯 군데 박혀 있어 5m·15m 을
#   받으려면 파일을 복제해야 했다 — 그러면 수집기가 둘로 갈린다.
TF = "1h"                      # main() 에서 --tf 로 덮는다
TF_TABLE = {"1h": "ohlcv_hourly", "15m": "ohlcv_15m",
            "5m": "ohlcv_5m", "1m": "ohlcv_1m"}
TF_MS = {"1h": 3_600_000, "15m": 900_000, "5m": 300_000,
         "1m": 60_000}


def month_file(sym: str, y: int, m: int) -> list[list] | None:
    return _fetch(f"{BASE}/monthly/klines/{sym}/{TF}/{sym}-{TF}-{y}-{m:02d}.zip")


def day_file(sym: str, d: date) -> list[list] | None:
    return _fetch(f"{BASE}/daily/klines/{sym}/{TF}/{sym}-{TF}-{d.isoformat()}.zip")


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


def bulk_copy(conn_raw, table: str, sym: str, rows: list,
              skip_delete: bool = False) -> int:
    """COPY 로 한 종목을 통째로 넣는다.

    ⚠ 유니크 제약이 없는 상태를 전제한다 — 적재 후 인덱스를 만든다.
      제약을 켜 놓고 COPY 하면 충돌 한 건에 전체가 죽는다.
    ⚠ 중복은 적재 후 인덱스 생성 시 드러난다. 그래서 **종목당 한 번만** 넣고
      재실행 시에는 그 종목을 먼저 지운다.
    """
    import io
    buf = io.StringIO()
    for ts, o, h, l, c, v in rows:
        t = datetime.fromtimestamp(ts / 1000, timezone.utc).replace(tzinfo=None)
        buf.write(f"{sym}\t{t.isoformat(sep=' ')}\t{o}\t{h}\t{l}\t{c}\t{v}\n")
    buf.seek(0)
    cur = conn_raw.cursor()
    # ⚠ 인덱스 없는 테이블에 이걸 매 종목 돌리면 **전체 스캔**이다. 2026-08-17
    #   실측: 1분봉 1.99억 행 적재 중 33,176 → 5,521행/초로 6배 느려졌다.
    #   빈 테이블에 처음 넣을 때는 `--fresh` 로 건너뛴다.
    if not skip_delete:
        cur.execute(f"DELETE FROM {table} WHERE symbol = %s", (sym,))
    cur.copy_expert(
        f"COPY {table} (symbol, ts, open, high, low, close, volume) FROM STDIN",
        buf)
    conn_raw.commit()
    cur.close()
    return len(rows)


def main() -> int:
    p = argparse.ArgumentParser(description="시간봉 수집")
    p.add_argument("--cohort", action="store_true",
                   help="신상저격수 코호트 (상장일 ~ +35일)")
    p.add_argument("--since", default="2025-01-01", help="코호트 상장일 하한")
    p.add_argument("--symbols", default="", help="쉼표 구분 (--cohort 대신)")
    p.add_argument("--from", dest="d_from", default="")
    p.add_argument("--to", dest="d_to", default="")
    p.add_argument("--live", type=int, default=0,
                   help="최근 N시간을 REST 로 받는다 (아카이브 T+1 지연 보완)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tf", default="1h", choices=["1h", "15m", "5m", "1m"])
    p.add_argument("--fresh", action="store_true",
                   help="빈 테이블 전제 — 종목별 DELETE 를 건너뛴다. "
                        "인덱스 없는 큰 테이블에서 DELETE 는 전체 스캔이라 "
                        "적재가 갈수록 느려진다(실측 6배)")
    p.add_argument("--bulk", action="store_true",
                   help="COPY 로 대량 적재. 1분봉처럼 억 단위면 필수 — "
                        "행 단위 INSERT 는 실측 3,768행/초로 1년치가 14.7시간이다")
    a = p.parse_args()

    global TF
    TF = a.tf
    table = TF_TABLE[TF]
    log.info("시간대 %s → 테이블 %s", TF, table)

    from sqlalchemy import text

    from app.db.session import engine

    targets: list[tuple[str, date, date]] = []
    if a.live and not (a.cohort or a.symbols):
        # 활성 신상저격수 세션 종목 — 라이브 사이클이 실제로 필요로 하는 것
        import glob as _glob
        syms_live = set()
        for f in _glob.glob(str(ROOT / "runs" / "paper_sessions" / "*" /
                                "session.json")):
            try:
                d = json.load(open(f))
            except Exception:
                continue
            if d.get("status") == "active" and "lifecycle" in (d.get("name") or ""):
                syms_live.add(d["symbol"])
        targets = [(s_, date.today(), date.today()) for s_ in sorted(syms_live)]
        log.info("라이브 모드 — 활성 세션 %d종목 · 최근 %d시간",
                 len(targets), a.live)
    elif a.cohort:
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
    if a.bulk:
        raw = engine.raw_connection()
        log.info("대량 적재(COPY) 경로")
        for i, (sym, d0, d1) in enumerate(targets, 1):
            try:
                rows = fetch_range(sym, d0, d1)
            except Exception as exc:
                log.warning("[%d/%d] %s 실패: %s", i, len(targets), sym, exc)
                continue
            if not rows:
                miss += 1
                continue
            total += bulk_copy(raw, table, sym, rows, a.fresh)
            if i % 10 == 0 or i == len(targets):
                el = time.time() - t0
                log.info("[%d/%d] %s — 누적 %s행 · %.0f초 · %s행/초 · 남은 %.0f분",
                         i, len(targets), sym, f"{total:,}", el,
                         f"{total/max(el,1):,.0f}",
                         (len(targets) - i) * el / max(i, 1) / 60)
        raw.close()
        print("=" * 76)
        with engine.connect() as c:
            n, s_, t_lo, t_hi = c.execute(text(
                f"SELECT count(*), count(distinct symbol), min(ts), max(ts) "
                f"FROM {table}")).one()
            print(f"  {table}  {n:>12,}행 · 종목 {s_:>4} · {t_lo} ~ {t_hi}")
        print(f"  신규 {total:,}행 · 아카이브 없음 {miss}종목 · {time.time()-t0:.0f}초")
        print("=" * 76)
        return 0
    with engine.connect() as conn:
        for i, (sym, d0, d1) in enumerate(targets, 1):
            try:
                rows = (rest_recent(sym, a.live) if a.live
                        else fetch_range(sym, d0, d1))
            except Exception as exc:
                log.warning("[%d/%d] %s 실패: %s", i, len(targets), sym, exc)
                continue
            if not rows:
                miss += 1
                continue
            new = 0
            for ts, o, h, l, c, v in rows:
                res = conn.execute(text(
                    f"INSERT INTO {table} "
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
            f"FROM {table}")).one()
        print(f"  {table}  {n:>9,}행 · 종목 {s:>4} · {t_lo} ~ {t_hi}")
    print(f"  신규 {total:,}행 · 아카이브 없음 {miss}종목 · {time.time()-t0:.0f}초")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
