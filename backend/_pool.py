# -*- coding: utf-8 -*-
"""풀 밖 갈래를 **현행 교체 조건 ①~⑥ 그대로** 걸어본다 (계좌15 기준)."""
import pathlib
import numpy as np, pandas as pd
P = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
now = pd.Timestamp.now(tz="UTC")
PERSIST_W, PERSIST_MIN, OFF = 4, 3, (0, 1, 2)
CORR_MAX, STOP_MAX = 0.50, 45.0
OUT = {"s6both_h240": ("s6양다리", 6), "s2both": ("s2양다리", 2),
       "s10both": ("s10양다리", 10), "s6both_ac1": ("체결자기여기", 6),
       "s10both_d5_utc01": ("되돌림UTC1", 10), "s3short_rmz": ("최장연속숏", 3),
       "s10both_d5_revcont": ("되돌림연속", 10)}
def load(tag):
    d = pd.read_csv(P/tag/"trades.csv")
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    return d
def cap(d, sl, h):
    return d[d.closed_ts >= now - pd.Timedelta(hours=h)].net_pct.sum()/sl
def bko(d, sl, off, n):
    end = now - pd.Timedelta(hours=off)
    e = pd.date_range(end - pd.Timedelta(hours=3*n), end, freq="3h")
    return np.array([d[(d.closed_ts>=e[i])&(d.closed_ts<e[i+1])].net_pct.sum()/sl
                     for i in range(len(e)-1)])
def persist(d, sl):
    pos, ex = [], []
    for o in OFF:
        b = bko(d, sl, o, PERSIST_W)
        pos.append(int((b>0).sum())); ex.append(float(b.sum()-b.max()))
    return int(np.median(pos)), float(np.median(ex))
def bk72(d, sl):
    e = pd.date_range(now-pd.Timedelta(hours=72), now, freq="3h")
    return np.array([d[(d.closed_ts>=e[i])&(d.closed_ts<e[i+1])].net_pct.sum()/sl
                     for i in range(len(e)-1)])
cur = load("s3short_dir"); other = load("s3short_anti")
c12, c24 = cap(cur,3,12), cap(cur,3,24)
ob = bk72(other, 3)
print(f"■ 계좌15 현행 방향숏3 — 12h {c12:+.2f}% · 24h {c24:+.2f}%")
print(f"■ 풀 밖 갈래를 조건 ①~⑥ 에 걸어본다 (상대계좌 = 역확인3)\n")
print(f"{'갈래':<12}{'12h':>8}{'24h':>8}{'①':>4}{'②':>4}{'상관':>8}{'③':>4}"
      f"{'손절':>7}{'④':>4}{'4토막+':>8}{'최대제외':>10}{'⑥':>4}  판정")
for tag,(nm,sl) in OUT.items():
    f = P/tag/"trades.csv"
    if not f.exists():
        print(f"{nm:<12}   원장 없음"); continue
    d = load(tag)
    a12, a24 = cap(d,sl,12), cap(d,sl,24)
    m24 = d[d.closed_ts >= now - pd.Timedelta(hours=24)]
    if len(m24) < 3:
        print(f"{nm:<12}{a12:>8.2f}{a24:>8.2f}   24h 거래 {len(m24)}건 — 표본부족"); continue
    stop = 100*m24.stopped.mean()
    tb = bk72(d, sl)
    r = np.corrcoef(ob, tb)[0,1] if tb.std()>0 and ob.std()>0 else 0.0
    pos, ex = persist(d, sl)
    o1 = a12 > c12 and a24 > c24
    o2 = a24 > 0
    o3 = r < CORR_MAX
    o4 = stop <= STOP_MAX
    o6 = pos >= PERSIST_MIN and ex > 0
    ok = o1 and o2 and o3 and o4 and o6
    M = lambda b: "✅" if b else "❌"
    print(f"{nm:<12}{a12:>+8.2f}{a24:>+8.2f}{M(o1):>4}{M(o2):>4}{r:>+8.3f}{M(o3):>4}"
          f"{stop:>6.0f}%{M(o4):>4}{pos:>6}/4{ex:>+10.2f}{M(o6):>4}  "
          f"{'🔄 **전부 통과**' if ok else ''}")
