"""신상저격수 — **신호 변형 5종 × 사이징 3종** 포트폴리오 시뮬 (1년 캘린더).

왜 다시 도는가 (2026-08-12)
  앞선 시도는 251건 · 5.4년을 전액 복리로 굴려 $724 → $803,901 (1,110배)이 됐다.
  신규 상장 종목의 유동성이 그 규모를 감당하지 못하므로 절대금액과 순위가 전부
  왜곡됐다. 그래서 기존 `notional_cap_portfolio_sim.py` 가 쓰던 **131건 · 약 1년
  캘린더**로 되돌려 다시 잰다. 현행 20% 상한을 고른 것도 그 캘린더였다.

무엇을 비교하나
  신호 5종 — base / h21 / earlyexit_d7 / earlyexit_d14 / bearskip
  사이징 3종 — 20%×1(현행) / 3%×1(대안A) / 3%×3(대안B)
  총 15칸.

읽는 법 — **수익률로 고르지 말 것**
  `lifecycle_live_signal_driver.py` 78행 주석: "수익 기준 최적 상한은 시간
  분할마다 100%/30%/25% 로 뒤집힌다 (단일 경로, 심한 중첩)". 모든 분할에서
  단조인 축은 **포착률 / MDD / 최악 단일거래** 셋뿐이다. 수익률은 참고로만 낸다.

변형 정의 (소스 구현 그대로)
  base          Day-1 종가 숏 → Day-30 종가, SL +50%
  h21           → Day-21 종가
  earlyexit_d7  Day-7 에 vol_cliff = mean(vol[1:7])/vol[0] ≥ 0.40 이면 그날 청산
  earlyexit_d14 Day-14 에 vol_cliff = mean(vol[7:14])/vol[0] ≥ 0.40 이면 그날 청산
  bearskip      상장 직전 BTC 30일 수익률 ≤ -5% 면 진입 안 함

사용:
  python3 scripts/research/lifecycle_variant_x_sizing_sim.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "research"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("var_x_size")

INITIAL = 724.04
FEE_RT = 0.0008
MIN_MARGIN = 5.0
MARGIN_FRAC = 0.97
SL_PCT = 0.50
VC_THR = 0.40
BEAR_THR = -0.05

VARIANTS = [("base", 30, None), ("h21", 21, None),
            ("earlyexit_d7", 30, 7), ("earlyexit_d14", 30, 14),
            ("bearskip", 30, None)]
SIZINGS = [("20%x1 현행", 0.20, 1), ("3%x1 대안A", 0.03, 1), ("3%x3 대안B", 0.03, 3)]


def resolve(daily: pd.DataFrame, hold: int, early: int | None):
    """Day-1 종가 숏. SL / 조기청산 / 시간청산 중 먼저. 반환 (수익률, 보유일)."""
    if len(daily) < 3:
        return None
    e = float(daily["close"].iloc[0])
    if e <= 0:
        return None
    stop = e * (1 + SL_PCT)
    exit_pos = min(hold, len(daily) - 1)
    if early is not None and len(daily) >= early and "volume" in daily.columns:
        v = daily["volume"].astype(float).values
        if v[0] > 0:
            win = v[7:14] if early == 14 else v[1:7]
            if len(win) >= 1 and float(win.mean()) / float(v[0]) >= VC_THR:
                exit_pos = min(early - 1, exit_pos)
    for k in range(1, exit_pos + 1):
        if float(daily["high"].iloc[k]) >= stop:
            return (-SL_PCT, k)
    # ⚠ 여기는 표기 문제가 아니라 **계산 결함**이었다. portfolio() 가
    #   `wallet += 명목 × ret` 로 복리를 돌리는데 entry/exit-1 은 상한이
    #   없어서 숏이 명목보다 많이 버는 결과가 나온다(불가능).
    #   손절 -50% 는 두 규약이 같아 **이익 거래만** 부풀려져 있었다.
    #   notional_cap_portfolio_sim.resolve_trade 는 처음부터 옳았다. 규약 통일 2026-08-14
    x = float(daily["close"].iloc[exit_pos])
    return ((e - x) / e, exit_pos)


def portfolio(events: list, cap: float, lev: int) -> dict:
    if not events:
        return {}
    days = pd.date_range(min(e["entry"] for e in events),
                         max(e["exit"] for e in events), freq="D")
    wallet, opn, taken, starved, curve = INITIAL, [], [], 0, []
    mx = 0
    by: dict = {}
    for e in events:
        by.setdefault(e["entry"], []).append(e)
    for d in days:
        dd = d.date()
        keep = []
        for p in opn:
            if p["exit"] <= dd:
                wallet += p["nom"] * (p["ret"] - FEE_RT)
                continue
            keep.append(p)
        opn = keep
        lock = sum(p["m"] for p in opn)
        for e in by.get(dd, []):
            m = min(cap * wallet, max(wallet - lock, 0.0) * MARGIN_FRAC)
            if m < MIN_MARGIN:
                starved += 1
                continue
            opn.append({**e, "m": m, "nom": m * lev})
            lock += m
            taken.append(m * lev * (e["ret"] - FEE_RT))
        mx = max(mx, len(opn))
        curve.append(wallet + sum(p["nom"] * p["ret"] for p in opn))
    for p in opn:
        wallet += p["nom"] * (p["ret"] - FEE_RT)
    a = np.array(curve, dtype=float)
    pk = np.maximum.accumulate(a) if len(a) else np.array([1.0])
    return {"n": len(taken), "starved": starved,
            "capture": round(100 * len(taken) / max(len(taken) + starved, 1), 1),
            "mdd": round(float(((a - pk) / np.maximum(pk, 1e-9)).min() * 100), 1),
            "worst": round(min(taken), 1) if taken else 0.0,
            "final": round(wallet, 0), "ret": round((wallet / INITIAL - 1) * 100, 1),
            "max_conc": mx}


def main() -> int:
    p = argparse.ArgumentParser(description="변형 x 사이징 포트폴리오 시뮬")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "lifecycle_phase" / "variant_x_sizing__metrics.json"))
    args = p.parse_args()

    from notional_cap_portfolio_sim import build_cohort
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        cohort = build_cohort(db)
    finally:
        db.close()
    log.info("코호트 %d건", len(cohort))

    # bearskip 판정용 BTC 사전 수익률 (월 단위 캐시)
    from sqlalchemy import text
    from app.db.session import engine
    btc: dict = {}
    with engine.connect() as conn:
        for c in cohort:
            ld = c["daily"].index[0].date()
            key = ld.strftime("%Y-%m")
            if key in btc:
                continue
            r = conn.execute(text(
                "SELECT timestamp, close FROM ohlcv WHERE symbol='BTCUSDT' "
                "AND time_frame='1m' AND timestamp >= :a AND timestamp < :b "
                "ORDER BY timestamp"),
                {"a": ld - timedelta(days=32), "b": ld}).fetchall()
            if not r:
                btc[key] = None
                continue
            s = pd.Series({pd.Timestamp(t): float(x) for t, x in r}).sort_index()
            dd = s.resample("1D").last().dropna()
            btc[key] = float(dd.iloc[-1] / dd.iloc[0] - 1.0) if len(dd) >= 20 else None

    res = {}
    for vname, hold, early in VARIANTS:
        events = []
        for c in cohort:
            dl = c["daily"]
            ld = dl.index[0].date()
            if vname == "bearskip":
                pre = btc.get(ld.strftime("%Y-%m"))
                if pre is not None and pre <= BEAR_THR:
                    continue                       # 진입 자체를 건너뜀
            t = resolve(dl, hold, early)
            if t is None:
                continue
            events.append({"sym": c["symbol"], "entry": ld,
                           "exit": ld + timedelta(days=int(t[1])), "ret": float(t[0])})
        for sname, cap, lev in SIZINGS:
            res[(vname, sname)] = portfolio(events, cap, lev)

    span = (max(c["daily"].index[-1] for c in cohort)
            - min(c["daily"].index[0] for c in cohort)).days
    print("\n" + "=" * 108)
    print(f"신호 변형 5종 x 사이징 3종 — 코호트 {len(cohort)}건 / 약 {span}일 / "
          f"초기 ${INITIAL:.0f}")
    print("=" * 108)
    print("  ** 수익률로 고르지 말 것 — 단조 축은 포착률 / MDD / 최악 셋뿐 **")
    print("-" * 108)
    print(f"  {'신호변형':<15}{'사이징':<13}{'포착%':>8}{'MDD%':>9}{'최악$':>9}"
          f"{'동시':>6}{'잡음':>6}{'놓침':>6}{'최종$':>10}{'수익%':>9}")
    print("-" * 108)
    for vname, _, _ in VARIANTS:
        for sname, _, _ in SIZINGS:
            r = res.get((vname, sname)) or {}
            if not r:
                continue
            print(f"  {vname:<15}{sname:<13}{r['capture']:>8.1f}{r['mdd']:>9.1f}"
                  f"{r['worst']:>9.1f}{r['max_conc']:>6}{r['n']:>6}{r['starved']:>6}"
                  f"{r['final']:>10,.0f}{r['ret']:>+9.1f}")
        print()
    print("-" * 108)
    print("  ** 사이징 고정, 신호 순위 (포착률 → MDD) **")
    for sname, _, _ in SIZINGS:
        row = [(v, res[(v, sname)]) for v, _, _ in VARIANTS if res.get((v, sname))]
        row.sort(key=lambda x: (-x[1]["capture"], x[1]["mdd"]))
        print(f"    [{sname}]  " + "  >  ".join(
            f"{v}({r['capture']:.0f}%/{r['mdd']:.0f}%)" for v, r in row))
    print("=" * 108 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"cohort": len(cohort), "span_days": span, "initial": INITIAL,
               "results": {f"{v}|{s}": r for (v, s), r in res.items()}},
              open(args.out, "w"), ensure_ascii=False, indent=2, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
