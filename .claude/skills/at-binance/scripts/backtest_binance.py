#!/usr/bin/env python3
"""
Binance Backtest Wrapper - at-backtest 엔진을 바이낸스 설정으로 래핑.

Usage:
    python backtest_binance.py --symbol BTCUSDT --strategy dip_martingale \
        --interval 1h --days 90 --leverage 5

    python backtest_binance.py --symbol ETHUSDT --strategy ema_momentum \
        --interval 4h --days 180 --spot  # Spot mode (no leverage)
"""

import argparse
import json
import sys
from pathlib import Path

# at-backtest scripts path
sys.path.insert(0, str(Path(__file__).parent / "../../at-backtest/scripts"))

from backtest import run_backtest
from metrics import format_results


def main():
    parser = argparse.ArgumentParser(description="Binance Backtest")
    parser.add_argument("--symbol", required=True, help="Symbol (e.g., BTCUSDT)")
    parser.add_argument("--strategy", "-s", default="dip_martingale", help="Strategy")
    parser.add_argument("--interval", "-i", default="1h", help="Interval (default: 1h)")
    parser.add_argument("--days", "-d", type=int, default=90, help="Days (default: 90)")
    parser.add_argument("--capital", "-c", type=float, default=10000, help="Capital in USDT (default: 10000)")
    parser.add_argument("--leverage", type=int, default=1, help="Leverage (default: 1)")
    parser.add_argument("--spot", action="store_true", help="Use spot exchange (no leverage)")
    parser.add_argument("--base-qty", type=float, default=None, help="Base quantity")
    parser.add_argument("--qty-mode", default="fixed", help="Qty mode: fixed or percent")
    parser.add_argument("--config", help="Extra config as JSON")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--compare", action="store_true", help="Compare with API result")

    args = parser.parse_args()

    exchange = "Binance" if args.spot else "BinanceFutures"
    leverage = 1 if args.spot else args.leverage

    config = {
        "exchange_name": exchange,
        "leverage": leverage,
        "qty_mode": args.qty_mode,
    }
    if args.base_qty is not None:
        config["base_quantity"] = args.base_qty
    if args.config:
        config.update(json.loads(args.config))

    print(f"Binance Backtest: {args.strategy} / {args.symbol}")
    print(f"  Exchange: {exchange}, Leverage: {leverage}x")
    print(f"  Interval: {args.interval}, Days: {args.days}, Capital: {args.capital} USDT")
    print()

    result = run_backtest(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
        initial_capital=args.capital,
        config=config,
    )

    if args.json:
        output = {
            "strategy_id": result.strategy_id,
            "symbol": args.symbol,
            "exchange": exchange,
            "leverage": leverage,
            "total_return": result.total_return,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "total_cycles": result.total_cycles,
            "sharpe_ratio": result.sharpe_ratio,
            "profit_factor": result.profit_factor,
            "stability_score": result.stability_score,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(result))

    if args.compare:
        print("\n--- API Comparison ---")
        sys.path.insert(0, str(Path(__file__).parent / "../../at-backtest/scripts"))
        from compare import get_api_result, compare_results, print_comparison_table

        api_result = get_api_result(
            args.strategy, args.symbol, args.interval, args.days, args.capital, config
        )
        if api_result:
            standalone_dict = {
                "total_return": result.total_return,
                "max_drawdown": result.max_drawdown,
                "win_rate": result.win_rate,
                "total_cycles": result.total_cycles,
                "avg_pnl": result.avg_pnl,
                "profit_factor": result.profit_factor,
                "sharpe_ratio": result.sharpe_ratio,
                "activity_rate": result.activity_rate,
                "stability_score": result.stability_score,
                "acceleration_score": result.acceleration_score,
            }
            comparison = compare_results(api_result, standalone_dict)
            print_comparison_table(comparison, args.strategy, args.symbol)


if __name__ == "__main__":
    main()
