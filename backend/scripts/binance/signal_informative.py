"""선택 신호가 결과를 예측하나 — 갈래 원장 하나로 재는 검정.

## 무엇을 묻나

운동학 갈래의 주장은 "**z_vel 이 낮을수록 롱이 좋다** (많이 떨어진 종목이 되돌린다)"
이다. 원장에는 각 거래의 `z_vel` 과 실현 `net_pct` 가 남아 있으니, 그 주장이
자기 원장 안에서 성립하는지 직접 잴 수 있다.

    ① 상관       롱은 z_vel 과 net_pct 가 **음의 상관**이어야 한다
                 (숏은 z_vel 자리에 신호가 그대로 들어가므로 다리마다 따로 본다)
    ② 단조성     밴드를 3등분해 순서가 맞는지 — 상관이 약해도 단조면 흔적이다
    ③ 방향 대조군 두 다리 합이 **-2×수수료** 근처면 정보가 없다 (교훈#91·#82)

## ⚠ 이 도구가 못 하는 것

원장에는 **고르지 않은 후보**가 없다. 그래서 "고른 것이 안 고른 것보다 나은가"는
못 잰다. 여기서 재는 것은 **고른 것들 사이에서 신호 세기가 결과를 가르는가**뿐이다.
그것도 못 하면 신호가 순위를 매길 근거가 없다는 뜻이다.

## ⚠ 표본

거래 150건 안팎이면 상관 |r| 0.16 부터 p<0.05 다. 그보다 작은 r 은 **0과 구별
못 한다** — 부호만 보고 방향을 읽지 마라.

사용:
    python3 -m scripts.binance.signal_informative --dir runs/kinematics_paper/s2both
    python3 -m scripts.binance.signal_informative --dir runs/kinematics_paper/s6both_h240
    python3 -m scripts.binance.signal_informative --all
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
FEE_RT = 0.072          # 페이퍼 가정(왕복). 실거래 실측은 0.1003
FEE_LIVE = 0.1003       # 48/48건 실측(2026-09-07)


def one(d: Path, fee: float) -> None:
    t = pd.read_csv(d / "trades.csv")
    if len(t) < 20:
        print("  거래 %d건 — 너무 적다" % len(t))
        return
    print("■ %s — %d거래" % (d.name, len(t)))

    print("  ① 신호가 결과를 예측하나")
    for k, g in t.groupby(t.short):
        lab = "숏" if k else "롱"
        if g.z_vel.nunique() < 3:
            print("    %s %3d건 — z_vel 이 상수라 검정 불가" % (lab, len(g)))
            continue
        r, p = stats.pearsonr(g.z_vel, g.net_pct)
        sr, sp = stats.spearmanr(g.z_vel, g.net_pct)
        # 150건에서 유의 문턱 |r| ≈ 1.96/sqrt(n)
        thr = 1.96 / np.sqrt(len(g))
        mark = " **유의**" if p < 0.05 else " (0과 구별 안 됨, |r| %.3f 필요)" % thr
        print("    %s %3d건  r %+.3f (p %.3f) · 스피어만 %+.3f (p %.3f)%s"
              % (lab, len(g), r, p, sr, sp, mark))

    print("  ② 밴드 3등분 — 순서가 맞나 (롱은 하<중<상 순으로 나빠져야 함)")
    for k, g in t.groupby(t.short):
        lab = "숏" if k else "롱"
        if g.z_vel.nunique() < 3:
            continue
        g = g.copy()
        g["b"] = pd.qcut(g.z_vel, 3, labels=["하", "중", "상"], duplicates="drop")
        m = g.groupby("b", observed=True).net_pct.agg(["size", "mean"])
        body = " | ".join("%s %d건 %+.3f%%" % (i, r["size"], r["mean"])
                          for i, r in m.iterrows())
        mono = m["mean"].is_monotonic_decreasing if not k else m["mean"].is_monotonic_increasing
        print("    %s  %s   %s" % (lab, body, "**단조**" if mono else "비단조"))

    print("  ③ 통행료 대비 — 정보가 0 이면 거래당 순손익은 **-수수료**다")
    # ⚠ `net_pct` 는 이미 왕복 수수료를 뺀 값이고 여기 평균은 **거래당**이다.
    #   기준선을 -2×fee 로 잡으면 통행료를 두 번 빼는 것이다(2026-09-07 수정).
    tot = t.net_pct.mean()
    print("    거래당 순 %+.3f%%  ·  정보 0 기준선 페이퍼 %.3f%% / 실거래 %.3f%%"
          % (tot, -FEE_RT, -FEE_LIVE))
    print("    총수익(수수료 前) = 순 + 수수료 = **%+.3f%%** (페이퍼 가정)"
          % (tot + FEE_RT))
    print("    실거래 수수료를 물리면 순 %+.3f%%  (총수익 - %.4f)"
          % (tot + FEE_RT - FEE_LIVE, FEE_LIVE))
    n = len(t)
    k = max(1, int(np.ceil(n * 0.05)))
    print("    거래당 %+.3f%% · 상5제외 %+.3f%% · 중앙 %+.3f%% · 승률 %.0f%%"
          % (t.net_pct.mean(),
             t.net_pct.sort_values(ascending=False).iloc[k:].mean(),
             t.net_pct.median(), 100 * (t.net_pct > 0).mean()))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="runs/kinematics_paper/s2both")
    ap.add_argument("--all", action="store_true", help="kinematics_paper 전 갈래")
    ap.add_argument("--fee", type=float, default=FEE_RT)
    a = ap.parse_args()
    if a.all:
        base = ROOT / "runs/kinematics_paper"
        for d in sorted(base.iterdir()):
            if (d / "trades.csv").exists() and not (d / "RETIRED_20260905.md").exists() \
                    and not (d / "RETIRED_20260906.md").exists():
                one(d, a.fee)
    else:
        one(ROOT / a.dir, a.fee)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
