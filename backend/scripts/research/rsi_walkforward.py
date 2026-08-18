"""전진 검증 — **고르는 행위까지 검정에 넣는다**.

왜 필요한가
    선택 규칙 격자(슬롯 5 × 규칙 4 = 20칸)의 최고가 최대통계량에서 p 0.150 에
    걸렸다. 격자를 뒤지는 것 자체가 +13% 를 만들기 때문이다.

    전진 검증은 그 문제를 **구조적으로** 없앤다. 매 해 **직전 데이터만으로**
    규칙·슬롯을 고르고, 고른 그대로 다음 해에 적용한다. 고른 것이 틀렸으면
    그 해 성과로 벌을 받는다.

⚠ 귀무도 **같은 절차**로 만든다
    무작위 규칙 4종으로 똑같이 "직전 데이터로 고르고 다음 해 적용"을 돌린다.
    그래야 전진 검증 자체가 만드는 이득을 뺄 수 있다.

⚠ 선택 기준은 하나로 고정한다
    학습 구간의 CAGR. 여기서 기준을 여러 개 시도하면 그게 또 격자가 된다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

D = ROOT / "runs" / "research_track" / "rsi_tp_sl"
SLOTS = (1, 2, 3, 5, 10)
REAL_RULES = ("first", "rsi_low", "rv_high", "rv_low")
MIN_TRAIN = 40          # 학습 구간 최소 거래. 이보다 적으면 그 해는 건너뛴다


def sec(t):
    print("\n" + "=" * 100)
    print(t)
    print("=" * 100)


def walk(T: pd.DataFrame, rules, fee_bp: float, seed0: int = 0,
         verbose: bool = False) -> dict:
    """매 해: 직전 전체로 (규칙·슬롯) 선택 → 그 해에 적용. 자본은 이어 붙인다."""
    from scripts.research.rsi_selection_sim import run
    years = sorted(pd.to_datetime(T.entry_ts).dt.year.unique())
    eq, per_yr, picks = 1.0, {}, {}
    for y in years[1:]:                       # 첫 해는 학습에만 쓴다
        tr = T[pd.to_datetime(T.exit_ts).dt.year < y]
        te = T[pd.to_datetime(T.entry_ts).dt.year == y]
        if len(tr) < MIN_TRAIN or len(te) < 10:
            continue
        best, bc = None, -1e9
        for s in SLOTS:
            for j, r in enumerate(rules):
                d = run(tr, s, r, fee_bp, seed=seed0 + j)
                if d.get("n", 0) < 20:
                    continue
                if d["cagr"] > bc:
                    bc, best = d["cagr"], (s, r, j)
        if best is None:
            continue
        s, r, j = best
        d = run(te, s, r, fee_bp, seed=seed0 + j)
        if d.get("n", 0) < 5:
            continue
        picks[int(y)] = (s, r, d["n"])
        per_yr[int(y)] = d["total"]
        eq *= (1.0 + d["total"] / 100.0)
        if verbose:
            print(f"    {y}: 학습 {len(tr):>3}건 → 선택 슬롯 {s} · {r:<8}"
                  f" → 그 해 체결 {d['n']:>3}건 · {d['total']:+7.2f}%")
    n_y = len(per_yr)
    return {"eq": eq, "cagr": 100.0 * (eq ** (1 / n_y) - 1.0) if n_y else np.nan,
            "n_years": n_y, "per_yr": per_yr, "picks": picks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee-bp", type=float, default=10.0)
    ap.add_argument("--nulls", type=int, default=200)
    a = ap.parse_args()

    from scripts.research.rsi_selection_sim import enrich, run

    T = pd.read_csv(D / "trades_long_short_h48_PF.csv")
    T = T[(T.placebo == "real") & (T.side == "long") & (T.thr == 12)
          & (T.tp == 0.08) & (T.sl == 0.03)]
    T = enrich(T)

    sec("전진 검증 — 매 해 직전 데이터로만 고르고 다음 해에 적용")
    print(f"  신호 {len(T):,}건 · 종목 {T.symbol.nunique()} · 마찰 {a.fee_bp:.0f}bp")
    print(f"  후보: 슬롯 {SLOTS} × 규칙 {REAL_RULES} · 선택 기준 = 학습 CAGR")
    print()
    w = walk(T, REAL_RULES, a.fee_bp, verbose=True)
    print()
    print(f"  전진 검증 {w['n_years']}년 · 누적 자본 {w['eq']:.3f} · "
          f"**CAGR {w['cagr']:+.2f}%**")

    # 고정 규칙 대조 (전 구간 후지식으로 고른 최고 = 상한선)
    sec("① 대조 — 전진 검증 vs 고정 규칙")
    for s, r in ((3, "rsi_low"), (5, "rsi_low"), (10, "first")):
        d = run(T, s, r, a.fee_bp)
        print(f"  후지식 고정 슬롯{s}·{r:<8} CAGR {d['cagr']:+6.2f}% "
              f"(전 구간을 다 보고 고른 값 — 실거래에선 못 쓴다)")
    print(f"  전진 검증(고르는 행위 포함)      CAGR {w['cagr']:+6.2f}%")

    # ── 귀무: 같은 절차를 무작위 규칙으로 ──────────────────────
    sec("② 최대통계량 귀무 — 같은 전진 절차를 **무작위 규칙**으로")
    print(f"  무작위 규칙 4종으로 똑같이 '직전으로 고르고 다음 해 적용' × "
          f"{a.nulls}회")
    nulls = []
    for k in range(a.nulls):
        d = walk(T, ("random",) * 4, a.fee_bp, seed0=50_000 + k * 41)
        if not np.isnan(d["cagr"]):
            nulls.append(d["cagr"])
        if (k + 1) % 50 == 0:
            print(f"    {k+1}/{a.nulls} …")
    nulls = np.array(nulls)
    p = float((nulls >= w["cagr"]).mean())
    print()
    print(f"  귀무 분포: 중앙 {np.median(nulls):+.2f}% · "
          f"90%분위 {np.quantile(nulls, .9):+.2f}% · 최대 {nulls.max():+.2f}%")
    print(f"  **관측 {w['cagr']:+.2f}%  →  p = {p:.3f}**")
    print(f"  → {'**통과**' if p < 0.05 else '경계' if p < 0.20 else '**못 넘었다**'}")

    # ── 선택 안정성 ────────────────────────────────────────────
    sec("③ 선택 안정성 — 매년 다른 것을 고르면 그건 잡음이다")
    for y, (s, r, n) in w["picks"].items():
        print(f"  {y}: 슬롯 {s} · {r:<8} (그 해 체결 {n}건 · "
              f"{w['per_yr'][y]:+.2f}%)")
    rr = [v[1] for v in w["picks"].values()]
    ss = [v[0] for v in w["picks"].values()]
    print(f"\n  규칙 선택: {dict(pd.Series(rr).value_counts())}")
    print(f"  슬롯 선택: {dict(pd.Series(ss).value_counts())}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
