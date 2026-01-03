from typing import List, Dict, Any
from datetime import datetime
from .backtest_engine import BacktestEngine

class IntegratedBacktestEngine(BacktestEngine):
    """
    Subclass of BacktestEngine specifically for Integrated Backtests.
    Overrides methods to provide enhanced visualization data (Matched Trades, Multi-Symbol OHLCV)
    without affecting the base class used by Single Strategies.
    """

    def _generate_stats(self, context, data_feed, feeds_map: Dict[str, List] = None):
        """
        Overrides base _generate_stats to include 'multi_ohlcv_data' and 'matched_trades'.
        Reuses base logic where possible, but re-implements return construction.
        """
        # Calculate Base Stats (Equity, Return, etc.)
        final_equity = context.equity_curve[-1]['equity'] if context.equity_curve else 0
        initial_equity = context.equity_curve[0]['equity'] if context.equity_curve else 1
        
        if not context.equity_curve:
             return { "total_return": "0%", "logs": context.logs, "win_rate": "0%", "chart_data": [], "ohlcv_data": [], "matched_trades": [] }

        total_return = (final_equity - initial_equity) / initial_equity * 100
        
        # Multi-Symbol OHLCV Processing (Exclusive to Integrated Engine)
        multi_ohlcv_data = {}
        if feeds_map:
            for sym, feed in feeds_map.items():
                multi_ohlcv_data[sym] = self._resample_ohlcv(feed, 2000)
        
        # Activity Rate Logic (Copied from Base or potentially refactored if Base exposes it)
        # For now, duplicate specific small logic to ensure independence.
        data_dates = set()
        for c in data_feed:
             try: data_dates.add(datetime.fromisoformat(c['timestamp']).date())
             except: pass
        
        traded_dates = set()
        for t in context.trades:
             try: traded_dates.add(datetime.fromisoformat(t['time']).date())
             except: pass
        
        total_days = len(data_dates)
        traded_count = len(traded_dates)
        activity_rate = (traded_count / total_days * 100) if total_days > 0 else 0

        # Return Enhanced Dictionary
        return {
            "total_return": f"{total_return:.2f}%",
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "activity_rate": f"{activity_rate:.1f}%",
            "total_days": total_days,
            "chart_data": self._resample_equity(context.equity_curve, 2000),
            "ohlcv_data": self._resample_ohlcv(data_feed, 2000),
            "multi_ohlcv_data": multi_ohlcv_data, # New Key
            "logs": context.logs,
            "trades": context.trades, # Raw Execution Trades
            **self._analyze_trades(context.trades, data_feed[0]['timestamp'], data_feed[-1]['timestamp']) # Calls Overridden Method below
        }

    def _analyze_trades(self, trades: List[Dict], start_ts: Any = None, end_ts: Any = None) -> Dict[str, Any]:
        """
        Overrides base _analyze_trades to include 'matched_trades' logic.
        This provides Round-Trip trade analysis for the Replay UI.
        """
        base_stats = super()._analyze_trades(trades, start_ts, end_ts)
        
        if not trades:
            base_stats['matched_trades'] = []
            return base_stats

        # Additional Logic for Matched Trades (Replay Data)
        # This matches Buy/Sell pairs to calculate realized PnL per trade.
        buy_queue = []
        completed_trades = []

        for t in trades:
            if t['type'] == 'buy':
                buy_queue.append({
                    'price': t['price'], 
                    'quantity': t['quantity'],
                    'time': t['time'],
                    'symbol': t['symbol']
                })
            elif t['type'] == 'sell':
                qty_to_sell = t['quantity']
                sell_price = t['price']
                sell_time = datetime.fromisoformat(t['time'])
                
                while qty_to_sell > 0 and buy_queue:
                    # Match with oldest buy for this symbol (FIFO) - Wait, base logic was global FIFO in simple mock.
                    # Here we should verify symbol matching if not already guaranteed by queue structure?
                    # Base logic was simple FIFO.
                    # Let's improve it: Filter buy_queue for matching symbol?
                    # The 'buy_queue' in this loop is global.
                    # We should match symbol.
                    
                    # Find first buy match for symbol
                    match_idx = -1
                    for i, b in enumerate(buy_queue):
                        if b['symbol'] == t['symbol']:
                            match_idx = i
                            break
                    
                    if match_idx == -1:
                        break # No buy found for this symbol (Short selling not fully supported in this simple logic)
                    
                    buy_order = buy_queue[match_idx]
                    matched_qty = min(qty_to_sell, buy_order['quantity'])
                    
                    cost = matched_qty * buy_order['price']
                    revenue = matched_qty * sell_price
                    profit = revenue - cost
                    profit_percent = (sell_price - buy_order['price']) / buy_order['price'] * 100 # Percentage for UI
                    
                    buy_time = datetime.fromisoformat(buy_order['time'])
                    holding_seconds = (sell_time - buy_time).total_seconds()
                    
                    completed_trades.append({
                        'symbol': t['symbol'],
                        'entry_price': buy_order['price'],
                        'exit_price': sell_price,
                        'entry_time': buy_order['time'],
                        'exit_time': t['time'],
                        'quantity': matched_qty,
                        'pnl': profit,
                        'pnl_percent': profit_percent,
                        'holding_seconds': holding_seconds,
                        'strategy_name': t.get('strategy_rank', 'Unknown')
                    })
                    
                    qty_to_sell -= matched_qty
                    buy_order['quantity'] -= matched_qty
                    
                    if buy_order['quantity'] == 0:
                        buy_queue.pop(match_idx)

        # Merge new data into base stats
        base_stats['matched_trades'] = completed_trades
        return base_stats
