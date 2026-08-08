#!/usr/bin/env python3
"""vol_cliff 조기청산 ablation — line 498(REAL 중도청산 차단) 해제 판단용.

팬텀 10% TP를 제거한 뒤 System-2가 낼 수 있는 중도 청산 신호는 사실상
`vol_cliff_invalidated` 하나다. 드라이버의 line 498은 그 신호를 실계좌에서
무시한다. 차단을 풀지 말지는 "조기청산이 baseline 대비 성과를 개선하는가"에
달려 있는데, R-3 그리드는 SL×보유기간만 훑었고 vol_cliff는 다루지 않았다.
r2__metrics.json에도 vol_cliff 키가 없다 — 즉 미검증 규칙이다.

규칙 (BinanceLifecycleDecayEarlyExitSource와 동일):
  check_day=14: vol_cliff = mean(vol[7:14]) / vol[0]
  check_day=7 : vol_cliff = mean(vol[1:7])  / vol[0]
  vol_cliff >= threshold → "감쇠 무효" → 포지션 (check_day-1) 바에서 청산
  그 전에 SL(진입가×1.5)이 닿으면 SL 우선

핵심 출력은 조건부 비교다: 조기청산이 **발동한 건들만** 모아서
"청산했을 때" vs "그냥 30일 보유했을 때"를 짝지어 본다. 전체 평균은
발동하지 않은 건들에 희석돼 규칙의 가치를 가린다.

결과: backend/runs/research_track/lifecycle_phase/earlyexit_ablation__metrics.json
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

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("earlyexit_ablation")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "earlyexit_ablation__metrics.json"

SL_LEVEL = 0.50
HOLD_DAYS = 30
FEE_ROUND_TRIP = 0.0008
VARIANTS = [(14, 0.40), (14, 0.30), (14, 0.50), (7, 0.40), (7, 0.30), (7, 0.50)]


def load_daily(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
        "volume": df["volume"].resample("1D").sum(),
    }).dropna()


def vol_cliff(daily: pd.DataFrame, entry_pos: int, check_day: int) -> float | None:
    """소스와 동일한 정의. 데이터 부족이면 None."""
    vols = daily["volume"].iloc[entry_pos:entry_pos + check_day].to_numpy(dtype=float)
    if len(vols) < check_day or vols[0] <= 0:
        return None
    seg = vols[7:14] if check_day == 14 else vols[1:7]
    if len(seg) == 0:
        return None
    return float(np.mean(seg) / vols[0])


def simulate(daily: pd.DataFrame, entry_pos: int, early_bar: int | None) -> dict:
    """early_bar = 진입 후 몇 번째 바에서 조기청산할지 (None이면 baseline)."""
    entry_price = float(daily.iloc[entry_pos]["close"])
    sl_trigger = entry_price * (1.0 + SL_LEVEL)
    limit = HOLD_DAYS if early_bar is None else min(early_bar, HOLD_DAYS)
    max_idx = min(entry_pos + limit, len(daily) - 1)
    exit_idx, exit_price, reason = max_idx, float(daily.iloc[max_idx]["close"]), \
        ("time" if early_bar is None else "vol_cliff")
    for i in range(entry_pos + 1, max_idx + 1):
        if float(daily.iloc[i]["high"]) >= sl_trigger:
            exit_idx, exit_price, reason = i, sl_trigger, "sl"
            break
    return {"ret": (entry_price - exit_price) / entry_price - FEE_ROUND_TRIP,
            "reason": reason, "hold": int(exit_idx - entry_pos)}


def kpis(rets: list[float]) -> dict:
    a = np.array(rets, dtype=float)
    if len(a) == 0:
        return {"n": 0}
    w, l = a[a > 0], a[a <= 0]
    gl = float(-l.sum())
    return {
        "n": int(len(a)),
        "median_pct": round(float(np.median(a)) * 100, 2),
        "mean_pct": round(float(a.mean()) * 100, 2),
        "win_rate_pct": round(float((a > 0).mean()) * 100, 1),
        "pf": round(float(w.sum()) / gl, 3) if gl > 0 else None,
        "t_stat": round(float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))), 2)
                  if len(a) > 1 and a.std(ddof=1) > 0 else None,
    }


def main() -> int:
    db = SessionLocal()
    try:
        listings = json.loads(LISTINGS_PATH.read_text())
        today = date.today()
        syms = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'")).fetchall()})
        cohort = []
        for sym in syms:
            meta = listings.get(sym)
            if not isinstance(meta, dict) or not meta.get("onboard_date"):
                continue
            ld = datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()
            if not (30 <= (today - ld).days <= 365):
                continue
            daily = load_daily(db, sym)
            if daily.empty or len(daily) < 30:
                continue
            try:
                pos = daily.index.get_indexer([pd.Timestamp(ld)], method="nearest")[0]
            except Exception:
                continue
            if abs((daily.index[pos].date() - ld).days) > 2 or pos >= len(daily) - 30:
                continue
            cohort.append({"symbol": sym, "daily": daily, "entry_pos": pos})
    finally:
        db.close()
    log.info("cohort: %d", len(cohort))
    if not cohort:
        return 1

    base = {c["symbol"]: simulate(c["daily"], c["entry_pos"], None) for c in cohort}
    log.info("baseline (hold 30, SL 50): %s", kpis([v["ret"] for v in base.values()]))

    results = {}
    for check_day, thresh in VARIANTS:
        key = f"d{check_day}_thr{thresh:.2f}"
        all_rets, fired, fired_base, not_fired = [], [], [], []
        for c in cohort:
            vc = vol_cliff(c["daily"], c["entry_pos"], check_day)
            b = base[c["symbol"]]
            if vc is not None and vc >= thresh:
                r = simulate(c["daily"], c["entry_pos"], check_day - 1)
                all_rets.append(r["ret"])
                fired.append({"symbol": c["symbol"], "vol_cliff": round(vc, 3),
                              "early_ret_pct": round(r["ret"] * 100, 2),
                              "base_ret_pct": round(b["ret"] * 100, 2),
                              "delta_pct": round((r["ret"] - b["ret"]) * 100, 2),
                              "early_reason": r["reason"]})
                fired_base.append(b["ret"])
            else:
                all_rets.append(b["ret"])
                not_fired.append(b["ret"])

        deltas = [f["delta_pct"] for f in fired]
        results[key] = {
            "check_day": check_day, "threshold": thresh,
            "fire_rate_pct": round(len(fired) / len(cohort) * 100, 1),
            "n_fired": len(fired),
            "overall": kpis(all_rets),
            "fired_subset_early": kpis([f["early_ret_pct"] / 100 for f in fired]),
            "fired_subset_baseline": kpis(fired_base),
            "delta_mean_pct": round(float(np.mean(deltas)), 2) if deltas else None,
            "delta_median_pct": round(float(np.median(deltas)), 2) if deltas else None,
            "delta_positive_pct": round(float(np.mean([d > 0 for d in deltas])) * 100, 1) if deltas else None,
            "fired_detail": sorted(fired, key=lambda x: x["delta_pct"])[:8],
        }
        r = results[key]
        log.info("%-14s 발동 %3d (%4.1f%%) | 전체 mean %+6.2f%% (base %+6.2f%%) | "
                 "발동건: 조기 %+7.2f%% vs 보유 %+7.2f%% → Δ %+6.2f%% (개선비율 %s%%)",
                 key, r["n_fired"], r["fire_rate_pct"], r["overall"]["mean_pct"],
                 kpis([v["ret"] for v in base.values()])["mean_pct"],
                 r["fired_subset_early"].get("mean_pct", 0),
                 r["fired_subset_baseline"].get("mean_pct", 0),
                 r["delta_mean_pct"] or 0, r["delta_positive_pct"])

    out = {
        "generated_at": datetime.utcnow().isoformat(),
        "params": {"sl_level": SL_LEVEL, "hold_days": HOLD_DAYS,
                   "fee_round_trip": FEE_ROUND_TRIP},
        "cohort_size": len(cohort),
        "baseline": kpis([v["ret"] for v in base.values()]),
        "variants": results,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    log.info("wrote %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
