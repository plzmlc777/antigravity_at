#!/usr/bin/env python3
"""신상저격수 TP ablation — 검증본(TP 없음) vs 라이브 실제(팬텀 10% TP).

R-3(lifecycle_phase_r3.py)의 코호트 구성/시뮬레이터를 그대로 재사용하되,
short 시뮬레이터에 take-profit 축을 추가해 orchestrator.py의 `or` 폴백이
심어놓은 10% TP가 성과에 어떤 영향을 줬는지 측정한다.

R-3 원본 simulate_short는 SL + 시간청산만 있고 TP가 없다 = 검증된 설계.
결과: backend/runs/research_track/lifecycle_phase/tp_ablation__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[0]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tp_ablation")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "tp_ablation__metrics.json"

FEE_ROUND_TRIP = 0.0008
SL_LEVEL = 0.50      # R-3 plateau, 현 운영값
HOLD_DAYS = 30       # max_hold_bars
TP_GRID = [None, 0.05, 0.10, 0.15, 0.20, 0.30]


def load_daily(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
    }).dropna()


def simulate_short(daily: pd.DataFrame, entry_idx: int, sl_level: float,
                   hold_days: int, tp_level: float | None) -> dict | None:
    """R-3 simulate_short + optional take-profit.

    동일 바에서 SL·TP가 모두 닿을 수 있으면 보수적으로 SL 우선(불리한 쪽).
    """
    if entry_idx >= len(daily):
        return None
    entry_price = daily.iloc[entry_idx]["close"]
    if entry_price <= 0:
        return None
    sl_trigger = entry_price * (1.0 + sl_level)
    tp_trigger = entry_price * (1.0 - tp_level) if tp_level is not None else None
    max_idx = min(entry_idx + hold_days, len(daily) - 1)
    exit_idx, exit_price, exit_reason = max_idx, daily.iloc[max_idx]["close"], "time"
    for i in range(entry_idx + 1, max_idx + 1):
        hi, lo = daily.iloc[i]["high"], daily.iloc[i]["low"]
        if hi >= sl_trigger:                       # 보수적: SL 먼저
            exit_idx, exit_price, exit_reason = i, sl_trigger, "sl"
            break
        if tp_trigger is not None and lo <= tp_trigger:
            exit_idx, exit_price, exit_reason = i, tp_trigger, "tp"
            break
    ret_gross = (entry_price - exit_price) / entry_price
    return {
        "ret_net": float(ret_gross - FEE_ROUND_TRIP),
        "exit_reason": exit_reason,
        "hold_days_actual": int(exit_idx - entry_idx),
    }


def kpis(rets: list[float], reasons: list[str]) -> dict:
    a = np.array(rets, dtype=float)
    wins, losses = a[a > 0], a[a <= 0]
    gp, gl = float(wins.sum()), float(-losses.sum())
    return {
        "n": int(len(a)),
        "median_pct": round(float(np.median(a)) * 100, 3),
        "mean_pct": round(float(a.mean()) * 100, 3),
        "win_rate_pct": round(float((a > 0).mean()) * 100, 2),
        "sum_pct": round(float(a.sum()) * 100, 2),
        "pf": round(gp / gl, 3) if gl > 0 else None,
        "std_pct": round(float(a.std(ddof=1)) * 100, 3) if len(a) > 1 else None,
        "t_stat": round(float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))), 3) if len(a) > 1 and a.std(ddof=1) > 0 else None,
        "worst_pct": round(float(a.min()) * 100, 2),
        "best_pct": round(float(a.max()) * 100, 2),
        "exit_mix": {r: reasons.count(r) for r in sorted(set(reasons))},
        "avg_hold_days": None,
    }


def main() -> int:
    listings = json.loads(LISTINGS_PATH.read_text())
    today = date.today()
    db = SessionLocal()
    try:
        syms_in_db = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'"
        )).fetchall()})
        cohort = []
        for sym in syms_in_db:
            if sym not in listings or not isinstance(listings[sym], dict):
                continue
            od = listings[sym].get("onboard_date")
            if not od:
                continue
            ld = datetime.strptime(od, "%Y-%m-%d").date()
            age = (today - ld).days
            if age < 30 or age > 365:
                continue
            daily = load_daily(db, sym)
            if daily.empty or len(daily) < 30:
                continue
            ld_ts = pd.Timestamp(ld)
            try:
                pos = daily.index.get_indexer([ld_ts], method="nearest")[0]
            except Exception:
                continue
            if abs((daily.index[pos].date() - ld).days) > 2:
                continue
            if pos >= len(daily) - 30:
                continue
            cohort.append((sym, ld, pos, daily))
        log.info("cohort: %d symbols", len(cohort))
    finally:
        db.close()

    if not cohort:
        log.error("empty cohort — OHLCV substrate missing?")
        return 1

    results = {}
    per_symbol = {}
    for tp in TP_GRID:
        key = "no_tp" if tp is None else f"tp_{int(tp*100)}pct"
        rets, reasons, holds = [], [], []
        for sym, ld, pos, daily in cohort:
            r = simulate_short(daily, pos, SL_LEVEL, HOLD_DAYS, tp)
            if r is None:
                continue
            rets.append(r["ret_net"]); reasons.append(r["exit_reason"]); holds.append(r["hold_days_actual"])
            per_symbol.setdefault(sym, {})[key] = round(r["ret_net"] * 100, 2)
        k = kpis(rets, reasons)
        k["avg_hold_days"] = round(float(np.mean(holds)), 1)
        results[key] = k
        log.info("%-12s n=%d median=%+.2f%% mean=%+.2f%% win=%.1f%% PF=%s hold=%.1fd %s",
                 key, k["n"], k["median_pct"], k["mean_pct"], k["win_rate_pct"], k["pf"],
                 k["avg_hold_days"], k["exit_mix"])

    out = {
        "generated_at": datetime.utcnow().isoformat(),
        "params": {"sl_level": SL_LEVEL, "hold_days": HOLD_DAYS, "fee_round_trip": FEE_ROUND_TRIP,
                   "intrabar_precedence": "SL first (conservative)"},
        "cohort_size": len(cohort),
        "cohort_symbols": [s for s, _, _, _ in cohort],
        "results": results,
        "per_symbol_ret_pct": per_symbol,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    log.info("wrote %s", OUT_PATH)
    print(json.dumps({"results": results, "cohort_size": len(cohort)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
