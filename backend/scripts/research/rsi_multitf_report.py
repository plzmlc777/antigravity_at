"""시간대 3종 판독 — **총손익이 주축**이다.

⚠ 거래당 엣지만 보면 결론이 뒤집힌다 (2026-08-18 실측)
    문턱을 내리면 엣지가 커지고 빈도가 준다. 거래당만 보면 항상 "더 조일수록
    좋다"가 나오지만, **빈도×엣지의 곱**이 최대인 지점이 답이다.
      문턱 5 : 종목·연당 0.68건 · 거래당 +7.000% · 총손익 +658%
      문턱 8 : 종목·연당 1.62건 · 거래당 +3.621% · 총손익 **+807%**  ← 답
      문턱 12: 종목·연당 7.25건 · 거래당 +0.430% · 총손익 +430%

⚠ 승률은 성과가 아니다 — 익절/손절 비율의 기하학이다. 보조 열로만 둔다.
⚠ 총손익도 단독으론 부족하다 — 소수 사건 구조를 배제하려면 상위거래 절삭과
   종목 집중도를 같이 본다 (교훈 #81).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "runs" / "research_track" / "rsi_tp_sl"


def load(tag: str) -> tuple:
    for name in (f"persym_long_{tag}.csv", f"partial_{tag}.csv"):
        for p in D.glob(name.replace("persym_long_", "persym_long_*")) if "persym" in name else [D / name]:
            if p.exists():
                P = pd.read_csv(p)
                P = P[P.n_trades.notna()].copy()
                P["placebo"] = P.key.str.rsplit("_", n=1).str[-1]
                return P, p.name
    return None, None


def report(tag: str, label: str) -> None:
    from scripts.research.rsi_corner_report import trades_of
    P, src = load(tag)
    if P is None:
        print(f"\n[{label}] 산출물 없음")
        return
    R, N = P[P.placebo == "real"], P[P.placebo == "rotate"]
    nsym = R.symbol.nunique()
    part = "**부분**" if src.startswith("partial") else "완주"
    print(f"\n{'='*96}\n[{label}] {part} · 종목 {nsym} · 실측 거래 {int(R.n_trades.sum()):,}\n{'='*96}")
    print(f"{'문턱':>5}{'익절%':>6}{'손절%':>7}{'거래':>8}{'종목연당':>9}"
          f"{'총손익%':>11}{'위약%':>10}{'초과총손익%p':>14}"
          f"{'거래당%':>9}{'승률%':>7}{'상위10제외 총손익%':>19}")
    print("-" * 96)
    rows = []
    for (t, tp, sl), g in R.groupby(["thr", "tp", "sl"]):
        r = trades_of(g)
        if len(r) < 20:
            continue
        gn = N[(N.thr == t) & (N.tp == tp) & (N.sl == sl)]
        rn = trades_of(gn)
        tot, totn = r.sum(), (rn.sum() if len(rn) else np.nan)
        c10 = np.sort(r)[::-1][10:].sum()
        rows.append({"thr": t, "tp": tp, "sl": sl, "n": len(r),
                     "tot": tot, "ex": tot - totn, "c10": c10})
        print(f"{t:>5.0f}{100*tp:>6.0f}{100*sl:>7.1f}{len(r):>8,}{len(r)/nsym:>9.2f}"
              f"{tot:>+11.1f}{totn:>+10.1f}{tot-totn:>+14.1f}"
              f"{r.mean():>+9.3f}{100*(r>0).mean():>7.1f}{c10:>+19.1f}")
    if not rows:
        return
    T = pd.DataFrame(rows)
    b = T.loc[T.ex.idxmax()]
    print(f"\n  초과 총손익 최고 — 문턱 {b.thr:.0f} · 익절 {100*b.tp:.0f}% / 손절 {100*b.sl:.1f}%"
          f" → **{b.ex:+.1f}%p** (총손익 {b.tot:+.1f}% · 거래 {int(b.n):,}"
          f" · 상위10제외 {b.c10:+.1f}%)")
    print(f"  위약을 이긴 칸 {int((T.ex>0).sum())}/{len(T)}"
          f" · 상위10 빼도 양수 {int((T.c10>0).sum())}/{len(T)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="MTF15:15분봉,MTF5:5분봉,MTF1:1분봉")
    a = ap.parse_args()
    for item in a.tags.split(","):
        tag, label = item.split(":")
        report(tag, label)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
