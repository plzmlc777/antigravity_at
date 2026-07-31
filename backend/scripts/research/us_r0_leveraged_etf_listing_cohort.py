#!/usr/bin/env python3
"""
R-0 프리스크린 — 레버리지 ETF 신규 상장 코호트 (미국).

가설 배경
--------
바이낸스 신상저격수(신규 상장 Day-1 SHORT)는 미국에 이식 불가다. 미국주식은
공매도가 막혀 있고(증거금 매수·매도 100%), REST API 는 옵션·선물을 지원하지 않는다.

대신 별개 DNA 의 가설이 있다: **발행사가 특정 테마의 레버리지 ETF 를 출시하는
시점 = 그 테마 수요의 정점**. 발행사는 수요가 있을 때 상품을 낸다. 이 경우
신규 상장 롱 레버리지 상품은 이후 부진하고, 같은 기초자산의 **인버스 상품을
매수**하면 공매도 없이 그 방향을 취할 수 있다.

주의: 이건 "신규 상장 자산의 가격발견 감쇠"(신상저격수)와 다른 메커니즘이다.
레버리지 ETF 의 기초자산은 이미 가격발견이 끝난 종목이고, 새로 상장되는 것은
래퍼일 뿐이다. 여기서 신규성은 **발행 타이밍 신호**로만 기능한다.

측정 (R-0 3종)
-------------
① 롱/숏 쌍 동시 상장 비율 — 실행 가능한 이벤트가 몇 건인지
② 2024년 이후 유효 코호트 크기 — 상장 급증으로 레짐이 바뀌어 이전 구간은 얇다
③ 상장 후 수익률 분포 — 롱 상품이 실제로 부진하고 인버스가 오르는가

출력: backend/runs/research_track/us_leveraged_etf_listing_cohort/r0__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_r0_leveraged_etf_listing_cohort
"""

import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
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
logger = logging.getLogger("us_r0_listing")

PARADIGM = "us_leveraged_etf_listing_cohort"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM
UNIVERSE_PATH = BACKEND / "configs" / "us_leveraged_universe.json"

FEE_ROUND_TRIP = 0.0025 * 2 + 0.0000206
ENTRY_OFFSETS = (1, 3, 5)          # 상장 후 N 거래일에 진입
HOLDS = (5, 10, 20, 30)            # 보유 거래일
PAIR_WINDOW_DAYS = 45              # 쌍 동시상장으로 인정할 상장일 간격
REGIME_CUTOFF = date(2024, 1, 1)   # 상장 급증 레짐 시작
MIN_BARS_FOR_EVENT = 10

# 발행사 / 레버리지 토큰 — 기초자산 이름을 남기기 위해 제거
ISSUER_TOKENS = {
    "GRANITESHARES", "DIREXION", "TRADR", "TREX", "T-REX", "LEVERAGE", "SHARES",
    "DEFIANCE", "ROUNDHILL", "PROSHARES", "MICROSECTORS", "AXS", "YIELDMAX",
    "INVESCO", "ISHARES", "VANGUARD", "SPDR", "STATE", "STREET", "GLOBAL", "X",
    "ETF", "ETN", "TRUST", "FUND", "FUNDS", "INDEX", "SERIES", "TR", "OPPORTUNITIES",
    "CORGI", "KURV", "REX", "TIDAL", "VOLATILITY", "INNOVATION", "ADVISORS",
}
LEV_TOKENS = {
    "DAILY", "2X", "3X", "-2X", "-3X", "1X", "-1X", "BULL", "BEAR", "LONG", "SHORT",
    "INVERSE", "ULTRA", "ULTRAPRO", "ULTRASHORT", "TARGET", "LEVERAGED", "2", "3",
}
_TOKEN_RE = re.compile(r"[A-Z0-9\-]+")


def underlying_key(name_en: str) -> str:
    """영문명에서 발행사·레버리지 토큰을 걷어내고 기초자산 토큰만 남긴다."""
    toks = _TOKEN_RE.findall((name_en or "").upper())
    keep = [t for t in toks
            if t not in ISSUER_TOKENS and t not in LEV_TOKENS and len(t) > 1]
    return " ".join(keep)


def load_universe() -> dict:
    u = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    return {s["symbol"]: s for s in u["symbols"]}


def load_series(symbols: list) -> dict:
    db = SessionLocal()
    out = {}
    try:
        rows = db.execute(text(
            "SELECT symbol, timestamp, close FROM ohlcv "
            "WHERE time_frame = '1d' AND symbol = ANY(:s) ORDER BY symbol, timestamp"
        ), {"s": symbols}).all()
    finally:
        db.close()
    by_sym = defaultdict(list)
    for sym, ts, close in rows:
        by_sym[sym].append((ts, float(close)))
    for sym, pairs in by_sym.items():
        if len(pairs) < MIN_BARS_FOR_EVENT:
            continue
        out[sym] = pd.Series([p[1] for p in pairs],
                             index=pd.to_datetime([p[0] for p in pairs]))
    return out


def forward_returns(series: pd.Series, offset: int, hold: int) -> float:
    """상장 후 offset 거래일 종가 진입 → hold 거래일 뒤 종가 청산 (수수료 차감)."""
    if len(series) <= offset + hold:
        return None
    entry = series.iloc[offset]
    exit_ = series.iloc[offset + hold]
    if entry <= 0:
        return None
    return float(exit_ / entry - 1.0) - FEE_ROUND_TRIP


def main() -> int:
    recs = load_universe()
    series = load_series(list(recs))
    logger.info("일봉 로드 %d/%d종", len(series), len(recs))

    listing = {s: series[s].index[0].date() for s in series}

    # ── ① 롱/숏 쌍 동시 상장 ──────────────────────────────────────
    groups = defaultdict(lambda: {"long": [], "short": []})
    for sym, s in series.items():
        key = underlying_key(recs[sym].get("name_en"))
        if not key:
            continue
        groups[key][recs[sym]["direction"]].append(sym)

    paired, unpaired_long = [], []
    for key, g in groups.items():
        for lsym in g["long"]:
            best = None
            for ssym in g["short"]:
                gap = abs((listing[lsym] - listing[ssym]).days)
                if gap <= PAIR_WINDOW_DAYS and (best is None or gap < best[1]):
                    best = (ssym, gap)
            if best:
                paired.append({"underlying": key, "long": lsym, "short": best[0],
                               "gap_days": best[1],
                               "long_listed": str(listing[lsym]),
                               "short_listed": str(listing[best[0]])})
            else:
                unpaired_long.append(lsym)

    # ── ② 레짐별 코호트 크기 ──────────────────────────────────────
    by_year = Counter(listing[s].year for s in series)
    post_cutoff = [s for s in series if listing[s] >= REGIME_CUTOFF]
    paired_post = [p for p in paired if date.fromisoformat(p["long_listed"]) >= REGIME_CUTOFF]

    # ── ③ 상장 후 수익률 분포 ────────────────────────────────────
    perf = {}
    for direction in ("long", "short"):
        syms = [s for s in series if recs[s]["direction"] == direction
                and listing[s] >= REGIME_CUTOFF]
        cells = {}
        for off in ENTRY_OFFSETS:
            for hold in HOLDS:
                vals = [forward_returns(series[s], off, hold) for s in syms]
                vals = [v for v in vals if v is not None]
                if len(vals) < 10:
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
        perf[direction] = cells

    result = {
        "paradigm": PARADIGM, "phase": "R-0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP, "entry_offsets": list(ENTRY_OFFSETS),
            "holds": list(HOLDS), "pair_window_days": PAIR_WINDOW_DAYS,
            "regime_cutoff": str(REGIME_CUTOFF),
        },
        "universe": {"n_symbols": len(recs), "n_with_data": len(series)},
        "pairing": {
            "n_underlying_groups": len(groups),
            "n_paired": len(paired),
            "n_unpaired_long": len(unpaired_long),
            "pair_rate": round(len(paired) / max(len(paired) + len(unpaired_long), 1), 3),
            "n_paired_post_cutoff": len(paired_post),
            "samples": paired[:10],
        },
        "regime": {
            "by_year": {str(k): v for k, v in sorted(by_year.items())},
            "n_post_cutoff": len(post_cutoff),
            "cutoff": str(REGIME_CUTOFF),
        },
        "performance_post_cutoff": perf,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r0__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    logger.info("① 쌍 성립 %d건 / 미성립 롱 %d건 (성립률 %.1f%%), 2024+ %d건",
                len(paired), len(unpaired_long),
                result["pairing"]["pair_rate"] * 100, len(paired_post))
    logger.info("② 2024+ 코호트 %d종 (전체 %d종)", len(post_cutoff), len(series))
    for direction, cells in perf.items():
        logger.info("③ [%s 상품] 상장 후 수익률 (수수료 차감)", direction)
        for k, v in cells.items():
            logger.info("     %-9s n=%3d  mean %+7.2f%%  median %+7.2f%%  win %.0f%%  t=%+.2f",
                        k, v["n"], v["net_mean_pct"], v["net_median_pct"],
                        v["win_rate"] * 100, v["t_stat"])
    print(json.dumps({"pairing": result["pairing"]["pair_rate"],
                      "n_paired": len(paired), "n_post_cutoff": len(post_cutoff)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
