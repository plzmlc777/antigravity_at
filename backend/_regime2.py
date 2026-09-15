# -*- coding: utf-8 -*-
"""🔬 공통 성분 ⑥편 — 남은 설명: **되돌림이 사라진 국면**인가.

지금까지 기각된 것: BTC 방향(-0.009) · 종목 겹침(중앙 0.166) ·
진폭 토막상관(-0.108) · 손절 규칙(무손숏3 이 가장 크게 무너져 반증).
남은 가설: 아홉 갈래가 공통으로 먹는 원재료 = **급등 뒤 되돌림**.
진폭이 +81% 늘었는데 숏이 진다면, 급등이 **되돌지 않고 이어졌다**는 뜻이다.
"""
import pathlib, json, urllib.request, time
import numpy as np, pandas as pd

PAPER = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")
BR = {"s3short_dir": "방향숏3", "s3short_anti": "역확인3", "s3short_conf": "확인숏3",
      "s6both_imp": "충격스프3", "s3short_imp": "충격숏3", "s3short_h4": "충격240",
      "s3short_h4ec": "충격240냉", "s3short_h1": "충격60", "s3short_impns": "무손숏3"}
D, freq = {}, {}
for tag, nm in BR.items():
    d = pd.read_csv(PAPER / tag / "trades.csv")
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    d = d[d.closed_ts >= START]
    D[nm] = d
    for s in d.symbol:
        freq[s] = freq.get(s, 0) + 1
allt = pd.concat(D.values())
half = allt.closed_ts.min() + (allt.closed_ts.max() - allt.closed_ts.min()) / 2

print("■ 만기 청산분(손절 제외)의 분포 — 되돌림이 오고 있나")
exp = allt[allt.stopped == 0]
for lab, m in (("앞 절반", exp.closed_ts < half), ("뒤 절반", exp.closed_ts >= half)):
    s = exp[m].net_pct
    print(f"   {lab}  {len(s):>4}건  평균 {s.mean():+.3f}  중앙 {s.median():+.3f}  "
          f"승률 {100*(s>0).mean():.1f}%  상위10% {s.quantile(0.9):+.2f}  "
          f"하위10% {s.quantile(0.1):+.2f}")

print("\n■ 알트 전반 방향 — 앞/뒤 (최다 거래 25종목 3h 수익률 평균)")
top = [s for s, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:25]]
rows = {}
for s in top:
    try:
        raw = json.load(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/klines?symbol={s}&interval=1h&limit=300",
            timeout=20))
        h = pd.DataFrame({"c": [float(k[4]) for k in raw], "o": [float(k[1]) for k in raw]},
                         index=pd.to_datetime([k[0] for k in raw], unit="ms", utc=True))
        g = h.resample("3h").agg({"o": "first", "c": "last"})
        rows[s] = 100 * (g.c / g.o - 1)
        time.sleep(0.05)
    except Exception:
        pass
R = pd.DataFrame(rows)
R = R[(R.index >= START) & (R.index <= allt.closed_ts.max())]
a, b = R[R.index < half], R[R.index >= half]
print(f"   앞 절반  토막평균 {a.mean(axis=1).mean():+.3f}%  "
      f"누적 {a.mean(axis=1).sum():+.2f}%  상승토막 "
      f"{int((a.mean(axis=1)>0).sum())}/{len(a)}")
print(f"   뒤 절반  토막평균 {b.mean(axis=1).mean():+.3f}%  "
      f"누적 {b.mean(axis=1).sum():+.2f}%  상승토막 "
      f"{int((b.mean(axis=1)>0).sum())}/{len(b)}")

print("\n■ 되돌림 지속성 — 3h 수익률의 1기 자기상관 (음수 = 되돌림)")
def ac(X):
    v = []
    for c in X.columns:
        s = X[c].dropna()
        if len(s) > 8:
            v.append(np.corrcoef(s[:-1], s[1:])[0, 1])
    return np.mean(v), len(v)
for lab, X in (("앞 절반", a), ("뒤 절반", b)):
    m, n = ac(X)
    print(f"   {lab}  자기상관 평균 {m:+.3f}  ({n}종목)")
print("   ▶ 뒤 절반에서 자기상관이 **0 쪽으로/양수로** 움직였으면,")
print("     급등이 되돌지 않고 이어진 것 — 숏 선별이 공통으로 굶는다")
