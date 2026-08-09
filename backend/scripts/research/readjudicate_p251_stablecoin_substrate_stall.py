#!/usr/bin/env python3
"""paradigm 251 재판정 — substrate stall 이 G1 판정을 오염시켰는지 판별한다.

배경 (2026-08-09 발견):
  3군 R-1 스크립트들은 `runs/ohlcv_cache/{sym}_1m.joblib` 를 읽는데 이 캐시가
  **2026-05-12 에서 89일째 정지**해 있다. 같은 DB 의 `ohlcv` 테이블은 214 종목·
  오늘까지 살아 있다. paradigm 251 의 신호(CoinGecko 스테이블코인 공급)는
  2026-08-08 까지 있으므로, 최근 88일 트리거는 가격이 없어서
  `price_by_date.get()` → None → continue 로 **조용히 버려졌다**.

  그런데 251 을 죽인 사유가 `decay_ratio 0.14 < 0.30` 이다. decay_ratio 는
  "최근 1/3 엣지 ÷ 과거 1/3 엣지" 이고, 그 "최근" 이 실제로는 2026-03~05 다.
  즉 **최근 3개월을 못 본 상태로 "최근에 죽었다" 고 판정**했을 가능성이 있다.

판별 설계 — 변수를 하나씩만 움직인다:
  A. STALE            joblib(2026-05-12 종료)          … 운영 재현
  B. FRESH_SAMEWINDOW DB, 같은 종료일로 절단           … 출처 정합성 대조
  C. FRESH_FULL       DB, 2026-08-08 까지              … 진짜 재판정

  A vs B 가 일치하면 두 출처의 데이터는 동일하다(= 차이는 순전히 기간).
  B vs C 의 차이가 decay_ratio 를 살리면 판정 오염이 확정된다.

now 앵커도 함께 분리한다. tier3_gate 는 `now=utcnow()` 로 시간가중하므로
데이터가 89일 낡으면 모든 거래 가중치가 0.5 이하로 눌린다. 각 시나리오를
now=오늘 / now=데이터종료 두 앵커로 모두 재본다.

사용:
  cd backend && source venv/bin/activate
  python3 scripts/research/readjudicate_p251_stablecoin_substrate_stall.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research.tier3_gate import (  # noqa: E402
    ExecContext,
    Trade,
    evaluate_g1,
    evaluate_g2,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("readjudicate_p251")

P251_DIR = ROOT / "runs" / "research_track" / "paradigm_251_stablecoin_supply_flow"
OHLCV_CACHE = ROOT / "runs" / "ohlcv_cache"
OUT = ROOT / "runs" / "research_track" / "readjudication_2026_08_09"
OUT.mkdir(parents=True, exist_ok=True)

# 원 스크립트와 완전 동일한 스펙 — 하나도 바꾸지 않는다.
FEE_RT = 0.0008
Z_THRESH = 1.0
ROLL_WIN = 60
NET_DAYS = 7
HOLDS = [1, 2, 3]
UNIVERSE = ["SOLUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "XRPUSDT", "BNBUSDT"]

# G2 입력 (원 판정과 동일)
ROUNDTRIP_FRICTION = 0.0008
CYCLE_MINUTES = 1440.0


# ── 신호: 기존 캐시 재사용 (CoinGecko 무료 365일) ────────────────────
def build_signal() -> pd.DataFrame:
    cache_path = P251_DIR / "stablecoin_supply_cache.json"
    raw = json.loads(cache_path.read_text())
    usdt = pd.DataFrame(raw["usdt"])
    usdc = pd.DataFrame(raw["usdc"])
    usdt["date"] = pd.to_datetime(usdt["date"], utc=True)
    usdc["date"] = pd.to_datetime(usdc["date"], utc=True)
    df = usdt.merge(usdc, on="date", suffixes=("_usdt", "_usdc"))
    df["combined_supply"] = df["mcap_usdt"] + df["mcap_usdc"]
    df = df.sort_values("date").reset_index(drop=True)
    df["net_7d"] = df["combined_supply"].diff(NET_DAYS)
    df["z"] = (
        df["net_7d"] - df["net_7d"].rolling(ROLL_WIN).mean()
    ) / df["net_7d"].rolling(ROLL_WIN).std()
    return df[["date", "combined_supply", "net_7d", "z"]].dropna().reset_index(drop=True)


# ── 가격: 두 출처 ────────────────────────────────────────────────────
def load_daily_joblib(sym: str) -> pd.DataFrame:
    """운영 경로 — 정지된 캐시."""
    import joblib

    f = OHLCV_CACHE / f"{sym}_1m.joblib"
    if not f.exists():
        return pd.DataFrame()
    df = joblib.load(f)
    if df.index.tz is not None:
        df = df.tz_convert("UTC").tz_localize(None)
    return pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
    }).dropna()


def load_daily_db(db, sym: str) -> pd.DataFrame:
    """positive_control_r1.load_daily 과 동일 쿼리."""
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
    }).dropna()


# ── 백테스트: 원 스크립트 로직 그대로 + 누락 카운터 ──────────────────
def backtest(sym: str, price: pd.DataFrame, signal_df: pd.DataFrame,
             hold: int, entry_lag_days: int = 1) -> tuple[list, int]:
    """반환: (trades, 가격없어서_버려진_트리거수)"""
    if price.empty:
        return [], 0
    by_date = {d: (o, c) for d, o, c in
               zip(price.index.date, price["open"], price["close"])}
    trades, skipped = [], 0
    for _, row in signal_df.iterrows():
        z = row["z"]
        if abs(z) < Z_THRESH:
            continue
        side = "long" if z > 0 else "short"
        sig_date = row["date"].date()
        entry_d = sig_date + timedelta(days=entry_lag_days)
        exit_d = entry_d + timedelta(days=hold)
        e, x = by_date.get(entry_d), by_date.get(exit_d)
        if e is None or x is None:
            skipped += 1
            continue
        entry_px, exit_px = float(e[0]), float(x[1])
        if not np.isfinite(entry_px) or not np.isfinite(exit_px) or entry_px <= 0:
            skipped += 1
            continue
        gross = ((exit_px - entry_px) / entry_px if side == "long"
                 else (entry_px - exit_px) / entry_px)
        trades.append({
            "entry_ts": datetime.combine(entry_d, datetime.min.time())
                                .replace(tzinfo=timezone.utc).isoformat(),
            "exit_ts": datetime.combine(exit_d, datetime.min.time())
                               .replace(tzinfo=timezone.utc).isoformat(),
            "net_ret": gross - FEE_RT, "side": side, "z": float(z),
            "sym": sym, "hold": hold,
        })
    return trades, skipped


def to_gate_trades(raw: list) -> list:
    return [Trade(entry_ts=datetime.fromisoformat(t["entry_ts"]).replace(tzinfo=None),
                  exit_ts=datetime.fromisoformat(t["exit_ts"]).replace(tzinfo=None),
                  net_ret=t["net_ret"]) for t in raw]


def judge(raw: list, raw_delayed: list, hold: int, now: datetime) -> dict:
    """G1 + G2 판정. tier3_gate 를 그대로 호출한다 (기준을 손대지 않는다)."""
    gt = to_gate_trades(raw)
    g1 = evaluate_g1(gt, now=now)
    delayed_edge = (float(np.mean([t["net_ret"] for t in raw_delayed]))
                    if raw_delayed else None)
    ctx = ExecContext(
        lookahead_clean=True,           # 일봉 신호 + T+1 시가 진입 (원 판정과 동일)
        edge_after_1bar_delay=delayed_edge,
        roundtrip_friction=ROUNDTRIP_FRICTION,
        hold_minutes=hold * 1440.0,
        cycle_minutes=CYCLE_MINUTES,
    )
    g2 = evaluate_g2(ctx, g1)
    return {"G1": g1, "G2": g2, "passed": bool(g1.get("ok") and g2.get("ok"))}


def main() -> int:
    signal_df = build_signal()
    sig_start, sig_end = signal_df["date"].min().date(), signal_df["date"].max().date()
    log.info(f"신호: {len(signal_df)}일 {sig_start} ~ {sig_end} "
             f"| 트리거 |z|>=1.0: {int((signal_df['z'].abs() >= Z_THRESH).sum())}건")

    db = SessionLocal()
    try:
        price_db, price_jl = {}, {}
        for sym in UNIVERSE:
            price_db[sym] = load_daily_db(db, sym)
            price_jl[sym] = load_daily_joblib(sym)
            d, j = price_db[sym], price_jl[sym]
            log.info(f"  {sym:10s} DB {len(d):5d}일 ~{d.index.max().date() if len(d) else 'NA'}"
                     f" | joblib {len(j):5d}일 ~{j.index.max().date() if len(j) else 'NA'}")

        # joblib 종료일 = 절단 기준
        jl_end = min(j.index.max().date() for j in price_jl.values() if len(j))
        log.info(f"joblib 공통 종료일: {jl_end} (절단 기준)")

        # 출처 정합성: 겹치는 구간의 종가 최대 상대오차
        parity = {}
        for sym in UNIVERSE:
            d, j = price_db[sym], price_jl[sym]
            if d.empty or j.empty:
                continue
            common = d.index.intersection(j.index)
            if len(common) == 0:
                continue
            rel = ((d.loc[common, "close"] - j.loc[common, "close"]).abs()
                   / j.loc[common, "close"].abs()).replace([np.inf, -np.inf], np.nan).dropna()
            parity[sym] = {"n_days": int(len(common)),
                           "max_rel_err": float(rel.max()) if len(rel) else None,
                           "median_rel_err": float(rel.median()) if len(rel) else None}
        log.info("출처 정합성(종가 상대오차): " + json.dumps(parity, ensure_ascii=False))

        scenarios = {
            "A_STALE_joblib": {sym: price_jl[sym] for sym in UNIVERSE},
            "B_FRESH_db_same_window": {
                sym: (price_db[sym][price_db[sym].index.date <= jl_end]
                      if not price_db[sym].empty else price_db[sym]) for sym in UNIVERSE},
            "C_FRESH_db_full": {sym: price_db[sym] for sym in UNIVERSE},
        }

        now_today = datetime.utcnow()
        results = {}
        for scen, prices in scenarios.items():
            cells = {}
            for sym in UNIVERSE:
                for hold in HOLDS:
                    tr, skipped = backtest(sym, prices[sym], signal_df, hold, 1)
                    trd, _ = backtest(sym, prices[sym], signal_df, hold, 2)
                    if not tr:
                        continue
                    last_exit = max(datetime.fromisoformat(t["exit_ts"]).replace(tzinfo=None)
                                    for t in tr)
                    cells[f"{sym}_h{hold}d"] = {
                        "n": len(tr),
                        "skipped_no_price": skipped,
                        "raw_edge_pct": round(float(np.mean([t["net_ret"] for t in tr])) * 100, 4),
                        "last_exit": last_exit.date().isoformat(),
                        "verdict_now_today": judge(tr, trd, hold, now_today),
                        "verdict_now_dataend": judge(tr, trd, hold, last_exit),
                    }
            results[scen] = cells
            best = max(cells.items(),
                       key=lambda kv: (kv[1]["verdict_now_today"]["G1"].get("wt_t") or -99))
            log.info(f"[{scen}] {len(cells)}셀 | 최고 wt_t 셀 {best[0]}: "
                     f"n={best[1]['n']} wt_t={best[1]['verdict_now_today']['G1'].get('wt_t')} "
                     f"decay={best[1]['verdict_now_today']['G1'].get('decay_ratio')} "
                     f"버려진트리거={best[1]['skipped_no_price']}")

        payload = {
            "generated_at_kst": (datetime.utcnow() + timedelta(hours=9)).isoformat(),
            "paradigm": "alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d",
            "purpose": "substrate stall(joblib 2026-05-12 정지)이 G1 decay 판정을 오염시켰는지 판별",
            "signal": {"days": int(len(signal_df)), "start": sig_start.isoformat(),
                       "end": sig_end.isoformat()},
            "joblib_common_end": jl_end.isoformat(),
            "source_parity_close": parity,
            "spec": {"fee_rt": FEE_RT, "z_thresh": Z_THRESH, "roll_win": ROLL_WIN,
                     "net_days": NET_DAYS, "holds": HOLDS, "universe": UNIVERSE},
            "scenarios": results,
        }
        (OUT / "p251_stablecoin_readjudication.json").write_text(
            json.dumps(payload, indent=1, ensure_ascii=False, default=str))
        log.info(f"기록 → {OUT / 'p251_stablecoin_readjudication.json'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
