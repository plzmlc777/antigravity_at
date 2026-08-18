"""손절판 판독 — 자본 누적 · 파산 시 종목 종료 · 손절 격자.

앞선 판(`martingale_ruin_report`)과 **관측 단위가 다르다**. 저기서 파산률은
사이클당 비율이었고, 여기서는 **종목당 생존 여부**다. 절대 섞어 읽지 마라.

무엇을 묻는가
    "손절을 당하더라도 이익 보는 구간이 있는가."
    손절은 두 가지를 동시에 한다 — 파산을 막고(좋다), 물타기가 회복할 자리를
    빼앗는다(나쁘다). 어느 쪽이 큰지는 재봐야 안다.

⚠ 손절이 파산을 없애는 것은 **당연하다**. 그건 결과가 아니라 정의다.
  물어야 할 것은 **최종 자본**이다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

D = ROOT / "runs" / "research_track" / "martingale_ruin"
BASE = "long_short_strict_persist_halt"


def sec(t):
    print("\n" + "=" * 112)
    print(t)
    print("=" * 112)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=30.0)
    a = ap.parse_args()

    A = pd.read_csv(D / f"agg_{BASE}_level_real.csv")
    Ax = pd.read_csv(D / f"agg_{BASE}_extreme_real.csv")
    An = pd.read_csv(D / f"agg_{BASE}_level_null_shuffle.csv")
    P = pd.read_csv(D / f"persym_{BASE}_level_real.csv")

    sec("손절판 — 자본 누적 · 파산하면 그 종목 테스트 종료")
    print(f"  격자 {len(A)}칸 · 종목 {A.n_sym.max()} · 총 사이클 {A.n_cycles.sum():,}")
    print("  ⚠ 파산률 = **종목당** 비율 (사이클당 아님). 손절률·승률만 사이클당.")

    # ── ① 손절이 파산과 최종자본을 각각 어떻게 움직이나 ──────────
    sec(f"① 손절 수준별 (자본 {a.cap:.0f}배 고정) — 파산은 줄지만 자본은?")
    q = A[A.cap == a.cap]
    for side in ("long", "short"):
        s = q[q.side == side]
        if s.empty:
            continue
        print(f"\n  ── {side} ──")
        print(f"{'스텝bp':>7}{'배수':>6}" +
              "".join(f"{'손절'+f'{x:g}':>19}" for x in sorted(s.sl.unique())))
        print(f"{'':>13}" +
              "".join(f"{'파산%/최종자본%':>19}" for _ in sorted(s.sl.unique())))
        for st in sorted(s.step_bp.unique()):
            for m in sorted(s['mult'].unique()):
                row = f"{st:>7.0f}{m:>6.1f}"
                for sl in sorted(s.sl.unique()):
                    r = s[(s.step_bp == st) & (s['mult'] == m) & (s.sl == sl)]
                    if r.empty:
                        row += f"{'-':>19}"
                    else:
                        r = r.iloc[0]
                        row += f"{r.sym_ruin_pct:>9.1f}/{r.med_final_equity:<9.0f}"
                print(row)

    # ── ② 손절 축만 뽑아 평균 ────────────────────────────────────
    sec("② 손절 축 요약 — 전 칸 중앙값 (파산·최종자본·승률의 맞바꿈)")
    print(f"{'손절':>6}{'종목파산%':>11}{'사이클승률%':>13}{'손절률%':>10}"
          f"{'최종자본중앙%':>15}{'생존종목 최종자본%':>19}{'최종자본>100%인 칸':>19}")
    print("-" * 112)
    for sl in sorted(A.sl.unique()):
        s = A[A.sl == sl]
        print(f"{sl:>6.2f}{s.sym_ruin_pct.median():>11.1f}"
              f"{s.win_rate.median():>13.2f}{s.stop_rate.median():>10.2f}"
              f"{s.med_final_equity.median():>15.1f}"
              f"{s.med_final_equity_survived.median():>19.1f}"
              f"{100*(s.med_final_equity>100).mean():>18.1f}%")
    print("\n  최종자본 100% = 본전. 파산이 0으로 가도 본전을 못 넘으면 손절은 "
          "파산을 **느린 출혈로 바꾼 것**이다.")

    # ── ③ 손절이 파산 없는 판(sl=1.0)을 이기는가 ────────────────
    sec("③ 같은 칸 대조 — 손절 있음 vs 없음(sl=1.0)")
    base = A[A.sl == 1.0].set_index(["side", "step_bp", "mult", "cap"])
    rows = []
    for sl in sorted(A.sl.unique()):
        if sl >= 1.0:
            continue
        s = A[A.sl == sl]
        w = d = 0
        dr, de = [], []
        for _, r in s.iterrows():
            k = (r.side, r.step_bp, r['mult'], r.cap)
            if k not in base.index:
                continue
            b = base.loc[k]
            d += 1
            w += int(r.med_final_equity > float(b.med_final_equity))
            de.append(r.med_final_equity - float(b.med_final_equity))
            dr.append(r.sym_ruin_pct - float(b.sym_ruin_pct))
        rows.append({"sl": sl, "n": d, "win": w,
                     "d_equity": np.median(de), "d_ruin": np.median(dr)})
    print(f"{'손절':>6}{'칸':>6}{'최종자본 이긴 칸':>18}{'최종자본 차이 중앙%p':>22}"
          f"{'종목파산률 차이%p':>20}")
    print("-" * 112)
    for r in rows:
        print(f"{r['sl']:>6.2f}{r['n']:>6}{r['win']:>10}/{r['n']:<7}"
              f"{r['d_equity']:>+22.1f}{r['d_ruin']:>+20.1f}")
    best = max(rows, key=lambda x: x["d_equity"])
    print(f"\n  최종자본을 가장 크게 올린 손절: **{best['sl']:.2f}** "
          f"({best['d_equity']:+.1f}%p · 파산률 {best['d_ruin']:+.1f}%p · "
          f"{best['win']}/{best['n']}칸)")
    anyw = any(r["d_equity"] > 0 and r["win"] > r["n"] / 2 for r in rows)
    print(f"  **손절이 무손절을 이겼나: {'예' if anyw else '아니오'}**")

    # ── ④ 절대 기준 — 본전을 넘긴 칸이 하나라도 있나 ────────────
    sec("④ 절대 기준 — 5.6년 뒤 본전(100%)을 넘긴 설정")
    pos = A[A.med_final_equity > 100].sort_values("med_final_equity",
                                                  ascending=False)
    print(f"  최종자본 중앙 > 100% 인 칸 **{len(pos)}/{len(A)}**")
    if len(pos):
        print(f"\n{'방향':<7}{'스텝bp':>7}{'배수':>6}{'자본':>6}{'손절':>6}"
              f"{'종목파산%':>10}{'승률%':>8}{'최종자본%':>11}{'생존시%':>10}")
        print("-" * 112)
        for _, r in pos.head(12).iterrows():
            print(f"{r.side:<7}{r.step_bp:>7.0f}{r['mult']:>6.1f}{r.cap:>6.0f}"
                  f"{r.sl:>6.2f}{r.sym_ruin_pct:>10.1f}{r.win_rate:>8.2f}"
                  f"{r.med_final_equity:>11.1f}{r.med_final_equity_survived:>10.1f}")

    # ── ⑤ 민감도 + 위약 ─────────────────────────────────────────
    sec("⑤ 손절 체결 가정 민감도 · 위약")
    m = A.merge(Ax, on=["side", "step_bp", "mult", "cap", "sl"],
                suffixes=("_l", "_x"))
    print(f"  손절 지정가 체결 vs 봉 극단 체결(갭 최악)")
    print(f"    최종자본 중앙 : level {m.med_final_equity_l.median():.1f}% vs "
          f"extreme {m.med_final_equity_x.median():.1f}%")
    print(f"    종목파산 중앙 : level {m.sym_ruin_pct_l.median():.1f}% vs "
          f"extreme {m.sym_ruin_pct_x.median():.1f}%")
    print(f"    본전 넘김이 뒤집히는 칸 "
          f"{int(((m.med_final_equity_l>100) != (m.med_final_equity_x>100)).sum())}/{len(m)}")
    n = A.merge(An, on=["side", "step_bp", "mult", "cap", "sl"],
                suffixes=("_r", "_n"))
    print(f"\n  실측 vs 위약(추세 제거)")
    print(f"    종목파산 중앙 : 실측 {n.sym_ruin_pct_r.median():.1f}% vs "
          f"위약 {n.sym_ruin_pct_n.median():.1f}%")
    print(f"    최종자본 중앙 : 실측 {n.med_final_equity_r.median():.1f}% vs "
          f"위약 {n.med_final_equity_n.median():.1f}%")
    print(f"    실측이 위약보다 최종자본 높은 칸 "
          f"{int((n.med_final_equity_r > n.med_final_equity_n).sum())}/{len(n)}")

    # ── ⑥ 종목별 생존 ───────────────────────────────────────────
    sec("⑥ 종목별 생존 (대표 설정 long · 200bp · 배수 2.0 · 자본 30배)")
    LH = 8760
    for sl in (0.20, 0.50, 1.0):
        k = P[(P.step_bp == 200) & (P['mult'] == 2.0) & (P.cap == 30) &
              (P.side == "long") & (P.sl == sl) & (P.bars >= LH)]
        if k.empty:
            continue
        rn = k.ruined.astype(bool)
        print(f"  손절 {sl:.2f} — 장기 {len(k)}종목 중 파산 {int(rn.sum())} "
              f"({100*rn.mean():.1f}%) · 생존 최종자본 중앙 "
              f"{k.loc[~rn,'final_equity_pct'].median():.1f}% · "
              f"전체 중앙 {k.final_equity_pct.median():.1f}%")
    k = P[(P.step_bp == 200) & (P['mult'] == 2.0) & (P.cap == 30) &
          (P.side == "long") & (P.sl == 0.20) & (P.bars >= LH)]
    if not k.empty:
        print(f"\n  손절 0.20 · 최종자본 상위 8종목")
        print(f"{'종목':<14}{'봉수':>8}{'사이클':>8}{'승률%':>8}{'손절률%':>9}"
              f"{'파산':>6}{'최종자본%':>11}")
        print("-" * 112)
        for _, r in k.nlargest(8, "final_equity_pct").iterrows():
            print(f"{r.symbol:<14}{r.bars:>8.0f}{r.n_cycles:>8.0f}"
                  f"{r.win_rate:>8.2f}{r.stop_rate:>9.2f}"
                  f"{'예' if r.ruined else '아니오':>6}{r.final_equity_pct:>11.1f}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
