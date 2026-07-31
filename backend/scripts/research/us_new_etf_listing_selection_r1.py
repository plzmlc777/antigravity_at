#!/usr/bin/env python3
"""
R-1 PoC — 미국 신규 상장 ETF 선별 매수 (일봉 스윙, LONG only).

R-0 결과 (us_new_etf_listing_cohort)
------------------------------------
비레버리지 신규 ETF 1,305종, 상장 후 수익률이 보유기간에 따라 단조 증가.
d1_h60 평균 +0.88%(t=+2.74, 승률 58%) — 무차별 매수로는 elite gate(+2%/trade)
근처도 못 간다. 그러나 표준편차 11.36%로 분포가 넓고 **상위 50% 선별 시 평균
+7.56%**. 즉 "먹을 게 있느냐"는 확인됐고, 남은 질문은 "사전에 고를 수 있느냐"다.

이 R-1이 답하는 것
-----------------
상장 시점에 관측 가능한 정보만으로 상위 코호트를 가려낼 수 있는가.

진입 규약 (룩어헤드 차단)
    D0 = 상장 첫 거래일. 피처는 D1~D10 구간에서만 계산.
    진입 = D10 종가, 청산 = D10+HOLD 종가. (R-0 d10_h60 셀에 대응)
    → 피처 관측 구간과 진입 시점이 겹치지 않는다.

선별 축 (4종, 전부 사전 관측 가능)
    vol_growth  : 거래량 D6-10 평균 / D1-5 평균 — 자금유입 모멘텀 가설의 직접 검증
    init_dd     : D1~D10 최저가 / D1 종가 - 1 — 초기 낙폭 (평균회귀 축)
    init_ret    : D10 종가 / D1 종가 - 1 — 초기 추세
    rs_vs_spy   : init_ret - 같은 구간 SPY 수익률 — 테마 상대강도
    (issuer 는 층화 확인용으로만 집계)

현실성 게이트
    평균 일 거래대금(D1-10)이 임계 미만인 종목은 애초에 못 산다. 필터별로
    코호트가 얼마나 줄고 엣지가 어떻게 변하는지 함께 보고한다.

게이트
    three-gate     : signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p <= 0.10
    Concentration  : 상장 분기별 t 양수 비율 >= 0.5 AND 발행사 편중 확인
    (종목별 CI 는 이벤트가 종목당 1건이라 적용 불가 → 분기·발행사 축으로 대체)

출력: backend/runs/research_track/us_new_etf_listing_selection/r1__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_new_etf_listing_selection_r1
"""

import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
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
logger = logging.getLogger("us_new_etf_r1")

PARADIGM = "us_new_etf_listing_selection"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM
COHORT_PATH = BACKEND / "configs" / "us_new_etf_cohort.json"

FEE_ROUND_TRIP = 0.0025 * 2 + 0.0000206
FEATURE_END = 10          # D10 까지 관측 → D10 종가 진입
HOLDS = (30, 60)
MIN_BARS = FEATURE_END + max(HOLDS) + 2
DOLLAR_VOL_FLOORS = (0, 100_000, 1_000_000)
TOP_FRACTIONS = (0.5, 0.3)

T_EXCESS_MIN = 2.0
PERM_P_MAX = 0.10
QUARTER_POS_T_RATIO_MIN = 0.5

_TOKEN = re.compile(r"[A-Z]+")


def issuer_of(name_en: str) -> str:
    toks = _TOKEN.findall((name_en or "").upper())
    return toks[0] if toks else "UNKNOWN"


def load_panel() -> tuple:
    cohort = {s["symbol"]: s for s in
              json.loads(COHORT_PATH.read_text(encoding="utf-8"))["symbols"]}
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT symbol, timestamp, close, volume FROM ohlcv "
            "WHERE time_frame = '1d' AND symbol = ANY(:s) ORDER BY symbol, timestamp"
        ), {"s": list(cohort) + ["SPY"]}).all()
    finally:
        db.close()

    buckets = defaultdict(list)
    for sym, ts, close, vol in rows:
        buckets[sym].append((ts, float(close), float(vol or 0)))

    spy = None
    if "SPY" in buckets:
        spy = pd.Series([p[1] for p in buckets["SPY"]],
                        index=pd.to_datetime([p[0] for p in buckets["SPY"]]))

    panel = {}
    for sym, pairs in buckets.items():
        if sym == "SPY" or len(pairs) < MIN_BARS:
            continue
        panel[sym] = pd.DataFrame(
            {"close": [p[1] for p in pairs], "volume": [p[2] for p in pairs]},
            index=pd.to_datetime([p[0] for p in pairs]))
    return cohort, panel, spy


def build_events(cohort: dict, panel: dict, spy: pd.Series) -> pd.DataFrame:
    recs = []
    for sym, df in panel.items():
        close, vol = df["close"], df["volume"]
        idx = df.index

        c1 = float(close.iloc[1])
        c10 = float(close.iloc[FEATURE_END])
        if c1 <= 0 or c10 <= 0:
            continue

        v_early = float(vol.iloc[1:6].mean())
        v_late = float(vol.iloc[6:FEATURE_END + 1].mean())
        vol_growth = (v_late / v_early) if v_early > 0 else np.nan
        dollar_vol = float((close.iloc[1:FEATURE_END + 1]
                            * vol.iloc[1:FEATURE_END + 1]).mean())

        init_ret = c10 / c1 - 1.0
        init_dd = float(close.iloc[1:FEATURE_END + 1].min()) / c1 - 1.0

        rs = np.nan
        if spy is not None:
            try:
                s0 = float(spy.asof(idx[1]))
                s1 = float(spy.asof(idx[FEATURE_END]))
                if s0 > 0:
                    rs = init_ret - (s1 / s0 - 1.0)
            except Exception:
                pass

        rec = {
            "symbol": sym,
            "listing_date": idx[0],
            "quarter": pd.Period(idx[0], freq="Q").strftime("%Y-Q%q"),
            "issuer": issuer_of(cohort[sym].get("name_en")),
            "vol_growth": vol_growth,
            "init_ret": init_ret,
            "init_dd": init_dd,
            "rs_vs_spy": rs,
            "dollar_vol": dollar_vol,
        }
        for hold in HOLDS:
            if len(close) > FEATURE_END + hold:
                rec[f"fwd_{hold}"] = (float(close.iloc[FEATURE_END + hold]) / c10
                                      - 1.0 - FEE_ROUND_TRIP)
            else:
                rec[f"fwd_{hold}"] = np.nan
        recs.append(rec)
    return pd.DataFrame(recs)


def quantile_profile(df: pd.DataFrame, feature: str, target: str, q: int = 5) -> list:
    sub = df[[feature, target]].dropna()
    if len(sub) < q * 20:
        return []
    try:
        sub = sub.assign(bucket=pd.qcut(sub[feature], q, labels=False, duplicates="drop"))
    except ValueError:
        return []
    out = []
    for b, g in sub.groupby("bucket"):
        a = g[target].to_numpy()
        sd = a.std(ddof=1)
        out.append({
            "bucket": int(b), "n": int(len(a)),
            "mean_pct": round(float(a.mean()) * 100, 3),
            "win_rate": round(float((a > 0).mean()), 3),
            "t": round(float(a.mean() / (sd / np.sqrt(len(a)))), 2) if sd > 0 else 0.0,
        })
    return out


def concentration(sel: pd.DataFrame, target: str) -> dict:
    q_t = {}
    for q, g in sel.groupby("quarter"):
        a = g[target].dropna().to_numpy()
        if len(a) < 5:
            continue
        sd = a.std(ddof=1)
        q_t[q] = round(float(a.mean() / (sd / np.sqrt(len(a)))), 2) if sd > 0 else 0.0
    ratio = float(np.mean([v > 0 for v in q_t.values()])) if q_t else 0.0
    top_issuers = Counter(sel["issuer"]).most_common(5)
    return {
        "n_quarters": len(q_t),
        "quarter_t": q_t,
        "quarter_pos_t_ratio": round(ratio, 3),
        "top_issuers": [{"issuer": i, "n": n,
                         "share": round(n / max(len(sel), 1), 3)} for i, n in top_issuers],
        "max_issuer_share": round(top_issuers[0][1] / max(len(sel), 1), 3) if top_issuers else 0.0,
    }


def evaluate_selection(df: pd.DataFrame, feature: str, ascending: bool,
                       frac: float, hold: int, floor: float) -> dict:
    target = f"fwd_{hold}"
    pool_df = df[df["dollar_vol"] >= floor].dropna(subset=[target, feature])
    if len(pool_df) < 60:
        return {"verdict": "INSUFFICIENT_POOL", "n_pool": int(len(pool_df))}

    k = max(int(len(pool_df) * frac), 20)
    sel = pool_df.nsmallest(k, feature) if ascending else pool_df.nlargest(k, feature)

    obs = sel[target].to_numpy()
    pool = pool_df[target].to_numpy()

    perm = fee_aware_perm_test(obs, pool, fee_per_trade=0.0, n_perms=1000)
    ci = bootstrap_ci(obs, n_boot=2000, block_size=1)
    conc = concentration(sel, target)

    perm_p = perm["perm_p_one_sided_above"]
    three_gate = (perm["signal_t_excess"] >= T_EXCESS_MIN
                  and ci["ci_lower"] > 0 and perm_p <= PERM_P_MAX)
    conc_gate = conc["quarter_pos_t_ratio"] >= QUARTER_POS_T_RATIO_MIN

    return {
        "feature": feature, "direction": "low" if ascending else "high",
        "frac": frac, "hold": hold, "dollar_vol_floor": floor,
        "n_pool": int(len(pool_df)), "n_selected": int(len(obs)),
        "sel_mean_pct": round(float(obs.mean()) * 100, 3),
        "pool_mean_pct": round(float(pool.mean()) * 100, 3),
        "lift_pct": round(float(obs.mean() - pool.mean()) * 100, 3),
        "win_rate": round(float((obs > 0).mean()), 3),
        "signal_t_excess": round(perm["signal_t_excess"], 3),
        "perm_p": round(perm_p, 4),
        "ci_lower_pct": round(ci["ci_lower"] * 100, 3),
        "ci_upper_pct": round(ci["ci_upper"] * 100, 3),
        "concentration": conc,
        "three_gate_pass": bool(three_gate),
        "concentration_gate_pass": bool(conc_gate),
        "elite_edge_pass": bool(obs.mean() >= 0.02),
        "verdict": "PASS" if (three_gate and conc_gate and obs.mean() >= 0.02) else "FAIL",
    }


def main() -> int:
    cohort, panel, spy = load_panel()
    logger.info("패널 %d종 (SPY %s)", len(panel), "확보" if spy is not None else "없음")

    ev = build_events(cohort, panel, spy)
    logger.info("이벤트 %d건 생성", len(ev))

    result = {
        "paradigm": PARADIGM, "phase": "R-1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP, "feature_end_day": FEATURE_END,
            "holds": list(HOLDS), "top_fractions": list(TOP_FRACTIONS),
            "dollar_vol_floors": list(DOLLAR_VOL_FLOORS),
            "entry": "D10 종가", "exit": "D10+HOLD 종가",
        },
        "n_events": int(len(ev)),
        "liquidity_profile": {},
        "quantile_profiles": {},
        "cells": [],
    }

    for floor in DOLLAR_VOL_FLOORS:
        n = int((ev["dollar_vol"] >= floor).sum())
        result["liquidity_profile"][f"floor_{floor}"] = {
            "n_symbols": n, "share": round(n / max(len(ev), 1), 3)}
        logger.info("유동성 필터 $%s: %d종 (%.0f%%)", f"{floor:,}", n, n / max(len(ev), 1) * 100)

    logger.info("=== 축별 5분위 프로파일 (hold=60, 유동성 $100k+)")
    liq = ev[ev["dollar_vol"] >= 100_000]
    for feat in ("vol_growth", "init_dd", "init_ret", "rs_vs_spy"):
        prof = quantile_profile(liq, feat, "fwd_60")
        result["quantile_profiles"][feat] = prof
        if prof:
            line = "  ".join(f"Q{p['bucket'] + 1}:{p['mean_pct']:+6.2f}%(n{p['n']})" for p in prof)
            logger.info("  %-11s %s", feat, line)

    logger.info("=== 선별 셀 평가")
    for feat, asc in (("vol_growth", False), ("init_dd", True), ("init_dd", False),
                      ("init_ret", False), ("init_ret", True), ("rs_vs_spy", False)):
        for hold in HOLDS:
            for frac in TOP_FRACTIONS:
                for floor in (100_000, 1_000_000):
                    cell = evaluate_selection(ev, feat, asc, frac, hold, floor)
                    if cell.get("verdict") == "INSUFFICIENT_POOL":
                        continue
                    result["cells"].append(cell)
                    logger.info(
                        "  %-11s %-4s f=%.1f h=%2d $%-9s n=%4d sel%+7.2f%% pool%+6.2f%% "
                        "lift%+6.2f%% t_exc%+6.2f ci_low%+7.2f%% → %s",
                        feat, cell["direction"], frac, hold, f"{floor:,}",
                        cell["n_selected"], cell["sel_mean_pct"], cell["pool_mean_pct"],
                        cell["lift_pct"], cell["signal_t_excess"], cell["ci_lower_pct"],
                        cell["verdict"])

    passes = [c for c in result["cells"] if c["verdict"] == "PASS"]
    near = [c for c in result["cells"]
            if c["verdict"] == "FAIL" and c["three_gate_pass"] and not c["elite_edge_pass"]]
    result["summary"] = {
        "n_cells": len(result["cells"]), "n_pass": len(passes),
        "passing": [f"{c['feature']}/{c['direction']}/f{c['frac']}/h{c['hold']}/${c['dollar_vol_floor']}"
                    for c in passes],
        "stat_sig_but_below_elite_edge": len(near),
        "verdict": "R-1 PASS" if passes else "R-1 FAIL",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r1__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    logger.info("판정: %s (%d/%d PASS, 통계유의하나 edge 미달 %d)",
                result["summary"]["verdict"], len(passes), len(result["cells"]), len(near))
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
