#!/usr/bin/env python3
"""Side-by-side trade comparison: StrategyAdapter vs Backend native."""
import warnings; warnings.filterwarnings('ignore')
import os, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# Load env
root = Path('/home/hcpark/antigravity')
env_path = root / '.env'
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

sys.path.insert(0, str(root / 'backend'))

from fetch_data import load_ohlcv

# Load data once
df = load_ohlcv('RIVERUSDT', '1m', days=7)
candles = df.to_dict('records')
print(f"Candles: {len(candles)}")

# ─── Run 1: StrategyAdapter (skill engine) ───
from strategies import get_strategy
from execution_engine import BacktestExecutor, StrategyAdapter

strategy_a = get_strategy('rsi_martingale', {})
strategy_a._initialize_trigger()
executor_a = BacktestExecutor(initial_capital=500, leverage=1, config={})
adapter_a = StrategyAdapter(strategy_a)

for candle in candles:
    ts = candle['timestamp']
    if not isinstance(ts, datetime): ts = datetime.fromisoformat(str(ts))
    price = candle['close']
    executor_a.on_candle(candle, strategy_a, ts)
    signals = adapter_a.process_candle(candle, ts, price, executor_a)
    adapter_a.execute_signals(signals, executor_a, ts, price)
    executor_a.record_equity(price, ts)

trades_a = executor_a.raw_trades

# ─── Run 2: Backend native (strategy.on_data) ───
from backtest_native import BacktestContext, _load_backend_strategy

feeds = {'RIVERUSDT': candles}
ctx_b = BacktestContext(feeds, 500, 'RIVERUSDT', leverage=1)
strategy_class = _load_backend_strategy('rsi_martingale')
strat_b = strategy_class(ctx_b, {'initial_capital': 500, 'symbol': 'RIVERUSDT'})
strat_b.initialize()

for i, candle in enumerate(candles):
    ts = candle['timestamp']
    if not isinstance(ts, datetime): ts = datetime.fromisoformat(str(ts))
    ctx_b.current_timestamp = ts
    ctx_b._current_candle = candle
    ctx_b._current_index = i
    try:
        strat_b.on_data(candle)
    except Exception:
        pass
    ctx_b.update_equity()

trades_b = ctx_b.trades

# ─── Compare ───
print(f"\nTrades: Adapter={len(trades_a)}, Native={len(trades_b)}")
print()

# Find first divergence
max_compare = min(len(trades_a), len(trades_b), 30)
print(f"{'#':>4} | {'Adapter':^30} | {'Native':^30} | Match")
print("-" * 80)

diverge_idx = None
for i in range(max_compare):
    ta = trades_a[i]
    tb = trades_b[i]

    ta_str = f"{ta.get('type','?'):5s} {ta.get('quantity',0):5} @ {ta.get('price',0):8.3f}"
    tb_str = f"{tb.get('type','?'):5s} {tb.get('quantity',0):5} @ {tb.get('price',0):8.3f}"

    ta_type = ta.get('type')
    tb_type = tb.get('type')
    ta_qty = ta.get('quantity', 0)
    tb_qty = tb.get('quantity', 0)
    ta_price = ta.get('price', 0)
    tb_price = tb.get('price', 0)

    match = (ta_type == tb_type and ta_qty == tb_qty and abs(ta_price - tb_price) < 0.001)
    marker = "  ✓" if match else "  ✗ ←"

    print(f"{i:4d} | {ta_str:^30} | {tb_str:^30} | {marker}")

    if not match and diverge_idx is None:
        diverge_idx = i

if diverge_idx is not None:
    print(f"\n⚠ First divergence at trade #{diverge_idx}")
else:
    print(f"\n✅ All {max_compare} trades match!")
