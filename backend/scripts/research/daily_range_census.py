"""일일 한 방 거래의 **천장** — 하루에 2.4% 가 열리기는 하는가.

## 왜 이것부터 (2026-08-27)

"하루 한 종목 한 거래로 2.4%" 를 검토하려면 순서가 있다. 종목 선별이 완벽하다
쳐도 **그 폭이 애초에 안 나오면** 뒤는 볼 필요가 없다. 그래서 천장부터 잰다.

    ① 천장   그날 그 종목이 2.4% 를 열었나 (방향까지 맞혔다 치고)
    ② 방향   지지·저항 규칙이 동전보다 나은가
    ③ 도달   손절 전에 익절에 닿았나

이 도구는 ①만 한다. ②·③ 은 봉 순서를 알아야 하므로 별도 하네스가 필요하다.

⚠ 일봉 고가·저가는 **순서를 모른다**. 롱을 걸었는데 저가가 먼저 왔으면 손절이
  먼저다. 그래서 여기 숫자는 전부 **낙관적 상한**이다. 상한이 못 넘으면
  실제는 확실히 못 넘는다 — 그게 이 관문의 쓸모다.

⚠ 기질은 `ohlcv_1m` 이다(RSI 트랙 정본). `ohlcv_daily` 는 오염이 미해결이고
  `ohlcv` 는 2026-08-25 에 버렸다.

⚠ **일수부터 찍는다.** BTC·ETH 는 최근 365일 중 140일뿐이다(실측). 커버리지
  결손을 모르고 유니버스를 평균 내면 조용히 틀린다 — 교훈#99 와 같은 함정.

사용:
  python3 -m scripts.research.daily_range_census --days 365 --smoke 10
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
OUT = ROOT / "runs" / "research_track" / "daily_range"
log = logging.getLogger("day_range")

Q = text("""
SELECT symbol, (ts AT TIME ZONE 'UTC')::date AS d, count(*) AS n_bars,
       min(low) AS lo, max(high) AS hi,
       (array_agg(open  ORDER BY ts))[1]      AS op,
       (array_agg(close ORDER BY ts DESC))[1] AS cl
FROM ohlcv_1m
WHERE symbol = ANY(:syms) AND ts >= :t0
GROUP BY 1, 2
""")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--batch", type=int, default=15)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--sleep", type=float, default=0.5,
                   help="배치 사이 쉼 — 실거래가 같은 DB 를 쓴다")
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    log.info("일봉 집계 — %d종목 · 최근 %d일 · 배치 %d", len(syms), a.days, a.batch)

    t0 = time.time()
    t_from = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=a.days)
    parts = []
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='300s'"))
        for i in range(0, len(syms), a.batch):
            chunk = syms[i:i + a.batch]
            r = c.execute(Q, {"syms": chunk, "t0": t_from})
            parts.append(pd.DataFrame(r.fetchall(), columns=r.keys()))
            done = min(i + a.batch, len(syms))
            if done % (a.batch * 5) == 0 or done == len(syms):
                el = time.time() - t0
                log.info("[%d/%d] 행 %s · %.1f분 · 남은 %.1f분", done, len(syms),
                         f"{sum(len(x) for x in parts):,}", el / 60,
                         (len(syms) - done) * el / done / 60)
            time.sleep(a.sleep)

    D = pd.concat(parts, ignore_index=True)
    for col in ("lo", "hi", "op", "cl"):
        D[col] = D[col].astype(float)
    D["d"] = pd.to_datetime(D["d"])
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / f"daily_range_{a.days}d.csv"
    D.to_csv(path, index=False)
    log.info("저장 %s — %s행 · 종목 %d · 날짜 %d · %.1f분", path, f"{len(D):,}",
             D.symbol.nunique(), D.d.nunique(), (time.time() - t0) / 60)

    # ── 커버리지부터. 평균 내기 전에 일수를 본다
    cov = D.groupby("symbol").d.nunique().sort_values()
    full = int(D.d.nunique())
    print(f"\n■ 커버리지 — 최대 {full}일")
    for lab, lo, hi in [("완전(≥95%)", 0.95, 1.01), ("부분(50~95%)", 0.5, 0.95),
                        ("결손(<50%)", 0.0, 0.5)]:
        m = cov[(cov >= lo * full) & (cov < hi * full)]
        print(f"    {lab:<14} {len(m):>4}종목")
    print(f"    가장 얇은 5: "
          + ", ".join(f"{s}({n}일)" for s, n in cov.head(5).items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
