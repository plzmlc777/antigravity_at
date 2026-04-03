#!/usr/bin/env python3
"""
A/B 테스트: baseline(기본 파라미터) vs AI 추천 파라미터 비교.

기존 at-backtest 인프라를 재사용하여 두 설정으로 백테스트 실행 후 결과 비교.

Usage:
    # 규칙 기반 AI 추천 vs 기본 파라미터
    python3 ab_test.py --symbol 005930 --strategy dip_martingale --interval 1d --days 365

    # 커스텀 파라미터 vs 기본 파라미터
    python3 ab_test.py --symbol 005930 --strategy dip_martingale --interval 1d --days 365 \
        --custom '{"dip_percent": 1.5, "level_gap_percent": 3.0}'

    # JSON 출력
    python3 ab_test.py --symbol 005930 --strategy dip_martingale --days 365 --json
"""

import sys
import json
import argparse
from pathlib import Path

# at-backtest 스크립트 경로 추가
BACKTEST_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "at-backtest" / "scripts"
sys.path.insert(0, str(BACKTEST_SCRIPTS))

# 같은 디렉토리의 analyze_symbol 임포트
STRATEGY_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(STRATEGY_SCRIPTS))

from backtest import run_backtest
from metrics import format_results
from fetch_data import load_ohlcv
from analyze_symbol import analyze, suggest_params


# dip_martingale 기본 파라미터 (PARAMETER_SCHEMA의 default 값)
DEFAULT_CONFIGS = {
    "dip_martingale": {
        "dip_percent": 1.0,
        "level_gap_percent": 2.0,
        "trailing_start_percent": 2.0,
        "trailing_stop_percent": 1.0,
        "max_buy_count": 4,
        "max_loss_percent": 10.0,
        "betting_strategy": "fixed",
        "base_quantity": 1,
        "qty_mode": "fixed",
    },
}


def run_ab_test(symbol: str, strategy: str, interval: str, days: int,
                capital: float, custom_config: dict = None) -> dict:
    """A/B 테스트 실행: baseline vs recommended(또는 custom)."""

    # --- Step 1: 데이터 로드 ---
    import pandas as pd
    print(f"\n[1/4] Loading OHLCV: {symbol}, {interval}, {days}days...")
    data = load_ohlcv(symbol, interval, days)
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return {"error": "No data loaded"}
        candles = data.to_dict("records")
        for c in candles:
            if hasattr(c.get("timestamp"), "isoformat"):
                c["timestamp"] = c["timestamp"].isoformat()
    else:
        candles = data
    if not candles:
        return {"error": "No data loaded"}
    print(f"  Loaded {len(candles)} candles")

    # --- Step 2: 종목 분석 + 파라미터 추천 ---
    print(f"\n[2/4] Analyzing symbol characteristics...")
    analysis = analyze(candles)
    suggestion = suggest_params(analysis)

    # 설정 준비
    baseline_config = DEFAULT_CONFIGS.get(strategy, {}).copy()

    if custom_config:
        recommended_config = {**baseline_config, **custom_config}
        config_source = "custom"
    else:
        recommended_config = {**baseline_config, **suggestion["recommended_config"]}
        config_source = "rule-based AI"

    # --- Step 3: 두 설정으로 백테스트 실행 ---
    print(f"\n[3/4] Running backtests...")
    print(f"  A (baseline): {json.dumps({k: baseline_config[k] for k in ['dip_percent', 'level_gap_percent', 'trailing_start_percent', 'max_buy_count']})}")
    print(f"  B ({config_source}): {json.dumps({k: recommended_config[k] for k in ['dip_percent', 'level_gap_percent', 'trailing_start_percent', 'max_buy_count']})}")

    result_a = run_backtest(
        strategy_name=strategy,
        symbol=symbol,
        interval=interval,
        days=days,
        initial_capital=capital,
        config=baseline_config,
    )

    result_b = run_backtest(
        strategy_name=strategy,
        symbol=symbol,
        interval=interval,
        days=days,
        initial_capital=capital,
        config=recommended_config,
    )

    # --- Step 4: 비교 ---
    print(f"\n[4/4] Comparing results...")

    comparison = compare_results(result_a, result_b, config_source)

    return {
        "symbol": symbol,
        "strategy": strategy,
        "interval": interval,
        "days": days,
        "candle_count": len(candles),
        "analysis_summary": {
            "volatility": analysis["volatility"]["level"],
            "avg_intra_vol": analysis["volatility"]["avg_intra_candle_pct"],
            "trend": analysis["trend"]["direction"],
            "avg_dip": analysis["dip_analysis"]["avg_dip_on_bearish_pct"],
        },
        "baseline_config": baseline_config,
        "recommended_config": recommended_config,
        "config_source": config_source,
        "reasoning": suggestion.get("reasoning", {}),
        "result_a": result_to_dict(result_a),
        "result_b": result_to_dict(result_b),
        "comparison": comparison,
    }


def result_to_dict(result) -> dict:
    """BacktestResult → 비교용 dict."""
    return {
        "total_return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "total_cycles": result.total_cycles,
        "win_rate": result.win_rate,
        "sharpe_ratio": result.sharpe_ratio,
        "profit_factor": result.profit_factor,
        "avg_pnl": result.avg_pnl,
        "max_profit": result.max_profit,
        "max_loss": result.max_loss,
        "avg_holding_time": result.avg_holding_time,
        "stability_score": result.stability_score,
    }


def compare_results(result_a, result_b, config_source: str) -> dict:
    """두 결과 비교 + 승자 판정."""
    metrics = [
        ("total_return", "총 수익률 (%)", True),      # True = 높을수록 좋음
        ("max_drawdown", "최대 낙폭 (%)", False),      # False = 낮을수록(절대값 작을수록) 좋음 (음수)
        ("total_cycles", "총 사이클", True),
        ("win_rate", "승률 (%)", True),
        ("sharpe_ratio", "샤프 비율", True),
        ("profit_factor", "수익 팩터", True),
        ("avg_holding_time", "평균 보유시간", False),    # 짧을수록 효율적
        ("stability_score", "안정성 점수", True),
    ]

    details = []
    a_wins = 0
    b_wins = 0

    for key, label, higher_is_better in metrics:
        val_a = getattr(result_a, key, 0) or 0
        val_b = getattr(result_b, key, 0) or 0

        if higher_is_better:
            if key == "max_drawdown":
                # MDD is negative; closer to 0 is better
                winner = "B" if val_b > val_a else ("A" if val_a > val_b else "TIE")
            else:
                winner = "B" if val_b > val_a else ("A" if val_a > val_b else "TIE")
        else:
            # For max_drawdown (negative), higher (less negative) is better
            if key == "max_drawdown":
                winner = "B" if val_b > val_a else ("A" if val_a > val_b else "TIE")
            else:
                winner = "B" if val_b < val_a else ("A" if val_a < val_b else "TIE")

        if winner == "A":
            a_wins += 1
        elif winner == "B":
            b_wins += 1

        details.append({
            "metric": key,
            "label": label,
            "baseline": val_a,
            "recommended": val_b,
            "winner": winner,
        })

    # 종합 판정: 수익률 + 샤프가 모두 B가 이기면 B 채택
    return_winner = next((d["winner"] for d in details if d["metric"] == "total_return"), "TIE")
    sharpe_winner = next((d["winner"] for d in details if d["metric"] == "sharpe_ratio"), "TIE")

    if return_winner == "B" and sharpe_winner == "B":
        verdict = "ADOPT_B"
        verdict_kr = "AI 추천 채택 (수익률 + 샤프 모두 우위)"
    elif return_winner == "B" or sharpe_winner == "B":
        verdict = "CONSIDER_B"
        verdict_kr = "AI 추천 검토 필요 (일부 지표 우위)"
    elif return_winner == "A" and sharpe_winner == "A":
        verdict = "KEEP_A"
        verdict_kr = "기본 파라미터 유지 (baseline 우위)"
    else:
        verdict = "INCONCLUSIVE"
        verdict_kr = "판단 불가 (추가 테스트 필요)"

    return {
        "a_wins": a_wins,
        "b_wins": b_wins,
        "details": details,
        "verdict": verdict,
        "verdict_kr": verdict_kr,
    }


def format_comparison(result: dict) -> str:
    """비교 결과를 사람이 읽기 좋은 형식으로."""
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  A/B 테스트 결과: {result['symbol']} / {result['strategy']} / {result['interval']}")
    lines.append(f"{'='*70}")

    a_sum = result["analysis_summary"]
    lines.append(f"\n  종목 특성: 변동성={a_sum['volatility']}, 추세={a_sum['trend']}, "
                 f"캔들내변동={a_sum['avg_intra_vol']:.2f}%, 평균dip={a_sum['avg_dip']:.2f}%")

    lines.append(f"\n  {'지표':<16} {'A (baseline)':>14} {'B (추천)':>14} {'승자':>6}")
    lines.append(f"  {'-'*54}")

    for d in result["comparison"]["details"]:
        a_val = d["baseline"]
        b_val = d["recommended"]

        # 포맷팅
        if d["metric"] in ("total_return", "max_drawdown", "win_rate"):
            a_str = f"{a_val:.2f}%"
            b_str = f"{b_val:.2f}%"
        elif d["metric"] in ("sharpe_ratio", "profit_factor", "stability_score"):
            a_str = f"{a_val:.3f}"
            b_str = f"{b_val:.3f}"
        elif d["metric"] == "total_cycles":
            a_str = f"{int(a_val)}"
            b_str = f"{int(b_val)}"
        elif d["metric"] == "avg_holding_time":
            a_str = f"{a_val}"
            b_str = f"{b_val}"
        else:
            a_str = f"{a_val}"
            b_str = f"{b_val}"

        winner_mark = "◀ A" if d["winner"] == "A" else ("B ▶" if d["winner"] == "B" else " = ")
        lines.append(f"  {d['label']:<16} {a_str:>14} {b_str:>14} {winner_mark:>6}")

    comp = result["comparison"]
    lines.append(f"\n  {'─'*54}")
    lines.append(f"  점수: A={comp['a_wins']}승 / B={comp['b_wins']}승")
    lines.append(f"\n  ▶ 판정: {comp['verdict_kr']}")

    # 추천 근거
    if result.get("reasoning"):
        lines.append(f"\n  추천 근거:")
        for param, reason in result["reasoning"].items():
            rec_val = result["recommended_config"].get(param, "?")
            base_val = result["baseline_config"].get(param, "?")
            if rec_val != base_val:
                lines.append(f"    {param}: {base_val} → {rec_val}  ({reason})")

    lines.append(f"\n{'='*70}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="A/B 테스트: baseline vs AI 추천")
    parser.add_argument("--symbol", required=True, help="종목 코드")
    parser.add_argument("--strategy", "-s", default="dip_martingale", help="전략 (default: dip_martingale)")
    parser.add_argument("--interval", "-i", default="1d", help="캔들 간격 (default: 1d)")
    parser.add_argument("--days", "-d", type=int, default=365, help="백테스트 기간 (default: 365)")
    parser.add_argument("--capital", "-c", type=float, default=10_000_000, help="초기 자본 (default: 10M)")
    parser.add_argument("--custom", type=str, default=None, help="커스텀 파라미터 JSON")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    custom_config = json.loads(args.custom) if args.custom else None

    result = run_ab_test(
        symbol=args.symbol,
        strategy=args.strategy,
        interval=args.interval,
        days=args.days,
        capital=args.capital,
        custom_config=custom_config,
    )

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    else:
        print(format_comparison(result))


if __name__ == "__main__":
    main()
