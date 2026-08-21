"""손절이 실제로 얼마나 밀리는지 — 1분봉으로 되짚어 추정한다.

하네스는 손절가에 **정확히** 체결된다고 본다. 스톱은 시장가로 나가므로
그럴 수 없다. 손절 0.3% 짜리 전략에서 이 가정은 결론을 좌우한다.

측정 방법 — 5분봉 거래를 1분봉으로 되짚는다
    ① 진입 시각부터 청산 시각까지의 1분봉을 읽는다
    ② `low <= 손절가` 가 **처음** 성립한 1분봉을 찾는다 = 트리거 순간
    ③ 체결가 추정 두 가지를 같이 낸다
         낙관 = 그 1분봉의 종가   (1분 안에 되돌아온 만큼 회복)
         비관 = 그 1분봉의 저가   (그 분의 최악)
       진짜 체결은 둘 사이에 있다. **둘 다 보고한다** — 하나만 내면
       그게 진실인 척한다.

⚠ 1분봉도 그 안의 체결 순서를 모른다. 이건 상한·하한이지 실측이 아니다.
   진짜 실측은 페이퍼의 `exit_slip_bp` 다(현재 표본 0건).

사용:
  python3 -m scripts.research.rsi_sl_slippage --trades <trades.csv> --sl 0.003
"""
from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from sqlalchemy import text

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.db.session import engine  # noqa: E402

log = logging.getLogger("sl_slip")

Q = text("SELECT ts, high, low, close FROM ohlcv_1m "
         "WHERE symbol=:s AND ts >= :a AND ts <= :b ORDER BY ts")


def one(row) -> tuple[float, float] | None:
    """(낙관 슬리피지 bp, 비관 슬리피지 bp). 양수 = 손해.

    ⚠ 손절가는 **원장의 `exit_price` 를 그대로 쓴다.** 커널이 손절로 청산할
      때 체결가가 곧 손절가다. 이렇게 하면 손절 폭이 격자마다 달라도
      (0.3% / 1% / 3% …) 같은 코드가 그대로 돈다. `--sl` 로 하나를 못 박으면
      폭이 섞인 원장에서 전부 틀린다.
    """
    sym, en, ex, stop = row[:4]
    with engine.connect() as c:
        r = c.execute(Q, {"s": sym, "a": en, "b": ex}).fetchall()
    if not r:
        return None
    for _ts, _h, lo, cl in r:
        if float(lo) <= stop:
            opt = 1e4 * (stop - min(float(cl), stop)) / stop
            pes = 1e4 * (stop - float(lo)) / stop
            return (opt, pes)
    return None                      # 5분봉이 잡은 저가를 1분봉이 확인 못 함


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trades", required=True)
    p.add_argument("--sl", type=float, default=0.003,
                   help="(미사용 — 손절가는 원장 exit_price 에서 읽는다)")
    p.add_argument("--sample", type=int, default=1500,
                   help="손절 거래 표본 수(전수는 DB 부담이 크다)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=20260821)
    p.add_argument("--out", default="",
                   help="거래별 실측 슬리피지를 CSV 로 남긴다. 대표값(평균·중앙)은 "
                        "분포를 못 담는다 — 중앙 25bp 인데 99분위가 2,843bp 다. "
                        "꼬리가 진짜 위험이므로 **거래별로** 붙여 돌려야 한다")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    T = pd.read_csv(a.trades)
    T = T[(T["placebo"] == "real") &
          (T["exit_reason"].astype(str).str.lower() == "sl")]
    log.info("손절 거래 %s건", f"{len(T):,}")
    if len(T) > a.sample:
        T = T.sample(a.sample, random_state=a.seed)
        log.info("표본 %s건 추출", f"{len(T):,}")

    if "exit_price" not in T.columns:
        raise SystemExit("원장에 exit_price 가 없다 — 손절가를 알 수 없다")
    rows = list(zip(T["symbol"], pd.to_datetime(T["entry_ts"]),
                    pd.to_datetime(T["exit_ts"]),
                    T["exit_price"].astype(float)))
    widths = (1e4 * (1.0 - T["exit_price"].astype(float)
                     / T["entry_price"].astype(float))).round(0)
    log.info("원장의 손절 폭 분포(bp): %s",
             dict(widths.value_counts().head(8).sort_index()))
    raw = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        # ⚠ 진행 로그가 없어 남은 시간을 못 알렸다(2026-08-21). N건마다 찍는다.
        for i, r in enumerate(ex.map(one, rows), 1):
            raw.append(r)
            if i % 500 == 0:
                log.info("[%s/%s건]", f"{i:,}", f"{len(rows):,}")
    out = [r for r in raw if r is not None]
    if not out:
        raise SystemExit("측정 가능한 거래가 없다 — 1분봉 구간을 확인하라")

    if a.out:
        # 거래 식별자를 그대로 실어 원장과 붙일 수 있게 한다.
        rec = pd.DataFrame({
            "symbol": T["symbol"].to_numpy(),
            "entry_ts": T["entry_ts"].to_numpy(),
            "exit_ts": T["exit_ts"].to_numpy(),
            "slip_opt_bp": [r[0] if r else np.nan for r in raw],
            "slip_pes_bp": [r[1] if r else np.nan for r in raw],
        })
        rec.to_csv(a.out, index=False)
        log.info("거래별 슬리피지 저장 %s (측정 %d / 미측정 %d)",
                 a.out, int(rec["slip_pes_bp"].notna().sum()),
                 int(rec["slip_pes_bp"].isna().sum()))

    opt = np.array([o for o, _ in out])
    pes = np.array([p for _, p in out])
    log.info("측정 %s/%s건", f"{len(out):,}", f"{len(T):,}")
    print(f"\n{'':<10}{'중앙':>8}{'평균':>8}{'75%':>8}{'90%':>8}"
          f"{'99%':>9}{'최대':>10}")
    for lab, v in (("낙관(종가)", opt), ("비관(저가)", pes)):
        q = np.percentile(v, [50, 75, 90, 99])
        print(f"{lab:<10}{q[0]:>8.1f}{v.mean():>8.1f}{q[1]:>8.1f}"
              f"{q[2]:>8.1f}{q[3]:>9.1f}{v.max():>10.1f}   (bp)")
    w = float(widths.median())
    if w > 0:
        print(f"\n손절 폭 중앙 {w:.0f}bp 대비 — 비관 중앙이 "
              f"{100*np.median(pes)/w:.0f}%, 평균이 {100*pes.mean()/w:.0f}%")
    print("※ 1분봉도 그 안의 체결 순서를 모른다. 상한·하한이지 실측이 아니다.")
    print("   진짜 실측은 페이퍼의 exit_slip_bp — 현재 표본 0건.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
