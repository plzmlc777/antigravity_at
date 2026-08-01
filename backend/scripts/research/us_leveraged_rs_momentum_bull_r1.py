#!/usr/bin/env python3
"""
R-1 PoC — 미국 레버리지 ETF 상대강도 모멘텀 (강세 레짐 한정, LONG).

DNA
---
universe  : 미국 레버리지·인버스 ETF (일 거래대금 $1M+, 상장 30일 경과)
feature   : rs_x_high = rank(20일 초과수익 vs SPY) + rank(종가/252일 최고가), 횡단면
regime    : SPY > 200일 이동평균 (진입일 기준)
action    : 상위 K% LONG, 60 거래일 보유, SL/TP 없음
fee       : 왕복 50.2bp (온라인 0.25% 편도 × 2 + SEC Fee)

R-0 근거 (us_axis_sweep, 480셀 스윕)
    leveraged/rs_x_high/bull/h60: top3% +5.82% / top5% +6.26% / top10% +5.85%
    단일축은 미달 — rs_20 단독 +1.04%, near_high 단독 -0.43%. 결합해야 뜬다.
    레짐 필터 없으면 +1.95% → 있으면 +2.53% (동일 셀 top3%).

R-1 이 답해야 하는 것
--------------------
R-0 은 480셀 스윕이라 다중검정 노출이 크다(Lesson #62). 통과 셀이 하나의 구조에
몰려 있다는 점은 신호에 가깝지만, 그 자체로는 증거가 아니다. 여기서 검증한다:

  three-gate    signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p <= 0.10
  Concentration 분기별 t 양수비율 >= 0.5, 종목별 CI 양수비율 >= 0.30, n_syms >= 3
  대칭 검증     하위 K%(모멘텀 최악)가 더 나쁜가 (Lesson #19/#39 mirror)
  레짐 층화     bull / bear 분리 — 필터가 진짜인지, 단순 하락회피인지
  워크포워드    5-fold 시간 분할 (Lesson #26 필수)

측정 단위 주의
    R-0 은 진입일별 픽 평균을 관측치로 썼다(포트폴리오 수익률). elite gate 의
    edge 는 **거래당**이므로 R-1 은 개별 거래를 관측치로 쓴다. 보유 60일 ×
    진입간격 5일 = 12개 코호트가 겹치므로 block bootstrap(block=12)을 적용한다.

출력: backend/runs/research_track/us_leveraged_rs_momentum_bull/r1__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_leveraged_rs_momentum_bull_r1
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
logger = logging.getLogger("us_lev_rs_r1")

PARADIGM = "us_leveraged_rs_momentum_bull"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM

FEE_RT = 0.0025 * 2 + 0.0000206
BENCH = "SPY"
DOLLAR_VOL_FLOOR = 1_000_000
MIN_HISTORY = 300
LISTING_EXCLUDE_DAYS = 30
STRIDE = 5
HOLDS = (40, 60, 80)
TOP_FRACS = (0.03, 0.05, 0.10)

T_EXCESS_MIN = 2.0
PERM_P_MAX = 0.10
EDGE_GATE = 0.02
QUARTER_POS_T_MIN = 0.5
SYM_CI_POS_RATIO_MIN = 0.30
N_SYM_CI_POS_MIN = 3
N_FOLDS = 5


def load_leveraged() -> set:
    p = BACKEND / "configs" / "us_leveraged_universe.json"
    return {s["symbol"] for s in json.loads(p.read_text(encoding="utf-8"))["symbols"]}


def load_panel(symbols: list) -> tuple:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT symbol, timestamp, high, close, volume FROM ohlcv "
            "WHERE time_frame = '1d' AND symbol = ANY(:s) ORDER BY symbol, timestamp"
        ), {"s": symbols}).all()
    finally:
        db.close()
    buckets = {}
    for sym, ts, hi, cl, vol in rows:
        buckets.setdefault(sym, []).append((ts, float(hi), float(cl), float(vol or 0)))

    close, high, dvol, listing = {}, {}, {}, {}
    for sym, recs in buckets.items():
        if len(recs) < MIN_HISTORY:
            continue
        idx = pd.to_datetime([r[0] for r in recs])
        c = pd.Series([r[2] for r in recs], index=idx)
        close[sym] = c
        high[sym] = pd.Series([r[1] for r in recs], index=idx)
        dvol[sym] = (c * pd.Series([r[3] for r in recs], index=idx)).rolling(
            20, min_periods=10).mean()
        listing[sym] = idx[0]
    return (pd.DataFrame(close).sort_index(), pd.DataFrame(high).sort_index(),
            pd.DataFrame(dvol).sort_index(), listing)


def build_signal(close: pd.DataFrame, high: pd.DataFrame, bench: pd.Series) -> pd.DataFrame:
    b20 = bench.pct_change(20).reindex(close.index).ffill()
    rs20 = close.pct_change(20).sub(b20, axis=0)
    near_high = close / high.rolling(252, min_periods=120).max()
    return (rs20.rank(axis=1, pct=True) + near_high.rank(axis=1, pct=True)) / 2.0


def collect_trades(close, sig, eligible, regime, hold, frac, side="top") -> pd.DataFrame:
    """개별 거래 단위 수집. side='bottom' 이면 대칭(mirror) 검증용."""
    recs = []
    idx = close.index
    for d in idx[MIN_HISTORY::STRIDE]:
        i = idx.get_loc(d)
        if i + hold >= len(idx):
            break
        row = sig.loc[d]
        row = row[eligible.loc[d] & row.notna()]
        if len(row) < 20:
            continue
        k = max(int(len(row) * frac), 3)
        picks = row.nsmallest(k).index if side == "bottom" else row.nlargest(k).index
        entry = close.loc[d, picks]
        exit_ = close.iloc[i + hold][picks]
        r = (exit_ / entry - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
        for sym, v in r.items():
            recs.append({"entry_ts": d, "symbol": sym, "net_ret": float(v) - FEE_RT,
                         "bull": bool(regime.get(d, False)),
                         "quarter": pd.Period(d, freq="Q").strftime("%Y-Q%q")})
    return pd.DataFrame(recs)


def candidate_pool(close, eligible, regime, hold, bull_only: bool) -> np.ndarray:
    """같은 진입일·같은 보유창의 **전체 적격 종목** 수익률 (트리거 무관 null)."""
    out = []
    idx = close.index
    for d in idx[MIN_HISTORY::STRIDE]:
        if bull_only and not bool(regime.get(d, False)):
            continue
        i = idx.get_loc(d)
        if i + hold >= len(idx):
            break
        cols = eligible.loc[d]
        cols = cols[cols].index
        if len(cols) < 20:
            continue
        entry = close.loc[d, cols]
        exit_ = close.iloc[i + hold][cols]
        r = (exit_ / entry - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
        out.extend(r.to_numpy())
    return np.array(out)


def concentration(df: pd.DataFrame) -> dict:
    q_t = {}
    for q, g in df.groupby("quarter"):
        a = g["net_ret"].to_numpy()
        if len(a) < 5:
            continue
        sd = a.std(ddof=1)
        q_t[q] = round(float(a.mean() / (sd / np.sqrt(len(a)))), 2) if sd > 0 else 0.0
    ratio = float(np.mean([v > 0 for v in q_t.values()])) if q_t else 0.0

    sym_pos, sym_stats = 0, {}
    for sym, g in df.groupby("symbol"):
        if len(g) < 5:
            continue
        ci = bootstrap_ci(g["net_ret"].to_numpy(), n_boot=800, block_size=12)
        sym_stats[sym] = round(ci["ci_lower"], 4)
        if ci["ci_lower"] > 0:
            sym_pos += 1
    n_sym = len(sym_stats)
    return {
        "n_quarters": len(q_t), "quarter_pos_t_ratio": round(ratio, 3),
        "quarter_t": q_t,
        "n_symbols_evaluated": n_sym, "n_symbols_ci_pos": sym_pos,
        "symbol_ci_pos_ratio": round(sym_pos / n_sym, 3) if n_sym else 0.0,
    }


def walk_forward(df: pd.DataFrame) -> dict:
    df = df.sort_values("entry_ts")
    folds = np.array_split(df, N_FOLDS)
    res, n_pass = [], 0
    for i, f in enumerate(folds):
        a = f["net_ret"].to_numpy()
        if len(a) < 20:
            res.append({"fold": i, "n": int(len(a)), "insufficient": True})
            continue
        sd = a.std(ddof=1)
        t = float(a.mean() / (sd / np.sqrt(len(a)))) if sd > 0 else 0.0
        ok = a.mean() > 0 and t > 0
        n_pass += int(ok)
        res.append({"fold": i, "n": int(len(a)),
                    "start": str(f["entry_ts"].iloc[0].date()),
                    "end": str(f["entry_ts"].iloc[-1].date()),
                    "mean_pct": round(float(a.mean()) * 100, 3),
                    "t": round(t, 2), "pass": bool(ok)})
    return {"folds": res, "n_pass": n_pass, "n_folds": N_FOLDS}


def evaluate(close, sig, eligible, regime, hold, frac) -> dict:
    trades = collect_trades(close, sig, eligible, regime, hold, frac, "top")
    bull = trades[trades["bull"]]
    bear = trades[~trades["bull"]]
    if len(bull) < 50:
        return {"insufficient": True, "n": int(len(bull))}

    obs = bull["net_ret"].to_numpy()
    pool = candidate_pool(close, eligible, regime, hold, bull_only=True)
    perm = fee_aware_perm_test(obs, pool, fee_per_trade=FEE_RT, n_perms=1000)
    ci = bootstrap_ci(obs, n_boot=2000, block_size=12)
    conc = concentration(bull)
    wf = walk_forward(bull)

    mirror = collect_trades(close, sig, eligible, regime, hold, frac, "bottom")
    mirror_bull = mirror[mirror["bull"]]["net_ret"].to_numpy()

    perm_p = perm["perm_p_one_sided_above"]
    three_gate = (perm["signal_t_excess"] >= T_EXCESS_MIN
                  and ci["ci_lower"] > 0 and perm_p <= PERM_P_MAX)
    conc_gate = (conc["quarter_pos_t_ratio"] >= QUARTER_POS_T_MIN
                 and conc["symbol_ci_pos_ratio"] >= SYM_CI_POS_RATIO_MIN
                 and conc["n_symbols_ci_pos"] >= N_SYM_CI_POS_MIN)
    mirror_ok = bool(len(mirror_bull) and mirror_bull.mean() < obs.mean())
    edge_ok = bool(obs.mean() >= EDGE_GATE)
    wf_ok = wf["n_pass"] >= 3

    return {
        "hold": hold, "top_frac": frac,
        "n_trades_bull": int(len(obs)), "n_trades_bear": int(len(bear)),
        "n_pool": int(len(pool)),
        "edge_pct": round(float(obs.mean()) * 100, 3),
        "median_pct": round(float(np.median(obs)) * 100, 3),
        "win_rate": round(float((obs > 0).mean()), 3),
        "bear_edge_pct": round(float(bear["net_ret"].mean()) * 100, 3) if len(bear) else None,
        "mirror_edge_pct": round(float(mirror_bull.mean()) * 100, 3) if len(mirror_bull) else None,
        "obs_t": round(perm["obs_t"], 2),
        "null_mean_t": round(perm["null_mean_t"], 2),
        "signal_t_excess": round(perm["signal_t_excess"], 3),
        "perm_p": round(perm_p, 4),
        "ci_lower_pct": round(ci["ci_lower"] * 100, 3),
        "ci_upper_pct": round(ci["ci_upper"] * 100, 3),
        "concentration": conc, "walk_forward": wf,
        "three_gate_pass": bool(three_gate), "concentration_gate_pass": bool(conc_gate),
        "mirror_pass": mirror_ok, "edge_gate_pass": edge_ok, "wf_pass": bool(wf_ok),
        "verdict": "PASS" if (three_gate and conc_gate and mirror_ok
                              and edge_ok and wf_ok) else "FAIL",
    }


def main() -> int:
    lev = load_leveraged()
    close, high, dvol, listing = load_panel(list(lev) + [BENCH])
    logger.info("패널 %d종 × %d일 (%s ~ %s)", close.shape[1], close.shape[0],
                close.index[0].date(), close.index[-1].date())
    if BENCH not in close.columns:
        logger.error("벤치마크 없음")
        return 1

    bench = close[BENCH]
    regime = (bench > bench.rolling(200, min_periods=150).mean())
    logger.info("강세 레짐 비율 %.1f%%", float(regime.mean()) * 100)

    syms = [s for s in close.columns if s != BENCH and s in lev]
    close, high, dvol = close[syms], high[syms], dvol[syms]

    eligible = dvol >= DOLLAR_VOL_FLOOR
    for s in syms:
        cutoff = listing[s] + pd.Timedelta(days=LISTING_EXCLUDE_DAYS)
        eligible.loc[eligible.index < cutoff, s] = False
    logger.info("레버리지 %d종, 게이트 통과 평균 %.0f종/일",
                len(syms), float(eligible.sum(axis=1).mean()))

    sig = build_signal(close, high, bench)

    result = {
        "paradigm": PARADIGM, "phase": "R-1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "fee_round_trip": FEE_RT, "dollar_vol_floor": DOLLAR_VOL_FLOOR,
            "listing_exclude_days": LISTING_EXCLUDE_DAYS, "stride": STRIDE,
            "holds": list(HOLDS), "top_fracs": list(TOP_FRACS),
            "regime": "SPY > 200MA", "edge_gate": EDGE_GATE,
        },
        "panel": {"n_leveraged": len(syms), "n_days": int(close.shape[0]),
                  "start": str(close.index[0].date()), "end": str(close.index[-1].date()),
                  "bull_share": round(float(regime.mean()), 3)},
        "cells": [],
    }

    for hold in HOLDS:
        for frac in TOP_FRACS:
            cell = evaluate(close, sig, eligible, regime, hold, frac)
            if cell.get("insufficient"):
                continue
            result["cells"].append(cell)
            logger.info(
                "h=%2d top%3.0f%%  n=%4d  edge %+6.2f%%  win %.0f%%  bear %+6.2f%%  "
                "mirror %+6.2f%%  t_exc %+5.2f  p=%.3f  ci_low %+6.2f%%  wf %d/5 → %s",
                hold, frac * 100, cell["n_trades_bull"], cell["edge_pct"],
                cell["win_rate"] * 100, cell["bear_edge_pct"] or 0,
                cell["mirror_edge_pct"] or 0, cell["signal_t_excess"], cell["perm_p"],
                cell["ci_lower_pct"], cell["walk_forward"]["n_pass"], cell["verdict"])

    passes = [c for c in result["cells"] if c["verdict"] == "PASS"]
    result["summary"] = {
        "n_cells": len(result["cells"]), "n_pass": len(passes),
        "passing": [f"h{c['hold']}/top{int(c['top_frac']*100)}" for c in passes],
        "verdict": "R-1 PASS" if passes else "R-1 FAIL",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r1__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    logger.info("판정: %s (%d/%d 셀)", result["summary"]["verdict"],
                len(passes), len(result["cells"]))
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
