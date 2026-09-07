"""실거래 ↔ 페이퍼 대조 — 마찰이 얼마인지 **따로** 잰다.

## 왜 필요한가

`kinematics-live-s2both`(계좌 15)와 `kinematics-paper-s2both` 는 같은 규칙·같은
유니버스인데 **기동 시각이 달라 슬롯 주기가 35~40분 어긋났다**. 그래서 매 순간
서로 다른 종목을 들고 있고, 둘의 손익 차이에 **체결 마찰과 종목 선택이 섞인다**.

두 갈래를 나란히 빼면 "라이브가 -0.061%p 나쁘다"까지는 나오지만 그게 슬리피지
때문인지 다른 종목을 집어서인지 못 가린다. 그래서 여기서는 **라이브 원장이 이미
기록한 값**으로 마찰만 직접 잰다.

    sig_px   신호 시각의 가격 (페이퍼가 체결가로 쓰는 값)
    entry_px 실제 체결가
    slip_bp  둘의 차이 (bp) — **이게 페이퍼가 못 재는 영역이다**
    fill_ts  실제 체결 시각 → 신호와의 간격이 진입 지연
    fee_pct  실제 수수료 (페이퍼는 왕복 0.072% 가정)

## 관측 단위

거래 하나가 관측 하나다. 다만 **같은 사이클에 열린 롱·숏 두 다리는 독립이
아니다** — 다리별로도 따로 낸다.

## 한계

라이브 표본이 얇으면(20건 안팎) 중앙값만 읽고 평균은 믿지 마라. 꼬리 한 건이
평균을 통째로 옮긴다(교훈#89 와 같은 형태).

사용:
    python3 -m scripts.binance.live_vs_paper
    python3 -m scripts.binance.live_vs_paper --live runs/kinematics_live/s2both \
                                             --paper runs/kinematics_paper/s2both
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def load(p: Path) -> pd.DataFrame:
    t = pd.read_csv(p / "trades.csv")
    for c in ("entry_ts", "exit_ts", "closed_ts", "fill_ts"):
        if c in t:
            t[c] = pd.to_datetime(t[c], utc=True, errors="coerce")
    t["kf"] = t.stake * t.net_pct
    return t


def pct(x: pd.Series, q) -> float:
    return float(np.nanpercentile(x.dropna(), q)) if x.notna().any() else np.nan


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", default="runs/kinematics_live/s2both")
    ap.add_argument("--paper", default="runs/kinematics_paper/s2both")
    a = ap.parse_args()
    L, P = load(ROOT / a.live), load(ROOT / a.paper)

    t0 = L.entry_ts.min()
    Pw = P[P.entry_ts >= t0]                      # 같은 창의 페이퍼
    print("■ 표본")
    print("  라이브   %3d건 · %s ~ %s" % (len(L), L.entry_ts.min(), L.entry_ts.max()))
    print("  페이퍼   %3d건 (전체 %d건 중 라이브 개시 후)" % (len(Pw), len(P)))

    print("\n■ 손익 — 같은 창")
    for lab, d in (("라이브", L), ("페이퍼", Pw)):
        print("  %s 거래당 %+.3f%% · 중앙 %+.3f%% · 합기여 %+.3f%% · 승률 %.0f%%"
              % (lab, d.net_pct.mean(), d.net_pct.median(),
                 d.kf.sum(), 100 * (d.net_pct > 0).mean()))
    print("  차이(라이브-페이퍼) 거래당 %+.3f%%p"
          % (L.net_pct.mean() - Pw.net_pct.mean()))
    print("  ⚠ 이 차이는 **마찰 + 종목선택**이 섞인 값이다. 아래에서 마찰만 뗀다.")

    if "slip_bp" in L:
        s = L.slip_bp.astype(float)
        print("\n■ 슬리피지 (신호가 → 실제 체결가, bp) — **페이퍼가 못 재는 영역**")
        print("  건수 %d · 중앙 %+.2f · 평균 %+.2f · p10 %+.2f · p90 %+.2f · 최악 %+.2f"
              % (s.notna().sum(), s.median(), s.mean(),
                 pct(s, 10), pct(s, 90), s.max()))
        for k, g in L.groupby(L.short):
            lab = "숏 " if k else "롱 "
            print("    %s %2d건 중앙 %+.2f bp · 평균 %+.2f bp"
                  % (lab, len(g), g.slip_bp.median(), g.slip_bp.mean()))
        print("  거래당 손익 환산 중앙 **%+.4f%%**  (1bp = 0.01%%)"
              % (s.median() / 100.0))

    if "fill_ts" in L and L.fill_ts.notna().any():
        d = (L.fill_ts - L.entry_ts).dt.total_seconds()
        print("\n■ 진입 지연 (신호 시각 → 실제 체결)")
        print("  중앙 %.1f초 · p90 %.1f초 · 최대 %.1f초"
              % (d.median(), pct(d, 90), d.max()))

    if "fee_pct" in L:
        f = L.fee_pct.astype(float)
        print("\n■ 수수료 — 페이퍼 가정 0.072%% (왕복)")
        print("  실제 중앙 %.4f%% · 평균 %.4f%% · 최대 %.4f%%"
              % (f.median(), f.mean(), f.max()))
        print("  가정 대비 %+.4f%%p" % (f.median() - 0.072))

    # 같은 종목·같은 방향을 둘 다 잡은 경우 — 있으면 가장 깨끗한 대조다
    key = ["symbol", "short"]
    both = L.merge(Pw, on=key, suffixes=("_L", "_P"))
    both = both[(both.entry_ts_L - both.entry_ts_P).abs() <= pd.Timedelta("2h")]
    print("\n■ 같은 종목·방향을 2시간 안에 둘 다 잡은 거래 — %d건" % len(both))
    if len(both):
        print("  라이브 %+.3f%% vs 페이퍼 %+.3f%% · 차이 %+.3f%%p"
              % (both.net_pct_L.mean(), both.net_pct_P.mean(),
                 both.net_pct_L.mean() - both.net_pct_P.mean()))
        for r in both.itertuples():
            print("    %-12s %s  라이브 %+7.3f%%  페이퍼 %+7.3f%%  간격 %+.0f분"
                  % (r.symbol, "S" if r.short else "L", r.net_pct_L, r.net_pct_P,
                     (r.entry_ts_L - r.entry_ts_P).total_seconds() / 60))
    else:
        print("  없다 — **주기가 어긋나 겹치는 거래가 없다**. 이 표가 채워지기 전에는")
        print("  손익 차이를 슬리피지로 읽지 마라. 위의 slip_bp 만이 마찰의 직접 측정이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
