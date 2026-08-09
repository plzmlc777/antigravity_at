#!/usr/bin/env python3
"""paradigm 251 전체 이력 검증 — CoinGecko 365일 제약을 DefiLlama 로 걷어낸다.

배경:
  2026-08-09 재판정에서 paradigm 251(스테이블코인 순공급 z)이 3군 게이트를
  통과했다(n=117, wt_t 2.574, decay 0.481). 그러나 신호 substrate 가
  CoinGecko 무료 티어의 **365일 캡**에 묶여 유효 표본이 299일이었고,
  DB 가격 가용 기간(950일) 대비 31% — Lesson #30 경계선이라 advisory 였다.

  DefiLlama stablecoins API 는 무료·공개이며 USDT 2017-11-29~, USDC 2018-09-11~
  전체 이력을 준다. 가격(1m 유도 일봉)이 2024-01-02 부터이므로 신호 창이
  299일 → 약 880일로 3배 확장된다.

핵심은 기간 확장 자체가 아니라 **out-of-window 검증**이다:
  CoinGecko 창은 2025-08-09~2026-08-08 이었다. 그 이전(2024-01~2025-08)은
  이 패러다임을 한 번도 검증해 본 적 없는 구간이다. 거기서도 엣지가 살아
  있으면 통과작이고, 창 안에서만 살아 있으면 창에 맞춰진 것이다.

시나리오
  CG365_control      CoinGecko 신호 + DB 전체 가격  … 어제 판정 재현 (대조)
  DL_full            DefiLlama 신호 + DB 전체 가격  … 전체 이력 판정
  DL_out_of_window   DL_full 중 청산 < 2025-08-09   … 창 밖 구간만 (진짜 검증)
  DL_in_window       DL_full 중 청산 >= 2025-08-09  … 창 안 구간만 (대조)

기준은 손대지 않는다 — tier3_gate.evaluate_g1/g2 를 그대로 호출한다.

사용:
  cd backend && source venv/bin/activate
  python3 scripts/research/p251_defillama_full_history_verify.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research.tier3_gate import (  # noqa: E402
    ExecContext, Trade, evaluate_g1, evaluate_g2,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p251_defillama")

P251_DIR = ROOT / "runs" / "research_track" / "paradigm_251_stablecoin_supply_flow"
OUT = ROOT / "runs" / "research_track" / "readjudication_2026_08_09"
OUT.mkdir(parents=True, exist_ok=True)
DL_CACHE = OUT / "defillama_stablecoin_supply_full.json"

# 원 스펙 그대로 — 하나도 바꾸지 않는다.
FEE_RT = 0.0008
Z_THRESH = 1.0
ROLL_WIN = 60
NET_DAYS = 7
HOLDS = [1, 2, 3]
UNIVERSE = ["SOLUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "XRPUSDT", "BNBUSDT"]
ROUNDTRIP_FRICTION = 0.0008
CYCLE_MINUTES = 1440.0

# CoinGecko 무료 티어가 보여준 창 — 이 이전이 out-of-window 다.
CG_WINDOW_START = date(2025, 8, 9)

DL_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
DL_IDS = {"usdt": 1, "usdc": 2}


# ── DefiLlama 전체 이력 ──────────────────────────────────────────────
def fetch_defillama() -> dict:
    if DL_CACHE.exists():
        log.info(f"DefiLlama 캐시 사용: {DL_CACHE}")
        return json.loads(DL_CACHE.read_text())
    out = {}
    for name, sid in DL_IDS.items():
        r = requests.get(DL_URL, params={"stablecoin": sid}, timeout=60,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        rows = r.json()
        series = []
        for row in rows:
            circ = row.get("totalCirculating") or {}
            val = circ.get("peggedUSD")
            if val is None:
                continue
            d = datetime.fromtimestamp(int(row["date"]), tz=timezone.utc).date()
            series.append({"date": d.isoformat(), "supply": float(val)})
        out[name] = series
        log.info(f"  {name.upper()}: {len(series)}일 {series[0]['date']} ~ {series[-1]['date']}")
    DL_CACHE.write_text(json.dumps(out, indent=1))
    return out


def signal_from_series(usdt: pd.DataFrame, usdc: pd.DataFrame) -> pd.DataFrame:
    """원 스크립트와 동일한 변환: 합산 → 7일 차분 → 60일 롤링 z."""
    df = usdt.merge(usdc, on="date", suffixes=("_usdt", "_usdc"))
    df["combined_supply"] = df["supply_usdt"] + df["supply_usdc"]
    df = df.sort_values("date").reset_index(drop=True)
    df["net_7d"] = df["combined_supply"].diff(NET_DAYS)
    df["z"] = ((df["net_7d"] - df["net_7d"].rolling(ROLL_WIN).mean())
               / df["net_7d"].rolling(ROLL_WIN).std())
    return df[["date", "combined_supply", "net_7d", "z"]].dropna().reset_index(drop=True)


def build_signal_defillama() -> pd.DataFrame:
    raw = fetch_defillama()
    frames = {}
    for k in ("usdt", "usdc"):
        d = pd.DataFrame(raw[k])
        d["date"] = pd.to_datetime(d["date"], utc=True)
        frames[k] = d.groupby("date", as_index=False)["supply"].last()
    return signal_from_series(frames["usdt"], frames["usdc"])


def build_signal_coingecko() -> pd.DataFrame:
    raw = json.loads((P251_DIR / "stablecoin_supply_cache.json").read_text())
    frames = {}
    for k in ("usdt", "usdc"):
        d = pd.DataFrame(raw[k]).rename(columns={"mcap": "supply"})
        d["date"] = pd.to_datetime(d["date"], utc=True)
        frames[k] = d.groupby("date", as_index=False)["supply"].last()
    return signal_from_series(frames["usdt"], frames["usdc"])


# ── 가격 (DB) ────────────────────────────────────────────────────────
def load_daily_db(db, sym: str) -> pd.DataFrame:
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
        "close": df["close"].resample("1D").last(),
    }).dropna()


# ── 백테스트 (원 로직 그대로) ────────────────────────────────────────
def backtest(sym: str, price: pd.DataFrame, signal_df: pd.DataFrame,
             hold: int, entry_lag_days: int = 1) -> tuple[list, int]:
    if price.empty:
        return [], 0
    by_date = {d: (o, c) for d, o, c in zip(price.index.date, price["open"], price["close"])}
    trades, skipped = [], 0
    for _, row in signal_df.iterrows():
        z = row["z"]
        if abs(z) < Z_THRESH:
            continue
        side = "long" if z > 0 else "short"
        entry_d = row["date"].date() + timedelta(days=entry_lag_days)
        exit_d = entry_d + timedelta(days=hold)
        e, x = by_date.get(entry_d), by_date.get(exit_d)
        if e is None or x is None:
            skipped += 1
            continue
        ep, xp = float(e[0]), float(x[1])
        if not np.isfinite(ep) or not np.isfinite(xp) or ep <= 0:
            skipped += 1
            continue
        gross = (xp - ep) / ep if side == "long" else (ep - xp) / ep
        trades.append({"entry_d": entry_d.isoformat(), "exit_d": exit_d.isoformat(),
                       "net_ret": gross - FEE_RT, "side": side, "z": float(z)})
    return trades, skipped


def raw_t(nets: np.ndarray) -> float:
    n = len(nets)
    if n < 2:
        return float("nan")
    sd = float(np.std(nets, ddof=1))
    return float(np.mean(nets) / (sd / np.sqrt(n))) if sd > 0 else float("nan")


def judge(raw: list, raw_delayed: list, hold: int, now: datetime) -> dict:
    gt = [Trade(entry_ts=datetime.fromisoformat(t["entry_d"]),
                exit_ts=datetime.fromisoformat(t["exit_d"]),
                net_ret=t["net_ret"]) for t in raw]
    g1 = evaluate_g1(gt, now=now)
    de = float(np.mean([t["net_ret"] for t in raw_delayed])) if raw_delayed else None
    g2 = evaluate_g2(ExecContext(
        lookahead_clean=True, edge_after_1bar_delay=de,
        roundtrip_friction=ROUNDTRIP_FRICTION,
        hold_minutes=hold * 1440.0, cycle_minutes=CYCLE_MINUTES), g1)
    nets = np.array([t["net_ret"] for t in raw], dtype=float)
    return {"G1": g1, "G2": g2, "passed": bool(g1.get("ok") and g2.get("ok")),
            "raw_t_unweighted": None if np.isnan(raw_t(nets)) else round(raw_t(nets), 3),
            "win_rate": round(float(np.mean(nets > 0)), 4) if len(nets) else None}


def run_cells(prices: dict, signal_df: pd.DataFrame, label: str,
              exit_before: date | None = None, exit_from: date | None = None) -> dict:
    cells = {}
    for sym in UNIVERSE:
        for hold in HOLDS:
            tr, skipped = backtest(sym, prices[sym], signal_df, hold, 1)
            trd, _ = backtest(sym, prices[sym], signal_df, hold, 2)
            if exit_before is not None:
                tr = [t for t in tr if date.fromisoformat(t["exit_d"]) < exit_before]
                trd = [t for t in trd if date.fromisoformat(t["exit_d"]) < exit_before]
            if exit_from is not None:
                tr = [t for t in tr if date.fromisoformat(t["exit_d"]) >= exit_from]
                trd = [t for t in trd if date.fromisoformat(t["exit_d"]) >= exit_from]
            if not tr:
                continue
            last_exit = max(date.fromisoformat(t["exit_d"]) for t in tr)
            anchor = datetime.combine(last_exit, datetime.min.time())
            cells[f"{sym}_h{hold}d"] = {
                "n": len(tr), "skipped_no_price": skipped,
                "first_exit": min(date.fromisoformat(t["exit_d"]) for t in tr).isoformat(),
                "last_exit": last_exit.isoformat(),
                "verdict_now_today": judge(tr, trd, hold, datetime.utcnow()),
                "verdict_now_dataend": judge(tr, trd, hold, anchor),
            }
    n_pass = sum(1 for v in cells.values() if v["verdict_now_dataend"]["passed"])
    log.info(f"[{label}] {len(cells)}셀 | PASS(앵커=구간종료) {n_pass}")
    return cells


def main() -> int:
    sig_dl = build_signal_defillama()
    sig_cg = build_signal_coingecko()
    log.info(f"DefiLlama 신호: {len(sig_dl)}일 {sig_dl['date'].min().date()} ~ {sig_dl['date'].max().date()}")
    log.info(f"CoinGecko 신호: {len(sig_cg)}일 {sig_cg['date'].min().date()} ~ {sig_cg['date'].max().date()}")

    # 출처 정합성 — 겹치는 구간에서 두 substrate 가 같은 신호를 주는가
    m = sig_dl.merge(sig_cg, on="date", suffixes=("_dl", "_cg"))
    parity = {
        "n_overlap_days": int(len(m)),
        "corr_supply_level": round(float(m["combined_supply_dl"].corr(m["combined_supply_cg"])), 6),
        "corr_z": round(float(m["z_dl"].corr(m["z_cg"])), 6),
        "median_rel_err_supply": round(float(((m["combined_supply_dl"] - m["combined_supply_cg"]).abs()
                                              / m["combined_supply_cg"]).median()), 6),
        "trigger_agreement": round(float(np.mean(
            (m["z_dl"].abs() >= Z_THRESH) == (m["z_cg"].abs() >= Z_THRESH))), 4),
        "sign_agreement_on_common_triggers": round(float(np.mean(
            np.sign(m.loc[(m["z_dl"].abs() >= Z_THRESH) & (m["z_cg"].abs() >= Z_THRESH), "z_dl"])
            == np.sign(m.loc[(m["z_dl"].abs() >= Z_THRESH) & (m["z_cg"].abs() >= Z_THRESH), "z_cg"]))), 4),
    }
    log.info("substrate 정합성: " + json.dumps(parity, ensure_ascii=False))

    db = SessionLocal()
    try:
        prices = {}
        for sym in UNIVERSE:
            prices[sym] = load_daily_db(db, sym)
            p = prices[sym]
            log.info(f"  {sym:10s} {len(p)}일 {p.index.min().date()} ~ {p.index.max().date()}")

        scenarios = {
            "CG365_control": run_cells(prices, sig_cg, "CG365_control"),
            "DL_full": run_cells(prices, sig_dl, "DL_full"),
            "DL_out_of_window": run_cells(prices, sig_dl, "DL_out_of_window",
                                          exit_before=CG_WINDOW_START),
            "DL_in_window": run_cells(prices, sig_dl, "DL_in_window",
                                      exit_from=CG_WINDOW_START),
        }

        payload = {
            "generated_at_kst": (datetime.utcnow() + timedelta(hours=9)).isoformat(),
            "paradigm": "alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d",
            "purpose": "CoinGecko 365일 캡을 DefiLlama 전체 이력으로 대체하고 out-of-window 구간에서 재검증",
            "substrate": {
                "defillama": {"days": int(len(sig_dl)),
                              "start": sig_dl["date"].min().date().isoformat(),
                              "end": sig_dl["date"].max().date().isoformat()},
                "coingecko": {"days": int(len(sig_cg)),
                              "start": sig_cg["date"].min().date().isoformat(),
                              "end": sig_cg["date"].max().date().isoformat()},
                "parity": parity,
            },
            "cg_window_start": CG_WINDOW_START.isoformat(),
            "spec": {"fee_rt": FEE_RT, "z_thresh": Z_THRESH, "roll_win": ROLL_WIN,
                     "net_days": NET_DAYS, "holds": HOLDS, "universe": UNIVERSE},
            "scenarios": scenarios,
        }
        (OUT / "p251_defillama_full_history.json").write_text(
            json.dumps(payload, indent=1, ensure_ascii=False, default=str))
        log.info(f"기록 → {OUT / 'p251_defillama_full_history.json'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
