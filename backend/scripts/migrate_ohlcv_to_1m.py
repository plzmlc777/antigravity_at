"""구 `ohlcv`(time_frame='1m') → `ohlcv_1m` 결손분 이관.

## 왜 (2026-08-25)

두 테이블이 **같은 1분봉을 두 번** 저장하고 있다. 구 `ohlcv` 는 2.67억 행
47GB(힙 29 + 인덱스 19), `ohlcv_1m` 은 4.13억 행 52GB. 구 쪽은 `id` PK 와
인덱스 4개를 달고 있어 행당 190바이트, 신 쪽은 135바이트다.

실사 결과(60종목 표본):
  · 구 테이블의 time_frame 은 **`1m` 하나뿐** — 5m/15m/1h/1d 는 0건
  · 구에 있는 종목은 **100% 신에도 있다** (구에만 있는 종목 0)
  · 다만 **구간**은 양쪽에 결손이 있다
      구가 더 과거 : 6/24종목 (XLM 2021-01-01 · CHZ 2021-01-21 — 최대 593일)
      구가 더 최신 : 19/24종목 (중앙 6일 — 상시 백필이 구만 채운다)

그래서 구를 지우기 전에 **양방향 결손을 신으로 옮긴다.**

## 방식

종목마다 양쪽 min/max 를 인덱스로 읽고, 빠진 구간만 복사한다.
아카이브에서 새로 받는 것보다 테이블 간 복사가 훨씬 빠르다(네트워크 없음).

⚠ 절대 삭제하지 않는다 — `INSERT ... ON CONFLICT (symbol, ts) DO NOTHING`.
  중간에 죽어도 안전하고, 다시 돌려도 무해하다(재개 가능).
⚠ 종목 열거는 **인덱스 스킵 스캔**을 쓴다. `select distinct symbol` 은
  29GB seq scan 이다 — 오늘 그걸로 40분을 날렸다.

사용:
  python3 -m scripts.migrate_ohlcv_to_1m --dry-run      # 결손만 센다
  python3 -m scripts.migrate_ohlcv_to_1m --commit
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text                                    # noqa: E402

from app.db.session import engine                              # noqa: E402

log = logging.getLogger("mig1m")

# ⚠ symbol 이 인덱스 선두 컬럼이라 스킵 스캔이 먹는다.
SYMS = text("""
WITH RECURSIVE t AS (
    (SELECT symbol FROM ohlcv ORDER BY symbol LIMIT 1)
  UNION ALL
    (SELECT (SELECT symbol FROM ohlcv WHERE symbol > t.symbol
             ORDER BY symbol LIMIT 1) FROM t WHERE t.symbol IS NOT NULL)
)
SELECT symbol FROM t WHERE symbol IS NOT NULL
""")

BOUNDS = text("""
SELECT (SELECT timestamp FROM ohlcv WHERE symbol=:s AND time_frame='1m'
        ORDER BY timestamp ASC  LIMIT 1),
       (SELECT timestamp FROM ohlcv WHERE symbol=:s AND time_frame='1m'
        ORDER BY timestamp DESC LIMIT 1),
       (SELECT ts FROM ohlcv_1m WHERE symbol=:s ORDER BY ts ASC  LIMIT 1),
       (SELECT ts FROM ohlcv_1m WHERE symbol=:s ORDER BY ts DESC LIMIT 1)
""")

COPY = text("""
INSERT INTO ohlcv_1m (symbol, ts, open, high, low, close, volume)
SELECT symbol, timestamp, open, high, low, close, volume
FROM ohlcv
WHERE symbol=:s AND time_frame='1m' AND timestamp >= :a AND timestamp <= :b
ON CONFLICT (symbol, ts) DO NOTHING
""")

CNT = text("SELECT count(*) FROM ohlcv WHERE symbol=:s AND time_frame='1m' "
           "AND timestamp >= :a AND timestamp <= :b")


def gaps(o0, o1, n0, n1):
    """구 테이블이 신보다 더 갖고 있는 구간들. 신이 비어 있으면 통째로."""
    if o0 is None:
        return []
    if n0 is None:
        return [(o0, o1)]
    out = []
    if o0 < n0:
        out.append((o0, n0))            # 앞쪽 — 경계는 겹쳐도 무해(DO NOTHING)
    if o1 > n1:
        out.append((n1, o1))            # 뒤쪽
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--commit", action="store_true", help="실제 이관. 없으면 점검만")
    p.add_argument("--dry-run", action="store_true", help="(기본) 결손만 센다")
    p.add_argument("--limit", type=int, default=0, help="종목 수 제한(시험용)")
    p.add_argument("--symbols", default="", help="쉼표 구분 (열거를 건너뛴다)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    commit = a.commit and not a.dry_run

    t0 = time.time()
    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        with engine.connect() as c:
            c.execute(text("SET statement_timeout='600s'"))
            syms = [r[0] for r in c.execute(SYMS)]
    if a.limit:
        syms = syms[:a.limit]
    log.info("종목 %d (열거 %.0f초) · 모드 %s", len(syms), time.time() - t0,
             "이관" if commit else "점검만")

    tot_rows = tot_ins = n_gap = 0
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='900s'"))
        for i, s in enumerate(syms, 1):
            try:
                o0, o1, n0, n1 = c.execute(BOUNDS, {"s": s}).fetchone()
            except Exception as e:                             # noqa: BLE001
                c.rollback(); log.warning("  ✗ %s 경계 조회 실패: %s", s, e); continue
            g = gaps(o0, o1, n0, n1)
            if not g:
                continue
            n_gap += 1
            for lo, hi in g:
                try:
                    n = c.execute(CNT, {"s": s, "a": lo, "b": hi}).scalar() or 0
                except Exception as e:                         # noqa: BLE001
                    c.rollback(); log.warning("  ✗ %s 계수 실패: %s", s, e); continue
                tot_rows += n
                if not n:
                    continue
                if commit:
                    try:
                        r = c.execute(COPY, {"s": s, "a": lo, "b": hi})
                        c.commit()
                        tot_ins += r.rowcount or 0
                    except Exception as e:                     # noqa: BLE001
                        c.rollback(); log.warning("  ✗ %s 이관 실패: %s", s, e)
                else:
                    log.debug("  %s %s ~ %s : %s행", s, lo, hi, f"{n:,}")
            if i % 25 == 0:
                el = time.time() - t0
                log.info("[%d/%d] 결손종목 %d · 대상 %s행 · 삽입 %s행 · "
                         "%.0f분 · 남은 %.0f분", i, len(syms), n_gap,
                         f"{tot_rows:,}", f"{tot_ins:,}", el / 60,
                         (len(syms) - i) * el / i / 60)
    log.info("완료 — 종목 %d · 결손 있는 종목 %d · 대상 %s행 · 삽입 %s행 · %.0f분",
             len(syms), n_gap, f"{tot_rows:,}", f"{tot_ins:,}",
             (time.time() - t0) / 60)
    if not commit:
        log.info("점검만 했다. 실제 이관은 --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
