"""RSI 극단 진입 × 마틴게일 판독 (대표님 지시 2026-08-17).

규칙
    RSI(14) <= 15  → **롱** 마틴게일 사이클 시작
    RSI(14) >= 85  → **숏** 마틴게일 사이클 시작
    이후는 기존 사다리 그대로 (스텝마다 물타기, 평단+tp 익절, 손절/파산)

무엇을 조심하는가
    ① **교차 대조** — 롱을 85 에, 숏을 15 에 걸어도 같이 돈다. 방향이 맞아야
       이기는지 본다. 둘 다 이기면 "RSI 극단"이 아니라 그냥 변동성이다.
    ② **회전 위약** — 게이트 빈도는 같고 시점만 무관. 못 이기면 RSI 는
       "거래를 줄인 것" 이상이 아니다.
    ③ **검정력** — RSI<=15 는 드물게 열린다. 사이클이 얇으면 판정하지 않는다.
    ④ 관측 단위는 **종목당 생존**(자본 누적 · 파산 시 종목 종료).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "runs" / "research_track" / "martingale_ruin"
LADDER = ["side", "step_bp", "mult", "cap", "sl"]
FKEY = ["filter", "fmode", "fthr"]
MIN_CYCLES = 30


def sec(t):
    print("\n" + "=" * 110)
    print(t)
    print("=" * 110)


def lab(r):
    if r["filter"] == "none":
        return "무필터"
    v = r.fthr * 100
    return f"RSI{'<=' if r.fmode == 'low' else '>='}{v:.0f}"


def aligned(side, fmode):
    """대표님 규칙과 방향이 맞는 조합인가 — 롱↔low(과매도) / 숏↔high(과매수)."""
    return (side == "long" and fmode == "low") or (side == "short" and fmode == "high")


def main() -> int:
    A = pd.read_csv(D / "agg_long_short_1h_strict_persist_halt_level_filt_RSIGATE.csv")
    N = pd.read_csv(D / "agg_long_short_1h_strict_persist_halt_level_filtnull_RSIGATE.csv")
    A["lab"] = A.apply(lab, axis=1)
    N["lab"] = N.apply(lab, axis=1)
    A["aligned"] = [aligned(s, m) for s, m in zip(A.side, A.fmode)]

    sec("RSI 극단 진입 × 마틴게일 — 롱 RSI≤15 / 숏 RSI≥85")
    print(f"  격자 {len(A)}칸 · 종목 {A.n_sym.max()} · 사이클 {A.n_cycles.sum():,}")
    print("  계좌: 자본 누적 · 파산하면 그 종목 종료 → **파산률은 종목당 비율**")

    # ── ① 검정력 사전검사 ───────────────────────────────────────
    sec("① 검정력 — RSI 극단은 드물게 열린다. 사이클이 몇 개나 쌓였나")
    F = A[A["filter"] != "none"]
    print(f"{'조건':<12}{'방향':<7}{'게이트%':>9}{'사이클 중앙':>13}"
          f"{'판정가능 칸':>14}{'칸':>6}")
    print("-" * 110)
    for (l, s), g in F.groupby(["lab", "side"]):
        ok = int((g.n_cycles / g.n_sym >= MIN_CYCLES).sum())
        mark = "  ← 대표님 규칙" if aligned(s, g.fmode.iloc[0]) else ""
        print(f"{l:<12}{s:<7}{g.gate_open_pct.median():>9.2f}"
              f"{(g.n_cycles/g.n_sym).median():>13.0f}{ok:>10}/{len(g):<3}"
              f"{len(g):>6}{mark}")

    # ── ② 방향이 맞아야 이기나 (교차 대조) ──────────────────────
    sec("② 교차 대조 — 방향이 맞아야 이기나")
    nof = A[A["filter"] == "none"].set_index(LADDER)
    rows = []
    for (l, s, al), g in F.groupby(["lab", "side", "aligned"]):
        de, w, d = [], 0, 0
        for _, r in g.iterrows():
            k = tuple(r[c] for c in LADDER)
            if k not in nof.index:
                continue
            b = float(nof.loc[k].med_final_equity)
            d += 1
            w += int(r.med_final_equity > b)
            de.append(r.med_final_equity - b)
        rows.append({"lab": l, "side": s, "aligned": al, "n": d, "win": w,
                     "d_eq": float(np.median(de)) if de else np.nan,
                     "equity": float(g.med_final_equity.median()),
                     "ruin": float(g.sym_ruin_pct.median()),
                     "cyc": float((g.n_cycles / g.n_sym).median())})
    R = pd.DataFrame(rows)
    print(f"{'조건':<12}{'방향':<7}{'정방향':>8}{'최종자본%':>12}{'무필터대비%p':>15}"
          f"{'무필터 이긴 칸':>16}{'종목파산%':>11}{'사이클':>9}")
    print("-" * 110)
    for _, r in R.sort_values(["aligned", "d_eq"], ascending=[False, False]).iterrows():
        print(f"{r.lab:<12}{r.side:<7}{'예' if r.aligned else '아니오':>8}"
              f"{r['equity']:>12.1f}{r.d_eq:>+15.1f}{r.win:>10}/{r.n:<5}"
              f"{r.ruin:>11.1f}{r.cyc:>9.0f}")
    al = R[R.aligned]
    cr = R[~R.aligned]
    print(f"\n  정방향(대표님 규칙) 무필터대비 중앙 **{al.d_eq.median():+.1f}%p**")
    print(f"  역방향(교차 대조)   무필터대비 중앙 **{cr.d_eq.median():+.1f}%p**")
    print(f"  → 둘 다 크게 양수면 'RSI 극단'이 아니라 **변동성**이 이유다")

    # ── ③ 회전 위약 ────────────────────────────────────────────
    sec("③ 회전 위약 — 게이트 빈도는 같고 시점만 무관")
    m = A.merge(N, on=LADDER + FKEY, suffixes=("_r", "_n"))
    m = m[m["filter"] != "none"]
    m["aligned"] = [aligned(s, f) for s, f in zip(m.side, m.fmode)]
    print(f"{'조건':<12}{'방향':<7}{'실측 자본%':>12}{'위약 자본%':>12}"
          f"{'차이%p':>10}{'실측이 이긴 칸':>16}")
    print("-" * 110)
    for (l, s), g in m.groupby(["lab_r", "side"]):
        d = g.med_final_equity_r - g.med_final_equity_n
        print(f"{l:<12}{s:<7}{g.med_final_equity_r.median():>12.1f}"
              f"{g.med_final_equity_n.median():>12.1f}{d.median():>+10.1f}"
              f"{int((d>0).sum()):>10}/{len(g):<5}")
    ma = m[m.aligned]
    d = ma.med_final_equity_r - ma.med_final_equity_n
    print(f"\n  정방향만: 실측 {ma.med_final_equity_r.median():.1f}% vs "
          f"위약 {ma.med_final_equity_n.median():.1f}% · 차이 {d.median():+.1f}%p · "
          f"이긴 칸 {int((d>0).sum())}/{len(ma)}")

    # ── ④ 절대 기준 ────────────────────────────────────────────
    sec("④ 절대 기준 — 본전(100%) 넘긴 칸 · 사이클 30 이상만")
    ok = A[(A.n_cycles / A.n_sym >= MIN_CYCLES)]
    print(f"  판정 가능 칸 {len(ok)}/{len(A)} · 그중 본전 초과 "
          f"**{int((ok.med_final_equity > 100).sum())}**")
    top = ok.nlargest(12, "med_final_equity")
    print(f"\n{'조건':<12}{'방향':<7}{'스텝':>6}{'배수':>6}{'손절':>6}{'게이트%':>9}"
          f"{'사이클':>9}{'파산%':>8}{'최종자본%':>11}")
    print("-" * 110)
    for _, r in top.iterrows():
        print(f"{r.lab:<12}{r.side:<7}{r.step_bp:>6.0f}{r['mult']:>6.1f}"
              f"{r.sl:>6.2f}{r.gate_open_pct:>9.2f}"
              f"{r.n_cycles/r.n_sym:>9.0f}{r.sym_ruin_pct:>8.1f}"
              f"{r.med_final_equity:>11.1f}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
