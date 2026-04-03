#!/usr/bin/env python3
"""
Binance Parameter Optimizer - at-backtest optimize를 바이낸스 설정으로 래핑.

Usage:
    python optimize_binance.py --symbol BTCUSDT --strategy dip_martingale \
        --interval 1h --days 90 --leverage 5 \
        --param "dip_threshold=1.0,2.0,3.0" \
        --param "trailing_start_percent=1.0,2.0,3.0"
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "../../at-backtest/scripts"))

from optimize import run_optimization, format_optimization_results, parse_param_args


def main():
    parser = argparse.ArgumentParser(description="Binance Parameter Optimizer")
    parser.add_argument("--symbol", required=True, help="Symbol (e.g., BTCUSDT)")
    parser.add_argument("--strategy", "-s", default="dip_martingale", help="Strategy")
    parser.add_argument("--interval", "-i", default="1h", help="Interval (default: 1h)")
    parser.add_argument("--days", "-d", type=int, default=90, help="Days (default: 90)")
    parser.add_argument("--capital", "-c", type=float, default=10000, help="Capital USDT")
    parser.add_argument("--leverage", type=int, default=1, help="Leverage (default: 1)")
    parser.add_argument("--spot", action="store_true", help="Spot mode")
    parser.add_argument("--param", action="append", default=[], help="key=v1,v2,v3")
    parser.add_argument("--top", type=int, default=10, help="Top N results")
    parser.add_argument("--workers", "-w", type=int, default=1, help="Parallel workers")
    parser.add_argument("--base-qty", type=float, default=None, help="Base quantity")
    parser.add_argument("--qty-mode", default="fixed", help="Qty mode")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    exchange = "Binance" if args.spot else "BinanceFutures"
    leverage = 1 if args.spot else args.leverage

    base_config = {
        "exchange_name": exchange,
        "leverage": leverage,
        "qty_mode": args.qty_mode,
    }
    if args.base_qty is not None:
        base_config["base_quantity"] = args.base_qty

    param_grid = parse_param_args(args.param) if args.param else None

    results = run_optimization(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
        initial_capital=args.capital,
        base_config=base_config,
        param_grid=param_grid,
        top_n=args.top,
        workers=args.workers,
    )

    if args.json:
        output = []
        for r in results:
            output.append({
                "rank": len(output) + 1,
                "score": r["score"],
                "config": r["config"],
                "total_return": r["result"].total_return,
                "max_drawdown": r["result"].max_drawdown,
                "win_rate": r["result"].win_rate,
                "total_cycles": r["result"].total_cycles,
                "sharpe_ratio": r["result"].sharpe_ratio,
            })
        print(json.dumps(output, indent=2))
    else:
        print(format_optimization_results(results, args.strategy))


if __name__ == "__main__":
    main()
