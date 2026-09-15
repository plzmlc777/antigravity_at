# -*- coding: utf-8 -*-
"""🔬 롱 다리 전수 조사 — 이미 `both` 로 도는 갈래에 롱이 이미 있다.

새로 띄우기 전에 **공짜로 있는 것부터** 본다. 6갈래가 이미 롱·숏 양다리로
돌고 있는데, 지금까지 롱 다리를 따로 본 적이 없다(충격스프3 만 쟀다).

대조 — 같은 구간 무조건 롱(240분 +0.615 / 480분 +1.330, 통행료 차감).
"""
import pathlib
import numpy as np, pandas as pd

P = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
TOLL = 0.1004
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")
# 태그 → (이름, 신호, 보유분, 대조 기준)
BOTH = {
    "s2both":      ("s2양다리",   "kine", 240, 0.615),
    "s6both_h240": ("s6양다리",   "kine", 240, 0.615),
    "s6both_imp":  ("충격스프3",  "imp",  480, 1.330),
    "s6both_ac1":  ("체결자기여기", "ac1",  480, 1.330),
    "s10both":     ("s10양다리",  "kine", 240, 0.615),
    "s10both_utc01": ("되돌림UTC1", "rev", 120, 0.219),
}
print(f"■ 롱 다리 전수 — 통행료 {TOLL}% · 출발선 09-09 11:00 KST")
print(f"{'갈래':<12}{'신호':<7}{'보유':>6}{'롱거래':>7}{'롱 net':>9}{'중앙':>8}"
      f"{'승률':>7}{'t':>7}{'95%하한':>9}{'무조건롱':>9}{'초과':>9}")
found = []
for tag, (nm, sig, hold, ctrl) in BOTH.items():
    f = P / tag / "trades.csv"
    if not f.exists():
        print(f"{nm:<12}{sig:<7}{hold:>6}   — 원장 없음 ({tag})")
        continue
    d = pd.read_csv(f)
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    d = d[d.closed_ts >= START]
    s = d[d.short == False].net_pct
    if len(s) < 10:
        print(f"{nm:<12}{sig:<7}{hold:>6}{len(s):>7}   표본부족")
        continue
    se = s.std(ddof=1)/np.sqrt(len(s))
    lo = s.mean() - 1.96*se
    print(f"{nm:<12}{sig:<7}{hold:>6}{len(s):>7}{s.mean():>+9.3f}{s.median():>+8.3f}"
          f"{100*(s>0).mean():>6.1f}%{s.mean()/se:>+7.2f}{lo:>+9.3f}"
          f"{ctrl:>+9.3f}{s.mean()-ctrl:>+9.3f}")
    found.append((nm, s.mean()-ctrl, s.mean()/se))
print("\n   초과 = 롱 다리 거래당 − 같은 구간 무조건 롱")
if found:
    best = max(found, key=lambda x: x[1])
    print(f"   ▶ 초과 1위 {best[0]} {best[1]:+.3f}%p (t {best[2]:+.2f})")
    print(f"   ▶ 무조건 롱을 이긴 갈래 {sum(1 for _,e,_ in found if e>0)}/{len(found)}")
