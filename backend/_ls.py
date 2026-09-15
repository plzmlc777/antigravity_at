# -*- coding: utf-8 -*-
"""🔬 국면 × 롱·숏 계열 — 같은 창에서 나란히 (2026-09-15 대표님 질문).

⚠ 롱과 숏은 **각자의 무조건 대조군**과 비교해야 한다. 지금처럼 알트가 오르는
  국면에서는 롱이 그냥 유리하고 숏이 그냥 불리하다 — 절대 수치를 나란히 놓으면
  "롱이 낫다"는 국면 얘기를 "롱 선별이 낫다"로 읽는다.
"""
import json, urllib.request, time, pathlib
import numpy as np, pandas as pd

P = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
TOLL, NSYM, BAR, BARMIN = 0.1004, 25, "15m", 15
WINS = (6, 12, 24)
HOLD = 240
now = pd.Timestamp.now(tz="UTC")
print(f"■ 설정 — 통행료 {TOLL}% · 대조 {NSYM}종목 {BAR}봉 · 보유 {HOLD}분 · 창 {WINS}h")

# ── 갈래 목록 (원장 디렉터리 → 이름) ──────────────────────────────
BR = {
    "s3short_dir": "방향숏3", "s3short_anti": "역확인3", "s3short_conf": "확인숏3",
    "s6both_imp": "충격스프3", "s3short_imp": "충격숏3", "s3short_h4": "충격240",
    "s3short_h4ec": "충격240냉", "s3short_h1": "충격60", "s3short_impns": "무손숏3",
    "s2both": "s2양다리", "s6both_h240": "s6양다리", "s10both": "s10양다리",
    "s6both_ac1": "체결자기여기", "s10both_d5_utc01": "되돌림UTC1",
    "s10both_d5_revcont": "되돌림연속", "s3short_rmz": "최장연속숏",
}
D = {}
for tag, nm in BR.items():
    f = P / tag / "trades.csv"
    if not f.exists():
        continue
    d = pd.read_csv(f)
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    if "short" not in d:
        d["short"] = True
    D[nm] = d

# ── 국면 ────────────────────────────────────────────────────────
freq = {}
for d in D.values():
    for s in d.symbol:
        freq[s] = freq.get(s, 0) + 1
top = [s for s, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:NSYM]]
rows = {}
for s in top:
    try:
        raw = json.load(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/klines?symbol={s}&interval={BAR}&limit=500",
            timeout=20))
        rows[s] = pd.Series([float(k[4]) for k in raw],
                            index=pd.to_datetime([k[0] for k in raw], unit="ms", utc=True))
        time.sleep(0.03)
    except Exception:
        pass
C = pd.DataFrame(rows).sort_index()
k = HOLD // BARMIN
print(f"\n■ ① 지금 국면 — 알트 {C.shape[1]}종목")
print(f"{'창':>6}{'전반 수익률':>13}{'상승종목':>10}{'진폭(|수익|평균)':>18}")
for W in WINS:
    c = C[C.index >= now - pd.Timedelta(hours=W)]
    if len(c) < 2:
        continue
    r = 100 * (c.iloc[-1] / c.iloc[0] - 1)
    amp = (100 * c.pct_change().abs()).mean().mean()
    print(f"{W:>5}h{r.mean():>+13.2f}%{int((r>0).sum()):>7}/{len(r):<3}{amp:>17.3f}%")

print(f"\n■ ② 무조건 대조군 — 선별 없이 {HOLD}분 (통행료 차감, 비겹침 표본)")
print(f"{'창':>6}{'표본':>7}{'무조건 롱':>11}{'무조건 숏':>11}")
CTRL = {}
for W in WINS:
    c = C[C.index >= now - pd.Timedelta(hours=W + HOLD / 60)]
    r = []
    for s in c.columns:
        v = c[s].dropna()
        if len(v) <= k:
            continue
        x = (v.shift(-k) / v - 1.0).dropna() * 100.0
        r.append(x.iloc[::k])
    if not r:
        continue
    x = pd.concat(r)
    L, S = x.mean() - TOLL, -x.mean() - TOLL
    CTRL[W] = (L, S)
    print(f"{W:>5}h{len(x):>7}{L:>+11.3f}{S:>+11.3f}")

# ── 계열별 ──────────────────────────────────────────────────────
def leg(W, short):
    tot, n = [], 0
    per = {}
    for nm, d in D.items():
        m = d[(d.closed_ts >= now - pd.Timedelta(hours=W)) & (d.short == short)]
        if len(m):
            per[nm] = (len(m), m.net_pct.mean())
            tot.append(m.net_pct); n += len(m)
    if not tot:
        return None, 0, per
    v = pd.concat(tot)
    return v.mean(), len(v), per

for short, lab in ((False, "롱"), (True, "숏")):
    print(f"\n■ ③ **{lab} 계열** — 전 갈래 합산 (거래당 %)")
    print(f"{'창':>6}{'거래':>7}{'거래당':>10}{'무조건 대조':>13}{'초과':>10}")
    for W in WINS:
        m, n, _ = leg(W, short)
        if m is None:
            print(f"{W:>5}h{0:>7}   거래 없음"); continue
        c = CTRL.get(W, (np.nan, np.nan))[1 if short else 0]
        print(f"{W:>5}h{n:>7}{m:>+10.3f}{c:>+13.3f}{m-c:>+10.3f}")
    _, _, per = leg(24, short)
    if per:
        print(f"   24h 갈래별 — ", end="")
        print(" · ".join(f"{k2}({v[0]}건 {v[1]:+.2f})"
                         for k2, v in sorted(per.items(), key=lambda kv: -kv[1][1])))
