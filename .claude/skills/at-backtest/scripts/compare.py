#!/usr/bin/env python3
"""
Result Comparator - API 결과 vs 독립 엔진 결과 비교
BacktestEngine(API)과 독립 스크립트의 결과가 동일한지 검증한다.

Usage:
    python compare.py --strategy dip_martingale --symbol 005930 --interval 1d --days 365
    python compare.py --strategy ema_momentum --symbol ETHUSDT --interval 1h --days 90
"""

import argparse
import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

from backtest import run_backtest

# API base URL
API_BASE = "http://localhost:8001/api/v1/strategies"


def get_api_result(
    strategy: str,
    symbol: str,
    interval: str,
    days: int,
    capital: float,
    config: Dict = None,
    exchange: str = None,
) -> Optional[Dict]:
    """
    기존 BacktestEngine API를 호출하여 결과를 가져온다.
    """
    if exchange is None:
        exchange = "Kiwoom" if symbol.isdigit() else "Binance"

    payload = {
        "symbol": symbol,
        "interval": interval,
        "days": days,
        "initial_capital": capital,
        "config": config or {},
        "exchange_name": exchange,
    }

    cmd = [
        "curl", "-s", "-m", "300",
        "-X", "POST",
        f"{API_BASE}/{strategy}/backtest",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=310)
        if result.returncode != 0:
            print(f"API call failed: {result.stderr}")
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print("API call timed out (300s)")
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from API: {e}")
        print(f"Response: {result.stdout[:500]}")
        return None


def compare_results(api: Dict, standalone: Dict) -> Dict[str, Any]:
    """
    두 결과를 비교하여 차이를 분석한다.

    Returns: {
        "match": True/False,
        "differences": [{field, api_val, standalone_val, diff, diff_pct}],
        "summary": str,
    }
    """
    compare_fields = [
        ("total_return", 0.5),       # 0.5% 오차 허용
        ("max_drawdown", 0.5),
        ("win_rate", 1.0),           # 1% 허용
        ("total_cycles", 0),         # 정확히 일치
        ("avg_pnl", 0.5),
        ("profit_factor", 0.2),
        ("sharpe_ratio", 0.2),
        ("activity_rate", 2.0),
        ("stability_score", 0.05),
        ("acceleration_score", 0.1),
    ]

    differences = []
    all_match = True

    for field, tolerance in compare_fields:
        api_val = api.get(field, 0)
        std_val = standalone.get(field, 0)

        # Handle string values (e.g., "-10.32%")
        if isinstance(api_val, str):
            api_val = float(api_val.replace("%", "").replace(",", ""))
        if isinstance(std_val, str):
            std_val = float(std_val.replace("%", "").replace(",", ""))

        api_val = float(api_val) if api_val else 0
        std_val = float(std_val) if std_val else 0

        diff = abs(api_val - std_val)

        if field == "total_cycles":
            match = api_val == std_val
        else:
            match = diff <= tolerance

        if not match:
            all_match = False

        diff_pct = (diff / abs(api_val) * 100) if api_val != 0 else (0 if diff == 0 else 100)

        differences.append({
            "field": field,
            "api": api_val,
            "standalone": std_val,
            "diff": round(diff, 4),
            "diff_pct": round(diff_pct, 2),
            "match": "OK" if match else "DIFF",
            "tolerance": tolerance,
        })

    # Summary
    matched = sum(1 for d in differences if d["match"] == "OK")
    total = len(differences)

    summary = f"Match: {matched}/{total} fields"
    if all_match:
        summary += " - ALL PASSED"
    else:
        failed = [d["field"] for d in differences if d["match"] != "OK"]
        summary += f" - FAILED: {', '.join(failed)}"

    return {
        "match": all_match,
        "differences": differences,
        "summary": summary,
    }


def print_comparison_table(comparison: Dict, strategy: str, symbol: str):
    """비교 결과를 테이블로 출력."""
    print(f"\n{'='*75}")
    print(f"  Comparison: {strategy} / {symbol}")
    print(f"  API (BacktestEngine) vs Standalone (scripts/backtest.py)")
    print(f"{'='*75}")
    print(f"  {'Field':22s} {'API':>12s} {'Standalone':>12s} {'Diff':>8s} {'Status':>8s}")
    print(f"  {'-'*62}")

    for d in comparison["differences"]:
        status_str = "  OK  " if d["match"] == "OK" else "**DIFF**"
        api_str = f"{d['api']:.4f}" if isinstance(d['api'], float) else str(d['api'])
        std_str = f"{d['standalone']:.4f}" if isinstance(d['standalone'], float) else str(d['standalone'])

        print(f"  {d['field']:22s} {api_str:>12s} {std_str:>12s} {d['diff']:>8.4f} {status_str:>8s}")

    print(f"  {'-'*62}")
    print(f"  {comparison['summary']}")
    print(f"{'='*75}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare API BacktestEngine results vs Standalone script results"
    )
    parser.add_argument("--strategy", "-s", required=True, help="Strategy name")
    parser.add_argument("--symbol", required=True, help="Symbol")
    parser.add_argument("--interval", "-i", default="1d", help="Interval (default: 1d)")
    parser.add_argument("--days", "-d", type=int, default=365, help="Days (default: 365)")
    parser.add_argument("--capital", "-c", type=float, default=10_000_000, help="Initial capital")
    parser.add_argument("--config", help="Strategy config as JSON")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    config = json.loads(args.config) if args.config else {}

    print(f"[1/3] Running API backtest ({args.strategy} / {args.symbol})...")
    api_result = get_api_result(
        args.strategy, args.symbol, args.interval, args.days, args.capital, config
    )

    if api_result is None:
        print("ERROR: API call failed. Is the backend running?")
        sys.exit(1)

    if "detail" in api_result:
        print(f"ERROR: API returned error: {api_result['detail']}")
        sys.exit(1)

    print(f"   API: {api_result.get('total_cycles', 0)} cycles, "
          f"return={api_result.get('total_return', 0)}%")

    print(f"\n[2/3] Running Standalone backtest...")
    standalone_result = run_backtest(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
        initial_capital=args.capital,
        config=config,
    )

    standalone_dict = {
        "total_return": standalone_result.total_return,
        "max_drawdown": standalone_result.max_drawdown,
        "win_rate": standalone_result.win_rate,
        "total_cycles": standalone_result.total_cycles,
        "avg_pnl": standalone_result.avg_pnl,
        "profit_factor": standalone_result.profit_factor,
        "sharpe_ratio": standalone_result.sharpe_ratio,
        "activity_rate": standalone_result.activity_rate,
        "stability_score": standalone_result.stability_score,
        "acceleration_score": standalone_result.acceleration_score,
    }

    print(f"   Standalone: {standalone_result.total_cycles} cycles, "
          f"return={standalone_result.total_return}%")

    print(f"\n[3/3] Comparing results...")
    comparison = compare_results(api_result, standalone_dict)

    if args.json:
        print(json.dumps(comparison, indent=2, ensure_ascii=False))
    else:
        print_comparison_table(comparison, args.strategy, args.symbol)


if __name__ == "__main__":
    main()
