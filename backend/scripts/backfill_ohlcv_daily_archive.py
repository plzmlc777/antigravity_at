"""`ohlcv_daily` 구멍 메우기 — 바이낸스 공개 아카이브 일봉으로.

⚠ 이 도구가 왜 생겼나 (2026-08-15)
    `ohlcv_daily` 는 1분봉 `ohlcv` 에서 유도한다. 그런데 **BTCUSDT·ETHUSDT 만
    139일**이었다(2026-03-27~). ADA·BNB·XRP·SOL·DOGE 는 전부 2,050일인데
    **가장 중요한 두 종목에 정확히 구멍**이 나 있었다.

    그 구멍 때문에 VRP 검정이 0행으로 죽었다. 더 나쁜 건 조용히 죽지 않는
    경우다 — BTC 를 벤치마크·대조군으로 쓰는 분석(알트-BTC 대조 등)은
    **경고 없이 139일짜리 대조군**으로 돌아간다.

    1분봉을 다시 수집하는 대신 **아카이브 일봉을 직접 받는다**. 월별 파일
    하나에 한 달치 일봉이 들어 있어 5.7년이 68개 요청이면 끝난다.

⚠ 원본(`ohlcv`)은 건드리지 않는다
    `ohlcv_daily` 는 읽기 모델이다. 여기에 아카이브 일봉을 넣어도 1분봉
    원본과 충돌하지 않는다. 다만 **출처가 섞이므로** 아카이브에서 온 행은
    `n_minutes = 1440` · `is_partial = false` 로 넣고, 이미 있는 행은
    **덮어쓰지 않는다**(1분봉 유도분이 우선).

출처: data.binance.vision/data/futures/um/monthly/klines/<SYM>/1d/
      무료 · 키 불필요

사용:
  python3 -m scripts.backfill_ohlcv_daily_archive --symbols BTCUSDT,ETHUSDT
  python3 -m scripts.backfill_ohlcv_daily_archive --min-days 200   # 얇은 종목 전부
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
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
log = logging.getLogger("backfill_daily")

BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
WORKERS = 8


def months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def fetch_month(symbol: str, y: int, m: int) -> list[dict]:
    """월별 일봉 zip. 없으면 빈 리스트(상장 전이거나 미공개)."""
    name = f"{symbol}-1d-{y}-{m:02d}.zip"
    url = f"{BASE}/{symbol}/1d/{name}"
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    except Exception as exc:
        log.warning("%s %d-%02d: %s", symbol, y, m, exc)
        return []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if not r or not r[0].strip().isdigit():
            continue                       # 헤더 행이 있는 달이 있다
        try:
            ts = int(r[0])
            # ⚠ 마이크로초로 주는 달이 있다 — 자릿수로 판별한다
            if ts > 10**14:
                ts //= 1000
            d0 = datetime.fromtimestamp(ts / 1000, timezone.utc).date()
            rows.append({"date": d0, "open": float(r[1]), "high": float(r[2]),
                         "low": float(r[3]), "close": float(r[4]),
                         "volume": float(r[5])})
        except (ValueError, IndexError):
            continue
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="ohlcv_daily 아카이브 백필")
    p.add_argument("--symbols", default="", help="쉼표 구분")
    p.add_argument("--min-days", type=int, default=0,
                   help="이 일수 미만인 종목 전부 (게이트 통과분 중)")
    p.add_argument("--since", default="2021-01-01")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine

    since = datetime.fromisoformat(a.since).date()
    end = date.today()

    with engine.connect() as conn:
        have = dict(conn.execute(text(
            "SELECT symbol, count(*) FROM ohlcv_daily WHERE is_partial = false "
            "GROUP BY symbol")).fetchall())

    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    elif a.min_days:
        import json
        gate = ROOT / "configs" / "liquid_universe.json"
        pool = (json.load(open(gate))["symbols"] if gate.exists()
                else list(have))
        syms = [s for s in pool if have.get(s, 0) < a.min_days]
    else:
        raise SystemExit("--symbols 또는 --min-days 중 하나는 필요하다")

    log.info("대상 %d종목 · %s ~ %s", len(syms), since, end)
    if a.dry_run:
        for s in syms[:40]:
            log.info("  %s (현재 %d일)", s, have.get(s, 0))
        return 0

    mons = months(since, end)
    total_new = 0
    with engine.connect() as conn:
        for i, sym in enumerate(syms, 1):
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                chunks = list(ex.map(lambda ym: fetch_month(sym, *ym), mons))
            rows = [r for c in chunks for r in c]
            if not rows:
                log.warning("[%d/%d] %s — 아카이브에 없음", i, len(syms), sym)
                continue
            new = 0
            for r in rows:
                if r["date"] >= end:            # 오늘은 아직 안 닫혔다
                    continue
                # ⚠ 이미 있는 행은 **덮지 않는다** — 1분봉 유도분이 우선이다
                res = conn.execute(text(
                    "INSERT INTO ohlcv_daily (symbol, date, open, high, low, "
                    "close, volume, n_minutes, is_partial, built_at) VALUES "
                    "(:s, :d, :o, :h, :l, :c, :v, 1440, false, now()) "
                    "ON CONFLICT (symbol, date) DO NOTHING"),
                    {"s": sym, "d": r["date"], "o": r["open"], "h": r["high"],
                     "l": r["low"], "c": r["close"], "v": r["volume"]})
                new += res.rowcount or 0
            conn.commit()
            total_new += new
            log.info("[%d/%d] %s — 아카이브 %d일 · **신규 %d일** (기존 %d)",
                     i, len(syms), sym, len(rows), new, have.get(sym, 0))

    print("=" * 76)
    with engine.connect() as c:
        for sym in syms[:12]:
            n, d0, d1 = c.execute(text(
                "SELECT count(*), min(date), max(date) FROM ohlcv_daily "
                "WHERE symbol = :s AND is_partial = false"), {"s": sym}).one()
            print(f"  {sym:<12} {n:>5}일 · {d0} ~ {d1}")
    print(f"  총 신규 {total_new:,}행")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
