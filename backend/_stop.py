# -*- coding: utf-8 -*-
"""🔬 공통 성분 ⑤편 — 공통 성분의 정체는 **손절 5%** 인가.

진폭이 뒤 절반에 +81% 늘었는데 성적은 +0.542 → -0.136. 토막 상관은 -0.108.
가설: 진폭↑ → 5% 손절 히트율↑ → **선별이 달라도 같이 진다.**
손절 5%·240분은 아홉 갈래가 **공유하는 유일한 규칙**이다.
반증 장치: 손절이 없는 **무손숏3** 이 이 패턴에서 빠져야 한다.
"""
import pathlib
import numpy as np, pandas as pd

PAPER = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")
BR = {"s3short_dir": "방향숏3", "s3short_anti": "역확인3", "s3short_conf": "확인숏3",
      "s6both_imp": "충격스프3", "s3short_imp": "충격숏3", "s3short_h4": "충격240",
      "s3short_h4ec": "충격240냉", "s3short_h1": "충격60", "s3short_impns": "무손숏3"}

D = {}
for tag, nm in BR.items():
    d = pd.read_csv(PAPER / tag / "trades.csv")
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    D[nm] = d[d.closed_ts >= START].copy()

allt = pd.concat(D.values())
half = allt.closed_ts.min() + (allt.closed_ts.max() - allt.closed_ts.min()) / 2
print(f"■ 손절율 — 앞 절반 vs 뒤 절반 (분기 {half.tz_convert('Asia/Seoul'):%m-%d %H:%M} KST)")
print(f"{'갈래':<11}{'앞 손절율':>11}{'뒤 손절율':>11}{'차이':>9}"
      f"{'앞 거래당':>11}{'뒤 거래당':>11}")
for nm, d in D.items():
    a, b = d[d.closed_ts < half], d[d.closed_ts >= half]
    if not len(a) or not len(b):
        continue
    sa, sb = 100*a.stopped.mean(), 100*b.stopped.mean()
    print(f"{nm:<11}{sa:>10.1f}%{sb:>10.1f}%{sb-sa:>+9.1f}"
          f"{a.net_pct.mean():>+11.3f}{b.net_pct.mean():>+11.3f}")
a, b = allt[allt.closed_ts < half], allt[allt.closed_ts >= half]
print(f"{'▶ 전체':<11}{100*a.stopped.mean():>10.1f}%{100*b.stopped.mean():>10.1f}%"
      f"{100*(b.stopped.mean()-a.stopped.mean()):>+9.1f}"
      f"{a.net_pct.mean():>+11.3f}{b.net_pct.mean():>+11.3f}")

print("\n■ 손절된 거래 / 안 된 거래의 거래당 손익 (전 갈래 합산)")
for lab, m in (("손절", allt.stopped == 1), ("만기", allt.stopped == 0)):
    s = allt[m]
    print(f"   {lab}  {len(s):>4}건  거래당 {s.net_pct.mean():+.3f}%  "
          f"(앞 {a[a.stopped==(lab=='손절')].net_pct.mean():+.3f} → "
          f"뒤 {b[b.stopped==(lab=='손절')].net_pct.mean():+.3f})")

print("\n■ 반증 장치 — 손절 없는 무손숏3 은 이 패턴에서 빠지는가")
d = D["무손숏3"]
a2, b2 = d[d.closed_ts < half], d[d.closed_ts >= half]
print(f"   무손숏3 손절율 {100*d.stopped.mean():.1f}% · "
      f"거래당 앞 {a2.net_pct.mean():+.3f} → 뒤 {b2.net_pct.mean():+.3f} "
      f"({b2.net_pct.mean()-a2.net_pct.mean():+.3f})")
oth = pd.concat([v for k, v in D.items() if k != "무손숏3"])
ao, bo = oth[oth.closed_ts < half], oth[oth.closed_ts >= half]
print(f"   나머지 8종        거래당 앞 {ao.net_pct.mean():+.3f} → "
      f"뒤 {bo.net_pct.mean():+.3f} ({bo.net_pct.mean()-ao.net_pct.mean():+.3f})")
print("   ▶ 무손숏3 이 더 나빠졌으면 '손절 때문'이라는 설명은 **틀렸다**")
