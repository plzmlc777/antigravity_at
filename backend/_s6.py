# -*- coding: utf-8 -*-
"""s6양다리(s6both_h240)가 교체 후보 풀 밖이다 — 실력을 재본다.

`_rotate.py` 의 BR 에는 9갈래만 등록돼 있다. s2both · s6both_h240 · s10both ·
ac16b · utc01 · revcont 는 **순위표에도 교체 판정에도 안 나온다.**
"""
import pathlib
import numpy as np, pandas as pd
P = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
TOLL = 0.1004
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")
now = pd.Timestamp.now(tz="UTC")
ROT9 = {"s3short_dir","s3short_anti","s3short_conf","s6both_imp","s3short_imp",
        "s3short_h4","s3short_h4ec","s3short_h1","s3short_impns"}
CAND = {"s6both_h240": ("s6양다리", 6), "s2both": ("s2양다리", 2),
        "s10both": ("s10양다리", 10), "s6both_ac1": ("체결자기여기", 6),
        "s10both_d5_utc01": ("되돌림UTC1", 10), "s3short_rmz": ("최장연속숏", 3),
        "s3short_conf": ("확인숏3(참고)", 3), "s3short_dir": ("방향숏3(현행15)", 3),
        "s3short_anti": ("역확인3(현행8)", 3)}
print("■ 후보 풀 밖 갈래의 실력 — 공통 출발선 09-09 11:00 KST")
print(f"{'갈래':<14}{'풀':<5}{'거래':>6}{'실현합%':>9}{'자본%':>8}{'거래당':>8}"
      f"{'승률':>7}{'손절':>7}{'24h자본%':>10}{'12h':>8}")
def cap(d, sl, h=None):
    m = d if h is None else d[d.closed_ts >= now - pd.Timedelta(hours=h)]
    return m.net_pct.sum()/sl
rows=[]
for tag,(nm,sl) in CAND.items():
    f=P/tag/"trades.csv"
    if not f.exists(): print(f"{nm:<14} 원장 없음"); continue
    d=pd.read_csv(f); d["closed_ts"]=pd.to_datetime(d.closed_ts,utc=True,format="mixed")
    d=d[d.closed_ts>=START]
    if "short" not in d: d["short"]=True
    inpool = "O" if tag in ROT9 else "**X**"
    print(f"{nm:<14}{inpool:<5}{len(d):>6}{d.net_pct.sum():>+9.2f}{cap(d,sl):>+8.2f}"
          f"{d.net_pct.mean():>+8.3f}{100*(d.net_pct>0).mean():>6.0f}%"
          f"{100*d.stopped.mean():>6.0f}%{cap(d,sl,24):>+10.2f}{cap(d,sl,12):>+8.2f}")
    rows.append((nm,tag,d,sl))
print("\n■ s6양다리 다리별 분해 (전 구간)")
d=[r for r in rows if r[1]=="s6both_h240"]
if d:
    d=d[0][2]
    for sh,lab in ((False,"롱"),(True,"숏")):
        s=d[d.short==sh].net_pct
        if len(s)<5: continue
        se=s.std(ddof=1)/np.sqrt(len(s))
        print(f"   {lab} {len(s):>4}건 net {s.mean():+7.3f} 중앙 {s.median():+7.3f} "
              f"승률 {100*(s>0).mean():5.1f}% t {s.mean()/se:+6.2f} 95%하한 {s.mean()-1.96*se:+7.3f}")
    print("\n■ s6양다리 ↔ 현행 두 계좌 상관 (3시간 토막, 조건 ③ 문턱 +0.50)")
    edges=pd.date_range(now-pd.Timedelta(hours=72),now,freq="3h")
    def bk(tag,sl):
        x=pd.read_csv(P/tag/"trades.csv")
        x["closed_ts"]=pd.to_datetime(x.closed_ts,utc=True,format="mixed")
        return np.array([x[(x.closed_ts>=edges[i])&(x.closed_ts<edges[i+1])].net_pct.sum()/sl
                         for i in range(len(edges)-1)])
    a=bk("s6both_h240",6)
    for t2,n2,s2 in (("s3short_dir","방향숏3(계좌15)",3),("s3short_anti","역확인3(계좌8)",3)):
        print(f"   s6양다리 ↔ {n2:<16} {np.corrcoef(a,bk(t2,s2))[0,1]:+.3f}")
