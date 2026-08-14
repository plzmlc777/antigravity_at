"""경계 구간(5~30분) 가설 9 — **충격의 영구/일시 분해**.

왜 이 구간인가
  초단기(초~분)는 닫혔다. 패시브로 서 있으면 채워지는 순간이 곧 틀린 순간이고,
  수수료로도 속도로도 못 고친다 ([[feedback-lesson-84]]).
  단기(30~90분) 사건형도 닫혔다. 일정이 공개된 사건은 미리 다 반영된다
  ([[feedback-lesson-85]]).
  그 사이 5~30분이 남는다. **속도는 이미 무의미하고(수백 ms 는 30분의 0.03%),
  마찰은 아직 크다(테이커 왕복 11~13bp).**

착상 — 우리 markout 이 준 단서
  체결 286,149건의 markout: 1초 -4.28bp → 300초 -4.31bp. **되돌림이 0 이다.**
  즉 우리가 밟힌 이동은 전부 **영구 충격**이었다.
  그런데 미시구조 이론(Kyle)은 모든 충격이 영구(정보) + 일시(유동성 프리미엄)
  로 나뉜다고 본다. 평균이 100% 영구로 나온 건 **두 성분을 섞어 쟀기 때문**일
  수 있다. 갈라내면 일시 성분은 되돌아오고, 그 되돌림이 5~30분에 실현된다.

가설
  같은 거래대금이라도 **시간에 몰린 체결**과 **흩어진 체결**은 성질이 다르다.
    · 한 번에 몰아친 것  = 급한 유동성 수요 → **일시 충격 → 되돌아온다**
    · 잘게 나뉜 것       = 정보 축적       → **영구 충격 → 계속 간다**
  거래대금을 통제하고 **집중도**만 바꿔 방향이 갈리는지 본다.

  집중도 = 그 1분 안 체결 건수의 역수 성격. 같은 금액을 3건으로 냈나 300건으로
  냈나. 거래대금과 건수를 각각 백분위로 만들고 **격자**로 본다 —
  "거래대금 상위 × 건수 하위" 칸이 몰아친 것이다.

무엇을 조심하는가 (전부 자체 교훈에서)
  · **겹치는 창 금지** — step >= 보유. 겹침만으로 상관이 조작된 전례
    ([[feedback-overlapping-window-persistence-artifact]]).
  · **종목별 백분위** — 절대값으로 자르면 큰 종목만 뽑힌다 (교훈 #75).
  · **유동성 관문** — 극단값은 얇은 종목에 몰린다 (교훈 #78).
  · **시간 독립성** — 같은 사건이 연속 분에 중복 계상되지 않게 debounce
    (Item 8 concentration temporal independence).
  · 표본 1,000건 미만 칸은 판정하지 않는다.
  · 마찰은 **테이커 왕복 + 실측 스프레드**. 낙관 금지.

사용:
  python3 scripts/research/boundary_impact_decomp_scan.py --days 60
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("boundary_impact_decomp")

TAKER_BP = 5.0                 # 편도
HOLDS_MIN = (5, 10, 15, 30)    # 경계 구간
ROLL = 1440                    # 백분위 창 (분) = 24시간
DEBOUNCE_MIN = 30              # 같은 사건 중복 계상 방지
MIN_CELL = 1000
Q = 5                          # 분위 수


def main() -> int:
    p = argparse.ArgumentParser(description="영구/일시 충격 분해 (5~30분)")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=20_000_000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "boundary_impact_decomp.json"))
    args = p.parse_args()

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    # cells[(hold, 금액분위, 건수분위)] = [수익 bp, ...]
    cells: dict = {}
    used = 0
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            d = joblib.load(f)
        except Exception:
            continue
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d.loc[d.index >= d.index.max() - pd.Timedelta(days=args.days)]
        if len(d) < 20000:
            continue
        if d["quote_volume"].resample("1D").sum().median() < args.min_dvol_usd:
            continue
        need = {"px_open", "quote_volume", "n_trades", "eff_spread_bp_adj"}
        if not need.issubset(d.columns):
            if used == 0:
                log.error("필요 컬럼 없음. 보유 컬럼: %s", list(d.columns)[:25])
                return 1
            continue
        used += 1

        px = d["px_open"].astype(float)
        vol = d["quote_volume"].astype(float)
        cnt = d["n_trades"].astype(float)
        fric = 2 * TAKER_BP + float(d["eff_spread_bp_adj"].median())

        # 종목 자기 이력 대비 백분위 (교훈 #75)
        pv = vol.rolling(ROLL, min_periods=ROLL // 4).rank(pct=True)
        pc = cnt.rolling(ROLL, min_periods=ROLL // 4).rank(pct=True)
        # 방향 — 그 분의 가격 이동
        ret1 = px.pct_change()
        ok = pv.notna() & pc.notna() & ret1.notna() & (ret1 != 0)

        idx = np.flatnonzero(ok.values)
        qv = np.clip((pv.values * Q).astype(int), 0, Q - 1)
        qc = np.clip((pc.values * Q).astype(int), 0, Q - 1)
        sign = np.sign(ret1.values)
        pxv = px.values
        n = len(pxv)

        for H in HOLDS_MIN:
            last = -10 ** 9
            for k in idx:
                if k - last < max(DEBOUNCE_MIN, H):   # 겹침·중복 동시 차단
                    continue
                if k + H >= n:
                    break
                last = k
                # 되돌림 베팅: 그 분 이동의 **반대** 방향으로 진입
                fwd = (pxv[k + H] / pxv[k] - 1.0) * 1e4
                bp = -sign[k] * fwd - fric
                cells.setdefault((H, qv[k], qc[k]), []).append(bp)

        if i % 100 == 0:
            log.info("%d/%d (사용 %d)", i, len(files), used)

    if used < 30:
        log.error("종목 부족: %d", used)
        return 1
    log.info("사용 종목 %d", used)

    rows = []
    for (H, a, b), v in cells.items():
        if len(v) < MIN_CELL:
            continue
        x = np.array(v)
        se = x.std(ddof=1) / np.sqrt(len(x))
        rows.append({"hold": H, "q_vol": int(a), "q_cnt": int(b), "n": len(x),
                     "net_bp": float(x.mean()), "se_bp": float(se),
                     "t": float(x.mean() / se) if se else np.nan})
    if not rows:
        log.error("판정 가능한 칸 없음")
        return 1
    df = pd.DataFrame(rows)

    print("\n" + "=" * 96)
    print(f"경계 가설 9 — 충격의 영구/일시 분해  ({used}종목 / 최근 {args.days}일)")
    print("=" * 96)
    print("  베팅: 그 분 가격이 움직인 **반대** 방향. 되돌아오면 이익.")
    print("  마찰: 테이커 왕복 10bp + 실측 스프레드, 이미 차감.")
    print("  행 = 거래대금 분위(작음→큼) / 열 = 체결건수 분위(적음→많음)")
    print("  ** 같은 금액을 적은 건수로 = 몰아친 것 = 좌하단 **")
    for H in HOLDS_MIN:
        sub = df[df.hold == H]
        if sub.empty:
            continue
        print(f"\n  [보유 {H}분]")
        hdr = "".join(f"{'건수'+str(c+1):>12}" for c in range(Q))
        print(f"    {'':<10}{hdr}")
        for a in range(Q):
            cs = []
            for b in range(Q):
                r = sub[(sub.q_vol == a) & (sub.q_cnt == b)]
                cs.append(f"{r.iloc[0].net_bp:>12.2f}" if len(r) else f"{'-':>12}")
            print(f"    {'금액'+str(a+1):<10}{''.join(cs)}")
    print("\n" + "-" * 96)
    df = df.sort_values("net_bp", ascending=False)
    print("  상위 8칸")
    print(f"  {'보유':>5}{'금액분위':>9}{'건수분위':>9}{'표본':>10}{'net bp':>11}"
          f"{'오차':>8}{'t':>8}  판정")
    for _, r in df.head(8).iterrows():
        ok = r.net_bp > 0 and r.t >= 3.0
        print(f"  {r.hold:>5.0f}{r.q_vol + 1:>9.0f}{r.q_cnt + 1:>9.0f}{r.n:>10,.0f}"
              f"{r.net_bp:>+11.2f}{r.se_bp:>8.2f}{r.t:>+8.2f}  "
              f"{'★ PASS' if ok else ''}")
    n_pass = int(((df.net_bp > 0) & (df.t >= 3.0)).sum())
    print("-" * 96)
    print(f"  net>0 & t>=3.0 통과 {n_pass}/{len(df)}")
    print("=" * 96 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": used, "days": args.days,
                   "rows": rows}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
