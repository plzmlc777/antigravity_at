"""RSI 진입 대조군 판독 — **RSI 가 번 것인가, 손절 1% 가 번 것인가.**

왜 이 판독이 필요한가
    2026-08-16 본 격자에서 거래당 평균 상위 칸이 **전부 손절 1%** 였다.
    손절 1% 는 1시간봉에서 거의 즉시 걸리는 폭이라, 그 수익이 RSI 신호 덕인지
    "짧게 자르고 길게 끄는 규칙" 자체의 덕인지 가려지지 않았다.

장치
    rotate — RSI 신호를 시간축으로 **원형회전**. 진입 **횟수와 뭉침 구조가
             동일**하고 가격 경로와의 연결만 끊긴다. 가장 강한 대조.
    random — 같은 횟수를 균등 무작위 시점에. 뭉침까지 없앤 약한 대조.

판정
    실측이 rotate 를 못 이기면 **RSI 는 아무것도 안 한 것**이고, 번 것은
    익절·손절 규칙이다.
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


def main() -> int:
    f = D / "persym_long_short_h48_placebo.csv"
    if not f.exists():
        f = D / "partial_placebo.csv"
        print(f"⚠ 본 산출물이 아직 없어 **부분 저장**을 읽는다: {f.name}")
    P = pd.read_csv(f)
    P = P[P.n_trades.notna()].copy()
    if "placebo" not in P.columns:
        # ⚠ 2026-08-16 실행은 `placebo` 열을 안 붙였다(하네스 편집이 들여쓰기
        #   불일치로 적용 안 됨). 다만 `key` 끝 토큰이 위약 종류라 **복원 가능**하다.
        #   재실행 없이 살린다. 열이 있으면 그대로 쓴다.
        P["placebo"] = P.key.str.rsplit("_", n=1).str[-1]
        print("⚠ placebo 열이 없어 `key` 끝 토큰에서 복원했다 — "
              f"{P.placebo.value_counts().to_dict()}")
    if not set(P.placebo.unique()) & {"rotate", "random"}:
        print("위약 칸이 없다 — 대조군 실행 산출물이 아니다")
        return 1

    sec("RSI 진입 대조군 — 실측 vs 원형회전 vs 무작위")
    print(f"  종목 {P.symbol.nunique()} · 칸 {P.key.nunique()} · "
          f"총 거래 {int(P.n_trades.sum()):,}")
    for pl in ("real", "rotate", "random"):
        q = P[P.placebo == pl]
        if q.empty:
            continue
        print(f"  {pl:<7} 거래 {int(q.n_trades.sum()):>12,} · "
              f"칸 {q.key.nunique():>3} · 종목 {q.symbol.nunique()}")

    A = (P.groupby(CELL + ["placebo"]).agg(
            trades=("n_trades", "sum"), win=("win_rate_calc", "median"),
            avg=("avg_pct", "median"), payoff=("payoff", "median"),
            pos=("sum_pct", lambda x: 100.0 * float((x > 0).mean())))
         .reset_index())
    W = A.pivot_table(index=CELL, columns="placebo",
                      values=["win", "avg", "trades", "pos"]).reset_index()
    W.columns = ["_".join([c for c in col if c]).strip("_")
                 for col in W.columns.to_flat_index()]

    have = [c for c in ("avg_rotate", "avg_random") if c in W.columns]
    if "avg_real" not in W.columns or not have:
        print("실측 또는 위약 칸이 비었다 — 아직 부분 결과일 수 있다")
        return 0

    # ── ① 칸별 대조 ────────────────────────────────────────────
    sec("① 칸별 — 실측이 위약을 이기나 (거래당 평균 %)")
    print(f"{'방향':<7}{'문턱':>6}{'익절%':>7}{'손절%':>7}{'실측':>10}"
          f"{'회전위약':>11}{'무작위위약':>12}{'실측-회전':>11}{'실측 거래':>12}")
    print("-" * 104)
    W = W.sort_values(CELL)
    for _, r in W.iterrows():
        rot = r.get("avg_rotate", np.nan)
        ran = r.get("avg_random", np.nan)
        print(f"{r.side:<7}{r.thr:>6.0f}{100*r.tp:>7.0f}{100*r.sl:>7.0f}"
              f"{r.avg_real:>+10.3f}{rot:>+11.3f}{ran:>+12.3f}"
              f"{r.avg_real - rot:>+11.3f}{int(r.get('trades_real', 0)):>12,}")

    # ── ② 요약 판정 ────────────────────────────────────────────
    sec("② 판정 — 실측이 위약을 이겼나")
    d_rot = W.avg_real - W.avg_rotate
    print(f"  칸 {len(W)}개")
    print(f"  실측 거래당 평균 중앙   **{W.avg_real.median():+.3f}%**")
    print(f"  회전 위약 중앙          **{W.avg_rotate.median():+.3f}%**")
    if "avg_random" in W.columns:
        print(f"  무작위 위약 중앙        **{W.avg_random.median():+.3f}%**")
    print(f"  실측 - 회전 중앙        **{d_rot.median():+.3f}%p**")
    print(f"  실측이 회전을 이긴 칸   **{int((d_rot > 0).sum())}/{len(W)}** "
          f"(동전던지기면 50%)")
    print(f"\n  최대통계량 — 격자 최고끼리 (교훈 #95)")
    print(f"    실측 최고 {W.avg_real.max():+.3f}% vs "
          f"회전 최고 {W.avg_rotate.max():+.3f}%  → "
          f"{'넘었다' if W.avg_real.max() > W.avg_rotate.max() else '**못 넘었다**'}")

    # ── ③ 손절폭이 원인인지 ────────────────────────────────────
    sec("③ 손절폭이 원인인가 — 손절 1% vs 2% 를 갈라 본다")
    print(f"{'손절%':>6}{'실측 중앙':>12}{'회전 중앙':>12}{'차이':>11}"
          f"{'실측이 이긴 칸':>16}")
    print("-" * 104)
    for sl in sorted(W.sl.unique()):
        q = W[W.sl == sl]
        d = q.avg_real - q.avg_rotate
        print(f"{100*sl:>6.0f}{q.avg_real.median():>+12.3f}"
              f"{q.avg_rotate.median():>+12.3f}{d.median():>+11.3f}"
              f"{int((d>0).sum()):>10}/{len(q):<5}")
    print("\n  → 회전 위약도 손절 1% 에서 크게 벌면, 번 것은 **RSI 가 아니라 규칙**이다.")

    # ── ④ 승률 ────────────────────────────────────────────────
    sec("④ 승률 — 실측과 위약이 다른가")
    print(f"{'손절%':>6}{'실측 승률%':>13}{'회전 승률%':>13}{'차이%p':>10}")
    print("-" * 104)
    for sl in sorted(W.sl.unique()):
        q = W[W.sl == sl]
        print(f"{100*sl:>6.0f}{q.win_real.median():>13.2f}"
              f"{q.win_rotate.median():>13.2f}"
              f"{(q.win_real - q.win_rotate).median():>+10.2f}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
