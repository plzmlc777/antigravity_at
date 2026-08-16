"""일별 프리미엄 수집 — 바이낸스 공개 아카이브 + REST (무료·키 불필요).

## 왜

R-5 시드 `premium_index_zscore` 를 재검정하려면 프리미엄 이력이 필요한데
DB 에 없었다. 소스는 `runtime['premium_df']` (joblib) 를 기대하고, 그 joblib 은
지금 없거나 낡았다.

    주장 (2026-05-06 R-4 gate)  DOGE alpha **+348%** · Sharpe 3.15 ·
                                perm_p 0.0000 · **거래 17건** (기준 30 미달)

## 정의 — 어느 계열을 쓰는가가 중요하다

소비자 `BinancePremiumIndexZScoreSource` 의 정의는

    premium = (mark_close − index_close) / index_close     (1일봉)

바이낸스가 직접 주는 `premiumIndexKlines` 는 impact bid/ask 기반의 **다른
공식**이다. 실측 비교(BTCUSDT 2026-08-12):

    (mark−index)/index  **-0.000412**
    premiumIndex close  **-0.000383**      ← 가깝지만 같지 않다 (~7%)

편한 건 후자 하나만 받는 것이지만, **소비자 정의를 따른다.** 오늘 이미 두 번
"정의가 다른 걸 재는" 실수를 했다(30분봉 RV 재구현 · 시장수익률을 초과수익으로
오독). 두 계열을 각각 저장하고 프리미엄은 유도한다.

## 경로 (전부 실측 확인)

    아카이브  data.binance.vision/data/futures/um/monthly/
                indexPriceKlines/<PAIR>/1d/<PAIR>-1d-YYYY-MM.zip
                markPriceKlines/<SYMBOL>/1d/<SYMBOL>-1d-YYYY-MM.zip
    당월      같은 경로의 daily/ (⚠ 월별 파일은 달이 끝나야 올라온다 —
              오늘만 세 번째 만난 함정)

⚠ `indexPriceKlines` 는 `symbol` 이 아니라 **`pair`** 를 받는다(REST 기준).
  아카이브 경로도 pair 디렉터리다. USDⓈ-M 무기한은 pair == symbol 이다.

사용:
  python3 -m scripts.collect_premium_index --universe --since 2021-01-01
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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("premium")

MONTHLY = "https://data.binance.vision/data/futures/um/monthly"
DAILY = "https://data.binance.vision/data/futures/um/daily"
WORKERS = 8


def parse(blob: bytes) -> dict[date, float]:
    """1일봉 zip → {날짜: 종가}."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        txt = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    out: dict[date, float] = {}
    for r in csv.reader(io.StringIO(txt)):
        if not r or not r[0].strip().isdigit():
            continue                       # 헤더가 있는 달이 있다
        try:
            ts = int(r[0])
            if ts > 10**14:                # 마이크로초로 주는 달이 있다
                ts //= 1000
            out[datetime.fromtimestamp(ts / 1000, timezone.utc).date()] = float(r[4])
        except (ValueError, IndexError):
            continue
    return out


def fetch(url: str) -> dict[date, float]:
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            return parse(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise
    except Exception as exc:
        log.warning("%s: %s", url.rsplit("/", 1)[-1], exc)
        return {}


def series(kind: str, sym: str, months: list[tuple[int, int]],
           days: list[date]) -> dict[date, float]:
    jobs = ([f"{MONTHLY}/{kind}/{sym}/1d/{sym}-1d-{y}-{m:02d}.zip"
             for y, m in months]
            + [f"{DAILY}/{kind}/{sym}/1d/{sym}-1d-{d.isoformat()}.zip"
               for d in days])
    out: dict[date, float] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for chunk in ex.map(fetch, jobs):
            out.update(chunk)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="일별 프리미엄 수집")
    p.add_argument("--universe", action="store_true",
                   help="`ohlcv_daily` 유동성 통과 종목")
    p.add_argument("--symbols", default="")
    p.add_argument("--since", default="2021-01-01")
    p.add_argument("--min-adv", type=float, default=3e6)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    from sqlalchemy import text
    from psycopg2.extras import execute_values

    from app.db.session import engine

    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    elif a.universe:
        with engine.connect() as c:
            syms = [r[0] for r in c.execute(text(
                "SELECT symbol FROM ohlcv_daily WHERE date >= :d "
                "GROUP BY symbol HAVING avg(close*volume) >= :v "
                "ORDER BY avg(close*volume) DESC"),
                {"d": a.since, "v": a.min_adv})]
    else:
        raise SystemExit("--universe 또는 --symbols 가 필요하다")
    if a.limit:
        syms = syms[:a.limit]

    d0 = datetime.fromisoformat(a.since).date()
    d1 = date.today()
    months, y, m = [], d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        if (y, m) != (d1.year, d1.month):
            months.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    days = [date(d1.year, d1.month, x) for x in range(1, d1.day + 1)]
    log.info("대상 %d종목 · 월별 %d개 + 당월 일별 %d개",
             len(syms), len(months), len(days))

    raw = engine.raw_connection()
    total, miss, t0 = 0, 0, time.time()
    try:
        cur = raw.cursor()
        for i, sym in enumerate(syms, 1):
            idx = series("indexPriceKlines", sym, months, days)
            mrk = series("markPriceKlines", sym, months, days)
            common = sorted(set(idx) & set(mrk))
            if not common:
                miss += 1
                continue
            buf = []
            for d in common:
                iv, mv = idx[d], mrk[d]
                if not (iv > 0):
                    continue
                buf.append((sym, d, iv, mv, (mv / iv - 1.0)))
            if not buf:
                miss += 1
                continue
            execute_values(cur,
                           "INSERT INTO binance_premium_index "
                           "(symbol, date, index_close, mark_close, premium, "
                           "built_at) VALUES %s "
                           "ON CONFLICT (symbol, date) DO NOTHING",
                           buf, template="(%s,%s,%s,%s,%s,now())",
                           page_size=5000)
            raw.commit()
            total += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            if i % 20 == 0:
                log.info("[%d/%d] %s — 누적 %s행 (%.0f초)",
                         i, len(syms), sym, f"{total:,}", time.time() - t0)
    finally:
        raw.close()

    print("=" * 76)
    with engine.connect() as c:
        n, s, lo, hi = c.execute(text(
            "SELECT count(*), count(distinct symbol), min(date), max(date) "
            "FROM binance_premium_index")).one()
        print(f"  binance_premium_index  {n:>9,}행 · 종목 {s:>4} · {lo} ~ {hi}")
        av = c.execute(text(
            "SELECT avg(premium)*100, stddev(premium)*100 "
            "FROM binance_premium_index")).one()
        print(f"  프리미엄 평균 {av[0]:+.4f}% · 표준편차 {av[1]:.4f}%")
    print(f"  신규 {total:,}행 · 이력 없음 {miss}종목 · {time.time()-t0:.0f}초")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
