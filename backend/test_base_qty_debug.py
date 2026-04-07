"""
Debug script: Trace equity flow for different base_qty values on WIFUSDT.
Run: cd backend && python3 test_base_qty_debug.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.waterfall_engine import WaterfallBacktestEngine, BacktestContext
from app.core.strategy_registry import StrategyRegistry
from app.core.data_schemas import EQUITY_VALUE_KEY, EQUITY_DATE_KEY


async def run_test(base_qty, exchange_name="Binance"):
    """Run a single backtest with given base_qty and trace equity."""

    # Get strategy class
    strategy_class = StrategyRegistry.get_strategy_class("dip_martingale")
    if not strategy_class:
        print("ERROR: dip_martingale not found in registry")
        return

    # Fetch WIFUSDT data
    from app.services.market_data_factory import get_market_data_service
    data_service = get_market_data_service(exchange_name)

    symbol = "WIFUSDT"
    interval = "5m"  # Match user's config
    days = 730
    from_date = "2026-01-01"
    to_date = "2026-02-24"

    initial_capital = 500  # Low capital test

    print(f"\n{'='*60}")
    print(f"TEST: base_qty={base_qty}, symbol={symbol}, capital={initial_capital}")
    print(f"{'='*60}")

    feed = await data_service.get_candles(symbol, interval=interval, days=days, to_date=to_date)
    if not feed:
        print("ERROR: No data for WIFUSDT")
        return

    if from_date:
        feed = [c for c in feed if c['timestamp'] >= from_date]
    feed.sort(key=lambda x: x['timestamp'])
    print(f"Data: {len(feed)} candles, from {feed[0]['timestamp'][:10]} to {feed[-1]['timestamp'][:10]}")
    print(f"Price range: {min(c['close'] for c in feed):.4f} - {max(c['close'] for c in feed):.4f}")
    print(f"Last price: {feed[-1]['close']:.4f}")

    # Match user's exact config
    config = {
        "symbol": symbol,
        "exchange_name": exchange_name,
        "strategy_id": "DipMartingaleStrategy",
        "base_quantity": base_qty,
        "qty_mode": "fixed",
        "max_buy_count": 200,
        "lot_size_multiplier": 1.5,
        "trailing_start_percent": 1.5,
        "trailing_stop_percent": 0,
        "max_loss_percent": 0,
        "betting_strategy": "compound",
        "safety_margin_percent": 1.0,
        "last_level_allin": "off",
        "use_martingale": "on",
        "additional_buy_mode": "step",
        "additional_buy_step": 2.0,
        "additional_buy_step_ref": "avg_price",
        "require_lower_price": "on",
        "dip_threshold_percent": 1,
        "level_gap_percent": 1,
        "interval": "5m",
        "leverage": 1,
        "liq_floor_percent": 3,
    }

    # Create engine and run
    engine = WaterfallBacktestEngine(strategy_class, config, exchange_name=exchange_name)

    result = await engine.run_single_backtest(
        config=config,
        feed=feed,
        initial_capital=initial_capital,
        symbol=symbol,
        optimize_mode=False,
        rank=1
    )

    # Print results
    print(f"\n--- Results ---")
    print(f"total_return: {result.get('total_return', 'N/A')}")
    print(f"total_trades (cycles): {result.get('total_trades', 'N/A')}")
    print(f"win_rate: {result.get('win_rate', 'N/A')}")
    print(f"avg_pnl: {result.get('avg_pnl', 'N/A')}")
    print(f"max_profit: {result.get('max_profit', 'N/A')}")
    print(f"max_loss: {result.get('max_loss', 'N/A')}")
    print(f"sharpe_ratio: {result.get('sharpe_ratio', 'N/A')}")
    print(f"profit_factor: {result.get('profit_factor', 'N/A')}")

    # Equity curve analysis
    eq = result.get('equity_curve', [])
    if eq:
        initial_eq = eq[0][EQUITY_VALUE_KEY]
        final_eq = eq[-1][EQUITY_VALUE_KEY]
        min_eq = min(e[EQUITY_VALUE_KEY] for e in eq)
        max_eq = max(e[EQUITY_VALUE_KEY] for e in eq)
        print(f"\n--- Equity Curve ({len(eq)} points) ---")
        print(f"Initial: {initial_eq:,.4f}")
        print(f"Final:   {final_eq:,.4f}")
        print(f"Min:     {min_eq:,.4f}")
        print(f"Max:     {max_eq:,.4f}")
        print(f"Computed return: {(final_eq - initial_eq) / initial_eq * 100:.6f}%")

    # Trade analysis
    trades = result.get('trades', [])
    buys = [t for t in trades if t['type'] == 'buy']
    sells = [t for t in trades if t['type'] == 'sell']
    print(f"\n--- Trades ---")
    print(f"Total records: {len(trades)} (buys: {len(buys)}, sells: {len(sells)})")

    if buys:
        buy_qtys = [t['quantity'] for t in buys]
        buy_prices = [t['price'] for t in buys]
        buy_costs = [t['quantity'] * t['price'] for t in buys]
        print(f"Buy qty range: {min(buy_qtys):.6f} - {max(buy_qtys):.6f}")
        print(f"Buy price range: {min(buy_prices):.4f} - {max(buy_prices):.4f}")
        print(f"Buy cost range: ${min(buy_costs):.4f} - ${max(buy_costs):.4f}")
        print(f"Avg buy cost: ${sum(buy_costs)/len(buy_costs):.4f}")
        print(f"Total buy cost: ${sum(buy_costs):,.2f}")

        # Level distribution from buys
        level_costs = {}
        for t in buys:
            lv = t.get('metadata', {}).get('level', 1)
            if lv not in level_costs:
                level_costs[lv] = {'count': 0, 'total_cost': 0}
            level_costs[lv]['count'] += 1
            level_costs[lv]['total_cost'] += t['quantity'] * t['price']

        print(f"\nBuy level distribution:")
        for lv in sorted(level_costs.keys())[:15]:
            info = level_costs[lv]
            avg = info['total_cost'] / info['count']
            print(f"  L{lv}: {info['count']} buys, avg cost=${avg:.2f}, total=${info['total_cost']:.2f}")
        if len(level_costs) > 15:
            remaining = {k: v for k, v in level_costs.items() if k > 15}
            r_count = sum(v['count'] for v in remaining.values())
            r_total = sum(v['total_cost'] for v in remaining.values())
            print(f"  L16+: {r_count} buys, total=${r_total:,.2f}")

    if sells:
        sell_revenues = [t['quantity'] * t['price'] for t in sells]
        print(f"\nSell revenue range: ${min(sell_revenues):.4f} - ${max(sell_revenues):,.4f}")
        print(f"Total sell revenue: ${sum(sell_revenues):,.2f}")

    # Reconstruct cycles for profit verification
    print(f"\n--- Cycle Profit Reconstruction ---")
    cycles = []
    current_buys = []
    for t in trades:
        if t['type'] == 'buy':
            current_buys.append(t)
        elif t['type'] == 'sell' and current_buys:
            total_cost = sum(b['price'] * b['quantity'] for b in current_buys)
            total_qty = sum(b['quantity'] for b in current_buys)
            avg_price = total_cost / total_qty if total_qty > 0 else 0
            sell_revenue = t['price'] * t['quantity']
            pnl = sell_revenue - total_cost
            pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0
            cycles.append({
                'cost': total_cost,
                'revenue': sell_revenue,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'num_buys': len(current_buys),
                'max_level': max(b.get('metadata', {}).get('level', 1) for b in current_buys),
            })
            current_buys = []

    if current_buys:
        open_cost = sum(b['price'] * b['quantity'] for b in current_buys)
        open_levels = max(b.get('metadata', {}).get('level', 1) for b in current_buys)
        print(f"  ** Open position: {len(current_buys)} buys, cost=${open_cost:,.2f}, max_level=L{open_levels}")

    print(f"  Completed cycles: {len(cycles)}")
    if cycles:
        total_pnl = sum(c['pnl'] for c in cycles)
        avg_pnl_pct = sum(c['pnl_pct'] for c in cycles) / len(cycles)
        avg_cost = sum(c['cost'] for c in cycles) / len(cycles)
        wins = sum(1 for c in cycles if c['pnl'] > 0)

        print(f"  Win rate: {wins}/{len(cycles)} = {wins/len(cycles)*100:.1f}%")
        print(f"  Avg cycle cost (investment): ${avg_cost:,.2f}")
        print(f"  Avg cycle PnL%: {avg_pnl_pct:.4f}%")
        print(f"  Total PnL (sum): ${total_pnl:,.2f}")
        print(f"  Expected return = total_pnl/initial_capital: {total_pnl/initial_capital*100:.6f}%")

        # Level distribution
        levels = {}
        for c in cycles:
            lv = c['max_level']
            levels[lv] = levels.get(lv, 0) + 1
        print(f"  Level distribution: {dict(sorted(levels.items()))}")

        # Top 5 most expensive cycles
        sorted_by_cost = sorted(cycles, key=lambda c: c['cost'], reverse=True)
        print(f"\n  Top 5 most expensive cycles:")
        for i, c in enumerate(sorted_by_cost[:5]):
            print(f"    #{i+1}: L{c['max_level']} ({c['num_buys']} buys), cost=${c['cost']:,.2f}, "
                  f"pnl=${c['pnl']:,.2f} ({c['pnl_pct']:.4f}%)")

    return result


async def main():
    test_qtys = [0.01, 1, 100]

    for qty in test_qtys:
        try:
            await run_test(qty)
        except Exception as e:
            print(f"\nERROR for base_qty={qty}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
