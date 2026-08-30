"""`ohlcv_1m` → 5분봉 캐시. 운동학 하네스를 **몇 년치**로 옮기기 위한 기질.

## 왜 (2026-08-30)

오늘 밤 여섯 번 기각했는데 전부 같은 이유로 죽었다 — **표본이 48블록**이다.
틱 기질이 4.3일뿐이라 회전 위약만으로 ±3% 가 나오고, 관측이 +3% 면
아무것도 못 가린다.

그런데 **z_vel 은 틱이 필요 없다**. 선도 승률·속도·가속도가 전부 종가에서
나온다. 익절·손절도 `ohlcv_1m` 에 고가·저가가 있어 그대로 된다. 틱이 꼭
필요했던 축(주문 흐름 불균형)은 이미 기각됐다.

`ohlcv_1m` 은 종목당 377~1,843일이다. 120분 블록으로 **약 4,500개** —
틱의 90배다.

## 왜 5분봉인가

신호의 창이 360분·간격 180분이라 5분 눈금으로 접어도 신호가 거의 안 변한다.
대신 자료가 5분의 1 이 되어 120종목 2년치가 메모리에 들어간다.

⚠ 익절·손절 판정에서 5분봉의 고가·저가를 쓰면 **한 봉 안에서 익절과 손절이
  같이 닿았을 때 순서를 모른다**. 손절이 먼저 닿은 것으로 본다(보수적).

⚠ **캐시한다.** 적재가 종목당 수십 초라 변형을 돌릴 때마다 다시 읽으면 안 된다.

사용:
  python3 -m scripts.research.build_bars5m --smoke 3
  python3 -m scripts.research.build_bars5m --symbols 120 --from 2024-08-01
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runs" / "bars5m"
log = logging.getLogger("bars5m")

Q = text("""
SELECT date_trunc('hour', ts)
         + (floor(extract(minute FROM ts) / 5) * 5) * interval '1 minute' AS b,
       max(high) AS h, min(low) AS l,
       (array_agg(close ORDER BY ts DESC))[1] AS c,
       sum(volume) AS v, count(*) AS n
FROM ohlcv_1m
WHERE symbol = :s AND ts >= :a AND ts < :z
GROUP BY 1 ORDER BY 1
""")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--symbols", type=int, default=120,
                   help="유니버스에서 고르게 뽑을 종목 수")
    p.add_argument("--from", dest="d_from", default="2024-08-01")
    p.add_argument("--to", dest="d_to", default="2026-08-29",
                   help="⚠ 이 표는 하루쯤 뒤처져 있다 — 끝을 넉넉히 끊는다")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--refresh", action="store_true", help="캐시가 있어도 다시 받는다")
    p.add_argument("--out-dir", default="",
                   help="⚠ 구간을 바꿔 받을 땐 **반드시** 다른 경로로. 같은 경로에 "
                        "--refresh 를 쓰면 기존 캐시를 덮어쓴다(2026-08-31 03:23 "
                        "에 실제로 그럴 뻔했다)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    uni = [s.strip().upper() for s in
           (ROOT / a.universe).read_text().split() if s.strip()]
    syms = uni[::max(len(uni) // a.symbols, 1)][:a.symbols]
    if a.smoke:
        syms = syms[:a.smoke]
    global CACHE
    if a.out_dir:
        CACHE = ROOT / a.out_dir
    CACHE.mkdir(parents=True, exist_ok=True)
    log.info("종목 %d · %s ~ %s · 캐시 %s", len(syms), a.d_from, a.d_to, CACHE)

    t0, done, skip, empty, rows = time.time(), 0, 0, 0, 0
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='300s'"))
        for i, s in enumerate(syms, 1):
            f = CACHE / f"{s}.parquet"
            if f.exists() and not a.refresh:
                skip += 1
                rows += len(pd.read_parquet(f, columns=["c"]))
                continue
            try:
                # ⚠ `pd.read_sql` 에 SQLAlchemy Connection + text() 를 주면
                #   "Query must be a string" 로 죽는다. 직접 실행해 받는다.
                res = c.execute(Q, {"s": s, "a": a.d_from, "z": a.d_to})
                d = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
            except Exception as e:                             # noqa: BLE001
                c.rollback(); log.warning("  ✗ %s: %s", s, str(e)[:90]); continue
            if d.empty:
                empty += 1
                continue
            d["b"] = pd.to_datetime(d.b, utc=True)
            d = d.rename(columns={"b": "ts"}).sort_values("ts").reset_index(drop=True)
            d.to_parquet(f, index=False)
            done += 1; rows += len(d)
            if i % 10 == 0 or i == len(syms):
                el = time.time() - t0
                log.info("[%d/%d] 받음 %d · 캐시 %d · 없음 %d · %s봉 · %.1f분 "
                         "· 남은 %.0f분", i, len(syms), done, skip, empty,
                         f"{rows:,}", el/60,
                         (len(syms)-i) * el / max(i-skip, 1) / 60)
    log.info("완료 — 받음 %d · 캐시 %d · 없음 %d · 총 %s봉 · %.1f분",
             done, skip, empty, f"{rows:,}", (time.time()-t0)/60)
    fs = sorted(CACHE.glob("*.parquet"))
    if fs:
        sp = [pd.read_parquet(f, columns=["ts"]) for f in fs[:5]]
        for f, d in zip(fs[:5], sp):
            print(f"  {f.stem:16s} {len(d):>8,}봉  {d.ts.min():%Y-%m-%d} ~ "
                  f"{d.ts.max():%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
