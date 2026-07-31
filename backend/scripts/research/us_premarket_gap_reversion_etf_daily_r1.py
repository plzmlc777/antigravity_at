#!/usr/bin/env python3
"""
R-1 PoC — 미국 ETF 프리마켓 갭 반전 (일봉 스윙).

DNA
---
data      : 키움 미국 일봉 (usa06012), 코어 ETF 59종 + 레버리지 29종, 2019-10~2026-07
mechanism : 프리마켓 구간 갭의 과잉 반응 → 정규장 개장 이후 되돌림
frame     : 일봉 (미국 분봉은 7개월뿐이라 장기 검증 불가 — 일봉이 유일한 선택)
side      : 양방향 (갭다운 → LONG, 갭업 → SHORT) — Lesson #20 sign-cond 대칭 검증
horizon   : 3/5/10 영업일 (R-0 판정: core 1일 보유는 수수료 구조상 도달 불가)

왜 이 갭이 특별한가
------------------
키움 미국 일봉의 종가는 정규장 종가가 아니라 오버나이트(Blue Ocean, ET 20:00~
익일 04:00)까지 반영한 그 영업일의 최종가다. 시가는 정규장 시가(09:30 ET)다.
따라서
    gap = open(D) / close(D-1) - 1
은 **ET 04:00 ~ 09:30 프리마켓 구간의 움직임**을 분리해 측정한다. 통상적인
"전일 정규장 종가 → 시가" 갭(애프터+오버나이트+프리마켓 합산)과 구성이 다르다.
한국 야간 세션이 끝난 뒤 미국 현지가 개장 전에 얼마나 되돌리는지를 보는 셈이다.

진입/청산
--------
진입: gap 이 심볼별 롤링 분포의 |z| >= Z_THRESH 를 넘은 날의 **종가**
      (시가 관측 후 종가 진입 — 룩어헤드 없음)
청산: HOLD 영업일 뒤 종가
비용: 왕복 0.502% (온라인 0.25% 편도 × 2 + SEC Fee) — 전량 차감

게이트 (Research Track R-1 three-gate)
    signal_t_excess >= 2.0  AND  ci_lower > 0  AND  perm_p <= 0.10
Concentration gate
    quarter_pos_t_ratio >= 0.5  AND  symbol_ci_pos_ratio >= 0.30  AND  n_symbols_ci_pos >= 3

출력: backend/runs/research_track/us_premarket_gap_reversion_etf_daily/r1__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_premarket_gap_reversion_etf_daily_r1
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND.parent / ".env")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("us_gap_r1")

PARADIGM = "us_premarket_gap_reversion_etf_daily"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM
UNIVERSE_PATH = BACKEND / "configs" / "us_universe.json"

FEE_ROUND_TRIP = 0.0025 * 2 + 0.0000206
Z_LOOKBACK = 60
Z_THRESH = 2.0
HOLDS = (3, 5, 10)
MIN_BARS = 500

# R-1 게이트
T_EXCESS_MIN = 2.0
PERM_P_MAX = 0.10
# Concentration 게이트
QUARTER_POS_T_RATIO_MIN = 0.5
SYMBOL_CI_POS_RATIO_MIN = 0.30
N_SYMBOLS_CI_POS_MIN = 3


def load_panel(symbols: list) -> dict:
    db = SessionLocal()
    out = {}
    try:
        for sym in symbols:
            rows = db.execute(text(
                "SELECT timestamp, open, close FROM ohlcv "
                "WHERE symbol = :s AND time_frame = '1d' ORDER BY timestamp"
            ), {"s": sym}).all()
            if len(rows) < MIN_BARS:
                continue
            df = pd.DataFrame(rows, columns=["timestamp", "open", "close"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").astype(float)
            out[sym] = df
    finally:
        db.close()
    return out


def build_trades(panel: dict, hold: int, direction: str) -> tuple:
    """(observed_net_returns, candidate_pool_gross, trade_records)

    direction='long'  : 갭다운(z <= -Z) 후 LONG
    direction='short' : 갭업  (z >= +Z) 후 SHORT
    """
    observed, pool, records = [], [], []

    for sym, df in panel.items():
        close, open_ = df["close"], df["open"]
        gap = (open_ / close.shift(1) - 1.0)

        mean = gap.rolling(Z_LOOKBACK, min_periods=Z_LOOKBACK // 2).mean()
        std = gap.rolling(Z_LOOKBACK, min_periods=Z_LOOKBACK // 2).std(ddof=0)
        z = (gap - mean) / std.replace(0.0, np.nan)

        fwd = (close.shift(-hold) / close - 1.0)   # 종가 진입 → hold 뒤 종가 청산

        valid = fwd.notna() & z.notna()
        # 후보 풀: 같은 hold 창의 모든 가능한 수익률 (트리거 무관)
        pool.extend((fwd[valid] if direction == "long" else -fwd[valid]).to_numpy())

        trig = valid & ((z <= -Z_THRESH) if direction == "long" else (z >= Z_THRESH))
        if not trig.any():
            continue

        raw = fwd[trig] if direction == "long" else -fwd[trig]
        net = raw - FEE_ROUND_TRIP
        observed.extend(net.to_numpy())
        for ts, r in net.items():
            records.append({"symbol": sym, "entry_ts": ts, "net_ret": float(r)})

    return np.array(observed), np.array(pool), records


def concentration(records: list) -> dict:
    """분기별 t + 심볼별 부트스트랩 CI (Lesson #16)."""
    if not records:
        return {}
    df = pd.DataFrame(records)
    df["quarter"] = pd.PeriodIndex(df["entry_ts"], freq="Q").astype(str)

    q_stats = {}
    for q, g in df.groupby("quarter"):
        if len(g) < 5:
            continue
        a = g["net_ret"].to_numpy()
        sd = a.std(ddof=1)
        q_stats[q] = float(a.mean() / (sd / np.sqrt(len(a)))) if sd > 0 else 0.0
    quarter_pos_t_ratio = (
        float(np.mean([t > 0 for t in q_stats.values()])) if q_stats else 0.0)

    sym_ci_pos, sym_stats = 0, {}
    for sym, g in df.groupby("symbol"):
        if len(g) < 5:
            continue
        ci = bootstrap_ci(g["net_ret"].to_numpy(), n_boot=1000)
        sym_stats[sym] = {"n": int(len(g)), "mean": float(g["net_ret"].mean()),
                          "ci_lower": ci["ci_lower"]}
        if ci["ci_lower"] > 0:
            sym_ci_pos += 1

    n_sym = len(sym_stats)
    return {
        "n_quarters": len(q_stats),
        "quarter_pos_t_ratio": round(quarter_pos_t_ratio, 3),
        "n_symbols_evaluated": n_sym,
        "n_symbols_ci_pos": sym_ci_pos,
        "symbol_ci_pos_ratio": round(sym_ci_pos / n_sym, 3) if n_sym else 0.0,
        "quarter_t": {k: round(v, 2) for k, v in sorted(q_stats.items())},
        "top_symbols": dict(sorted(
            ((k, {kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()})
             for k, v in sym_stats.items()),
            key=lambda kv: -kv[1]["mean"])[:8]),
    }


def evaluate(panel: dict, group: str, hold: int, direction: str) -> dict:
    obs, pool, records = build_trades(panel, hold, direction)
    if len(obs) < 30:
        return {"group": group, "hold": hold, "direction": direction,
                "n_trades": int(len(obs)), "verdict": "INSUFFICIENT_SAMPLE"}

    perm = fee_aware_perm_test(obs, pool, fee_per_trade=FEE_ROUND_TRIP, n_perms=1000)
    ci = bootstrap_ci(obs, n_boot=2000, block_size=max(hold, 1))
    conc = concentration(records)

    perm_p = perm["perm_p_one_sided_above"]
    three_gate = (
        perm["signal_t_excess"] >= T_EXCESS_MIN
        and ci["ci_lower"] > 0
        and perm_p <= PERM_P_MAX
    )
    conc_gate = (
        conc.get("quarter_pos_t_ratio", 0) >= QUARTER_POS_T_RATIO_MIN
        and conc.get("symbol_ci_pos_ratio", 0) >= SYMBOL_CI_POS_RATIO_MIN
        and conc.get("n_symbols_ci_pos", 0) >= N_SYMBOLS_CI_POS_MIN
    )

    return {
        "group": group, "hold": hold, "direction": direction,
        "n_trades": int(len(obs)), "n_pool": int(len(pool)),
        "net_mean_bp": round(float(obs.mean()) * 10000, 2),
        "win_rate": round(float((obs > 0).mean()), 4),
        "obs_t": round(perm["obs_t"], 3),
        "null_mean_t": round(perm["null_mean_t"], 3),
        "signal_t_excess": round(perm["signal_t_excess"], 3),
        "perm_p_one_sided_above": round(perm_p, 4),
        "ci_lower_bp": round(ci["ci_lower"] * 10000, 2),
        "ci_upper_bp": round(ci["ci_upper"] * 10000, 2),
        "concentration": conc,
        "three_gate_pass": bool(three_gate),
        "concentration_gate_pass": bool(conc_gate),
        "verdict": "PASS" if (three_gate and conc_gate) else "FAIL",
    }


def main() -> int:
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    groups = {
        "core": [r["symbol"] for r in universe["core"]],
        "leveraged": [r["symbol"] for r in universe["leveraged"]],
    }

    result = {
        "paradigm": PARADIGM, "phase": "R-1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP, "z_lookback": Z_LOOKBACK,
            "z_thresh": Z_THRESH, "holds": list(HOLDS), "min_bars": MIN_BARS,
        },
        "cells": [],
    }

    for gname, syms in groups.items():
        panel = load_panel(syms)
        logger.info("[%s] %d 종목 로드", gname, len(panel))
        for hold in HOLDS:
            for direction in ("long", "short"):
                cell = evaluate(panel, gname, hold, direction)
                result["cells"].append(cell)
                logger.info(
                    "  %-9s hold=%2d %-5s n=%4d net=%+7.1fbp t_exc=%6s p=%6s "
                    "ci_low=%+8s → %s",
                    gname, hold, direction, cell.get("n_trades", 0),
                    cell.get("net_mean_bp", 0), cell.get("signal_t_excess", "—"),
                    cell.get("perm_p_one_sided_above", "—"),
                    cell.get("ci_lower_bp", "—"), cell["verdict"],
                )

    passes = [c for c in result["cells"] if c["verdict"] == "PASS"]
    result["summary"] = {
        "n_cells": len(result["cells"]),
        "n_pass": len(passes),
        "passing_cells": [f"{c['group']}/{c['hold']}d/{c['direction']}" for c in passes],
        # Lesson #37: 셀 하나만 보지 말고 전체 sweep 판정을 스캔할 것
        "verdict": "R-1 PASS" if passes else "R-1 FAIL",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r1__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    logger.info("판정: %s (%d/%d 셀 PASS)", result["summary"]["verdict"],
                len(passes), len(result["cells"]))
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
