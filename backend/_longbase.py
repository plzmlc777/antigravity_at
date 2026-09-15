# -*- coding: utf-8 -*-
"""🧪 롱 축 발굴 — 0단계: **대조군과 검정력** (2026-09-15 대표님 승인).

하네스 규칙 7번 — 격자를 돌리기 전에 검정력을 먼저 잰다. 못 잡을 크기를
찾겠다고 몇 시간을 태우는 일을 막는다.

대조군 — **무조건 롱**. 선별 없이 유니버스를 그냥 사서 H분 들고 있기.
  롱 갈래가 이걸 못 이기면 **선별을 만들 이유가 없다**(그냥 사면 된다).
  뒤 절반에 알트가 +19.36% 올랐으므로 이 대조군은 지금 세다.
"""
import json, urllib.request, time, pathlib
import numpy as np, pandas as pd

# ── 설정 (한 곳 · 실행 시 전문을 찍어 도달을 증명한다) ──────────────
PAPER = pathlib.Path("/home/mint/auto_trading/backend/runs/kinematics_paper")
TOLL   = 0.1004        # 왕복 통행료 %(실측)
NSYM   = 25            # 대조군 종목 수 (최다 거래 순)
HOLDS  = (60, 120, 240, 480)
# ⚠ 1분봉은 limit 1000 이라 **16.6시간**밖에 못 덮는다. 갈래는 6일 구간인데
#   대조군만 하루도 안 되는 다른 구간이면 비교가 아니다. 15분봉이면 10.4일 —
#   보유 60/120/240/480 이 전부 15의 배수라 잘려나가는 것도 없다.
BAR    = "15m"
BARMIN = 15
START  = pd.Timestamp("2026-09-09 02:00", tz="UTC")
ALPHA, POWER = 0.05, 0.80
print(f"■ 설정 — 통행료 {TOLL}% · 대조 종목 {NSYM} · 보유 {HOLDS} · "
      f"α {ALPHA} · 검정력 {POWER}")

# ── 기존 갈래에서 거래당 표준편차를 얻는다 (검정력의 분모) ──────────
BR = {"s6both_imp": "충격스프3", "s3short_dir": "방향숏3",
      "s3short_anti": "역확인3", "s3short_conf": "확인숏3"}
print("\n■ ① 거래당 표준편차 — 검정력의 분모")
print(f"{'갈래':<12}{'다리':<5}{'거래':>6}{'평균':>9}{'SD':>8}{'SE':>8}{'t':>7}")
sd_long = sd_short = None
for tag, nm in BR.items():
    d = pd.read_csv(PAPER / tag / "trades.csv")
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    for sh in (False, True):
        s = d[d.short == sh].net_pct
        if len(s) < 10:
            continue
        sd = s.std(ddof=1); se = sd / np.sqrt(len(s))
        print(f"{nm:<12}{'숏' if sh else '롱':<5}{len(s):>6}{s.mean():>+9.3f}"
              f"{sd:>8.3f}{se:>8.3f}{s.mean()/se:>+7.2f}")
        if tag == "s6both_imp":
            if sh: sd_short = sd
            else:  sd_long = sd

z = 1.959964 + 0.841621
print(f"\n■ ② 검정력 사전검사 — 몇 거래가 있어야 잡히나 (양측 α{ALPHA} · {POWER})")
print(f"{'찾는 엣지':>10}{'롱 SD %.2f' % sd_long:>16}{'숏 SD %.2f' % sd_short:>16}")
for d_ in (0.25, 0.50, 1.00, 2.00):
    nl = (z * sd_long / d_) ** 2
    ns = (z * sd_short / d_) ** 2
    print(f"{d_:>9.2f}%{nl:>14.0f}건{ns:>14.0f}건")
print(f"   3슬롯 · 240분 보유 = 하루 약 18거래 → "
      f"롱 +0.50%/거래를 잡으려면 {(z*sd_long/0.5)**2/18:.0f}일")

# ── 무조건 롱 대조군 ────────────────────────────────────────────
freq = {}
for tag in ("s6both_imp", "s3short_dir", "s3short_anti", "s3short_conf"):
    d = pd.read_csv(PAPER / tag / "trades.csv")
    for s in d.symbol:
        freq[s] = freq.get(s, 0) + 1
top = [s for s, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:NSYM]]
rows = {}
for s in top:
    try:
        raw = json.load(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/klines?symbol={s}&interval={BAR}&limit=1000",
            timeout=20))
        rows[s] = pd.Series([float(k[4]) for k in raw],
                            index=pd.to_datetime([k[0] for k in raw],
                                                 unit="ms", utc=True))
        time.sleep(0.04)
    except Exception:
        pass
C = pd.DataFrame(rows).sort_index()
C = C[C.index >= START]
print(f"\n■ ③ 무조건 롱 대조군 — {C.shape[1]}종목 × {BAR}봉 {len(C)}개 "
      f"({C.index[0].tz_convert('Asia/Seoul'):%m-%d %H:%M} ~ "
      f"{C.index[-1].tz_convert('Asia/Seoul'):%m-%d %H:%M} KST)")
print(f"{'보유':>6}{'표본':>7}{'net 평균':>10}{'중앙':>9}{'승률':>8}"
      f"{'SD':>8}{'t':>7}{'95%하한':>10}")
for H in HOLDS:
    r = []
    for s in C.columns:
        v = C[s].dropna()
        k = H // BARMIN                       # 보유 H분 = 봉 k개
        if len(v) <= k:
            continue
        x = (v.shift(-k) / v - 1.0).dropna() * 100.0
        r.append(x.iloc[::k])          # 겹치지 않게 k봉 간격으로만 표본
    if not r:
        continue
    x = pd.concat(r) - TOLL
    se = x.std(ddof=1) / np.sqrt(len(x))
    print(f"{H:>5}분{len(x):>7}{x.mean():>+10.3f}{x.median():>+9.3f}"
          f"{100*(x>0).mean():>7.1f}%{x.std(ddof=1):>8.3f}"
          f"{x.mean()/se:>+7.2f}{x.mean()-1.96*se:>+10.3f}")
print("   ※ 통행료 차감 후. **이것이 롱 갈래가 넘어야 할 선이다.**")
