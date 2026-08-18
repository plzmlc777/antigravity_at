"""RSI 격자 판독 — **문턱에 따른 승률 변화**가 주축.

⚠ 승률만 보면 반드시 속는다
    익절 2% / 손절 1% 면 승률이 낮고 익절 3% / 손절 3% 면 높다. 그건 RSI 와
    아무 상관이 없는 **기하학**이다. 그래서 승률은 항상
      ① 같은 익절·손절 안에서 문턱만 움직여 보고
      ② 거래당 평균·손익비와 같이
    본다. 그리고 **손익비 대비 필요 승률**(손익분기 승률)을 같이 찍어
    "이 승률이 이기는 승률인가"를 바로 판별한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "runs" / "research_track" / "rsi_tp_sl"


def sec(t):
    print("\n" + "=" * 104)
    print(t)
    print("=" * 104)


def main() -> int:
    P = pd.read_csv(D / "persym_long_short_h48_full.csv")
    P = P[P.n_trades.notna()].copy()

    sec("RSI 진입문턱 × 익절 × 손절 — 정본 커널 · 1h · 장기 85종목")
    print(f"  격자 {P.key.nunique()}칸 · 종목 {P.symbol.nunique()} · "
          f"총 거래 {int(P.n_trades.sum()):,}")
    print("  진입: 롱=RSI≤문턱(과매도) / 숏=RSI≥100-문턱(과매수) · "
          "체결=신호 다음 봉 시가 · 보유상한 48봉")

    G = ["side", "thr", "tp", "sl"]
    A = (P.groupby(G).agg(
            n_sym=("symbol", "nunique"), trades=("n_trades", "sum"),
            win=("win_rate_calc", "median"), avg=("avg_pct", "median"),
            payoff=("payoff", "median"), tot=("sum_pct", "median"),
            pos=("sum_pct", lambda x: 100.0 * float((x > 0).mean())))
         .reset_index())
    # 손익분기 승률 = 1 / (1 + 손익비)
    A["be_win"] = 100.0 / (1.0 + A.payoff)
    A["edge"] = A.win - A.be_win

    # ── ① 주축: 문턱별 승률 (익절·손절 고정) ────────────────────
    sec("① 문턱에 따른 승률 변화 — 익절·손절을 고정하고 문턱만 움직인다")
    for side in ("long", "short"):
        s = A[A.side == side]
        if s.empty:
            continue
        print(f"\n  ── {side} ({'과매도 진입' if side=='long' else '과매수 진입'}) ──")
        for tp in sorted(s.tp.unique()):
            for sl in sorted(s.sl.unique()):
                q = s[(s.tp == tp) & (s.sl == sl)].sort_values("thr")
                if q.empty:
                    continue
                head = f"  익절 {100*tp:.0f}% / 손절 {100*sl:.0f}%"
                print(f"\n{head}   (손익분기 승률 {q.be_win.median():.1f}%)")
                print("    " + "".join(f"{'문턱'+str(int(t)):>10}"
                                       for t in q.thr))
                print("    승률" + "".join(f"{w:>10.1f}" for w in q.win))
                print("    평균" + "".join(f"{v:>+10.3f}" for v in q.avg))
                print("    거래" + "".join(f"{int(t):>10,}" for t in q.trades))

    # ── ② 문턱 축만 요약 ────────────────────────────────────────
    sec("② 문턱 축 요약 — 전 익절·손절 조합에서의 중앙값")
    print(f"{'방향':<7}{'문턱':>6}{'거래':>12}{'승률%':>9}{'손익분기승률%':>15}"
          f"{'초과%p':>9}{'거래당평균%':>13}{'손익비':>8}{'양수종목%':>11}")
    print("-" * 104)
    for side in ("long", "short"):
        for t in sorted(A.thr.unique()):
            q = A[(A.side == side) & (A.thr == t)]
            if q.empty:
                continue
            print(f"{side:<7}{t:>6.0f}{int(q.trades.sum()):>12,}"
                  f"{q.win.median():>9.2f}{q.be_win.median():>15.2f}"
                  f"{q.edge.median():>+9.2f}{q.avg.median():>+13.3f}"
                  f"{q.payoff.median():>8.2f}{q.pos.median():>11.1f}")

    # ── ③ 익절·손절 축 ──────────────────────────────────────────
    sec("③ 익절·손절이 승률을 어떻게 움직이나 (문턱 전체 중앙값)")
    print(f"{'방향':<7}{'익절%':>7}{'손절%':>7}{'승률%':>9}{'손익분기%':>11}"
          f"{'초과%p':>9}{'거래당평균%':>13}{'손익비':>8}")
    print("-" * 104)
    for side in ("long", "short"):
        for tp in sorted(A.tp.unique()):
            for sl in sorted(A.sl.unique()):
                q = A[(A.side == side) & (A.tp == tp) & (A.sl == sl)]
                if q.empty:
                    continue
                print(f"{side:<7}{100*tp:>7.0f}{100*sl:>7.0f}"
                      f"{q.win.median():>9.2f}{q.be_win.median():>11.2f}"
                      f"{q.edge.median():>+9.2f}{q.avg.median():>+13.3f}"
                      f"{q.payoff.median():>8.2f}")

    # ── ④ 절대 판정 ────────────────────────────────────────────
    sec("④ 절대 판정 — 거래당 평균이 양수인 칸")
    pos = A[A.avg > 0].sort_values("avg", ascending=False)
    print(f"  거래당 평균 > 0 인 칸 **{len(pos)}/{len(A)}**")
    print(f"  승률이 손익분기를 넘긴 칸 **{int((A.edge > 0).sum())}/{len(A)}**")
    if len(pos):
        print(f"\n{'방향':<7}{'문턱':>6}{'익절%':>7}{'손절%':>7}{'거래':>11}"
              f"{'승률%':>9}{'거래당평균%':>13}{'손익비':>8}{'양수종목%':>11}")
        print("-" * 104)
        for _, r in pos.head(12).iterrows():
            print(f"{r.side:<7}{r.thr:>6.0f}{100*r.tp:>7.0f}{100*r.sl:>7.0f}"
                  f"{int(r.trades):>11,}{r.win:>9.2f}{r.avg:>+13.3f}"
                  f"{r.payoff:>8.2f}{r.pos:>11.1f}")
    print(f"\n  전 격자 거래당 평균 중앙 **{A.avg.median():+.3f}%** · "
          f"최고 {A.avg.max():+.3f}% · 최저 {A.avg.min():+.3f}%")

    # ── ⑤ 방향 대조 ────────────────────────────────────────────
    sec("⑤ 방향 대조 — 롱과 숏은 거울인가 (교훈 #91)")
    m = (A[A.side == "long"].merge(A[A.side == "short"],
                                   on=["thr", "tp", "sl"],
                                   suffixes=("_l", "_s")))
    print(f"  롱 거래당평균 중앙 {m.avg_l.median():+.3f}% · "
          f"숏 {m.avg_s.median():+.3f}% · 합 {(m.avg_l+m.avg_s).median():+.3f}%")
    print(f"  롱·숏 둘 다 양수인 칸 {int(((m.avg_l>0)&(m.avg_s>0)).sum())}/{len(m)}")
    print("  → 합이 0 근처면 국면이 아니라 **마찰만 낸 거울**이다.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
