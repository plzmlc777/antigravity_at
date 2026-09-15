# -*- coding: utf-8 -*-
"""📈 추세 진단 — "이득이 점점 강해지는 갈래는 어느 것인가" (2026-09-15 대표님 질문).

현행 교체 조건 ①은 **수준**만 본다(후보의 12h·24h 자본%가 현행보다 높은가).
강해지는 중인지 식는 중인지는 판정에 안 들어간다. 이 진단은 그 빈칸을 잰다.

⚠ 3h/6h/12h/24h 창은 **서로 겹친다**(24h 안에 6h 가 들어 있다). 그 넷을 나란히
  놓고 기울기를 읽으면 안 된다 — 겹친 창은 지속성을 허상으로 만든다.
  여기서는 **비겹침 3시간 토막**으로만 잰다.
⚠ 토막당 거래 수를 같이 찍는다. 1~2건짜리 토막의 부호는 잡음이다.
"""
import pathlib
import numpy as np
import pandas as pd

# ── 설정 (한 곳에만 둔다 · 실행 시 전문을 찍어 도달을 증명한다) ──────────
ROOT   = pathlib.Path("/home/mint/auto_trading/backend")
PAPER  = ROOT / "runs" / "kinematics_paper"
BUCKET = "3h"   # 비겹침 토막 길이
NBUCK  = 16     # 최근 몇 토막을 볼 것인가 (16 × 3h = 48h)
HALF   = 4      # 앞뒤 비교 구간 (4 × 3h = 12h)
BR = {
    "s3short_dir":   ("방향숏3",   3), "s3short_anti":  ("역확인3",   3),
    "s3short_conf":  ("확인숏3",   3), "s6both_imp":    ("충격스프3", 6),
    "s3short_imp":   ("충격숏3",   3), "s3short_h4":    ("충격240",   3),
    "s3short_h4ec":  ("충격240냉", 3), "s3short_h1":    ("충격60",    3),
    "s3short_impns": ("무손숏3",   3),
}
LIVE = {"s3short_dir": "계좌15", "s3short_anti": "계좌8"}


def buckets(tag, slots):
    d = pd.read_csv(PAPER / tag / "trades.csv")
    d["closed_ts"] = pd.to_datetime(d.closed_ts, utc=True, format="mixed")
    d = d.sort_values("closed_ts")
    key = d.closed_ts.dt.floor(BUCKET)
    cap = d.groupby(key).net_pct.sum() / slots
    cnt = d.groupby(key).size()
    idx = pd.date_range(key.min(), key.max(), freq=BUCKET)
    return cap.reindex(idx, fill_value=0.0), cnt.reindex(idx, fill_value=0)


def ols_t(y):
    x = np.arange(len(y), dtype=float)
    if len(y) < 6 or np.allclose(y, y[0]):
        return np.nan, np.nan
    b, a = np.polyfit(x, y, 1)
    res = y - (a + b * x)
    den = ((x - x.mean()) ** 2).sum()
    se = np.sqrt((res ** 2).sum() / (len(x) - 2) / den)
    return b, (b / se if se else np.nan)


def main():
    print("■ 설정 — 비겹침 토막 %s · 최근 %d토막(%dh) · 앞뒤 비교 %d토막(%dh)"
          % (BUCKET, NBUCK, NBUCK * 3, HALF, HALF * 3))
    rows = []
    for tag, (nm, sl) in BR.items():
        cap, cnt = buckets(tag, sl)
        y = cap.to_numpy()[-NBUCK:]
        c = cnt.to_numpy()[-NBUCK:]
        if len(y) < NBUCK:
            y = np.pad(y, (NBUCK - len(y), 0)); c = np.pad(c, (NBUCK - len(c), 0))
        b, t = ols_t(y)
        late, early = y[-HALF:].mean(), y[-2 * HALF:-HALF].mean()
        rows.append((nm, LIVE.get(tag, ""), y.sum(), early, late, late - early,
                     b, t, c[-NBUCK:].mean(), (y[-HALF:] > 0).sum(), y[-1]))
    rows.sort(key=lambda r: -r[5])
    print("\n■ 강해지는 순서 — 최근12h평균 − 직전12h평균 (토막당 자본%)")
    print(f"{'갈래':<11}{'계좌':<8}{'48h합':>8}{'직전12h':>9}{'최근12h':>9}"
          f"{'증분':>9}{'기울기':>9}{'t':>7}{'토막거래':>9}{'최근4토막+':>11}{'마지막토막':>11}")
    print("-" * 102)
    for nm, ac, s48, e, l, d, b, t, n, pos, last in rows:
        print(f"{nm:<11}{ac:<8}{s48:>8.2f}{e:>9.3f}{l:>9.3f}{d:>+9.3f}"
              f"{b:>+9.4f}{t:>+7.2f}{n:>9.1f}{pos:>8d}/4{last:>+11.3f}")
    print("\n  증분 = 최근 12h 토막평균 − 직전 12h 토막평균 (%p/토막)")
    print("  기울기 = 최근 48h 비겹침 토막 회귀 (%p/토막) · t 는 그 회귀의 t")
    print("  ⚠ 토막당 거래가 1~2건이면 부호는 잡음이다. 토막거래 열을 먼저 보라")


if __name__ == "__main__":
    main()
