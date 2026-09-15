# -*- coding: utf-8 -*-
"""🔬 공통 성분 ④편 — 공통 성분 = **알트 전반의 진폭**인가.

BTC 방향도(-0.009), 종목 겹침도(중앙 0.166) 아니었다. 남은 후보는
"이 갈래들이 공통으로 먹고 사는 원재료" — 즉 알트의 급등락 자체다.
급등락이 없으면 충격·속도 선별은 **동시에** 굶는다.
진폭 대리변수 = 실제로 거래된 종목들의 3h 토막 |수익률| 평균.
"""
import pathlib, json, urllib.request, time
import numpy as np, pandas as pd

PAPER = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
BUCKET, START = "3h", pd.Timestamp("2026-09-09 02:00", tz="UTC")
BR = {"s3short_dir": ("방향숏3", 3), "s3short_anti": ("역확인3", 3),
      "s3short_conf": ("확인숏3", 3), "s6both_imp": ("충격스프3", 6),
      "s3short_imp": ("충격숏3", 3), "s3short_h4": ("충격240", 3),
      "s3short_h4ec": ("충격240냉", 3), "s3short_h1": ("충격60", 3),
      "s3short_impns": ("무손숏3", 3)}

cols, freq = {}, {}
for tag, (nm, sl) in BR.items():
    d = pd.read_csv(PAPER / tag / "trades.csv")
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    d = d[d.closed_ts >= START]
    cols[nm] = d.groupby(d.closed_ts.dt.floor(BUCKET)).net_pct.sum() / sl
    for s in d.symbol:
        freq[s] = freq.get(s, 0) + 1
P = pd.DataFrame(cols)
P = P.reindex(pd.date_range(P.index.min(), P.index.max(), freq=BUCKET)).fillna(0.0)
com = P.mean(axis=1)

top = [s for s, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:25]]
print(f"■ 진폭 대리변수 — 최다 거래 종목 {len(top)}개의 3h |수익률| 평균")
rows = {}
for s in top:
    try:
        raw = json.load(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/klines?symbol={s}&interval=1h&limit=300",
            timeout=20))
        h = pd.DataFrame({"c": [float(k[4]) for k in raw],
                          "o": [float(k[1]) for k in raw]},
                         index=pd.to_datetime([k[0] for k in raw], unit="ms", utc=True))
        g = h.resample(BUCKET).agg({"o": "first", "c": "last"})
        rows[s] = (100 * (g.c / g.o - 1)).reindex(P.index)
        time.sleep(0.05)
    except Exception:
        pass
R = pd.DataFrame(rows)
amp = R.abs().mean(axis=1)          # 진폭
drift = R.mean(axis=1)              # 알트 전반 방향
ok = amp.notna() & (R.notna().sum(axis=1) >= 10)
print(f"   종목 {R.shape[1]}개 · 유효 토막 {int(ok.sum())}/{len(P)}")

def c(a, b):
    return np.corrcoef(a[ok], b[ok])[0, 1]

print(f"\n■ 공통 성분과의 상관")
print(f"   ↔ 알트 진폭(|수익률| 평균)   {c(com, amp):+.3f}")
print(f"   ↔ 알트 방향(수익률 평균)     {c(com, drift):+.3f}")
print(f"\n■ 갈래별 상관")
print(f"{'갈래':<11}{'진폭':>9}{'방향':>9}")
for n in P.columns:
    print(f"{n:<11}{c(P[n], amp):>+9.3f}{c(P[n], drift):>+9.3f}")

half = int(ok.sum()) // 2
a, b = amp[ok][:half].mean(), amp[ok][half:].mean()
print(f"\n■ 진폭의 시간 구조 — 앞 절반 {a:.3f}% · 뒤 절반 {b:.3f}% "
      f"({100*(b/a-1):+.1f}%)")
a, b = com[ok][:half].mean(), com[ok][half:].mean()
print(f"   공통 성분    — 앞 절반 {a:+.3f} · 뒤 절반 {b:+.3f}")
