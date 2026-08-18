"""RSI 15 · 익절/손절 최적화 판독 — 최적화 구간과 **표본 밖**을 나란히.

⚠ 종목당 거래가 9건 남짓이다 (1년 · 문턱 15 · 게이트 0.1%)
    그래서 **종목별 중앙값**은 못 쓴다. 9건짜리 승률은 0/11/22/33% 처럼
    계단으로만 움직인다. 여기서는 **거래 가중 합산(pooled)** 을 주축으로 쓴다:
        pooled 평균 = Σ(nᵢ · avgᵢ) / Σnᵢ      ← 전체 거래의 평균과 같다
        pooled 승률 = Σ(nᵢ · winᵢ) / Σnᵢ
    종목 분산은 **양수 종목 비율**로 따로 본다.

⚠ 1년으로 고른 최적값은 그 1년에 대한 서술이다
    직전 1년(표본 밖)에서 같은 칸이 어떻게 되는지 **같은 표에** 놓는다.
    최적 칸이 표본 밖에서 무너지면 그건 최적화가 아니라 과적합이다.

⚠ 격자를 뒤졌으므로 최고 칸은 최대통계량으로 (교훈 #95)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "runs" / "research_track" / "rsi_tp_sl"
CELL = ["side", "tp", "sl"]


def sec(t):
    print("\n" + "=" * 106)
    print(t)
    print("=" * 106)


def pooled(P: pd.DataFrame) -> pd.DataFrame:
    """거래 가중 합산. 종목당 표본이 얇을 때 중앙값은 못 쓴다."""
    P = P[P.n_trades.notna()].copy()
    if "placebo" not in P.columns:
        P["placebo"] = P.key.str.rsplit("_", n=1).str[-1]

    def agg(g):
        n = g.n_trades.to_numpy(float)
        tot = n.sum()
        if tot <= 0:
            return pd.Series({"trades": 0})
        return pd.Series({
            "trades": int(tot),
            "n_sym": int(g.symbol.nunique()),
            "avg": float((n * g.avg_pct).sum() / tot),
            "win": float((n * g.win_rate_calc).sum() / tot),
            "aw": float((n * g.avg_win.fillna(0)).sum() / tot),
            "al": float((n * g.avg_loss.fillna(0)).sum() / tot),
            "pos_sym": 100.0 * float((g.sum_pct > 0).mean()),
            "sym_med": float(g.sum_pct.median()),
        })
    return P.groupby(CELL + ["placebo"]).apply(agg,
                                               include_groups=False).reset_index()


def wide(A: pd.DataFrame) -> pd.DataFrame:
    W = A.pivot_table(index=CELL, columns="placebo",
                      values=["avg", "win", "trades", "pos_sym"]).reset_index()
    W.columns = ["_".join([c for c in col if c]).strip("_")
                 for col in W.columns.to_flat_index()]
    return W


def main() -> int:
    f_opt = D / "persym_long_short_h48_2025-08-17_2026-08-17_OPT.csv"
    f_oos = D / "persym_long_short_h48_2024-08-17_2025-08-17_OOS.csv"
    if not f_opt.exists():
        print(f"최적화 구간 산출물이 없다: {f_opt.name}")
        return 1
    O = wide(pooled(pd.read_csv(f_opt)))
    S = wide(pooled(pd.read_csv(f_oos))) if f_oos.exists() else None

    sec("RSI(14) ≤ 15 롱 / ≥ 85 숏 — 익절·손절 최적화")
    print("  최적화 구간 2025-08-17 ~ 2026-08-17 (최근 1년) · 보유상한 48봉 · 85종목")
    print(f"  칸 {len(O)} · 실측 총 거래 {int(O.trades_real.sum()):,}")
    print("  ⚠ 종목당 거래가 얇아 **거래 가중 합산**으로 본다 (종목 중앙값 아님)")
    print("  ⚠ 마찰 미반영. 왕복 4bp(메이커)/10bp(테이커) 를 빼고 읽어라")

    # ── ① 익절 × 손절 격자 — 거래당 평균 ────────────────────────
    sec("① 격자 — 거래당 평균 % (실측, 마찰 前)")
    for side in ("long", "short"):
        q = O[O.side == side]
        if q.empty:
            continue
        print(f"\n  ── {side} ({'RSI≤15' if side=='long' else 'RSI≥85'}) ──")
        print(f"{'손절\\익절':>10}" + "".join(f"{100*t:>11.0f}%"
                                            for t in sorted(q.tp.unique())))
        for sl in sorted(q.sl.unique()):
            row = f"{100*sl:>9.1f}%"
            for tp in sorted(q.tp.unique()):
                r = q[(q.tp == tp) & (q.sl == sl)]
                row += (f"{r.avg_real.iloc[0]:>+12.3f}" if len(r) else f"{'-':>12}")
            print(row)

    # ── ② 위약 대비 ────────────────────────────────────────────
    sec("② 회전 위약 대비 — RSI 가 한 일인가")
    O["edge"] = O.avg_real - O.avg_rotate
    print(f"  실측 pooled 중앙 {O.avg_real.median():+.3f}% · "
          f"위약 {O.avg_rotate.median():+.3f}% · 차이 {O.edge.median():+.3f}%p")
    print(f"  실측이 위약을 이긴 칸 **{int((O.edge > 0).sum())}/{len(O)}**")
    print(f"  최대통계량 — 실측 최고 {O.avg_real.max():+.3f}% vs "
          f"위약 최고 {O.avg_rotate.max():+.3f}% → "
          f"{'넘었다' if O.avg_real.max() > O.avg_rotate.max() else '**못 넘었다**'}")

    # ── ③ 최적 칸과 표본 밖 ────────────────────────────────────
    sec("③ 최적 칸 — 그리고 **직전 1년(표본 밖)** 에서의 같은 칸")
    top = O.nlargest(10, "avg_real")
    if S is not None:
        top = top.merge(S, on=CELL, how="left", suffixes=("", "_oos"))
    print(f"{'방향':<7}{'익절%':>7}{'손절%':>7}{'거래':>9}{'승률%':>8}"
          f"{'거래당%':>10}{'위약%':>9}{'초과':>9}{'양수종목%':>11}"
          + (f"{'OOS 거래당%':>13}{'OOS 거래':>10}" if S is not None else ""))
    print("-" * 106)
    for _, r in top.iterrows():
        extra = ""
        if S is not None:
            v = r.get("avg_real_oos", np.nan)
            t = r.get("trades_real_oos", np.nan)
            extra = (f"{v:>+13.3f}{int(t):>10,}" if pd.notna(v)
                     else f"{'-':>13}{'-':>10}")
        print(f"{r.side:<7}{100*r.tp:>7.1f}{100*r.sl:>7.1f}"
              f"{int(r.trades_real):>9,}{r.win_real:>8.2f}{r.avg_real:>+10.3f}"
              f"{r.avg_rotate:>+9.3f}{r.avg_real-r.avg_rotate:>+9.3f}"
              f"{r.pos_sym_real:>11.1f}{extra}")

    if S is not None:
        M = O.merge(S, on=CELL, suffixes=("_in", "_out"))
        best = M.loc[M.avg_real_in.idxmax()]
        rho = M[["avg_real_in", "avg_real_out"]].corr().iloc[0, 1]
        sec("④ 과적합 판정 — 최적화 구간 vs 표본 밖")
        print(f"  최적 칸: {best.side} 익절 {100*best.tp:.1f}% / 손절 {100*best.sl:.1f}%")
        print(f"    최적화 구간 {best.avg_real_in:+.3f}%  →  "
              f"표본 밖 **{best.avg_real_out:+.3f}%**")
        print(f"  칸별 상관(최적화 vs 표본 밖) **{rho:+.3f}**")
        print(f"  두 구간 모두 양수인 칸 "
              f"**{int(((M.avg_real_in>0)&(M.avg_real_out>0)).sum())}/{len(M)}**")
        print(f"  표본 밖 pooled 중앙 {M.avg_real_out.median():+.3f}% "
              f"(최적화 구간 {M.avg_real_in.median():+.3f}%)")
        print("\n  → 상관이 0 근처거나 최적 칸이 표본 밖에서 음수면 **과적합**이다.")

    # ── ⑤ 마찰 ────────────────────────────────────────────────
    sec("⑤ 마찰 반영 — 거래당 평균은 상수 이동이라 정확하다")
    print(f"{'왕복bp':>8}{'실측>0 칸':>12}{'실측 중앙%':>13}{'위약 중앙%':>13}"
          + ("" if S is None else f"{'표본밖>0 칸':>14}"))
    print("-" * 106)
    for bp in (0, 4, 10):
        c = bp / 100.0
        line = (f"{bp:>8}{int((O.avg_real-c > 0).sum()):>9}/{len(O):<3}"
                f"{(O.avg_real-c).median():>+13.3f}"
                f"{(O.avg_rotate-c).median():>+13.3f}")
        if S is not None:
            line += f"{int((S.avg_real-c > 0).sum()):>11}/{len(S):<3}"
        print(line)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
