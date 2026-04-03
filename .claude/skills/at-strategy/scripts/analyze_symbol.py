#!/usr/bin/env python3
"""
종목 특성 분석 스크립트.
OHLCV 데이터로 변동성, 패턴, 추세를 분석하여 AI 파라미터 추천의 근거를 제공한다.

Usage:
    python3 analyze_symbol.py --symbol 005930 --interval 1d --days 180
    python3 analyze_symbol.py --symbol BTCUSDT --interval 1h --days 90 --json
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# at-backtest의 fetch_data 재사용
BACKTEST_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "at-backtest" / "scripts"
sys.path.insert(0, str(BACKTEST_SCRIPTS))

from fetch_data import load_ohlcv


def analyze(candles: list) -> dict:
    """종목 특성 분석. 캔들 리스트 → 분석 결과 dict."""
    if not candles or len(candles) < 10:
        return {"error": "데이터 부족 (최소 10개 캔들 필요)"}

    n = len(candles)

    # --- 변동성 분석 ---
    intra_changes = []   # 캔들 내 변동 (|close - open| / open)
    inter_changes = []   # 캔들 간 변동 (close-to-close %)
    dip_rates = []       # 캔들 내 하락률 ((open - close) / open, 양수 = 하락)
    upper_wicks = []     # 위꼬리 비율
    lower_wicks = []     # 아래꼬리 비율

    for i, c in enumerate(candles):
        o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
        if o <= 0:
            continue

        # 캔들 내 변동
        intra = abs(cl - o) / o * 100
        intra_changes.append(intra)

        # 캔들 내 하락률 (음봉일 때 양수)
        dip = (o - cl) / o * 100
        dip_rates.append(dip)

        # 캔들 간 변동
        if i > 0 and candles[i - 1]["close"] > 0:
            prev_cl = candles[i - 1]["close"]
            inter = (cl - prev_cl) / prev_cl * 100
            inter_changes.append(inter)

        # 꼬리 분석
        body = abs(cl - o)
        candle_range = h - l
        if candle_range > 0:
            upper_wick = (h - max(o, cl)) / candle_range * 100
            lower_wick = (min(o, cl) - l) / candle_range * 100
            upper_wicks.append(upper_wick)
            lower_wicks.append(lower_wick)

    # --- 기본 통계 ---
    avg_intra = sum(intra_changes) / len(intra_changes) if intra_changes else 0
    avg_inter = sum(abs(x) for x in inter_changes) / len(inter_changes) if inter_changes else 0

    # 양봉/음봉 비율
    positive_dips = [d for d in dip_rates if d > 0]   # 음봉 (하락)
    negative_dips = [d for d in dip_rates if d <= 0]   # 양봉 (상승 또는 보합)
    bearish_ratio = len(positive_dips) / len(dip_rates) * 100 if dip_rates else 50

    # 음봉 평균 하락률
    avg_dip = sum(positive_dips) / len(positive_dips) if positive_dips else 0

    # --- 추세 분석 ---
    first_price = candles[0]["close"]
    last_price = candles[-1]["close"]
    total_return = (last_price - first_price) / first_price * 100 if first_price > 0 else 0

    # 단순 추세 판단 (20등분하여 방향성)
    segment_size = max(n // 5, 1)
    segment_returns = []
    for i in range(0, n - segment_size, segment_size):
        seg_start = candles[i]["close"]
        seg_end = candles[min(i + segment_size, n - 1)]["close"]
        if seg_start > 0:
            segment_returns.append((seg_end - seg_start) / seg_start * 100)

    up_segments = sum(1 for r in segment_returns if r > 0.5)
    down_segments = sum(1 for r in segment_returns if r < -0.5)
    flat_segments = len(segment_returns) - up_segments - down_segments

    # 추세 판단
    if up_segments >= len(segment_returns) * 0.6:
        trend = "uptrend"
    elif down_segments >= len(segment_returns) * 0.6:
        trend = "downtrend"
    else:
        trend = "sideways"

    # --- 변동성 수준 분류 ---
    if avg_intra < 0.5:
        volatility_level = "very_low"
    elif avg_intra < 1.0:
        volatility_level = "low"
    elif avg_intra < 2.0:
        volatility_level = "medium"
    elif avg_intra < 4.0:
        volatility_level = "high"
    else:
        volatility_level = "very_high"

    # --- Dip 빈도 분석 (dip_percent 설정 기준) ---
    dip_thresholds = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    dip_frequency = {}
    for threshold in dip_thresholds:
        count = sum(1 for d in positive_dips if d >= threshold)
        pct = count / len(dip_rates) * 100 if dip_rates else 0
        dip_frequency[f"dip_{threshold}pct"] = {
            "count": count,
            "frequency_pct": round(pct, 1),
            "avg_per_week": round(count / max(n / 5, 1), 1) if n > 0 else 0,
        }

    # --- 최대 연속 하락 ---
    max_consecutive_loss = 0
    current_loss_streak = 0
    for d in dip_rates:
        if d > 0:
            current_loss_streak += 1
            max_consecutive_loss = max(max_consecutive_loss, current_loss_streak)
        else:
            current_loss_streak = 0

    # --- MDD (Maximum Drawdown) ---
    peak = candles[0]["close"]
    max_dd = 0
    for c in candles:
        peak = max(peak, c["close"])
        dd = (c["close"] - peak) / peak * 100 if peak > 0 else 0
        max_dd = min(max_dd, dd)

    return {
        "summary": {
            "candle_count": n,
            "first_date": candles[0].get("timestamp", ""),
            "last_date": candles[-1].get("timestamp", ""),
            "first_price": round(first_price, 2),
            "last_price": round(last_price, 2),
            "total_return_pct": round(total_return, 2),
            "max_drawdown_pct": round(max_dd, 2),
        },
        "volatility": {
            "avg_intra_candle_pct": round(avg_intra, 3),
            "avg_inter_candle_pct": round(avg_inter, 3),
            "level": volatility_level,
        },
        "trend": {
            "direction": trend,
            "up_segments": up_segments,
            "down_segments": down_segments,
            "flat_segments": flat_segments,
        },
        "dip_analysis": {
            "bearish_candle_ratio_pct": round(bearish_ratio, 1),
            "avg_dip_on_bearish_pct": round(avg_dip, 3),
            "max_consecutive_bearish": max_consecutive_loss,
            "dip_frequency": dip_frequency,
        },
        "wick_analysis": {
            "avg_upper_wick_pct": round(sum(upper_wicks) / len(upper_wicks), 1) if upper_wicks else 0,
            "avg_lower_wick_pct": round(sum(lower_wicks) / len(lower_wicks), 1) if lower_wicks else 0,
        },
    }


def suggest_params(analysis: dict) -> dict:
    """분석 결과를 기반으로 dip_martingale 파라미터 제안 (규칙 기반 baseline)."""
    vol = analysis.get("volatility", {})
    dip_info = analysis.get("dip_analysis", {})
    trend_info = analysis.get("trend", {})

    avg_intra = vol.get("avg_intra_candle_pct", 1.0)
    avg_dip = dip_info.get("avg_dip_on_bearish_pct", 1.0)
    trend = trend_info.get("direction", "sideways")

    # dip_percent: 평균 음봉 하락률의 50~80%
    dip_pct = round(avg_dip * 0.6, 1)
    dip_pct = max(0.3, min(dip_pct, 10.0))

    # level_gap: dip의 1.5~2.5배
    gap_pct = round(dip_pct * 2.0, 1)
    gap_pct = max(0.5, min(gap_pct, 15.0))

    # trailing_start: 일변동의 1.0~1.5배
    trail_start = round(avg_intra * 1.2, 1)
    trail_start = max(0.5, min(trail_start, 20.0))

    # trailing_stop: 일변동의 0.3~0.5배
    trail_stop = round(avg_intra * 0.4, 1)
    trail_stop = max(0.2, min(trail_stop, 5.0))

    # max_buy_count: 추세에 따라 조정
    if trend == "downtrend":
        max_buys = 2  # 하락장에서는 보수적
    elif trend == "sideways":
        max_buys = 4  # 횡보장에서는 일반적
    else:
        max_buys = 3  # 상승장에서는 중간

    # max_loss: 변동성에 비례
    max_loss = round(avg_intra * 5, 1)
    max_loss = max(3.0, min(max_loss, 20.0))

    return {
        "strategy": "dip_martingale",
        "recommended_config": {
            "dip_percent": dip_pct,
            "level_gap_percent": gap_pct,
            "trailing_start_percent": trail_start,
            "trailing_stop_percent": trail_stop,
            "max_buy_count": max_buys,
            "max_loss_percent": max_loss,
        },
        "reasoning": {
            "dip_percent": f"avg bearish candle dip={avg_dip:.2f}% × 0.6 = {dip_pct}%",
            "level_gap_percent": f"dip_percent × 2.0 = {gap_pct}%",
            "trailing_start_percent": f"avg intra-candle vol={avg_intra:.2f}% × 1.2 = {trail_start}%",
            "trailing_stop_percent": f"avg intra-candle vol={avg_intra:.2f}% × 0.4 = {trail_stop}%",
            "max_buy_count": f"trend={trend} → {max_buys} levels",
            "max_loss_percent": f"avg intra-candle vol={avg_intra:.2f}% × 5 = {max_loss}%",
        },
    }


def format_report(symbol: str, interval: str, analysis: dict, suggestion: dict) -> str:
    """사람이 읽기 좋은 보고서 형식."""
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"  종목 분석 보고서: {symbol} ({interval})")
    lines.append(f"{'='*60}")

    s = analysis["summary"]
    lines.append(f"\n📊 기본 정보")
    lines.append(f"  기간: {s['first_date'][:10]} ~ {s['last_date'][:10]} ({s['candle_count']}캔들)")
    lines.append(f"  가격: {s['first_price']:,.0f} → {s['last_price']:,.0f} ({s['total_return_pct']:+.1f}%)")
    lines.append(f"  MDD: {s['max_drawdown_pct']:.1f}%")

    v = analysis["volatility"]
    lines.append(f"\n📈 변동성: {v['level'].upper()}")
    lines.append(f"  캔들 내 평균 변동: {v['avg_intra_candle_pct']:.2f}%")
    lines.append(f"  캔들 간 평균 변동: {v['avg_inter_candle_pct']:.2f}%")

    t = analysis["trend"]
    trend_kr = {"uptrend": "상승 추세", "downtrend": "하락 추세", "sideways": "횡보"}
    lines.append(f"\n🔀 추세: {trend_kr.get(t['direction'], t['direction'])}")
    lines.append(f"  상승 구간: {t['up_segments']} / 하락 구간: {t['down_segments']} / 횡보 구간: {t['flat_segments']}")

    d = analysis["dip_analysis"]
    lines.append(f"\n🔻 Dip 분석")
    lines.append(f"  음봉 비율: {d['bearish_candle_ratio_pct']:.1f}%")
    lines.append(f"  음봉 평균 하락: {d['avg_dip_on_bearish_pct']:.2f}%")
    lines.append(f"  최대 연속 음봉: {d['max_consecutive_bearish']}개")
    lines.append(f"\n  Dip 빈도 (전체 캔들 대비):")
    for key, val in d["dip_frequency"].items():
        pct_label = key.replace("dip_", "").replace("pct", "%")
        lines.append(f"    {pct_label} 이상: {val['count']}회 ({val['frequency_pct']}%)")

    r = suggestion["recommended_config"]
    lines.append(f"\n{'='*60}")
    lines.append(f"  AI 파라미터 추천 (규칙 기반)")
    lines.append(f"{'='*60}")
    for param, value in r.items():
        reason = suggestion["reasoning"].get(param, "")
        lines.append(f"  {param}: {value}  ← {reason}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="종목 특성 분석")
    parser.add_argument("--symbol", required=True, help="종목 코드")
    parser.add_argument("--interval", "-i", default="1d", help="캔들 간격 (default: 1d)")
    parser.add_argument("--days", "-d", type=int, default=180, help="분석 기간 (default: 180)")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    print(f"Loading OHLCV: {args.symbol}, {args.interval}, {args.days}days...")
    data = load_ohlcv(args.symbol, args.interval, args.days)
    # load_ohlcv returns DataFrame — convert to list of dicts
    import pandas as pd
    if isinstance(data, pd.DataFrame):
        if data.empty:
            print("ERROR: No data loaded")
            sys.exit(1)
        candles = data.to_dict("records")
        for c in candles:
            if hasattr(c.get("timestamp"), "isoformat"):
                c["timestamp"] = c["timestamp"].isoformat()
    else:
        candles = data
    if not candles:
        print("ERROR: No data loaded")
        sys.exit(1)
    print(f"Loaded {len(candles)} candles")

    analysis = analyze(candles)
    suggestion = suggest_params(analysis)

    if args.json:
        output = {
            "symbol": args.symbol,
            "interval": args.interval,
            "analysis": analysis,
            "suggestion": suggestion,
        }
        print(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    else:
        report = format_report(args.symbol, args.interval, analysis, suggestion)
        print(report)


if __name__ == "__main__":
    main()
