#!/usr/bin/env python3
"""신상저격수 종목당 notional 상한 포트폴리오 시뮬레이션.

tp_ablation.py는 **거래당** 지표만 본다. 그 지표로는 실계좌에서 실제로 터진
문제 — 한 종목이 가용증거금을 다 먹어서 그 뒤 상장들을 아예 못 잡는 것 —
이 안 잡힌다. 그래서 상장 캘린더를 따라 자본을 굴리는 시뮬레이션이 필요하다.

모델 (실계좌 acct 8 구성에 맞춤):
  - 레버리지 1x → 증거금 = 명목가
  - 상장일(Day-1) 종가 진입, SL 50% 또는 30일 시간청산
  - 진입 증거금 = min(cap_frac × 지갑잔고, 가용증거금 × 0.97)
  - 가용 < $5면 진입 포기(starved) — 실계좌 MIN_REAL_NOTIONAL과 동일
  - 왕복 수수료 0.08%
  - 에쿼티 = 지갑 + Σ미실현 (일별 마킹)

cap_frac=1.00이 현행(풀-복리 몰빵), 0.30이 제안값.
결과: backend/runs/research_track/lifecycle_phase/notional_cap__metrics.json
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
log = logging.getLogger("notional_cap_sim")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "notional_cap__metrics.json"

INITIAL_CAPITAL = 593.44   # 실계좌 최초 입금액
SL_LEVEL = 0.50
HOLD_DAYS = 30
FEE_ROUND_TRIP = 0.0008
MIN_NOTIONAL = 5.0
MARGIN_FRACTION = 0.97
CAP_GRID = [1.00, 0.50, 0.30, 0.25, 0.20, 0.10]


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


def build_cohort(db) -> list[dict]:
    listings = json.loads(LISTINGS_PATH.read_text())
    today = date.today()
    syms = sorted({r[0] for r in db.execute(text(
        "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'"
    )).fetchall()})
    out = []
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
        out.append({"symbol": sym, "listing": ld, "entry_pos": pos, "daily": daily})
    return out


def resolve_trade(daily: pd.DataFrame, entry_pos: int) -> dict:
    """진입 후 청산 시점/가격 (SL 50% 또는 30일 시간청산). 자본과 무관."""
    entry_price = float(daily.iloc[entry_pos]["close"])
    sl_trigger = entry_price * (1.0 + SL_LEVEL)
    max_idx = min(entry_pos + HOLD_DAYS, len(daily) - 1)
    exit_idx, exit_price, reason = max_idx, float(daily.iloc[max_idx]["close"]), "time"
    for i in range(entry_pos + 1, max_idx + 1):
        if float(daily.iloc[i]["high"]) >= sl_trigger:
            exit_idx, exit_price, reason = i, sl_trigger, "sl"
            break
    return {
        "entry_date": daily.index[entry_pos].date(),
        "exit_date": daily.index[exit_idx].date(),
        "entry_price": entry_price, "exit_price": exit_price,
        "ret": (entry_price - exit_price) / entry_price - FEE_ROUND_TRIP,
        "reason": reason,
        "path": daily.iloc[entry_pos:exit_idx + 1],
    }


def run(cohort: list[dict], cap_frac: float) -> dict:
    trades = []
    for c in cohort:
        t = resolve_trade(c["daily"], c["entry_pos"])
        t["symbol"] = c["symbol"]
        trades.append(t)
    trades.sort(key=lambda t: t["entry_date"])

    days = pd.date_range(min(t["entry_date"] for t in trades),
                         max(t["exit_date"] for t in trades), freq="D")
    wallet = INITIAL_CAPITAL
    open_pos = []          # {symbol, margin, entry_price, exit_date, ret, path}
    taken, starved = [], []
    equity_curve = []
    max_concurrent = 0

    by_entry = {}
    for t in trades:
        by_entry.setdefault(t["entry_date"], []).append(t)

    for d in days:
        dd = d.date()
        # 1) 청산 먼저 (증거금 반환 → 같은 날 진입에 재사용 가능)
        still = []
        for p in open_pos:
            if p["exit_date"] <= dd:
                wallet += p["margin"] * p["ret"]
                continue
            still.append(p)
        open_pos = still

        # 2) 진입
        locked = sum(p["margin"] for p in open_pos)
        for t in by_entry.get(dd, []):
            avail = max(wallet - locked, 0.0)
            margin = min(cap_frac * wallet, avail * MARGIN_FRACTION)
            if margin < MIN_NOTIONAL:
                starved.append({"symbol": t["symbol"], "date": str(dd),
                                "would_be_ret_pct": round(t["ret"] * 100, 2)})
                continue
            open_pos.append({**t, "margin": margin})
            locked += margin
            taken.append({"symbol": t["symbol"], "date": str(dd),
                          "margin": round(margin, 2), "ret_pct": round(t["ret"] * 100, 2),
                          "pnl": round(margin * t["ret"], 2), "reason": t["reason"]})

        max_concurrent = max(max_concurrent, len(open_pos))

        # 3) 마킹
        unreal = 0.0
        for p in open_pos:
            try:
                px = float(p["path"].loc[:d].iloc[-1]["close"])
            except Exception:
                px = p["entry_price"]
            unreal += p["margin"] * ((p["entry_price"] - px) / p["entry_price"])
        equity_curve.append((dd, wallet + unreal))

    for p in open_pos:  # 잔여 청산
        wallet += p["margin"] * p["ret"]

    eq = np.array([e for _, e in equity_curve], dtype=float)
    peak = np.maximum.accumulate(eq)
    mdd = float(((eq - peak) / peak).min() * 100) if len(eq) else 0.0
    pnls = [t["pnl"] for t in taken]
    return {
        "cap_frac": cap_frac,
        "final_wallet": round(wallet, 2),
        "return_pct": round((wallet / INITIAL_CAPITAL - 1) * 100, 2),
        "mdd_pct": round(mdd, 2),
        "n_taken": len(taken),
        "n_starved": len(starved),
        "starved_symbols": [s["symbol"] for s in starved],
        "max_concurrent": max_concurrent,
        "worst_trade_pnl": round(min(pnls), 2) if pnls else 0.0,
        "best_trade_pnl": round(max(pnls), 2) if pnls else 0.0,
        "avg_margin": round(float(np.mean([t["margin"] for t in taken])), 2) if taken else 0.0,
        "max_margin": round(float(max(t["margin"] for t in taken)), 2) if taken else 0.0,
        "equity_curve": [(str(d), round(v, 2)) for d, v in equity_curve[::7]],
    }


def main() -> int:
    db = SessionLocal()
    try:
        cohort = build_cohort(db)
    finally:
        db.close()
    log.info("cohort: %d listings", len(cohort))
    if not cohort:
        log.error("empty cohort")
        return 1

    results = [run(cohort, c) for c in CAP_GRID]
    for r in results:
        log.info("cap %5.0f%%  최종 %8.2f (%+7.2f%%)  MDD %7.2f%%  진입 %3d  굶음 %3d  "
                 "최대증거금 %7.2f  최악거래 %+8.2f",
                 r["cap_frac"] * 100, r["final_wallet"], r["return_pct"], r["mdd_pct"],
                 r["n_taken"], r["n_starved"], r["max_margin"], r["worst_trade_pnl"])

    out = {
        "generated_at": datetime.utcnow().isoformat(),
        "params": {"initial_capital": INITIAL_CAPITAL, "sl_level": SL_LEVEL,
                   "hold_days": HOLD_DAYS, "fee_round_trip": FEE_ROUND_TRIP,
                   "leverage": 1, "min_notional": MIN_NOTIONAL,
                   "margin_fraction": MARGIN_FRACTION},
        "cohort_size": len(cohort),
        "results": results,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    log.info("wrote %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
