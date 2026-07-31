#!/usr/bin/env python3
"""
R-0 프리스크린 — 미국 신규 상장 ETF 코호트 (비레버리지 중심).

배경
----
앞선 R-0(us_leveraged_etf_listing_cohort)은 레버리지·인버스 567종만 봤고
롱·인버스 12/12 셀 전부 음수였다. 다만 그 하락의 원인은 "상장"이 아니라
**일간 리밸런싱 변동성 드래그**일 가능성이 크다 — 신규 상장 직후는 변동성이
극대화되는 구간이라 드래그도 최대가 된다.

비레버리지 신규 ETF 에는 그 드래그가 없다. 따라서 완전히 다른 모집단이고,
레버리지에서 관측된 하락 편향이 그대로 적용된다는 보장이 없다.

검증 대상 (롱 표현 가능한 것만 — 미국주식 공매도 불가)
    A) 초기 자금유입 모멘텀 — 신규 ETF 는 상장 초기 마케팅·AUM 유입을 받는다
    B) 테마 모멘텀 지속 — 발행사는 이미 강세인 테마로 상품을 낸다
    (C) 테마 정점 역지표는 숏이 필요해 실행 불가 → 참으로 나와도 못 씀)

판정
----
평균 net > 0 이고 승률 > 50% 인 셀이 존재 → 롱 표현 가능한 축 성립 (R-1 진행)
레버리지처럼 전 셀 음수 → 상장 이벤트 축 폐기

주의 — 오판 필터:
    상장일 프로브(strt_dt 0행)는 "데이터 없는 종목"도 신규로 잡는다.
    일봉 봉 수가 MIN_BARS 미만인 심볼은 코호트에서 제외한다.

출력: backend/runs/research_track/us_new_etf_listing_cohort/r0__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_r0_new_etf_listing_cohort
"""

import json
import logging
import os
import sys
from collections import Counter
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
logger = logging.getLogger("us_r0_new_etf")

PARADIGM = "us_new_etf_listing_cohort"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM
COHORT_PATH = BACKEND / "configs" / "us_new_etf_cohort.json"

FEE_ROUND_TRIP = 0.0025 * 2 + 0.0000206
ENTRY_OFFSETS = (1, 3, 5, 10)
HOLDS = (5, 10, 20, 30, 60)
MIN_BARS = 40          # 진입 오프셋 + 최장 보유를 커버할 최소 봉 수
MIN_CELL_N = 20        # 셀당 최소 표본 (Lesson #11 완화판 — R-0 탐색 단계)


def load_cohort() -> dict:
    data = json.loads(COHORT_PATH.read_text(encoding="utf-8"))
    return {s["symbol"]: s for s in data["symbols"]}


def load_series(symbols: list) -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT symbol, timestamp, close FROM ohlcv "
            "WHERE time_frame = '1d' AND symbol = ANY(:s) ORDER BY symbol, timestamp"
        ), {"s": symbols}).all()
    finally:
        db.close()

    buckets: dict = {}
    for sym, ts, close in rows:
        buckets.setdefault(sym, []).append((ts, float(close)))

    out = {}
    for sym, pairs in buckets.items():
        if len(pairs) < MIN_BARS:
            continue
        out[sym] = pd.Series([p[1] for p in pairs],
                             index=pd.to_datetime([p[0] for p in pairs]))
    return out


def fwd(series: pd.Series, offset: int, hold: int):
    if len(series) <= offset + hold:
        return None
    entry = float(series.iloc[offset])
    if entry <= 0:
        return None
    return float(series.iloc[offset + hold]) / entry - 1.0 - FEE_ROUND_TRIP


def cells_for(series_map: dict, syms: list) -> dict:
    cells = {}
    for off in ENTRY_OFFSETS:
        for hold in HOLDS:
            vals = [fwd(series_map[s], off, hold) for s in syms]
            vals = [v for v in vals if v is not None]
            if len(vals) < MIN_CELL_N:
                continue
            a = np.array(vals)
            sd = a.std(ddof=1)
            cells[f"d{off}_h{hold}"] = {
                "n": int(len(a)),
                "net_mean_pct": round(float(a.mean()) * 100, 3),
                "net_median_pct": round(float(np.median(a)) * 100, 3),
                "win_rate": round(float((a > 0).mean()), 3),
                "t_stat": round(float(a.mean() / (sd / np.sqrt(len(a)))), 3) if sd > 0 else 0.0,
                "p10_pct": round(float(np.percentile(a, 10)) * 100, 2),
                "p90_pct": round(float(np.percentile(a, 90)) * 100, 2),
            }
    return cells


def main() -> int:
    cohort = load_cohort()
    series = load_series(list(cohort))
    logger.info("코호트 %d종 중 일봉 %d봉 이상 확보 %d종 (나머지는 데이터 부재로 제외)",
                len(cohort), MIN_BARS, len(series))

    groups = {
        "non_leveraged": [s for s in series if not cohort[s].get("leveraged")],
        "leveraged": [s for s in series if cohort[s].get("leveraged")],
    }
    logger.info("  비레버리지 %d종 / 레버리지 %d종",
                len(groups["non_leveraged"]), len(groups["leveraged"]))

    listing_year = Counter(series[s].index[0].year for s in series)

    result = {
        "paradigm": PARADIGM, "phase": "R-0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP,
            "entry_offsets": list(ENTRY_OFFSETS), "holds": list(HOLDS),
            "min_bars": MIN_BARS, "min_cell_n": MIN_CELL_N,
        },
        "cohort": {
            "n_probed_new": len(cohort),
            "n_with_data": len(series),
            "n_non_leveraged": len(groups["non_leveraged"]),
            "n_leveraged": len(groups["leveraged"]),
            "listing_year": {str(k): v for k, v in sorted(listing_year.items())},
        },
        "performance": {},
    }

    for gname, syms in groups.items():
        if len(syms) < MIN_CELL_N:
            logger.warning("[%s] 표본 %d종 — 측정 생략", gname, len(syms))
            continue
        cells = cells_for(series, syms)
        result["performance"][gname] = cells
        logger.info("=== [%s] 상장 후 수익률 (수수료 차감, n=%d종)", gname, len(syms))
        for k, v in cells.items():
            flag = "  ←양수" if v["net_mean_pct"] > 0 and v["win_rate"] > 0.5 else ""
            logger.info("     %-9s n=%4d  mean %+7.2f%%  median %+7.2f%%  win %.0f%%  t=%+.2f%s",
                        k, v["n"], v["net_mean_pct"], v["net_median_pct"],
                        v["win_rate"] * 100, v["t_stat"], flag)

    pos = {
        g: [k for k, v in cells.items() if v["net_mean_pct"] > 0 and v["win_rate"] > 0.5]
        for g, cells in result["performance"].items()
    }
    result["verdict"] = {
        "positive_cells": pos,
        "conclusion": ("LONG_EXPRESSIBLE_EDGE_FOUND"
                       if pos.get("non_leveraged") else "NO_LONG_EDGE"),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r0__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    logger.info("판정: %s / 양수 셀: %s",
                result["verdict"]["conclusion"], json.dumps(pos, ensure_ascii=False))
    print(json.dumps(result["verdict"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
