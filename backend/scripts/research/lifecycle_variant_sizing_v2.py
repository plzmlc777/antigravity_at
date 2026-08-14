"""신상저격수 — 신호 변형 × 사이징 포트폴리오 시뮬 **v2 (회귀 검사 내장)**.

왜 v2 인가 (2026-08-12)
  v1 을 두 번 잘못 만들었다.
    1차: 251건·5.4년 전액 복리 → $724 → $803,901 (1,110배). 절대금액 무효.
    2차: 미실현을 **최종 수익률로 마킹** → MDD 왜곡, 1년에 32~54배.
         조기청산 두 변형이 base 와 소수점까지 동일 = 한 번도 발동 안 함.

  원인은 하나다 — **검증된 코드를 두고 매번 새로 짰고, 알려진 기준값과 대조하지
  않고 보고했다.**

  그래서 v2 는 두 가지를 바꾼다:
    (a) `notional_cap_portfolio_sim.py` 의 `build_cohort` / `run` 구조를 **그대로**
        쓴다. 마킹은 원본대로 **일별 실제 종가**(`path`)로 한다.
    (b) **회귀 검사를 먼저 돌린다.** base × cap 0.20 × 1배가 기존 기록값
        (final 740.20 / mdd -37.70 / taken 78 / starved 51, 초기 593.44)을
        재현하지 못하면 **즉시 중단**한다. 재현되면 그때만 변형·사이징으로 확장.

변형 정의 (소스 구현 그대로)
  base          Day-1 종가 숏 → Day-30 종가, SL +50%
  h21           → Day-21
  earlyexit_d7  Day-7 에 vol_cliff = mean(vol[1:7])/vol[0] ≥ 0.40 이면 그날 청산
  earlyexit_d14 Day-14 에 vol_cliff = mean(vol[7:14])/vol[0] ≥ 0.40 이면 그날 청산
  bearskip      상장 직전 BTC 30일 수익률 ≤ -5% 면 진입 안 함

읽는 법
  **수익률로 고르지 말 것** — `lifecycle_live_signal_driver.py` 78행:
  "수익 기준 최적 상한은 시간 분할마다 100%/30%/25% 로 뒤집힌다".
  단조 축은 **포착률 / MDD / 최악 단일거래** 셋뿐이다.

사용:
  python3 scripts/research/lifecycle_variant_sizing_v2.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "research"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("var_size_v2")

import notional_cap_portfolio_sim as BASE   # noqa: E402  검증된 원본

# 회귀 기준값 — notional_cap__metrics.json 의 cap 0.20 행
BASELINE = {"final": 740.20, "mdd": -37.70, "taken": 78, "starved": 51}
TOL = {"final": 1.0, "mdd": 0.2, "taken": 0, "starved": 0}

VC_THR = 0.40
BEAR_THR = -0.05
VARIANTS = [("base", 30, None), ("h21", 21, None),
            ("earlyexit_d7", 30, 7), ("earlyexit_d14", 30, 14),
            ("bearskip", 30, None)]
SIZINGS = [("20%x1 현행", 0.20, 1), ("3%x1 대안A", 0.03, 1), ("3%x3 대안B", 0.03, 3)]


def resolve_variant(daily: pd.DataFrame, entry_pos: int, hold: int, early: int | None) -> dict:
    """원본 `resolve_trade` 와 같은 형태. hold / 조기청산만 파라미터화."""
    e = float(daily.iloc[entry_pos]["close"])
    sl = e * (1.0 + BASE.SL_LEVEL)
    max_idx = min(entry_pos + hold, len(daily) - 1)
    # 조기청산 — vol_cliff 가 임계 이상이면 Day-N 종가에 나간다
    if early is not None and "volume" in daily.columns:
        v = daily["volume"].astype(float).values
        v0 = float(v[entry_pos]) if entry_pos < len(v) else 0.0
        if v0 > 0:
            lo = entry_pos + (7 if early == 14 else 1)
            hi = entry_pos + (14 if early == 14 else 7)
            win = v[lo:min(hi, len(v))]
            if len(win) >= 1 and float(win.mean()) / v0 >= VC_THR:
                max_idx = min(entry_pos + early - 1, max_idx)
    exit_idx, exit_px, reason = max_idx, float(daily.iloc[max_idx]["close"]), "time"
    for i in range(entry_pos + 1, max_idx + 1):
        if float(daily.iloc[i]["high"]) >= sl:
            exit_idx, exit_px, reason = i, sl, "sl"
            break
    if early is not None and reason == "time" and exit_idx == entry_pos + early - 1:
        reason = "early"
    return {"entry_date": daily.index[entry_pos].date(),
            "exit_date": daily.index[exit_idx].date(),
            "entry_price": e, "exit_price": exit_px,
            "ret": (e - exit_px) / e - BASE.FEE_ROUND_TRIP,
            "reason": reason, "path": daily.iloc[entry_pos:exit_idx + 1]}


def run_pf(trades: list, cap_frac: float, lev: int, initial: float) -> dict:
    """원본 `run` 과 동일한 루프. **마킹은 일별 실제 종가**. 레버리지만 추가."""
    trades = sorted(trades, key=lambda t: t["entry_date"])
    days = pd.date_range(min(t["entry_date"] for t in trades),
                         max(t["exit_date"] for t in trades), freq="D")
    wallet, open_pos, taken, starved, curve = initial, [], [], [], []
    max_conc = 0
    by_entry: dict = {}
    for t in trades:
        by_entry.setdefault(t["entry_date"], []).append(t)

    for d in days:
        dd = d.date()
        still = []
        for p in open_pos:
            if p["exit_date"] <= dd:
                wallet += p["notional"] * p["ret"]
                continue
            still.append(p)
        open_pos = still

        locked = sum(p["margin"] for p in open_pos)
        for t in by_entry.get(dd, []):
            avail = max(wallet - locked, 0.0)
            margin = min(cap_frac * wallet, avail * BASE.MARGIN_FRACTION)
            if margin < BASE.MIN_NOTIONAL:
                starved.append(t["symbol"])
                continue
            open_pos.append({**t, "margin": margin, "notional": margin * lev})
            locked += margin
            taken.append({"symbol": t["symbol"], "margin": margin,
                          "pnl": margin * lev * t["ret"], "reason": t["reason"]})
        max_conc = max(max_conc, len(open_pos))

        unreal = 0.0
        for p in open_pos:            # 원본과 동일 — 일별 실제 종가로 마킹
            try:
                px = float(p["path"].loc[:d].iloc[-1]["close"])
            except Exception:
                px = p["entry_price"]
            unreal += p["notional"] * ((p["entry_price"] - px) / p["entry_price"])
        curve.append(wallet + unreal)

    for p in open_pos:
        wallet += p["notional"] * p["ret"]

    eq = np.array(curve, dtype=float)
    peak = np.maximum.accumulate(eq) if len(eq) else np.array([1.0])
    mdd = float(((eq - peak) / np.maximum(peak, 1e-9)).min() * 100) if len(eq) else 0.0
    pn = [t["pnl"] for t in taken]
    rs = [t["reason"] for t in taken]
    return {"final": round(wallet, 2), "ret_pct": round((wallet / initial - 1) * 100, 2),
            "mdd_pct": round(mdd, 2), "taken": len(taken), "starved": len(starved),
            "capture": round(100 * len(taken) / max(len(taken) + len(starved), 1), 1),
            "max_conc": max_conc, "worst": round(min(pn), 2) if pn else 0.0,
            "sl_pct": round(100 * rs.count("sl") / max(len(rs), 1), 1),
            "early_pct": round(100 * rs.count("early") / max(len(rs), 1), 1)}


def main() -> int:
    p = argparse.ArgumentParser(description="변형 x 사이징 v2")
    p.add_argument("--initial", type=float, default=None,
                   help="미지정 시 회귀 기준(593.44)으로 검사 후 실계좌 잔고로 본 실행")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "lifecycle_phase" / "variant_sizing_v2__metrics.json"))
    args = p.parse_args()

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        cohort = BASE.build_cohort(db)
    finally:
        db.close()
    log.info("코호트 %d건", len(cohort))

    # ── ① 회귀 검사 — 재현 못 하면 중단 ────────────────────────────
    base_tr = []
    for c in cohort:
        t = resolve_variant(c["daily"], c["entry_pos"], 30, None)
        t["symbol"] = c["symbol"]
        base_tr.append(t)
    chk = run_pf(base_tr, 0.20, 1, BASE.INITIAL_CAPITAL)
    log.info("회귀 검사: final %.2f (기준 %.2f) / mdd %.2f (%.2f) / "
             "taken %d (%d) / starved %d (%d)",
             chk["final"], BASELINE["final"], chk["mdd_pct"], BASELINE["mdd"],
             chk["taken"], BASELINE["taken"], chk["starved"], BASELINE["starved"])
    bad = []
    if abs(chk["final"] - BASELINE["final"]) > TOL["final"]:
        bad.append(f"final {chk['final']} vs {BASELINE['final']}")
    if abs(chk["mdd_pct"] - BASELINE["mdd"]) > TOL["mdd"]:
        bad.append(f"mdd {chk['mdd_pct']} vs {BASELINE['mdd']}")
    if abs(chk["taken"] - BASELINE["taken"]) > TOL["taken"]:
        bad.append(f"taken {chk['taken']} vs {BASELINE['taken']}")
    if abs(chk["starved"] - BASELINE["starved"]) > TOL["starved"]:
        bad.append(f"starved {chk['starved']} vs {BASELINE['starved']}")
    if bad:
        log.error("**회귀 검사 실패 — 중단**: %s", " | ".join(bad))
        log.error("검증된 원본을 재현하지 못하는 시뮬은 결과를 쓸 수 없다.")
        return 1
    log.info("**회귀 검사 통과** — 확장 실행")

    # ── ② bearskip 판정용 BTC 사전 수익률 ─────────────────────────
    from sqlalchemy import text
    from app.db.session import engine
    btc: dict = {}
    with engine.connect() as conn:
        for c in cohort:
            ld = c["daily"].index[c["entry_pos"]].date()
            key = ld.strftime("%Y-%m")
            if key in btc:
                continue
            r = conn.execute(text(
                "SELECT timestamp, close FROM ohlcv WHERE symbol='BTCUSDT' "
                "AND time_frame='1m' AND timestamp >= :a AND timestamp < :b ORDER BY timestamp"),
                {"a": ld - timedelta(days=32), "b": ld}).fetchall()
            if not r:
                btc[key] = None
                continue
            s = pd.Series({pd.Timestamp(t): float(x) for t, x in r}).sort_index()
            dd = s.resample("1D").last().dropna()
            btc[key] = float(dd.iloc[-1] / dd.iloc[0] - 1.0) if len(dd) >= 20 else None

    initial = args.initial if args.initial else BASE.INITIAL_CAPITAL
    res = {}
    for vname, hold, early in VARIANTS:
        trs = []
        for c in cohort:
            if vname == "bearskip":
                ld = c["daily"].index[c["entry_pos"]].date()
                pre = btc.get(ld.strftime("%Y-%m"))
                if pre is not None and pre <= BEAR_THR:
                    continue
            t = resolve_variant(c["daily"], c["entry_pos"], hold, early)
            t["symbol"] = c["symbol"]
            trs.append(t)
        for sname, cap, lev in SIZINGS:
            res[f"{vname}|{sname}"] = run_pf(trs, cap, lev, initial)

    print("\n" + "=" * 108)
    print(f"신호 변형 5종 x 사이징 3종 (v2, 회귀 검사 통과) — 코호트 {len(cohort)}건 / "
          f"초기 ${initial:.2f}")
    print("=" * 108)
    print("  ** 수익률로 고르지 말 것 — 단조 축은 포착률 / MDD / 최악 셋뿐 **")
    print("-" * 108)
    print(f"  {'신호변형':<15}{'사이징':<13}{'포착%':>8}{'MDD%':>9}{'최악$':>10}"
          f"{'SL%':>7}{'조기%':>7}{'동시':>6}{'잡음':>6}{'놓침':>6}{'최종$':>10}")
    print("-" * 108)
    for vname, _, _ in VARIANTS:
        for sname, _, _ in SIZINGS:
            r = res[f"{vname}|{sname}"]
            print(f"  {vname:<15}{sname:<13}{r['capture']:>8.1f}{r['mdd_pct']:>9.2f}"
                  f"{r['worst']:>10.2f}{r['sl_pct']:>7.1f}{r['early_pct']:>7.1f}"
                  f"{r['max_conc']:>6}{r['taken']:>6}{r['starved']:>6}{r['final']:>10,.2f}")
        print()
    print("-" * 108)
    print("  ** 사이징 고정 — 신호 순위 (포착률 → MDD) **")
    for sname, _, _ in SIZINGS:
        row = [(v, res[f"{v}|{sname}"]) for v, _, _ in VARIANTS]
        row.sort(key=lambda x: (-x[1]["capture"], x[1]["mdd_pct"]))
        print(f"    [{sname}]  " + "  >  ".join(
            f"{v}({r['capture']:.0f}%/{r['mdd_pct']:.0f}%)" for v, r in row))
    print("=" * 108 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"cohort": len(cohort), "initial": initial,
               "regression_check": chk, "baseline": BASELINE, "results": res},
              open(args.out, "w"), ensure_ascii=False, indent=2, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
