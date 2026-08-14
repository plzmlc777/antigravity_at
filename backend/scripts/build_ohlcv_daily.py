"""1분봉 → 일봉 캐시 적재. 초기 1회 + 매일 증분.

왜
    `ohlcv` 는 1분봉만 담고 45GB · 2.5억 행이다. 유니버스 스캔은 종목마다 전체
    이력이 필요한데 그건 응답이 안 온다(실측: 11분에 25종목도 못 넘김).

전략 — **종목별 범위 조회로 나눈다**
    통짜 `GROUP BY` 는 전체 스캔이라 안 돌아온다. 종목 하나씩, 시작~끝을 잘라
    도는 방식은 인덱스를 타서 종목당 수 초다(30일 범위 조회 실측 1.4초).

    집계는 **DB 가 한다**. 1분봉을 파이썬으로 끌어오면 그게 병목이다.

⚠ 부분 봉
    `n_minutes < 1440` 이면 `is_partial=True`. 오늘(진행 중)·상장 첫날·데이터
    결손이 여기 걸린다. 소비자가 완전한 봉처럼 쓰면 시가·종가가 틀린다.

⚠ 오늘 날짜는 다시 만든다
    어제까지는 불변이지만 오늘은 계속 자란다. 증분 갱신은 **마지막 완전한
    날짜 다음부터** 다시 계산하고, 오늘 행은 덮어쓴다.

사용:
  python3 -m scripts.build_ohlcv_daily --all           # 초기 적재
  python3 -m scripts.build_ohlcv_daily --incremental   # 매일 (크론)
  python3 -m scripts.build_ohlcv_daily --symbol BTCUSDT
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("build_daily")

# 종목 하나를 한 번에 집계한다. 범위가 좁아 인덱스를 탄다.
# ⚠ `array_agg(... ORDER BY ...)` 를 쓰면 안 된다.
#   시가·종가를 뽑으려고 배열을 만드는데 그게 병목이다. 실측(1000PEPEUSDT,
#   1196일 · 약 170만 행): array_agg **22.2초** vs `row_number()` 윈도우 **2.0초**.
#   11배다. 608 종목이면 17시간 대 30분의 차이가 된다.
#
# ⚠ `timestamp >= :start` 을 항상 붙이면 안 된다.
#   초기 적재는 start 가 사실상 무한 과거라 선택도가 없고, 플래너가 인덱스를
#   버리고 전체 스캔으로 간다(실측: 4일치 종목에 27초). 조건을 빼면
#   (symbol, time_frame) 접두사로 **Index Only Scan** 을 탄다.
#   그래서 전체/증분 두 판본을 따로 둔다.
_AGG_HEAD = """
INSERT INTO ohlcv_daily
    (symbol, date, open, high, low, close, volume, n_minutes, is_partial, built_at)
SELECT :sym, d::date,
       max(open)  FILTER (WHERE ra = 1),
       max(high), min(low),
       max(close) FILTER (WHERE rd = 1),
       sum(volume), count(*), count(*) < 1440, now()
FROM (
    SELECT date_trunc('day', timestamp) AS d,
           open, high, low, close, volume,
           row_number() OVER (PARTITION BY date_trunc('day', timestamp)
                              ORDER BY timestamp)       AS ra,
           row_number() OVER (PARTITION BY date_trunc('day', timestamp)
                              ORDER BY timestamp DESC)  AS rd
    FROM ohlcv
    WHERE symbol = :sym AND time_frame = '1m'
      {ts_filter}
) x
GROUP BY d
ON CONFLICT (symbol, date) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
    close = EXCLUDED.close, volume = EXCLUDED.volume,
    n_minutes = EXCLUDED.n_minutes, is_partial = EXCLUDED.is_partial,
    built_at = EXCLUDED.built_at
"""

AGG_FULL = _AGG_HEAD.replace("{ts_filter}", "")
AGG_INCR = _AGG_HEAD.replace("{ts_filter}", "AND timestamp >= :start")


def symbols(conn) -> list[str]:
    """종목 목록.

    ⚠ `SELECT DISTINCT symbol FROM ohlcv` 를 쓰면 안 된다 — 2.5억 행을 훑느라
      **적재를 시작도 못 한다**(2026-08-14 실측: 500초 타임아웃, 0행).
      상장 목록 파일이 곧 유니버스이므로 그걸 쓴다.
    """
    import json
    lst = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
    if lst.exists():
        try:
            return sorted(json.load(open(lst)))
        except Exception:
            pass
    # 폴백 — 느리지만 목록 파일이 없을 때만
    from sqlalchemy import text
    log.warning("상장 목록 파일 없음 — DISTINCT 스캔 (느림)")
    return [r[0] for r in conn.execute(text(
        "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m' ORDER BY symbol"))]


def build_one(conn, sym: str, start) -> int:
    """start 가 None 이면 전체(인덱스 스캔), 아니면 그 이후만."""
    from sqlalchemy import text
    if start is None:
        r = conn.execute(text(AGG_FULL), {"sym": sym})
    else:
        r = conn.execute(text(AGG_INCR), {"sym": sym, "start": start})
    conn.commit()
    return r.rowcount or 0


def main() -> int:
    p = argparse.ArgumentParser(description="1분봉 → 일봉 캐시")
    p.add_argument("--all", action="store_true", help="전 종목 전체 이력")
    p.add_argument("--incremental", action="store_true",
                   help="종목별 마지막 완전한 날짜 이후만")
    p.add_argument("--symbol", default="")
    p.add_argument("--from-gate", action="store_true",
                   help="유동성 게이트 통과 종목만 (configs/liquid_universe.json). "
                        "전 종목 적재는 4~5시간이고 대부분은 거래도 못 할 종목이다")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    if not (a.all or a.incremental or a.symbol or a.from_gate):
        raise SystemExit("--all / --incremental / --symbol 중 하나를 주십시오")

    from datetime import date, datetime, timedelta

    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        if a.from_gate:
            import json
            gp = ROOT / "configs" / "liquid_universe.json"
            if not gp.exists():
                raise SystemExit(
                    f"{gp} 없음 — 먼저 게이트를 만드십시오:\n"
                    f"  python3 -m scripts.build_liquidity_gate")
            g = json.load(open(gp))
            syms = g["symbols"]
            log.info("게이트 통과 %d종목 (기준 일 $%s, %s)",
                     len(syms), f"{g['min_dollar_vol']:,.0f}", g["built_at"][:10])
        else:
            syms = [a.symbol] if a.symbol else symbols(conn)
        if a.limit:
            syms = syms[:a.limit]
        log.info("대상 %d종목 · 모드 %s", len(syms),
                 "증분" if a.incremental else "전체")

        # 증분: 종목별 **마지막 완전한 날짜** 다음부터. 오늘 행은 어차피 덮어쓴다.
        last_by_sym: dict[str, date] = {}
        if a.incremental:
            for s, d in conn.execute(text(
                    "SELECT symbol, max(date) FROM ohlcv_daily "
                    "WHERE is_partial = false GROUP BY symbol")):
                last_by_sym[s] = d

        t_all = time.time()
        total, done, failed = 0, 0, []
        for i, sym in enumerate(syms, 1):
            start = (datetime.combine(last_by_sym[sym], datetime.min.time())
                     if sym in last_by_sym else None)
            t0 = time.time()
            try:
                n = build_one(conn, sym, start)
            except Exception as exc:
                conn.rollback()
                failed.append(f"{sym}: {type(exc).__name__}: {exc}")
                log.warning("%s 실패: %s", sym, exc)
                continue
            total += n
            done += 1
            if i % 25 == 0 or time.time() - t0 > 20:
                log.info("%d/%d %s +%d행 (%.1f초) · 누적 %s행",
                         i, len(syms), sym, n, time.time() - t0, f"{total:,}")

        print("=" * 72)
        print(f"일봉 적재 — {done}/{len(syms)}종목 · {total:,}행 · "
              f"{time.time() - t_all:.0f}초")
        if failed:
            print(f"실패 {len(failed)}건:")
            for f in failed[:10]:
                print(f"  {f}")
        with engine.connect() as c2:
            n, s, rng, part = c2.execute(text(
                "SELECT count(*), count(distinct symbol), "
                "min(date)::text || ' ~ ' || max(date)::text, "
                "count(*) FILTER (WHERE is_partial) FROM ohlcv_daily")).one()
            print(f"테이블: {n:,}행 · 종목 {s} · {rng} · 부분봉 {part:,}")
        print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
