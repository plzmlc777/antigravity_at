#!/usr/bin/env python3
"""Debug: compare first N trades between skill engine and backend."""
import warnings; warnings.filterwarnings('ignore')
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from backtest import _load_candles
from strategies import get_strategy
from execution_engine import BacktestExecutor, StrategyAdapter

# Load same data as backend
df = _load_candles('RIVERUSDT', '1m', 7, source='db')
candles = df.to_dict('records')
print(f"Candles loaded: {len(candles)}")
print(f"Period: {candles[0]['timestamp']} ~ {candles[-1]['timestamp']}")
print()

# Initialize
config = {}
strategy = get_strategy('rsi_martingale', config)
strategy._initialize_trigger()

executor = BacktestExecutor(initial_capital=500, leverage=1, config=config)
adapter = StrategyAdapter(strategy)

# Run full backtest
for i, candle in enumerate(candles):
    ts = candle['timestamp']
    if not isinstance(ts, datetime):
        ts = datetime.fromisoformat(str(ts))

    price = candle['close']
    executor.on_candle(candle, strategy, ts)
    signals = adapter.process_candle(candle, ts, price, executor)
    adapter.execute_signals(signals, executor, ts, price)
    executor.record_equity(price, ts)

# Force liquidate
if strategy.current_level > 0:
    final_price = candles[-1]['close']
    final_ts = candles[-1]['timestamp']
    if not isinstance(final_ts, datetime):
        final_ts = datetime.fromisoformat(str(final_ts))
    executor._last_trade = None
    executor.force_liquidate(strategy, final_price, final_ts)

# Print summary
print(f"Total raw trades: {len(executor.raw_trades)}")
print(f"Final cash: {executor.cash:.2f}")
print(f"Final holdings: {executor.holdings}")
print(f"Strategy level: {strategy.current_level}")
print()

# Print first 20 trades
print("First 20 raw trades:")
for i, t in enumerate(executor.raw_trades[:20]):
    ttype = t.get('type', '?')
    qty = t.get('quantity', '?')
    price = t.get('price', '?')
    ts = str(t.get('timestamp', '?'))[:19]
    level = t.get('metadata', {}).get('level', '-')
    print(f"  [{i:3d}] {ttype:5s} qty={qty:6} @ {price:10} | {ts} | L{level}")

# Count buy/sell
buys = [t for t in executor.raw_trades if t.get('type') == 'buy']
sells = [t for t in executor.raw_trades if t.get('type') == 'sell']
print(f"\nBuys: {len(buys)}, Sells: {len(sells)}")

# Calculate metrics
from metrics import calculate_metrics
timestamps = [c['timestamp'] for c in candles]
result = calculate_metrics(
    adapter.trades, executor.equity_curve, timestamps,
    500, 'rsi_martingale', raw_trades=executor.raw_trades,
)
print(f"\n=== SKILL RESULTS ===")
print(f"Return: {result.total_return:.4f}%")
print(f"Cycles: {result.total_cycles}")
print(f"Win Rate: {result.win_rate:.2f}%")
print(f"MDD: {result.max_drawdown:.4f}%")
print(f"Profit Factor: {result.profit_factor:.4f}")
print(f"Sharpe: {result.sharpe_ratio:.4f}")
