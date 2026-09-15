# -*- coding: utf-8 -*-
"""🔬 공통 성분 ②편 — 공통 성분의 정체와 시간 구조.

⚠ Binance 선물 klines 는 `3h` 인터벌이 **없다**(1h/2h/4h…). 1시간봉을 접는다.
"""
import pathlib, json, urllib.request
import numpy as np, pandas as pd

ROOT = pathlib.Path("/home/mint/auto_trading/backend")
PAPER = ROOT / "runs" / "kinematics_paper"
BUCKET, START = "3h", pd.Timestamp("2026-09-09 02:00", tz="UTC")
BR = {"s3short_dir": ("방향숏3", 3), "s3short_anti": ("역확인3", 3),
      "s3short_conf": ("확인숏3", 3), "s6both_imp": ("충격스프3", 6),
      "s3short_imp": ("충격숏3", 3), "s3short_h4": ("충격240", 3),
      "s3short_h4ec": ("충격240냉", 3), "s3short_h1": ("충격60", 3),
      "s3short_impns": ("무손숏3", 3)}
cols = {}
for tag, (nm, sl) in BR.items():
    d = pd.read_csv(PAPER / tag / "trades.csv")
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    d = d[d.closed_ts >= START]
    cols[nm] = d.groupby(d.closed_ts.dt.floor(BUCKET)).net_pct.sum() / sl
P = pd.DataFrame(cols)
P = P.reindex(pd.date_range(P.index.min(), P.index.max(), freq=BUCKET)).fillna(0.0)

raw = json.load(urllib.request.urlopen(
    "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=300",
    timeout=20))
h = pd.Series([float(k[4]) for k in raw],
              index=pd.to_datetime([k[0] for k in raw], unit="ms", utc=True))
b3 = h.resample(BUCKET).agg(["first", "last"])
btc = (100 * (b3["last"] / b3["first"] - 1)).reindex(P.index)

com = P.mean(axis=1)
ok = btc.notna()
print(f"■ ④ 공통 성분의 정체 — 토막 {int(ok.sum())}개")
print(f"   공통성분 ↔ BTC 3h 수익률  상관 {np.corrcoef(com[ok], btc[ok])[0,1]:+.3f}")
print(f"   BTC 토막평균 {btc[ok].mean():+.3f}% · 상승토막 "
      f"{int((btc[ok] > 0).sum())}/{int(ok.sum())}")
print(f"\n   갈래별 ↔ BTC 상관 (음수 = BTC 오르면 진다 = 숏 노출)")
for n in P.columns:
    print(f"   {n:<11}{np.corrcoef(P[n][ok], btc[ok])[0,1]:>+8.3f}")

print(f"\n■ ⑥ 시간 구조 — 앞 절반 vs 뒤 절반 (토막평균 자본%)")
half = len(P) // 2
print(f"{'갈래':<11}{'앞 25토막':>11}{'뒤 25토막':>11}{'차이':>9}")
for n in P.columns:
    a, b = P[n][:half].mean(), P[n][half:].mean()
    print(f"{n:<11}{a:>+11.3f}{b:>+11.3f}{b-a:>+9.3f}")
a, b = com[:half].mean(), com[half:].mean()
print(f"{'▶ 공통':<11}{a:>+11.3f}{b:>+11.3f}{b-a:>+9.3f}")
print(f"   뒤 절반에서 나빠진 갈래 "
      f"{sum(1 for n in P.columns if P[n][half:].mean() < P[n][:half].mean())}/9")

print(f"\n■ ⑦ 최근 12토막(36h) 드리프트")
print(f"{'갈래':<11}{'토막평균':>10}{'플러스':>9}{'공통대비 초과':>14}")
r = P[-12:]
rc = r.mean(axis=1)
for n in P.columns:
    print(f"{n:<11}{r[n].mean():>+10.3f}{int((r[n]>0).sum()):>6}/12"
          f"{r[n].mean()-rc.mean():>+14.3f}")
print(f"   ▶ 공통 {rc.mean():+.3f} · 플러스 갈래 "
      f"{sum(1 for n in P.columns if r[n].mean() > 0)}/9")
