# -*- coding: utf-8 -*-
"""🔬 공통 성분 ③편 — 갈래들이 **같은 종목을 동시에** 잡고 있나.

공통 성분이 BTC 방향이 아니라면(실측 -0.009), 다음 후보는 **선별 풀의 겹침**이다.
아홉 갈래가 이름만 다르고 같은 종목을 같은 시각에 숏하고 있으면,
분산은 명목뿐이고 손익은 당연히 같이 움직인다.
"""
import pathlib, itertools
import numpy as np, pandas as pd

PAPER = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")
BR = {"s3short_dir": "방향숏3", "s3short_anti": "역확인3", "s3short_conf": "확인숏3",
      "s6both_imp": "충격스프3", "s3short_imp": "충격숏3", "s3short_h4": "충격240",
      "s3short_h4ec": "충격240냉", "s3short_h1": "충격60", "s3short_impns": "무손숏3"}

ent, sym = {}, {}
for tag, nm in BR.items():
    d = pd.read_csv(PAPER / tag / "trades.csv")
    d["entry_ts"] = pd.to_datetime(d.entry_ts, utc=True, format="mixed")
    d = d[d.entry_ts >= START]
    # (종목, 진입 3시간 토막) 쌍의 집합
    ent[nm] = set(zip(d.symbol, d.entry_ts.dt.floor("3h")))
    sym[nm] = set(d.symbol)

nms = list(BR.values())
print("■ 진입 겹침 — (종목 × 진입 3h토막) 쌍의 자카드 지수")
print("   1.000 = 완전히 같은 것을 같은 때 잡는다 · 0 = 전혀 안 겹친다\n")
hdr = "".join(f"{n[:5]:>8}" for n in nms)
print(f"{'':<11}{hdr}")
for a in nms:
    row = ""
    for b in nms:
        if a == b:
            row += f"{'·':>8}"
        else:
            j = len(ent[a] & ent[b]) / max(1, len(ent[a] | ent[b]))
            row += f"{j:>8.3f}"
    print(f"{a:<11}{row}")

pairs = [(a, b) for a, b in itertools.combinations(nms, 2)]
js = [len(ent[a] & ent[b]) / max(1, len(ent[a] | ent[b])) for a, b in pairs]
print(f"\n   36쌍 중앙값 {np.median(js):.3f} · 최대 {max(js):.3f} "
      f"({pairs[int(np.argmax(js))][0]}↔{pairs[int(np.argmax(js))][1]})")

print("\n■ 종목 풀 겹침 — 어떤 종목을 고르는가 (진입 시각 무시)")
ss = [len(sym[a] & sym[b]) / max(1, len(sym[a] | sym[b])) for a, b in pairs]
print(f"   36쌍 중앙값 {np.median(ss):.3f} · 최대 {max(ss):.3f} "
      f"({pairs[int(np.argmax(ss))][0]}↔{pairs[int(np.argmax(ss))][1]})")
for n in nms:
    print(f"   {n:<11} 서로 다른 종목 {len(sym[n]):>4}개")

allsym = set().union(*sym.values())
print(f"\n   아홉 갈래가 건드린 종목 합집합 {len(allsym)}개")
cnt = pd.Series({s: sum(1 for n in nms if s in sym[n]) for s in allsym})
print(f"   그중 갈래 1개만 잡은 종목 {int((cnt == 1).sum())}개 · "
      f"5개 이상이 잡은 종목 {int((cnt >= 5).sum())}개")
