"""rv7·high 좁은 재검정 판독 — 세 장치 중 **하나만 무너져도 닫는다**.

장치
    ① 기간 분할 : IS(2021-01~2024-12) 에서의 부호가 OOS(2025-01~) 에서 유지되나
    ② 문턱 고원 : 0.8 이 고원의 한 점인가, 뾰족한 점인가
    ③ 1분봉     : 체결 해상도를 60배 올려도 남나

⚠ 교훈 #96 — **장치 하나 통과는 통과가 아니다.** 오늘 처음 위약을 통과한
   결과가 세 장치에서 전부 죽은 전례가 있다.
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


def sec(t):
    print("\n" + "=" * 108)
    print(t)
    print("=" * 108)


def load(name):
    p = D / name
    return pd.read_csv(p) if p.exists() else None


def flab(r):
    return "무필터" if r["filter"] == "none" else f"{r['filter']}·{r.fmode}·{r.fthr:g}"


def vs_nofilter(A):
    """필터별로 같은 사다리 칸의 무필터와 짝지어 비교."""
    nof = A[A["filter"] == "none"].set_index(LADDER)
    out = []
    for k, g in A[A["filter"] != "none"].groupby(FKEY):
        de, w, d = [], 0, 0
        for _, r in g.iterrows():
            kk = tuple(r[c] for c in LADDER)
            if kk not in nof.index:
                continue
            b = float(nof.loc[kk].med_final_equity)
            d += 1
            w += int(r.med_final_equity > b)
            de.append(r.med_final_equity - b)
        out.append({"lab": f"{k[0]}·{k[1]}·{k[2]:g}", "n": d, "win": w,
                    "d_eq": float(np.median(de)) if de else np.nan,
                    "equity": float(g.med_final_equity.median()),
                    "ruin": float(g.sym_ruin_pct.median())})
    return pd.DataFrame(out)


def main() -> int:
    B = "long_1h_strict_persist_halt_level_filt"
    IS = load(f"agg_{B}_beg_2025-01-01_IS.csv")
    OOS = load(f"agg_{B}_2025-01-01_end_OOS.csv")
    PL = load(f"agg_{B}_PLATEAU.csv")
    PLN = load(f"agg_long_1h_strict_persist_halt_level_filtnull_PLATEAU.csv")
    H8 = load(f"agg_{B}_TF8.csv")
    M8 = load("agg_long_1m_strict_persist_halt_level_filt_TF8.csv")

    sec("rv7·high·0.8 좁은 재검정 — 세 장치")

    # ── ① 기간 분할 ─────────────────────────────────────────────
    sec("① 기간 분할 — IS(~2024-12) 부호가 OOS(2025-01~) 에서 유지되나")
    if IS is None or OOS is None:
        print("  파일 없음")
    else:
        a, b = vs_nofilter(IS), vs_nofilter(OOS)
        m = a.merge(b, on="lab", suffixes=("_is", "_oos"))
        print(f"{'필터':<18}{'IS 최종자본%':>14}{'IS 무필터대비':>15}"
              f"{'OOS 최종자본%':>15}{'OOS 무필터대비':>16}{'부호유지':>10}")
        print("-" * 108)
        for _, r in m.sort_values("d_eq_is", ascending=False).iterrows():
            keep = "예" if np.sign(r.d_eq_is) == np.sign(r.d_eq_oos) else "**아니오**"
            print(f"{r.lab:<18}{r['equity_is']:>14.1f}{r.d_eq_is:>+15.1f}"
                  f"{r['equity_oos']:>15.1f}{r.d_eq_oos:>+16.1f}{keep:>10}")
        w = m[m.lab == "rv7·high·0.8"]
        if len(w):
            w = w.iloc[0]
            ok = np.sign(w.d_eq_is) == np.sign(w.d_eq_oos) and w.d_eq_oos > 0
            print(f"\n  승자 칸 rv7·high·0.8 : IS {w.d_eq_is:+.1f}%p → "
                  f"OOS {w.d_eq_oos:+.1f}%p  → **{'통과' if ok else '탈락'}**")

    # ── ② 문턱 고원 ─────────────────────────────────────────────
    sec("② 문턱 고원 — 0.8 이 고원인가 뾰족한 점인가")
    if PL is None:
        print("  파일 없음")
    else:
        v = vs_nofilter(PL)
        n = vs_nofilter(PLN) if PLN is not None else None
        if n is not None:
            v = v.merge(n[["lab", "equity"]], on="lab", suffixes=("", "_null"))
        print(f"{'필터':<18}{'최종자본%':>12}{'무필터대비%p':>15}"
              f"{'이긴 칸':>12}{'파산%':>9}" + (f"{'위약 최종자본%':>16}" if n is not None else ""))
        print("-" * 108)
        hi = v[v.lab.str.contains("high")].copy()
        hi["thr"] = hi.lab.str.split("·").str[-1].astype(float)
        for _, r in hi.sort_values("thr").iterrows():
            extra = f"{r['equity_null']:>16.1f}" if n is not None else ""
            print(f"{r.lab:<18}{r['equity']:>12.1f}{r.d_eq:>+15.1f}"
                  f"{r.win:>8}/{r.n:<3}{r.ruin:>9.1f}{extra}")
        for _, r in v[v.lab.str.contains("low")].iterrows():
            extra = f"{r['equity_null']:>16.1f}" if n is not None else ""
            print(f"{r.lab:<18}{r['equity']:>12.1f}{r.d_eq:>+15.1f}"
                  f"{r.win:>8}/{r.n:<3}{r.ruin:>9.1f}{extra}")
        pk = hi.loc[hi.d_eq.idxmax()]
        near = hi[(hi.thr - pk.thr).abs() <= 0.06]
        share = 100.0 * float((near.d_eq > 0).mean())
        print(f"\n  최고 문턱 {pk.thr:g} ({pk.d_eq:+.1f}%p) · 주변 문턱 "
              f"{len(near)}개 중 양수 {share:.0f}%")
        print(f"  → {'**고원**' if share >= 60 else '**뾰족한 점 — 고원 없음**'}")

    # ── ③ 1분봉 ────────────────────────────────────────────────
    sec("③ 1분봉 교차검증 — 같은 8종목, 해상도만 60배")
    if H8 is None or M8 is None:
        print("  파일 없음")
    else:
        a, b = vs_nofilter(H8), vs_nofilter(M8)
        m = a.merge(b, on="lab", suffixes=("_1h", "_1m"))
        print(f"{'필터':<18}{'1h 최종자본%':>14}{'1h 무필터대비':>15}"
              f"{'1m 최종자본%':>15}{'1m 무필터대비':>16}{'부호유지':>10}")
        print("-" * 108)
        for _, r in m.iterrows():
            keep = "예" if np.sign(r.d_eq_1h) == np.sign(r.d_eq_1m) else "**아니오**"
            print(f"{r.lab:<18}{r['equity_1h']:>14.1f}{r.d_eq_1h:>+15.1f}"
                  f"{r['equity_1m']:>15.1f}{r.d_eq_1m:>+16.1f}{keep:>10}")
        w = m[m.lab == "rv7·high·0.8"]
        if len(w):
            w = w.iloc[0]
            ok = w.d_eq_1m > 0
            print(f"\n  승자 칸 rv7·high·0.8 : 1h {w.d_eq_1h:+.1f}%p → "
                  f"1m {w.d_eq_1m:+.1f}%p  → **{'통과' if ok else '탈락'}**")
        print(f"\n  ⚠ 8종목이라 종목 표본이 작다. 부호와 크기만 본다.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
