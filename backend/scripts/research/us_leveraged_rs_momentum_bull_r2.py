#!/usr/bin/env python3
"""
R-2 — 미국 레버리지 ETF 상대강도 모멘텀: 파라미터 안정성 + 포트폴리오 + 워크포워드.

R-1 결과 (9/9 셀 PASS)
    h60/top5  edge +6.84% win 52% bear +0.51% mirror -9.72% t_exc +7.00 ci_low +3.73%
    h80/top5  edge +10.14% win 51% bear -2.54% mirror -12.03% t_exc +7.31 ci_low +6.09%
    대칭 검증(하위 K% = -8~-13%)과 레짐 분리(약세 -1.5~-4.3%)가 함께 성립.

R-1 에서 남은 우려 3가지를 여기서 정면으로 다룬다
------------------------------------------------
1) **승률 50~52%** — 평균 +7%인데 승률이 반반이면 분산이 극단적이다.
   거래당 통계로는 실전 감각을 알 수 없다 → **포트폴리오 시뮬레이션**으로
   자본 곡선·Sharpe·최대낙폭(MDD)을 직접 만든다.
2) **표본 중첩** — 보유 60~80일 × 진입간격 5일 = 12~16 코호트 중첩.
   포트폴리오 시뮬은 중첩을 자본 분할로 자연스럽게 처리한다(코호트당 1/N 배분).
3) **강세장 편향** — 패널이 대체로 강세장. 연도별 + 2022 약세장 분리 성과를 낸다.

추가 검증
    파라미터 그리드 (rs 룩백 × 레짐 MA × 보유 × 상위비율 × 손절)
      → plateau 인지 spike 인지. 인접 셀이 함께 좋아야 진짜다.
    5-fold 시간분할 워크포워드 — in-sample 최적 파라미터를 out-of-sample 평가.
      R-1 의 WF 4/5 에서 실패한 fold 가 어디인지도 식별한다.

출력: backend/runs/research_track/us_leveraged_rs_momentum_bull/r2__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_leveraged_rs_momentum_bull_r2
"""

import json
import logging
import os
import sys
from datetime import datetime
from itertools import product
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("us_lev_rs_r2")

PARADIGM = "us_leveraged_rs_momentum_bull"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM

FEE_RT = 0.0025 * 2 + 0.0000206
BENCH = "SPY"
DOLLAR_VOL_FLOOR = 1_000_000
MIN_HISTORY = 300
LISTING_EXCLUDE_DAYS = 30
STRIDE = 5

# 파라미터 그리드
RS_LOOKBACKS = (10, 20, 40)
REGIME_MAS = (150, 200, 250)
HOLDS = (40, 60, 80)
TOP_FRACS = (0.05, 0.10)
STOP_LOSSES = (None, 0.25)      # 진입가 대비 -25% 손절

N_FOLDS = 5
TRADING_DAYS = 252


def load_panel() -> tuple:
    lev = {s["symbol"] for s in json.loads(
        (BACKEND / "configs" / "us_leveraged_universe.json").read_text(encoding="utf-8")
    )["symbols"]}
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT symbol, timestamp, high, low, close, volume FROM ohlcv "
            "WHERE time_frame = '1d' AND symbol = ANY(:s) ORDER BY symbol, timestamp"
        ), {"s": list(lev) + [BENCH]}).all()
    finally:
        db.close()

    buckets = {}
    for sym, ts, hi, lo, cl, vol in rows:
        buckets.setdefault(sym, []).append(
            (ts, float(hi), float(lo), float(cl), float(vol or 0)))

    close, high, low, dvol, listing = {}, {}, {}, {}, {}
    for sym, recs in buckets.items():
        if len(recs) < MIN_HISTORY:
            continue
        idx = pd.to_datetime([r[0] for r in recs])
        c = pd.Series([r[3] for r in recs], index=idx)
        close[sym] = c
        high[sym] = pd.Series([r[1] for r in recs], index=idx)
        low[sym] = pd.Series([r[2] for r in recs], index=idx)
        dvol[sym] = (c * pd.Series([r[4] for r in recs], index=idx)).rolling(
            20, min_periods=10).mean()
        listing[sym] = idx[0]

    C = pd.DataFrame(close).sort_index()
    return (C, pd.DataFrame(high).sort_index().reindex(columns=C.columns),
            pd.DataFrame(low).sort_index().reindex(columns=C.columns),
            pd.DataFrame(dvol).sort_index().reindex(columns=C.columns),
            listing, lev)


def build_signal(close, high, bench, rs_lb) -> pd.DataFrame:
    b = bench.pct_change(rs_lb).reindex(close.index).ffill()
    rs = close.pct_change(rs_lb).sub(b, axis=0)
    near = close / high.rolling(252, min_periods=120).max()
    return (rs.rank(axis=1, pct=True) + near.rank(axis=1, pct=True)) / 2.0


def simulate(close, low, sig, eligible, regime, hold, frac, stop_loss):
    """중첩 코호트 포트폴리오 시뮬레이션.

    진입간격 STRIDE 로 코호트를 열고 각 코호트에 자본 1/n_cohorts 를 배분한다.
    현금 구간(약세 레짐이라 진입 안 한 코호트)은 수익률 0.
    반환: (일별 포트폴리오 수익률 Series, 거래 리스트)
    """
    idx = close.index
    n_cohorts = max(hold // STRIDE, 1)
    weight = 1.0 / n_cohorts

    daily = pd.Series(0.0, index=idx)
    trades = []

    for d in idx[MIN_HISTORY::STRIDE]:
        i = idx.get_loc(d)
        if i + hold >= len(idx):
            break
        if not bool(regime.get(d, False)):
            continue
        row = sig.loc[d]
        row = row[eligible.loc[d] & row.notna()]
        if len(row) < 20:
            continue
        k = max(int(len(row) * frac), 3)
        picks = row.nlargest(k).index

        entry_px = close.loc[d, picks]
        window = close.iloc[i + 1:i + hold + 1][picks]
        low_win = low.iloc[i + 1:i + hold + 1][picks]

        # 종목별 경로 수익률 (손절 반영)
        path = window.div(entry_px, axis=1) - 1.0
        if stop_loss is not None:
            low_path = low_win.div(entry_px, axis=1) - 1.0
            hit = low_path <= -stop_loss
            for sym in path.columns:
                h = hit[sym]
                if h.any():
                    j = h.idxmax()
                    path.loc[path.index > j, sym] = -stop_loss
                    path.loc[j, sym] = -stop_loss

        # 코호트 일별 수익률 = 픽 평균 경로의 일간 증분
        cohort_curve = (1.0 + path.mean(axis=1))
        cohort_daily = cohort_curve.pct_change()
        cohort_daily.iloc[0] = cohort_curve.iloc[0] - 1.0
        # 진입/청산 수수료를 첫날·마지막날에 배분
        cohort_daily.iloc[0] -= FEE_RT / 2
        cohort_daily.iloc[-1] -= FEE_RT / 2
        daily.loc[cohort_daily.index] += cohort_daily * weight

        final = float(path.mean(axis=1).iloc[-1]) - FEE_RT
        trades.append({"entry_ts": d, "n_picks": int(len(picks)), "net_ret": final,
                       "year": d.year,
                       "quarter": pd.Period(d, freq="Q").strftime("%Y-Q%q")})

    return daily, pd.DataFrame(trades)


def portfolio_stats(daily: pd.Series) -> dict:
    d = daily[daily.index >= daily.index[MIN_HISTORY]] if len(daily) > MIN_HISTORY else daily
    d = d.fillna(0.0)
    if d.std(ddof=1) == 0 or len(d) < 100:
        return {"insufficient": True}
    curve = (1.0 + d).cumprod()
    years = len(d) / TRADING_DAYS
    cagr = float(curve.iloc[-1]) ** (1 / years) - 1.0 if years > 0 else 0.0
    sharpe = float(d.mean() / d.std(ddof=1) * np.sqrt(TRADING_DAYS))
    running_max = curve.cummax()
    mdd = float((curve / running_max - 1.0).min())
    return {
        "years": round(years, 2),
        "total_return_pct": round((float(curve.iloc[-1]) - 1.0) * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "calmar": round(cagr / abs(mdd), 2) if mdd < 0 else None,
        "exposure_days": int((d != 0).sum()),
    }


def year_breakdown(daily: pd.Series) -> dict:
    out = {}
    for y, g in daily.groupby(daily.index.year):
        g = g.fillna(0.0)
        if len(g) < 30:
            continue
        out[str(y)] = round((float((1 + g).prod()) - 1.0) * 100, 2)
    return out


def walk_forward(close, low, sig_cache, eligible, regimes, grid) -> dict:
    """5-fold 시간분할: in-sample 최적 파라미터 → out-of-sample 평가."""
    idx = close.index[MIN_HISTORY:]
    bounds = np.array_split(np.arange(len(idx)), N_FOLDS)
    folds = []
    for f in range(1, N_FOLDS):
        tr_end = idx[bounds[f - 1][-1]]
        te_start, te_end = idx[bounds[f][0]], idx[bounds[f][-1]]

        best, best_sharpe = None, -1e9
        for params in grid:
            rs_lb, ma, hold, frac, sl = params
            daily, _ = simulate(close, low, sig_cache[rs_lb], eligible,
                                regimes[ma], hold, frac, sl)
            d = daily[daily.index <= tr_end].fillna(0.0)
            if len(d) < 100 or d.std(ddof=1) == 0:
                continue
            s = float(d.mean() / d.std(ddof=1) * np.sqrt(TRADING_DAYS))
            if s > best_sharpe:
                best_sharpe, best = s, params

        if best is None:
            continue
        rs_lb, ma, hold, frac, sl = best
        daily, _ = simulate(close, low, sig_cache[rs_lb], eligible,
                            regimes[ma], hold, frac, sl)
        oos = daily[(daily.index >= te_start) & (daily.index <= te_end)].fillna(0.0)
        oos_ret = float((1 + oos).prod() - 1.0)
        oos_sharpe = (float(oos.mean() / oos.std(ddof=1) * np.sqrt(TRADING_DAYS))
                      if oos.std(ddof=1) > 0 else 0.0)
        folds.append({
            "fold": f, "train_end": str(tr_end.date()),
            "test": f"{te_start.date()}~{te_end.date()}",
            "best_params": {"rs_lb": rs_lb, "regime_ma": ma, "hold": hold,
                            "top_frac": frac, "stop_loss": sl},
            "is_sharpe": round(best_sharpe, 2),
            "oos_return_pct": round(oos_ret * 100, 2),
            "oos_sharpe": round(oos_sharpe, 2),
            "pass": bool(oos_ret > 0),
        })
    return {"folds": folds, "n_pass": sum(1 for f in folds if f["pass"]),
            "n_folds": len(folds)}


def main() -> int:
    close, high, low, dvol, listing, lev = load_panel()
    if BENCH not in close.columns:
        logger.error("벤치마크 없음")
        return 1
    bench = close[BENCH]
    syms = [s for s in close.columns if s != BENCH and s in lev]
    close, high, low, dvol = close[syms], high[syms], low[syms], dvol[syms]
    logger.info("레버리지 패널 %d종 × %d일 (%s ~ %s)", len(syms), close.shape[0],
                close.index[0].date(), close.index[-1].date())

    eligible = dvol >= DOLLAR_VOL_FLOOR
    for s in syms:
        eligible.loc[eligible.index < listing[s] + pd.Timedelta(days=LISTING_EXCLUDE_DAYS), s] = False

    regimes = {ma: (bench > bench.rolling(ma, min_periods=int(ma * 0.75)).mean())
               for ma in REGIME_MAS}
    sig_cache = {lb: build_signal(close, high, bench, lb) for lb in RS_LOOKBACKS}

    grid = list(product(RS_LOOKBACKS, REGIME_MAS, HOLDS, TOP_FRACS, STOP_LOSSES))
    logger.info("파라미터 그리드 %d셀", len(grid))

    result = {
        "paradigm": PARADIGM, "phase": "R-2",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {"fee_round_trip": FEE_RT, "stride": STRIDE,
                   "dollar_vol_floor": DOLLAR_VOL_FLOOR,
                   "grid": {"rs_lookbacks": list(RS_LOOKBACKS),
                            "regime_mas": list(REGIME_MAS), "holds": list(HOLDS),
                            "top_fracs": list(TOP_FRACS),
                            "stop_losses": [s for s in STOP_LOSSES]}},
        "panel": {"n_symbols": len(syms), "n_days": int(close.shape[0]),
                  "start": str(close.index[0].date()), "end": str(close.index[-1].date())},
        "cells": [],
    }

    logger.info("=== 파라미터 그리드 (Sharpe 순 상위 표시)")
    for params in grid:
        rs_lb, ma, hold, frac, sl = params
        daily, trades = simulate(close, low, sig_cache[rs_lb], eligible,
                                 regimes[ma], hold, frac, sl)
        stats = portfolio_stats(daily)
        if stats.get("insufficient"):
            continue
        cell = {"rs_lb": rs_lb, "regime_ma": ma, "hold": hold, "top_frac": frac,
                "stop_loss": sl, "n_trades": int(len(trades)), **stats,
                "edge_pct": round(float(trades["net_ret"].mean()) * 100, 3) if len(trades) else None,
                "years_detail": year_breakdown(daily)}
        result["cells"].append(cell)

    result["cells"].sort(key=lambda c: -(c.get("sharpe") or -99))
    for c in result["cells"][:10]:
        logger.info("  rs%2d ma%3d h%2d top%3.0f%% sl=%-5s → CAGR %+7.2f%% Sharpe %5.2f "
                    "MDD %7.2f%% Calmar %s edge %+6.2f%%",
                    c["rs_lb"], c["regime_ma"], c["hold"], c["top_frac"] * 100,
                    str(c["stop_loss"]), c["cagr_pct"], c["sharpe"],
                    c["max_drawdown_pct"], c["calmar"], c["edge_pct"])

    # plateau 판정: 상위 셀 주변 인접 파라미터가 함께 좋은가
    top = result["cells"][0]
    neigh = [c for c in result["cells"]
             if abs(c["rs_lb"] - top["rs_lb"]) <= 20 and abs(c["hold"] - top["hold"]) <= 20
             and c["regime_ma"] == top["regime_ma"]]
    plateau_ratio = (sum(1 for c in neigh if c["sharpe"] >= top["sharpe"] * 0.6)
                     / max(len(neigh), 1))
    result["plateau"] = {"n_neighbors": len(neigh),
                         "ratio_within_60pct_of_best": round(plateau_ratio, 3),
                         "is_plateau": bool(plateau_ratio >= 0.6)}
    logger.info("plateau: 인접 %d셀 중 최고 대비 60%% 이상 %.0f%% → %s",
                len(neigh), plateau_ratio * 100,
                "PLATEAU" if result["plateau"]["is_plateau"] else "SPIKE")

    logger.info("=== 워크포워드 (5-fold)")
    wf = walk_forward(close, low, sig_cache, eligible, regimes, grid)
    result["walk_forward"] = wf
    for f in wf["folds"]:
        logger.info("  fold%d test %s  params rs%d/ma%d/h%d/top%.0f%%/sl%s  "
                    "IS_sharpe %.2f → OOS %+7.2f%% (sharpe %.2f) %s",
                    f["fold"], f["test"], f["best_params"]["rs_lb"],
                    f["best_params"]["regime_ma"], f["best_params"]["hold"],
                    f["best_params"]["top_frac"] * 100, f["best_params"]["stop_loss"],
                    f["is_sharpe"], f["oos_return_pct"], f["oos_sharpe"],
                    "PASS" if f["pass"] else "FAIL")

    logger.info("=== 최상위 셀 연도별 성과")
    for y, v in sorted(top["years_detail"].items()):
        logger.info("  %s: %+8.2f%%", y, v)

    # R-2 게이트 (T-type: 지속형 전략)
    gate = {
        "sharpe_ge_1.5": bool(top["sharpe"] >= 1.5),
        "cagr_positive": bool(top["cagr_pct"] > 0),
        "plateau": result["plateau"]["is_plateau"],
        "wf_pass_ge_3": bool(wf["n_pass"] >= 3),
        "edge_ge_2pct": bool((top.get("edge_pct") or 0) >= 2.0),
    }
    result["gate"] = gate
    result["summary"] = {
        "n_cells": len(result["cells"]),
        "best": {k: top[k] for k in ("rs_lb", "regime_ma", "hold", "top_frac",
                                     "stop_loss", "cagr_pct", "sharpe",
                                     "max_drawdown_pct", "calmar", "edge_pct")},
        "gate": gate,
        "verdict": "R-2 PASS" if all(gate.values()) else "R-2 FAIL",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r2__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    logger.info("게이트: %s", json.dumps(gate, ensure_ascii=False))
    logger.info("판정: %s", result["summary"]["verdict"])
    print(json.dumps(result["summary"], ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
