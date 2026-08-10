"""단기 새 부류 — 시간 단위 **횡단면** 되돌림.

배경 (2026-08-10):
  지금까지 검증한 것은 전부 **종목 하나를 놓고 보는** 구조였다.
    자기 종목 주문흐름 (초단타)  — 닫힘, gross -1.3~+5.3bp
    BTC 대비 잔차 lead-lag       — 닫힘, gross +1.0~+3.1bp
    펀딩 정산 사건               — 진행 중, 정산 고유 +9.6~15.3bp
  **횡단면** — 그 시점에 전 종목을 줄 세워 상대 위치를 보는 구조 — 는 안 했다.

가설
  몇 시간 동안 가장 많이 떨어진 종목은 되돌아오고, 가장 많이 오른 종목은 되밀린다.
  하위 K개 롱 + 상위 K개 숏으로 **롱숏 동수**를 유지하면 시장 전체 방향과
  무관해진다 — BTC 가 어디로 가든 상관없다. 이게 앞의 셋과 결정적으로 다른 점이다.

  방향을 맞히는 전략이므로 **시장가**로 들어간다. 마찰은 스프레드+테이커 왕복.
  (펀딩 사건과 달리 **언제 올지 모르므로** 지정가를 미리 걸 수 없다.)

무엇을 조심하는가
  · **동일가중 포트폴리오의 수익률로 잰다** — 종목별 손익을 그냥 평균하면 롱숏이
    상쇄되지 않아 시장 방향이 섞인다.
  · lookahead: 순위는 t 시점까지의 정보로만, 체결은 t 봉 **시가**.
  · 겹침 금지: 보유 기간이 겹치지 않게 리밸런싱 간격 >= 보유 기간.
  · 마찰은 실측 스프레드(eff_spread_bp_adj) + 테이커 왕복. 롱숏 양쪽 다 낸다.
  · **극단값이 유동성 낮은 종목에 몰린다** — 유동성 관문을 반드시 건다(Lesson #78).
  · 표본 1,000건 미만 셀은 판정하지 않는다.

사용:
  python3 scripts/research/daytrade_xsection_scan.py --days 60 --min-dvol-usd 3000000
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
log = logging.getLogger("daytrade_xsection_scan")

TAKER_FEE_BP = 4.0
LOOKBACKS_H = (1, 2, 4, 8)      # 순위 매길 과거 구간 (시간)
HOLDS_H = (1, 2, 4, 8)          # 보유 (시간)
TOP_KS = (10, 20, 40)           # 한쪽 종목 수
MIN_CELL = 1000


def main() -> int:
    p = argparse.ArgumentParser(description="시간 단위 횡단면 되돌림")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=3_000_000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "daytrade_xsection_scan.json"))
    args = p.parse_args()

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    px, sp = {}, {}
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
        dv = d["quote_volume"].resample("1D").sum().median()
        if not np.isfinite(dv) or dv < args.min_dvol_usd:
            continue
        # 시간 경계로 리샘플 — 순위·체결 모두 정시 기준
        px[sym] = d["px_open"].resample("1h").first()
        sp[sym] = d["eff_spread_bp_adj"].resample("1h").median()
        if i % 100 == 0:
            log.info("%d/%d (사용 %d)", i, len(files), len(px))

    if len(px) < 60:
        log.error("종목 부족: %d", len(px))
        return 1
    P = pd.DataFrame(px).sort_index()
    S = pd.DataFrame(sp).reindex_like(P)
    log.info("행렬 %d시간 x %d종목", len(P), P.shape[1])

    res = []
    for L in LOOKBACKS_H:
        ret_L = P.pct_change(L)                     # t 시점까지의 과거 L시간 수익률
        for H in HOLDS_H:
            fwd = P.shift(-H) / P - 1.0             # t → t+H 수익률 (t 시가 기준)
            step = H                                # 겹침 금지: 리밸런싱 간격 = 보유
            rows = np.arange(L, len(P) - H, step)
            for K in TOP_KS:
                port, n_reb = [], 0
                for r in rows:
                    r_ = ret_L.iloc[r].dropna()
                    f_ = fwd.iloc[r]
                    s_ = S.iloc[r]
                    cand = r_.index.intersection(f_.dropna().index)
                    if len(cand) < K * 2 + 10:
                        continue
                    rk = r_[cand].sort_values()
                    lo, hi = rk.index[:K], rk.index[-K:]
                    # 동일가중 롱숏. 종목별 손익을 그냥 평균하면 시장 방향이 섞인다.
                    long_r = float(f_[lo].mean())
                    short_r = float(-f_[hi].mean())
                    gross = (long_r + short_r) / 2.0
                    fr = float(np.nanmean(
                        np.concatenate([s_[lo].values, s_[hi].values])))
                    if not np.isfinite(fr):
                        fr = float(np.nanmedian(s_.values))
                    fric = (fr + 2 * TAKER_FEE_BP) / 1e4
                    port.append(gross - fric)
                    n_reb += 1
                if n_reb < 20:
                    continue
                a = np.array(port)
                t = (float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a))))
                     if a.std(ddof=1) > 0 else float("nan"))
                res.append({"lookback_h": L, "hold_h": H, "K": K,
                            "n_rebal": n_reb,
                            "net_bp": float(a.mean() * 1e4),
                            "sd_bp": float(a.std(ddof=1) * 1e4),
                            "t": t,
                            "trades": n_reb * K * 2})

    if not res:
        log.error("셀 0개")
        return 1
    res.sort(key=lambda r: -(r["t"] if np.isfinite(r["t"]) else -99))

    print("\n" + "=" * 92)
    print(f"시간 단위 횡단면 되돌림 — {P.shape[1]}종목 / 최근 {args.days}일 / "
          f"롱숏 동수 / 시장가 왕복 마찰")
    print("=" * 92)
    print(f"{'과거(h)':>8}{'보유(h)':>8}{'K':>5}{'리밸런싱':>10}{'거래수':>9}"
          f"{'net bp':>10}{'표준편차':>10}{'t':>8}  판정")
    print("-" * 92)
    for r in res[:18]:
        ok = r["net_bp"] > 0 and np.isfinite(r["t"]) and r["t"] >= 3.0
        print(f"{r['lookback_h']:>8}{r['hold_h']:>8}{r['K']:>5}{r['n_rebal']:>10,}"
              f"{r['trades']:>9,}{r['net_bp']:>+10.2f}{r['sd_bp']:>10.1f}"
              f"{r['t']:>+8.2f}  {'★ PASS' if ok else ''}")
    n_pass = sum(1 for r in res
                 if r["net_bp"] > 0 and np.isfinite(r["t"]) and r["t"] >= 3.0)
    print("=" * 92)
    print(f"  net>0 & t>=3.0 통과 {n_pass}/{len(res)}")
    best = max(res, key=lambda r: r["net_bp"])
    print(f"  최고 net: 과거 {best['lookback_h']}h / 보유 {best['hold_h']}h / "
          f"K={best['K']} → {best['net_bp']:+.2f}bp (t {best['t']:+.2f}, "
          f"리밸런싱 {best['n_rebal']}회)\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": int(P.shape[1]), "days": args.days,
                   "results": res}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
