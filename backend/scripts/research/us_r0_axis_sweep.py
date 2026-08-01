#!/usr/bin/env python3
"""
R-0 축 스윕 — 미국 ETF 일봉에서 elite gate 도달 가능한 축 탐색.

왜 이 설계인가 (앞선 4건 종결에서 확정된 제약)
---------------------------------------------
- LONG only (공매도 불가) → 모든 축을 롱으로 표현
- 왕복 수수료 50.2bp 고정 → **거래당 엣지가 커야만 산다** (Lesson #80)
- 표적 구간 hold 5~10일 × trades/yr 12~25 (첫 R-0 실측)
- 유동성 게이트 필수 (Lesson #78) — 자동 구성 유니버스는 거래 불가 종목이 태반
- 상장 30일 이내 레버리지 ETF 제외 (graveyard 2 부산물, n=261 t=-3.03)

**레버리지 유니버스를 함께 스윕하는 이유**: 수수료가 고정이면 승부는 움직임의
크기에서 난다. 첫 R-0 실측에서 상위 30% 선별 시 도달 엣지가
  비레버리지 5일 +4.45% / 레버리지 5일 +13.02% (2.9배)
로 갈렸다. 레버리지 ETF 는 미국 유니버스에서 롱 매수가 가능하면서 변위가 큰
유일한 도구다. 단 일간 리밸런싱 감쇠가 있으므로 반드시 분리 측정한다.

측정 방식 — 횡단면 패널
---------------------
매 거래일 유니버스 전체를 피처로 랭킹 → 상위 K% 매수 → hold 일 뒤 청산.
룩어헤드 없음(피처는 t 시점까지, 수익률은 t→t+hold).
셀 = (유니버스 × 축 × 상위비율 × 보유일).

축 (전부 일봉 OHLCV 파생, 롱 표현 가능)
    rs_20      20일 수익률 − SPY 20일 수익률 (상대강도 모멘텀)
    near_high  종가 / 252일 최고가 (신고가 근접)
    vol_comp   20일 실현변동성 / 60일 실현변동성 (변동성 압축, 낮을수록 상위)
    dd_20      20일 최고가 대비 낙폭 (평균회귀, 깊을수록 상위)
    rs_x_high  rs_20 랭크 + near_high 랭크 (모멘텀 × 위치 결합)

판정
    net_mean >= +2.0% (elite gate edge) AND 승률 > 50% AND t >= 2.0
출력: backend/runs/research_track/us_axis_sweep/r0__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_r0_axis_sweep
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("us_r0_axis")

PARADIGM = "us_axis_sweep"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM

FEE_RT = 0.0025 * 2 + 0.0000206
BENCH = "SPY"
DOLLAR_VOL_FLOOR = 1_000_000       # Lesson #78
MIN_HISTORY = 300                  # 252일 룩백 + 여유
LISTING_EXCLUDE_DAYS = 30          # graveyard 2 부산물
HOLDS = (5, 10, 20, 30, 40, 60)
TOP_FRACS = (0.03, 0.05, 0.10, 0.20)
REBALANCE_STRIDE = 5               # 진입 간격(거래일) — 중복 표본 완화
EDGE_GATE = 0.02


def load_universe_symbols() -> dict:
    """{symbol: {'leveraged': bool}} — 레버리지 전수 + 코어 + 신규 코호트."""
    out = {}
    lev = BACKEND / "configs" / "us_leveraged_universe.json"
    if lev.exists():
        for s in json.loads(lev.read_text(encoding="utf-8"))["symbols"]:
            out[s["symbol"]] = {"leveraged": True}
    core = BACKEND / "configs" / "us_universe.json"
    if core.exists():
        u = json.loads(core.read_text(encoding="utf-8"))
        for grp in ("core", "leveraged"):
            for s in u.get(grp, []):
                out.setdefault(s["symbol"], {"leveraged": bool(s.get("leveraged"))})
    new = BACKEND / "configs" / "us_new_etf_cohort.json"
    if new.exists():
        for s in json.loads(new.read_text(encoding="utf-8"))["symbols"]:
            out.setdefault(s["symbol"], {"leveraged": bool(s.get("leveraged"))})
    return out


def load_panel(symbols: list) -> tuple:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT symbol, timestamp, high, low, close, volume FROM ohlcv "
            "WHERE time_frame = '1d' AND symbol = ANY(:s) ORDER BY symbol, timestamp"
        ), {"s": symbols}).all()
    finally:
        db.close()

    buckets = {}
    for sym, ts, hi, lo, cl, vol in rows:
        buckets.setdefault(sym, []).append((ts, float(hi), float(lo), float(cl), float(vol or 0)))

    close, dvol, high, listing = {}, {}, {}, {}
    for sym, recs in buckets.items():
        if len(recs) < MIN_HISTORY:
            continue
        idx = pd.to_datetime([r[0] for r in recs])
        c = pd.Series([r[3] for r in recs], index=idx)
        close[sym] = c
        high[sym] = pd.Series([r[1] for r in recs], index=idx)
        dvol[sym] = (c * pd.Series([r[4] for r in recs], index=idx)).rolling(
            20, min_periods=10).mean()
        listing[sym] = idx[0]
    return (pd.DataFrame(close).sort_index(), pd.DataFrame(high).sort_index(),
            pd.DataFrame(dvol).sort_index(), listing)


def build_features(close: pd.DataFrame, high: pd.DataFrame,
                   bench: pd.Series) -> dict:
    ret20 = close.pct_change(20)
    b20 = bench.pct_change(20).reindex(close.index).ffill()
    rs_20 = ret20.sub(b20, axis=0)

    roll_high_252 = high.rolling(252, min_periods=120).max()
    near_high = close / roll_high_252

    daily = close.pct_change()
    vol20 = daily.rolling(20, min_periods=15).std()
    vol60 = daily.rolling(60, min_periods=40).std()
    vol_comp = vol20 / vol60.replace(0.0, np.nan)

    roll_high_20 = high.rolling(20, min_periods=15).max()
    dd_20 = close / roll_high_20 - 1.0

    # 결합축: 두 랭크의 평균 (각 시점 횡단면 백분위)
    r1 = rs_20.rank(axis=1, pct=True)
    r2 = near_high.rank(axis=1, pct=True)
    rs_x_high = (r1 + r2) / 2.0

    return {
        "rs_20": (rs_20, False),           # (feature, ascending)
        "near_high": (near_high, False),
        "vol_comp": (vol_comp, True),      # 압축 = 낮을수록 상위
        "dd_20": (dd_20, True),            # 낙폭 깊을수록 상위
        "rs_x_high": (rs_x_high, False),
    }


def evaluate(close: pd.DataFrame, feat: pd.DataFrame, ascending: bool,
             eligible: pd.DataFrame, hold: int, frac: float,
             regime_ok: pd.Series = None) -> dict:
    """regime_ok: 진입일에 True 인 날만 진입 (예: SPY 200일선 위).

    레버리지 롱 모멘텀은 시장 레짐에 강하게 의존할 것으로 예상되므로 분리 측정한다.
    """
    dates = close.index[MIN_HISTORY::REBALANCE_STRIDE]
    rets, skipped = [], 0
    for d in dates:
        if regime_ok is not None and not bool(regime_ok.get(d, False)):
            skipped += 1
            continue
        i = close.index.get_loc(d)
        if i + hold >= len(close.index):
            break
        row = feat.loc[d]
        elig = eligible.loc[d]
        row = row[elig & row.notna()]
        if len(row) < 20:
            continue
        k = max(int(len(row) * frac), 3)
        picks = row.nsmallest(k).index if ascending else row.nlargest(k).index
        entry = close.loc[d, picks]
        exit_ = close.iloc[i + hold][picks]
        r = (exit_ / entry - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
        if len(r):
            rets.append(float(r.mean()) - FEE_RT)

    if len(rets) < 20:
        return {"n_periods": len(rets), "insufficient": True}


    a = np.array(rets)
    sd = a.std(ddof=1)
    return {
        "n_periods": int(len(a)),
        "net_mean_pct": round(float(a.mean()) * 100, 3),
        "net_median_pct": round(float(np.median(a)) * 100, 3),
        "win_rate": round(float((a > 0).mean()), 3),
        "t_stat": round(float(a.mean() / (sd / np.sqrt(len(a)))), 2) if sd > 0 else 0.0,
        "trades_per_yr": round(252 / REBALANCE_STRIDE, 1),
        "skipped_by_regime": int(skipped),
        "gate_pass": bool(a.mean() >= EDGE_GATE and (a > 0).mean() > 0.5
                          and (a.mean() / (sd / np.sqrt(len(a)))) >= 2.0 if sd > 0 else False),
    }


def main() -> int:
    meta = load_universe_symbols()
    logger.info("유니버스 후보 %d종", len(meta))

    close, high, dvol, listing = load_panel(list(meta) + [BENCH])
    logger.info("일봉 패널 %d종 × %d일 (%s ~ %s)", close.shape[1], close.shape[0],
                close.index[0].date(), close.index[-1].date())

    if BENCH not in close.columns:
        logger.error("벤치마크 %s 없음", BENCH)
        return 1
    bench = close[BENCH]
    bench_ma200 = bench.rolling(200, min_periods=150).mean()
    regime_bull = (bench > bench_ma200)

    # 유동성 + 상장경과 게이트
    eligible = dvol >= DOLLAR_VOL_FLOOR
    for sym in close.columns:
        if meta.get(sym, {}).get("leveraged") and sym in listing:
            cutoff = listing[sym] + pd.Timedelta(days=LISTING_EXCLUDE_DAYS)
            eligible.loc[eligible.index < cutoff, sym] = False
    logger.info("유동성 $%s + 상장30일 게이트 통과 평균 종목수: %.0f",
                f"{DOLLAR_VOL_FLOOR:,}", float(eligible.sum(axis=1).mean()))

    groups = {
        "leveraged": [s for s in close.columns
                      if s != BENCH and meta.get(s, {}).get("leveraged")],
        "non_leveraged": [s for s in close.columns
                          if s != BENCH and not meta.get(s, {}).get("leveraged")],
    }
    for g, syms in groups.items():
        logger.info("  %s: %d종", g, len(syms))

    result = {
        "paradigm": PARADIGM, "phase": "R-0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "fee_round_trip": FEE_RT, "dollar_vol_floor": DOLLAR_VOL_FLOOR,
            "listing_exclude_days": LISTING_EXCLUDE_DAYS, "holds": list(HOLDS),
            "top_fracs": list(TOP_FRACS), "rebalance_stride": REBALANCE_STRIDE,
            "edge_gate": EDGE_GATE, "benchmark": BENCH,
        },
        "panel": {"n_symbols": int(close.shape[1]), "n_days": int(close.shape[0]),
                  "start": str(close.index[0].date()), "end": str(close.index[-1].date())},
        "cells": [],
    }

    for gname, syms in groups.items():
        if len(syms) < 20:
            logger.warning("[%s] 종목 %d개 — 생략", gname, len(syms))
            continue
        sub_close = close[syms]
        sub_high = high[syms]
        sub_elig = eligible[syms]
        feats = build_features(sub_close, sub_high, bench)

        logger.info("=== [%s] %d종", gname, len(syms))
        for axis, (fdf, asc) in feats.items():
            for hold in HOLDS:
                for frac in TOP_FRACS:
                  for rname, rser in (("all", None), ("bull", regime_bull)):
                    cell = evaluate(sub_close, fdf, asc, sub_elig, hold, frac, rser)
                    if cell.get("insufficient"):
                        continue
                    cell.update({"universe": gname, "axis": axis, "regime": rname,
                                 "hold": hold, "top_frac": frac})
                    result["cells"].append(cell)
                    if cell["gate_pass"] or cell["net_mean_pct"] > 1.0:
                        logger.info("  %-10s %-4s h=%2d top%3.0f%%  n=%3d  net %+7.3f%%  "
                                    "win %.0f%%  t=%+5.2f%s",
                                    axis, rname, hold, frac * 100, cell["n_periods"],
                                    cell["net_mean_pct"], cell["win_rate"] * 100,
                                    cell["t_stat"], "  ★GATE" if cell["gate_pass"] else "")

    passes = [c for c in result["cells"] if c["gate_pass"]]
    best = sorted(result["cells"], key=lambda c: -c["net_mean_pct"])[:8]
    result["summary"] = {
        "n_cells": len(result["cells"]), "n_gate_pass": len(passes),
        "passing": [f"{c['universe']}/{c['axis']}/{c['regime']}/h{c['hold']}/top{int(c['top_frac']*100)}"
                    for c in passes],
        "top8_by_edge": [{k: c[k] for k in
                          ("universe", "axis", "regime", "hold", "top_frac",
                           "net_mean_pct", "win_rate", "t_stat", "n_periods")}
                         for c in best],
        "verdict": "AXIS_FOUND" if passes else "NO_AXIS_ABOVE_GATE",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r0__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    logger.info("판정: %s (%d/%d 셀 게이트 통과)",
                result["summary"]["verdict"], len(passes), len(result["cells"]))
    for c in best[:5]:
        logger.info("  상위: %s/%s/%s h%d top%.0f%% → net %+.2f%% win %.0f%% t=%+.2f",
                    c["universe"], c["axis"], c["regime"], c["hold"], c["top_frac"] * 100,
                    c["net_mean_pct"], c["win_rate"] * 100, c["t_stat"])
    print(json.dumps(result["summary"]["verdict"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
