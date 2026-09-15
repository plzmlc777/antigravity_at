# -*- coding: utf-8 -*-
"""🔬 공통 성분 진단 — "왜 갈래가 다 같이 지는가" (2026-09-15 대표님 질문).

상관이 낮은데도 같이 지는 일은 흔하다. **상관은 평균을 빼고 재기 때문**이다.
갈래마다 버는 *시점* 이 달라도(=상관 낮음), 평균이 다 같이 마이너스면
분산으로는 아무것도 못 막는다. 그래서 둘을 나눠 잰다.

① 토막 수익의 짝 상관 — 서로 다른 시점에 버는가
② 평균(드리프트) — 다 같이 지고 있는가
③ 공통 성분 — 횡단면 평균으로 각 갈래를 회귀했을 때 R²
④ 공통 성분의 정체 — 시장(BTC) 방향과 얼마나 같은가
⑤ 통행료 — 총수익에서 통행료를 빼기 전/후
"""
import pathlib, json, urllib.request
import numpy as np, pandas as pd

ROOT = pathlib.Path("/home/mint/auto_trading/backend")
PAPER = ROOT / "runs" / "kinematics_paper"
TOLL = 0.1004          # 왕복 통행료 %(실측)
BUCKET = "3h"
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")
BR = {
    "s3short_dir":   ("방향숏3",   3), "s3short_anti":  ("역확인3",   3),
    "s3short_conf":  ("확인숏3",   3), "s6both_imp":    ("충격스프3", 6),
    "s3short_imp":   ("충격숏3",   3), "s3short_h4":    ("충격240",   3),
    "s3short_h4ec":  ("충격240냉", 3), "s3short_h1":    ("충격60",    3),
    "s3short_impns": ("무손숏3",   3),
}


def load():
    cols, meta = {}, {}
    for tag, (nm, sl) in BR.items():
        d = pd.read_csv(PAPER / tag / "trades.csv")
        d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
        d = d[d.closed_ts >= START]
        k = d.closed_ts.dt.floor(BUCKET)
        cols[nm] = d.groupby(k).net_pct.sum() / sl
        meta[nm] = (len(d), d.net_pct.mean(), d.net_pct.mean() + TOLL)
    P = pd.DataFrame(cols)
    idx = pd.date_range(P.index.min(), P.index.max(), freq=BUCKET)
    return P.reindex(idx).fillna(0.0), meta


def btc_buckets(idx):
    url = ("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT"
           "&interval=3h&limit=200")
    raw = json.load(urllib.request.urlopen(url, timeout=20))
    t = pd.to_datetime([r[0] for r in raw], unit="ms", utc=True)
    r = pd.Series([100 * (float(k[4]) / float(k[1]) - 1) for k in raw], index=t)
    return r.reindex(idx)


P, meta = load()
nm = list(P.columns)
print(f"■ 표본 — 비겹침 {BUCKET} 토막 {len(P)}개 "
      f"({P.index[0].tz_convert('Asia/Seoul'):%m-%d %H:%M} ~ "
      f"{P.index[-1].tz_convert('Asia/Seoul'):%m-%d %H:%M} KST)")

C = P.corr()
iu = np.triu_indices(len(nm), 1)
pw = C.to_numpy()[iu]
print(f"\n■ ① 짝 상관 — 36쌍 중앙값 {np.median(pw):+.3f} · "
      f"평균 {pw.mean():+.3f} · 최소 {pw.min():+.3f} · 최대 {pw.max():+.3f}")
print(f"   +0.50 이상인 쌍 {int((pw >= 0.5).sum())}개 / 36")

print("\n■ ② 드리프트 — 토막당 평균 자본% (마이너스면 '그냥 지고 있다')")
print(f"{'갈래':<11}{'토막평균':>10}{'플러스토막':>11}{'거래':>7}"
      f"{'거래당net':>11}{'거래당gross':>12}{'통행료몫':>10}")
for n in nm:
    v = P[n].to_numpy()
    cnt, net, gross = meta[n]
    share = (TOLL / abs(gross) * 100) if gross else float("nan")
    print(f"{n:<11}{v.mean():>+10.3f}{int((v > 0).sum()):>8}/{len(v):<3}"
          f"{cnt:>7}{net:>+11.3f}{gross:>+12.3f}"
          f"{('%.0f%%' % share) if np.isfinite(share) else '—':>10}")

com = P.mean(axis=1)
print(f"\n■ ③ 공통 성분 — 횡단면 평균 토막수익 "
      f"(평균 {com.mean():+.3f} · 플러스 {int((com > 0).sum())}/{len(com)})")
print(f"{'갈래':<11}{'공통과 상관':>12}{'R²':>8}{'잔차평균':>10}")
for n in nm:
    r = np.corrcoef(P[n], com)[0, 1]
    b = np.polyfit(com, P[n], 1)[0]
    res = P[n] - np.polyval(np.polyfit(com, P[n], 1), com)
    print(f"{n:<11}{r:>+12.3f}{r*r:>8.3f}{res.mean():>+10.3f}")

try:
    b = btc_buckets(P.index)
    ok = b.notna() & com.notna()
    r = np.corrcoef(com[ok], b[ok])[0, 1]
    print(f"\n■ ④ 공통 성분의 정체 — BTC 3h 수익률과 상관 {r:+.3f} "
          f"({int(ok.sum())}토막)")
    print(f"   BTC 토막평균 {b[ok].mean():+.3f}% · "
          f"상승토막 {int((b[ok] > 0).sum())}/{int(ok.sum())}")
except Exception as e:
    print(f"\n■ ④ BTC 대조 실패 — {e}")

print(f"\n■ ⑤ 통행료 — 전 갈래 합산")
tot_n = sum(m[0] for m in meta.values())
tot_net = sum(m[0] * m[1] for m in meta.values())
tot_gr = sum(m[0] * m[2] for m in meta.values())
print(f"   거래 {tot_n}건 · 총 net {tot_net:+.1f}%p · 총 gross {tot_gr:+.1f}%p · "
      f"통행료 {tot_n * TOLL:.1f}%p")
