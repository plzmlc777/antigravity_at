"""진입 필터 판독 — 필터가 **위약을 이기는가**.

무엇을 조심하는가
    필터는 거래를 줄인다. 거래를 줄이면 파산도 줄고 마찰도 준다. 그래서
    "필터를 켰더니 파산이 줄었다"는 **아무 정보가 없다**. 물어야 할 것은
    같은 빈도로 게이트를 여는 **회전 위약**을 이겼느냐다.

⚠ 격자를 뒤졌으므로 최고 칸은 **최대통계량**으로 봐야 한다 (교훈 #95).
   실측 격자의 최고와 위약 격자의 최고를 견준다 — 칸별 비교는 이미 선택된
   칸이라 통과한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "runs" / "research_track" / "martingale_ruin"
BASE = "long_short_strict_persist_halt_level"
LADDER = ["side", "step_bp", "mult", "cap", "sl"]
FKEY = ["filter", "fmode", "fthr"]


def sec(t):
    print("\n" + "=" * 110)
    print(t)
    print("=" * 110)


def flab(r):
    return "무필터" if r["filter"] == "none" else f"{r['filter']}·{r.fmode}·{r.fthr:g}"


def main() -> int:
    A = pd.read_csv(D / f"agg_{BASE}_filt_real.csv")
    N = pd.read_csv(D / f"agg_{BASE}_filtnull_real.csv")
    P = pd.read_csv(D / f"persym_{BASE}_filt_real.csv")

    sec("진입 필터 — 실측 vs 필터 원형회전 위약 (장기 종목만)")
    print(f"  격자 {len(A)}칸 · 종목 {A.n_sym.max()} · 사이클 {A.n_cycles.sum():,}")
    print("  사다리 격자: 방향2 × 스텝3 × 배수2 × 손절2 = 24 · 필터 15종(무필터 포함)")

    # ── ① 필터별 요약 (사다리 칸 전체에서의 중앙값) ─────────────
    sec("① 필터별 요약 — 사다리 24칸에서의 중앙값")
    print(f"{'필터':<18}{'게이트%':>9}{'사이클':>10}{'승률%':>8}{'종목파산%':>11}"
          f"{'최종자본%':>11}{'위약 최종자본%':>16}{'실측-위약':>11}")
    print("-" * 110)
    m = A.merge(N, on=LADDER + FKEY, suffixes=("_r", "_n"))
    rows = []
    for k, g in m.groupby(FKEY, dropna=False):
        r0 = g.iloc[0]
        rows.append({
            "lab": flab(r0), "filter": k[0], "fmode": k[1], "fthr": k[2],
            "gate": g.gate_open_pct_r.median(),
            "cyc": g.n_cycles_r.sum(),
            "win": g.win_rate_r.median(),
            "ruin": g.sym_ruin_pct_r.median(),
            "equity": g.med_final_equity_r.median(),
            "equity_n": g.med_final_equity_n.median(),
            "n_cell": len(g),
            "beat": int((g.med_final_equity_r > g.med_final_equity_n).sum()),
        })
    R = pd.DataFrame(rows)
    R["delta"] = R["equity"] - R["equity_n"]
    base_eq = float(R[R["filter"] == "none"]["equity"].iloc[0])
    for _, r in R.sort_values("equity", ascending=False).iterrows():
        print(f"{r.lab:<18}{r.gate:>9.1f}{r.cyc:>10,}{r.win:>8.2f}{r.ruin:>11.1f}"
              f"{r['equity']:>11.1f}{r['equity_n']:>16.1f}{r.delta:>+11.1f}")
    print(f"\n  무필터 기준선 최종자본 **{base_eq:.1f}%**")

    # ── ② 최대통계량 — 격자를 뒤진 대가를 치른다 ────────────────
    sec("② 최대통계량 귀무 — 격자 최고끼리 견준다 (교훈 #95)")
    fr = A[A["filter"] != "none"]
    fn = N[N["filter"] != "none"]
    print(f"  실측 격자 최고 최종자본 : **{fr.med_final_equity.max():.1f}%**  "
          f"({flab(fr.loc[fr.med_final_equity.idxmax()])})")
    print(f"  위약 격자 최고 최종자본 : **{fn.med_final_equity.max():.1f}%**  "
          f"({flab(fn.loc[fn.med_final_equity.idxmax()])})")
    obs, null = fr.med_final_equity.max(), fn.med_final_equity.max()
    print(f"  → 관측 최고가 위약 최고를 {'넘었다' if obs > null else '**못 넘었다**'} "
          f"({obs:.1f} vs {null:.1f})")
    print(f"\n  필터 칸 중 위약 대비 우세 {int((m[m['filter']!='none'].med_final_equity_r > m[m['filter']!='none'].med_final_equity_n).sum())}"
          f"/{len(m[m['filter']!='none'])} (동전던지기면 50%)")

    # ── ③ 무필터 대조 — 같은 사다리 칸에서 ──────────────────────
    sec("③ 같은 사다리 칸 대조 — 필터 있음 vs 무필터")
    nof = A[A["filter"] == "none"].set_index(LADDER)
    out = []
    for k, g in A[A["filter"] != "none"].groupby(FKEY):
        w = d = 0
        de, dr = [], []
        for _, r in g.iterrows():
            kk = tuple(r[c] for c in LADDER)
            if kk not in nof.index:
                continue
            b = nof.loc[kk]
            d += 1
            w += int(r.med_final_equity > float(b.med_final_equity))
            de.append(r.med_final_equity - float(b.med_final_equity))
            dr.append(r.sym_ruin_pct - float(b.sym_ruin_pct))
        out.append({"lab": f"{k[0]}·{k[1]}·{k[2]:g}", "n": d, "win": w,
                    "d_eq": np.median(de), "d_ruin": np.median(dr)})
    O = pd.DataFrame(out).sort_values("d_eq", ascending=False)
    print(f"{'필터':<18}{'칸':>5}{'무필터 이긴 칸':>16}{'최종자본 차이%p':>18}"
          f"{'파산률 차이%p':>16}")
    print("-" * 110)
    for _, r in O.iterrows():
        print(f"{r.lab:<18}{r.n:>5}{r.win:>10}/{r.n:<5}{r.d_eq:>+18.1f}"
              f"{r.d_ruin:>+16.1f}")
    best = O.iloc[0]
    print(f"\n  최고 필터 **{best.lab}** — 최종자본 {best.d_eq:+.1f}%p · "
          f"파산률 {best.d_ruin:+.1f}%p · {best.win}/{best.n}칸")

    # ── ④ 저변동 필터를 따로 본다 (사전 가설이었다) ─────────────
    sec("④ 사전 가설 검정 — '고변동에서 사이클을 열지 않는다' (rv7·low)")
    print("  ⚠ 이건 판독 전에 세운 유일한 사전 가설이다. 나머지는 탐색이다.")
    for thr in (0.2, 0.4, 0.6):
        rr = m[(m["filter"] == "rv7") & (m.fmode == "low") & (m.fthr == thr)]
        if rr.empty:
            continue
        print(f"    문턱 {thr:g} — 실측 최종자본 {rr.med_final_equity_r.median():>6.1f}% · "
              f"위약 {rr.med_final_equity_n.median():>6.1f}% · "
              f"파산 {rr.sym_ruin_pct_r.median():>5.1f}% (위약 {rr.sym_ruin_pct_n.median():.1f}%) · "
              f"위약 이긴 칸 {int((rr.med_final_equity_r>rr.med_final_equity_n).sum())}/{len(rr)}")
    hi = m[(m["filter"] == "rv7") & (m.fmode == "high")]
    print(f"\n  거울 대조(rv7·high — 고변동에서만 진입): 실측 최종자본 중앙 "
          f"{hi.med_final_equity_r.median():.1f}% · 파산 {hi.sym_ruin_pct_r.median():.1f}%")

    # ── ⑤ 절대 기준 ────────────────────────────────────────────
    sec("⑤ 절대 기준 — 본전(100%)을 넘긴 칸")
    print(f"  실측 {int((A.med_final_equity>100).sum())}/{len(A)} · "
          f"위약 {int((N.med_final_equity>100).sum())}/{len(N)}")
    top = A.nlargest(10, "med_final_equity")
    print(f"\n{'방향':<7}{'스텝':>6}{'배수':>6}{'손절':>6}{'필터':<18}{'게이트%':>9}"
          f"{'파산%':>8}{'최종자본%':>11}")
    print("-" * 110)
    for _, r in top.iterrows():
        print(f"{r.side:<7}{r.step_bp:>6.0f}{r['mult']:>6.1f}{r.sl:>6.2f}"
              f"{flab(r):<18}{r.gate_open_pct:>9.1f}{r.sym_ruin_pct:>8.1f}"
              f"{r.med_final_equity:>11.1f}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
