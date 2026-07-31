#!/usr/bin/env python3
"""
R-0 프리스크린 — 파도타기(paradigm 127) 미국 ETF 이식 가능성.

원본 (바이낸스 paradigm 127, R-4 PASS 2026-05-21)
------------------------------------------------
트리거: 1분 거래량 > 30일 트레일링 p99 AND |1분 수익률| > 0.5% AND 수익률 > 0
집계  : 5분 bin 의 first-burst-sign (Lesson #50), 종목별 30분 디바운스
행동  : LONG 75분 보유, SL/TP 없음
실측  : n=13,175 / 2.2년 / gross +83.43bp / sigex +43.96 / 13/13 종목 CI 양수

왜 이것만 이식 후보인가
----------------------
1군 신상저격수와 2군 되치기(128)는 SHORT 이라 미국 계좌에서 실행 불가
(키움 공식: 증거금 매수·매도 100%). 128 은 추가로 SL 0.5% ≈ 미국 왕복 수수료
0.502% 라 손절 자체가 수수료와 같은 두께가 되어 설계가 성립하지 않는다.
127 만 LONG + 무손절이라 계좌 제약을 통과한다.

수수료 산술
    바이낸스 gross +83.43bp − 8bp  = net +75.4bp
    미국    gross +83.43bp − 50.2bp = net +33.2bp  (엣지 보존율 44%)
→ 미국에서 살아남으려면 **gross edge > 50.2bp** 가 필수 조건이다.

Lesson #40 구조적 임계 검증 (필수 선행)
-------------------------------------
|ret_1m| > 0.5% 는 크립토 알트에 맞춰진 절대 임계다. 미국 대형 ETF 의 1분
수익률 분포는 훨씬 좁아 이 임계가 구조적으로 도달 불가일 수 있다. 따라서
분포를 먼저 측정하고, 절대 임계와 **분위 기반 등가 임계** 두 가지로 평가한다.

미국 고유 제약
    - 정규장 391분/일 (크립토 1,440분) → 이벤트 공급 27% 수준
    - 75분 보유가 마감을 넘길 수 있음 → 마감 임박 버스트 분리 평가

출력: backend/runs/research_track/us_volume_burst_continuation/r0__metrics.json
실행: cd backend && PYTHONPATH=. python3 -m scripts.research.us_r0_volume_burst_continuation
"""

import json
import logging
import os
import sys
from datetime import datetime, time as dtime
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
logger = logging.getLogger("us_r0_vb")

PARADIGM = "us_volume_burst_continuation"
OUT_DIR = BACKEND / "runs" / "research_track" / PARADIGM

SYMBOLS = ["SPY", "QQQ", "IWM", "SOXX", "TLT", "XLK", "EEM", "HYG"]

FEE_ROUND_TRIP_BP = 50.2          # 미국 왕복 (0.25%×2 + SEC)
BINANCE_FEE_BP = 8.0
VOL_PCTL = 99.0                   # 거래량 임계 (원본과 동일)
VOL_LOOKBACK_MIN = 30 * 391       # 30 거래일치 1분봉
MAG_ABS = 0.005                   # 원본 절대 임계 0.5%
MAG_PCTL_EQUIV = 99.0             # 분위 등가 임계
BIN_MIN = 5                       # 5분 bin 집계
DEBOUNCE_MIN = 30
HOLDS = (15, 30, 45, 60, 75)
CLOSE_TIME = dtime(16, 0)


def load_1m(symbol: str) -> pd.DataFrame:
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT timestamp, close, volume FROM ohlcv "
            "WHERE symbol = :s AND time_frame = '1m' ORDER BY timestamp"
        ), {"s": symbol}).all()
    finally:
        db.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame({"close": [float(r[1]) for r in rows],
                       "volume": [float(r[2] or 0) for r in rows]},
                      index=pd.to_datetime([r[0] for r in rows]))
    return df


def distribution(df: pd.DataFrame) -> dict:
    ret = df["close"].pct_change().abs().dropna()
    return {
        "n_bars": int(len(df)),
        "abs_ret_p50_bp": round(float(np.percentile(ret, 50)) * 10000, 2),
        "abs_ret_p99_bp": round(float(np.percentile(ret, 99)) * 10000, 2),
        "abs_ret_p999_bp": round(float(np.percentile(ret, 99.9)) * 10000, 2),
        "abs_ret_max_bp": round(float(ret.max()) * 10000, 2),
        "frac_above_abs_thresh": round(float((ret > MAG_ABS).mean()), 6),
    }


def detect_bursts(df: pd.DataFrame, mag_thresh: float) -> pd.DatetimeIndex:
    """127 트리거: 거래량 p99 초과 + |수익률|>임계 + 수익률>0.
    5분 bin first-burst-sign 집계 + 30분 디바운스."""
    ret = df["close"].pct_change()
    vol = df["volume"]
    vol_p99 = vol.rolling(VOL_LOOKBACK_MIN, min_periods=VOL_LOOKBACK_MIN // 4).quantile(
        VOL_PCTL / 100.0)

    raw = (vol > vol_p99) & (ret.abs() > mag_thresh) & (ret > 0)
    hits = df.index[raw.fillna(False)]
    if len(hits) == 0:
        return pd.DatetimeIndex([])

    # 5분 bin first-burst-sign: 같은 bin 안에서는 첫 버스트만
    binned, seen_bins = [], set()
    for ts in hits:
        b = ts.floor(f"{BIN_MIN}min")
        if b in seen_bins:
            continue
        seen_bins.add(b)
        binned.append(ts)

    # 30분 디바운스
    out, last = [], None
    for ts in binned:
        if last is not None and (ts - last).total_seconds() < DEBOUNCE_MIN * 60:
            continue
        out.append(ts)
        last = ts
    return pd.DatetimeIndex(out)


def evaluate(df: pd.DataFrame, bursts: pd.DatetimeIndex, hold: int,
             exclude_near_close: bool) -> dict:
    close = df["close"]
    pos = {ts: i for i, ts in enumerate(df.index)}
    rets, dropped = [], 0

    for ts in bursts:
        i = pos.get(ts)
        if i is None:
            continue
        # 마감 임박 판정: 진입 시각 + hold 이 정규장 마감을 넘는가
        end_of_day = datetime.combine(ts.date(), CLOSE_TIME)
        crosses_close = (ts + pd.Timedelta(minutes=hold)).to_pydatetime() > end_of_day
        if exclude_near_close and crosses_close:
            dropped += 1
            continue
        j = i + hold
        if j >= len(close):
            continue
        entry, exit_ = float(close.iloc[i]), float(close.iloc[j])
        if entry <= 0:
            continue
        rets.append(exit_ / entry - 1.0)

    if len(rets) < 10:
        return {"n": len(rets), "dropped_near_close": dropped, "insufficient": True}

    a = np.array(rets)
    sd = a.std(ddof=1)
    gross_bp = float(a.mean()) * 10000
    return {
        "n": int(len(a)), "dropped_near_close": int(dropped),
        "gross_bp": round(gross_bp, 2),
        "net_us_bp": round(gross_bp - FEE_ROUND_TRIP_BP, 2),
        "net_binance_bp": round(gross_bp - BINANCE_FEE_BP, 2),
        "win_rate": round(float((a > 0).mean()), 3),
        "t_stat": round(float(a.mean() / (sd / np.sqrt(len(a)))), 2) if sd > 0 else 0.0,
        "beats_us_fee": bool(gross_bp > FEE_ROUND_TRIP_BP),
    }


def main() -> int:
    result = {
        "paradigm": PARADIGM, "phase": "R-0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paradigm": "binance 127 (gross +83.43bp, hold 75m)",
        "config": {
            "fee_round_trip_bp": FEE_ROUND_TRIP_BP, "vol_pctl": VOL_PCTL,
            "mag_abs": MAG_ABS, "mag_pctl_equiv": MAG_PCTL_EQUIV,
            "bin_min": BIN_MIN, "debounce_min": DEBOUNCE_MIN, "holds": list(HOLDS),
        },
        "distribution": {}, "cells": [], "per_symbol": {},
    }

    panels = {}
    for sym in SYMBOLS:
        df = load_1m(sym)
        if df.empty or len(df) < VOL_LOOKBACK_MIN // 2:
            logger.warning("%s 분봉 부족 (%d봉) — 제외", sym, len(df))
            continue
        panels[sym] = df
        d = distribution(df)
        result["distribution"][sym] = d
        logger.info("%-5s %6d봉  |ret| p50 %5.2fbp  p99 %6.2fbp  p99.9 %7.2fbp  "
                    "max %8.2fbp  0.5%%초과비율 %.4f%%",
                    sym, d["n_bars"], d["abs_ret_p50_bp"], d["abs_ret_p99_bp"],
                    d["abs_ret_p999_bp"], d["abs_ret_max_bp"],
                    d["frac_above_abs_thresh"] * 100)

    if not panels:
        logger.error("분봉 데이터 없음 — 중단")
        return 1

    # Lesson #40 구조적 임계 판정
    all_p999 = [d["abs_ret_p999_bp"] for d in result["distribution"].values()]
    abs_reachable = any(d["frac_above_abs_thresh"] > 0.0001
                        for d in result["distribution"].values())
    result["lesson40_abs_threshold_reachable"] = bool(abs_reachable)
    logger.info("Lesson #40 절대임계(0.5%%) 도달가능: %s (p99.9 중앙 %.1fbp)",
                abs_reachable, float(np.median(all_p999)))

    modes = [("abs_0.5pct", MAG_ABS)]
    if not abs_reachable:
        logger.info("→ 절대임계 구조적 불가. 분위 등가 임계로 재구성 (Lesson #40)")

    # 종목별 분위 등가 임계 (p99 of |ret|)
    for sym, df in panels.items():
        r = df["close"].pct_change().abs().dropna()
        panels[sym].attrs["mag_pctl"] = float(np.percentile(r, MAG_PCTL_EQUIV))
    modes.append(("pctl_p99", None))

    for mode, fixed_thresh in modes:
        for exclude_close in (False, True):
            agg_by_hold = {h: [] for h in HOLDS}
            per_sym = {}
            for sym, df in panels.items():
                thresh = fixed_thresh if fixed_thresh is not None else df.attrs["mag_pctl"]
                bursts = detect_bursts(df, thresh)
                per_sym[sym] = {"n_bursts": int(len(bursts)),
                                "mag_thresh_bp": round(thresh * 10000, 2)}
                for h in HOLDS:
                    cell = evaluate(df, bursts, h, exclude_close)
                    if not cell.get("insufficient"):
                        agg_by_hold[h].append((sym, cell))

            for h in HOLDS:
                cells = agg_by_hold[h]
                if not cells:
                    continue
                total_n = sum(c["n"] for _, c in cells)
                wsum = sum(c["gross_bp"] * c["n"] for _, c in cells)
                gross = wsum / total_n if total_n else 0.0
                pos_syms = sum(1 for _, c in cells if c["gross_bp"] > FEE_ROUND_TRIP_BP)
                row = {
                    "mode": mode, "exclude_near_close": exclude_close, "hold_min": h,
                    "n_symbols": len(cells), "n_events": total_n,
                    "gross_bp": round(gross, 2),
                    "net_us_bp": round(gross - FEE_ROUND_TRIP_BP, 2),
                    "n_symbols_beating_us_fee": pos_syms,
                    "per_symbol": {s: c for s, c in cells},
                }
                result["cells"].append(row)
                logger.info("  [%s%s] hold %2dm  n=%5d  gross %+7.2fbp  "
                            "net_US %+7.2fbp  수수료초과종목 %d/%d",
                            mode, " ex-close" if exclude_close else "", h,
                            total_n, gross, gross - FEE_ROUND_TRIP_BP,
                            pos_syms, len(cells))
            result["per_symbol"][f"{mode}{'_exclose' if exclude_close else ''}"] = per_sym

    winners = [c for c in result["cells"] if c["net_us_bp"] > 0
               and c["n_symbols_beating_us_fee"] >= max(len(panels) // 2, 2)]
    result["verdict"] = {
        "n_cells": len(result["cells"]),
        "cells_beating_us_fee": len(winners),
        "winners": [f"{c['mode']}/h{c['hold_min']}/{'exclose' if c['exclude_near_close'] else 'all'}"
                    for c in winners],
        "conclusion": "US_TRANSFER_VIABLE" if winners else "US_TRANSFER_NOT_VIABLE",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "r0__metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    logger.info("판정: %s (%d/%d 셀이 미국 수수료 초과)",
                result["verdict"]["conclusion"], len(winners), len(result["cells"]))
    print(json.dumps(result["verdict"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
