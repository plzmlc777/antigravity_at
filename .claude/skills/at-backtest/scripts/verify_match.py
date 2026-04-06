#!/usr/bin/env python3
"""
Backend vs Independent Skill 백테스트 결과 비교 검증.

동일 조건(종목, 기간, 전략, 파라미터)으로 두 엔진을 실행하고
거래 내역, 수익률, MDD 등이 100% 일치하는지 검증한다.

Usage:
    python verify_match.py --symbol BTCUSDT --strategy rsi_martingale --interval 1h --days 30
    python verify_match.py --symbol RIVERUSDT --strategy rsi_martingale --interval 1m --days 7 --futures
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

from backtest import run_backtest
from fetch_exchange import load_ohlcv_exchange

# Backend API URL
API_URL = "http://localhost:8001"


def run_backend_backtest(
    strategy_name: str,
    symbol: str,
    interval: str,
    days: int,
    initial_capital: float,
    config: Dict[str, Any],
    from_date: str = None,
    to_date: str = None,
) -> Optional[Dict]:
    """Backend API를 통한 백테스트 실행."""
    payload = {
        "strategy_name": strategy_name,
        "symbol": symbol,
        "interval": interval,
        "days": days,
        "initial_capital": initial_capital,
        "config": config or {},
    }
    if from_date:
        payload["from_date"] = from_date
    if to_date:
        payload["to_date"] = to_date

    try:
        url = f"{API_URL}/api/v1/strategies/{strategy_name}/backtest"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[Backend API Error] {e}")
        return None


def compare_results(backend: Dict, skill_result, config: Dict) -> Dict:
    """두 결과를 비교하고 차이를 리포트."""
    comparisons = {}

    # Metric mapping: backend key → skill attribute
    metrics = [
        ("total_return", "total_return", "%", 0.01),
        ("win_rate", "win_rate", "%", 0.01),
        ("max_drawdown", "max_drawdown", "%", 0.01),
        ("total_cycles", "total_cycles", "", 0),
        ("profit_factor", "profit_factor", "", 0.01),
        ("sharpe_ratio", "sharpe_ratio", "", 0.01),
        ("activity_rate", "activity_rate", "%", 0.1),
        ("avg_pnl", "avg_pnl", "", 0.01),
        ("avg_holding_time", "avg_holding_time", "h", 0.1),
    ]

    all_match = True

    for be_key, sk_attr, unit, tolerance in metrics:
        be_val = backend.get(be_key, backend.get("metrics", {}).get(be_key, None))
        sk_val = getattr(skill_result, sk_attr, None)

        if be_val is None or sk_val is None:
            comparisons[be_key] = {
                "backend": be_val, "skill": sk_val,
                "diff": "N/A", "match": be_val is None and sk_val is None,
            }
            continue

        try:
            be_val = float(be_val)
            sk_val = float(sk_val)
        except (ValueError, TypeError):
            comparisons[be_key] = {
                "backend": be_val, "skill": sk_val,
                "diff": "type_error", "match": False,
            }
            all_match = False
            continue

        diff = abs(be_val - sk_val)
        match = diff <= tolerance if tolerance > 0 else be_val == sk_val

        if not match:
            all_match = False

        comparisons[be_key] = {
            "backend": be_val, "skill": sk_val,
            "diff": round(diff, 6), "match": match,
        }

    return {"comparisons": comparisons, "all_match": all_match}


def print_comparison_report(
    symbol: str, strategy: str, interval: str, days: int,
    backend_result: Dict, skill_result, comparison: Dict,
):
    """비교 결과를 포맷팅하여 출력."""
    print("=" * 70)
    print(f"  BACKTEST COMPARISON: Backend API vs Independent Skill")
    print(f"  {strategy} / {symbol} / {interval} / {days}d")
    print("=" * 70)
    print()

    header = f"{'Metric':<22} {'Backend':>12} {'Skill':>12} {'Diff':>10} {'Match':>6}"
    print(header)
    print("-" * len(header))

    for key, vals in comparison["comparisons"].items():
        be = vals["backend"]
        sk = vals["skill"]
        diff = vals["diff"]
        match = "✓" if vals["match"] else "✗"

        be_str = f"{be:.4f}" if isinstance(be, float) else str(be)
        sk_str = f"{sk:.4f}" if isinstance(sk, float) else str(sk)
        diff_str = f"{diff:.6f}" if isinstance(diff, float) else str(diff)

        print(f"{key:<22} {be_str:>12} {sk_str:>12} {diff_str:>10} {match:>6}")

    print()
    if comparison["all_match"]:
        print("  ✅ ALL METRICS MATCH — 백엔드와 독립 스킬 결과 일치!")
    else:
        mismatches = [k for k, v in comparison["comparisons"].items() if not v["match"]]
        print(f"  ❌ MISMATCH in: {', '.join(mismatches)}")

    # Trade count comparison
    be_cycles = backend_result.get("total_cycles",
                    backend_result.get("metrics", {}).get("total_cycles", "?"))
    sk_cycles = skill_result.total_cycles
    print(f"\n  Cycles: Backend={be_cycles}, Skill={sk_cycles}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Backend vs Skill 백테스트 비교 검증")
    parser.add_argument("--strategy", "-s", default="rsi_martingale")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", "-i", default="1h")
    parser.add_argument("--days", "-d", type=int, default=30)
    parser.add_argument("--capital", "-c", type=float, default=10_000_000)
    parser.add_argument("--config", help="Strategy config JSON string")
    parser.add_argument("--from-date", help="Start date YYYY-MM-DD")
    parser.add_argument("--to-date", help="End date YYYY-MM-DD")
    parser.add_argument("--futures", action="store_true")
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--skill-only", action="store_true",
                        help="독립 스킬만 실행 (Backend 비교 없이)")

    args = parser.parse_args()

    global API_URL
    API_URL = args.api_url

    config = json.loads(args.config) if args.config else {}

    print(f"\n{'='*70}")
    print(f"  Backtest Verification")
    print(f"  Strategy: {args.strategy}")
    print(f"  Symbol: {args.symbol} ({'futures' if args.futures else 'spot'})")
    print(f"  Interval: {args.interval} | Days: {args.days}")
    print(f"  Capital: {args.capital:,.0f}")
    print(f"{'='*70}\n")

    # ─── Run Independent Skill Backtest ───
    print("[1/2] Running independent skill backtest...")
    skill_result = run_backtest(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
        initial_capital=args.capital,
        config=config,
        from_date=args.from_date,
        to_date=args.to_date,
        source="db",  # 비교 시 동일 데이터소스 사용
        futures=args.futures,
    )
    print(f"  → Skill: return={skill_result.total_return:.2f}%, "
          f"cycles={skill_result.total_cycles}, "
          f"MDD={skill_result.max_drawdown:.2f}%")

    if args.skill_only:
        from metrics import format_results
        print()
        print(format_results(skill_result))
        return

    # ─── Run Backend API Backtest ───
    print("[2/2] Running backend API backtest...")
    backend_result = run_backend_backtest(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
        initial_capital=args.capital,
        config=config,
        from_date=args.from_date,
        to_date=args.to_date,
    )

    if backend_result is None:
        print("  → Backend API not available. Showing skill-only results:")
        from metrics import format_results
        print(format_results(skill_result))
        return

    be_return = backend_result.get("total_return",
                    backend_result.get("metrics", {}).get("total_return", "?"))
    be_cycles = backend_result.get("total_cycles",
                    backend_result.get("metrics", {}).get("total_cycles", "?"))
    be_mdd = backend_result.get("max_drawdown",
                backend_result.get("metrics", {}).get("max_drawdown", "?"))
    print(f"  → Backend: return={be_return}%, cycles={be_cycles}, MDD={be_mdd}%")

    # ─── Compare ───
    print()
    comparison = compare_results(backend_result, skill_result, config)
    print_comparison_report(
        args.symbol, args.strategy, args.interval, args.days,
        backend_result, skill_result, comparison,
    )


if __name__ == "__main__":
    main()
