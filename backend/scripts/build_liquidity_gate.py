"""유동성 게이트 — 어떤 종목을 아예 볼 것인지 먼저 정한다.

왜 먼저인가
    `ohlcv` 는 45GB · 2.5억 행이고 **차가운 읽기가 병목**이다. 이력 긴 종목
    하나가 275초라 608종목 전체 일봉 적재는 4~5시간이다(2026-08-14 실측).

    그런데 그중 상당수는 **거래도 못 할 종목**이다. 기억의 교훈 #78:
    "자동구성 코호트는 유동성 필터 필수. 실측 +0.60% → $1M 필터 시 **-0.25% 로
    부호 반전**". 즉 게이트는 속도 문제이기 전에 **정확성 문제**다.

    그래서 순서를 뒤집는다 — 게이트를 먼저 만들고 **통과한 종목만** 일봉을
    적재한다.

어떻게 재나
    최근 30일 1분봉의 `close * volume` **중앙값**을 일 환산한다.
      · 범위가 좁아 인덱스를 탄다 (종목당 3~4초)
      · **중앙값**을 쓰는 이유 — 평균은 상장일 폭발 거래량 하나에 끌려간다
      · 최근 30일이라 **지금 거래 가능한가**를 답한다. 과거 유동성은 의미 없다

    상장 30일 미만 종목은 표본이 짧아 별도 표시한다(`is_new`). 신규 상장을
    버리지는 않는다 — 그건 별개 판단이다.

사용:
  python3 -m scripts.build_liquidity_gate --min-dollar-vol 1000000
  python3 -m scripts.build_liquidity_gate --out configs/liquid_universe.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("liq_gate")

OUT = ROOT / "configs" / "liquid_universe.json"
LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"

PROBE_SQL = """
SELECT count(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY close * volume) AS med_dv,
       min(timestamp) AS t0, max(timestamp) AS t1
FROM ohlcv
WHERE symbol = :s AND time_frame = '1m'
  AND timestamp >= now() - (:days || ' days')::interval
"""


def main() -> int:
    p = argparse.ArgumentParser(description="유동성 게이트 산출")
    p.add_argument("--days", type=int, default=30, help="최근 며칠로 재나")
    p.add_argument("--min-dollar-vol", type=float, default=1_000_000,
                   help="일 거래대금 중앙값 하한 (기본 $1M — 교훈 #78)")
    p.add_argument("--min-minutes", type=int, default=5_000,
                   help="이 기간 최소 1분봉 수 (데이터 결손 배제)")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine

    universe = sorted(json.load(open(LISTINGS)))
    if a.limit:
        universe = universe[:a.limit]
    log.info("후보 %d종목 · 최근 %d일 · 하한 일 $%s",
             len(universe), a.days, f"{a.min_dollar_vol:,.0f}")

    rows, t_all = [], time.time()
    with engine.connect() as conn:
        for i, sym in enumerate(universe, 1):
            try:
                r = conn.execute(text(PROBE_SQL),
                                 {"s": sym, "days": a.days}).one()
            except Exception as exc:
                log.warning("%s 실패: %s", sym, exc)
                continue
            n, med, t0, t1 = r
            if not n:
                continue
            dv_day = float(med or 0) * 1440
            rows.append({
                "symbol": sym, "n_minutes": int(n),
                "dollar_vol_day": dv_day,
                "first": str(t0)[:19], "last": str(t1)[:19],
                # 표본이 짧다 = 최근 상장. 버리지 않고 표시만 한다
                "is_new": int(n) < a.days * 1440 * 0.8,
                "pass": dv_day >= a.min_dollar_vol and int(n) >= a.min_minutes,
            })
            if i % 50 == 0:
                log.info("%d/%d · 통과 %d · %.0f초",
                         i, len(universe), sum(1 for x in rows if x["pass"]),
                         time.time() - t_all)

    passed = [r for r in rows if r["pass"]]
    passed.sort(key=lambda r: -r["dollar_vol_day"])
    out = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "probe_days": a.days,
        "min_dollar_vol": a.min_dollar_vol,
        "min_minutes": a.min_minutes,
        "n_candidates": len(universe), "n_probed": len(rows),
        "n_pass": len(passed),
        "symbols": [r["symbol"] for r in passed],
        "detail": passed,
        "rejected": sorted([r for r in rows if not r["pass"]],
                           key=lambda r: -r["dollar_vol_day"])[:40],
    }
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("=" * 78)
    print(f"유동성 게이트 — 후보 {len(universe)} · 조회됨 {len(rows)} · "
          f"**통과 {len(passed)}** ({time.time()-t_all:.0f}초)")
    print(f"기준: 일 거래대금 중앙값 >= ${a.min_dollar_vol:,.0f} · "
          f"최근 {a.days}일 1분봉 >= {a.min_minutes:,}")
    print("=" * 78)
    print(f"  {'종목':<14}{'일 거래대금':>16}{'분봉':>9}  신규")
    for r in passed[:15]:
        print(f"  {r['symbol']:<14}${r['dollar_vol_day']:>15,.0f}"
              f"{r['n_minutes']:>9}  {'예' if r['is_new'] else ''}")
    if len(passed) > 15:
        print(f"  … 외 {len(passed)-15}종목")
    print("-" * 78)
    print(f"  탈락 상위(거의 통과한 것들):")
    for r in out["rejected"][:5]:
        print(f"  {r['symbol']:<14}${r['dollar_vol_day']:>15,.0f}"
              f"{r['n_minutes']:>9}")
    print("=" * 78)
    print(f"  → {a.out}")
    print(f"  다음: python3 -m scripts.build_ohlcv_daily --from-gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
