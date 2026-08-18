"""모서리 검정 판독 — 익절 5~8% × 손절 2~3% 구역이 **사건인가 전략인가**.

세 검정
    ① 상위 거래 절삭 — 상위 K건을 빼도 남나 (교훈 #81)
       R-1 에서 9/9 PASS 였는데 소수 대박 구조라 포트폴리오가 무너진 전례가 있다.
    ② 종목 집중도  — 몇 종목이 전체 이익을 만드나
       한두 종목이 전부면 전략이 아니라 사건이다 (그룹 C 가설 2 에서 겪음).
    ③ 문턱 고원    — 12·15·18 이 같은 방향인가, 15 만 튀는가

⚠ 세 검정은 **이미 정한 구역 안에서** 깎는 것이다. 격자를 넓히면 최대통계량
   벽에 다시 걸린다 — 그래서 새 파라미터를 추가하지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "runs" / "research_track" / "rsi_tp_sl"
CELL = ["side", "thr", "tp", "sl"]


def sec(t):
    print("\n" + "=" * 104)
    print(t)
    print("=" * 104)


def trades_of(g: pd.DataFrame) -> np.ndarray:
    """칸 하나의 **전 종목 거래**를 한 배열로. 종목별 중앙값이 아니다."""
    out = []
    for s in g.trades_pct.dropna():
        if isinstance(s, str) and s:
            out.extend(float(x) for x in s.split(","))
    return np.array(out, dtype=float)


def main() -> int:
    f = D / "persym_long_short_h48_CORNER.csv"
    if not f.exists():
        f = D / "partial_CORNER.csv"
        print(f"⚠ 본 산출물이 없어 **부분 저장**을 읽는다: {f.name}")
    P = pd.read_csv(f)
    P = P[P.n_trades.notna()].copy()
    if "placebo" not in P.columns:
        P["placebo"] = P.key.str.rsplit("_", n=1).str[-1]
    if "trades_pct" not in P.columns:
        print("trades_pct 열이 없다 — --dump-trades 로 다시 돌려야 한다")
        return 1

    R = P[P.placebo == "real"]
    N = P[P.placebo == "rotate"]
    sec("모서리 검정 — RSI 12/15/18 × 익절 5·8% × 손절 2·3% (전 구간 2021-2026)")
    print(f"  칸 {R.groupby(CELL).ngroups} · 종목 {R.symbol.nunique()} · "
          f"실측 거래 {int(R.n_trades.sum()):,}")

    # ── ① 상위 거래 절삭 ────────────────────────────────────────
    sec("① 상위 거래 절삭 — 큰 몇 건을 빼도 남나 (교훈 #81)")
    print(f"{'방향':<6}{'문턱':>5}{'익절%':>6}{'손절%':>6}{'거래':>8}"
          f"{'전체':>9}{'상위1제외':>11}{'상위5제외':>11}{'상위10제외':>12}"
          f"{'상위1%제외':>12}{'위약 전체':>11}")
    print("-" * 104)
    rows = []
    for k, g in R.groupby(CELL):
        r = trades_of(g)
        if len(r) < 50:
            continue
        srt = np.sort(r)[::-1]
        n1p = max(1, int(round(len(r) * 0.01)))
        gn = N[(N.side == k[0]) & (N.thr == k[1]) & (N.tp == k[2]) & (N.sl == k[3])]
        rn = trades_of(gn)
        cut = {c: float(srt[c:].mean()) for c in (0, 1, 5, 10, n1p)}
        rows.append({"cell": k, "n": len(r), **{f"c{c}": v for c, v in cut.items()},
                     "null": float(rn.mean()) if len(rn) else np.nan,
                     "n1p": n1p})
        print(f"{k[0]:<6}{k[1]:>5.0f}{100*k[2]:>6.0f}{100*k[3]:>6.0f}{len(r):>8,}"
              f"{cut[0]:>+9.3f}{cut[1]:>+11.3f}{cut[5]:>+11.3f}{cut[10]:>+12.3f}"
              f"{cut[n1p]:>+12.3f}"
              + (f"{float(rn.mean()):>+11.3f}" if len(rn) else f"{'-':>11}"))
    T = pd.DataFrame(rows)
    if len(T):
        surv = int(((T.c10 > 0) & (T.c10 > T.null)).sum())
        print(f"\n  상위 10건을 빼고도 **양수이며 위약보다 높은 칸: {surv}/{len(T)}**")
        n_1p = int(T.apply(lambda r: r[f"c{int(r.n1p)}"] > 0, axis=1).sum())
        print(f"  상위 1%를 빼고도 양수인 칸: **{n_1p}/{len(T)}**")
        print("  → 상위 몇 건을 빼자마자 음수가 되면 그건 전략이 아니라 **사건**이다")

    # ── ② 종목 집중도 ──────────────────────────────────────────
    sec("② 종목 집중도 — 몇 종목이 전체 이익을 만드나")
    print(f"{'방향':<6}{'문턱':>5}{'익절%':>6}{'손절%':>6}{'양수종목%':>11}"
          f"{'상위1종목 비중%':>16}{'상위3종목 비중%':>16}{'상위3제외 평균%':>16}")
    print("-" * 104)
    for k, g in R.groupby(CELL):
        if g.n_trades.sum() < 50:
            continue
        s = g.sum_pct.astype(float)
        pos = s[s > 0].sum()
        top1 = s.nlargest(1).sum()
        top3 = s.nlargest(3).sum()
        rest = g[~g.symbol.isin(g.nlargest(3, "sum_pct").symbol)]
        rn = trades_of(rest)
        print(f"{k[0]:<6}{k[1]:>5.0f}{100*k[2]:>6.0f}{100*k[3]:>6.0f}"
              f"{100*float((s>0).mean()):>11.1f}"
              f"{100*top1/pos if pos else np.nan:>16.1f}"
              f"{100*top3/pos if pos else np.nan:>16.1f}"
              f"{float(rn.mean()) if len(rn) else np.nan:>+16.3f}")
    print("\n  → 상위 3종목을 빼도 평균이 양수여야 전략이다")

    # ── ③ 문턱 고원 ────────────────────────────────────────────
    sec("③ 문턱 고원 — 12·15·18 이 같은 방향인가")
    print(f"{'방향':<6}{'익절%':>6}{'손절%':>6}"
          + "".join(f"{'RSI'+str(int(t)):>22}" for t in sorted(R.thr.unique())))
    print(f"{'':>18}" + "".join(f"{'실측 / 위약 / 거래':>22}"
                                for _ in sorted(R.thr.unique())))
    print("-" * 104)
    for (sd, tp, sl), g in R.groupby(["side", "tp", "sl"]):
        row = f"{sd:<6}{100*tp:>6.0f}{100*sl:>6.0f}"
        for t in sorted(R.thr.unique()):
            gg = g[g.thr == t]
            r = trades_of(gg)
            gn = N[(N.side == sd) & (N.thr == t) & (N.tp == tp) & (N.sl == sl)]
            rn = trades_of(gn)
            if len(r) < 30:
                row += f"{'표본부족':>22}"
            else:
                row += (f"{r.mean():>+8.3f}/{rn.mean() if len(rn) else np.nan:>+7.3f}"
                        f"/{len(r):>5,}")
        print(row)
    print("\n  → 12·15·18 이 같은 부호로 매끄러우면 고원, 15 만 튀면 뽑기다")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
