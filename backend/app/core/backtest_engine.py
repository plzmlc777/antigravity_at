import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..strategies.base import IContext, BaseStrategy

class BacktestContext(IContext):
    def __init__(self, data_feed: List[Dict]):
        self.data_feed = data_feed
        self.current_index = 0
        self.cash = 10000000 # 10 Million KRW
        self.holdings = {} # {symbol: quantity}
        self.trades = []
        self.logs = []
        self.equity_curve = []

    @property
    def current_candle(self):
        if 0 <= self.current_index < len(self.data_feed):
            return self.data_feed[self.current_index]
        return None

    def get_time(self) -> datetime:
        if self.current_candle:
            return datetime.fromisoformat(self.current_candle['timestamp'])
        return datetime.now()

    def get_current_price(self, symbol: str) -> float:
        if self.current_candle:
            return self.current_candle['close']
        return 0

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        exec_price = price if price > 0 else self.get_current_price(symbol)
        cost = exec_price * quantity
        
        if self.cash >= cost:
            self.cash -= cost
            self.holdings[symbol] = self.holdings.get(symbol, 0) + quantity
            
            trade = {
                "type": "buy",
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat()
            }
            self.trades.append(trade)
            self.log(f"BUY EXECUTED: {quantity} @ {exec_price}")
            return trade
        else:
            self.log("BUY FAILED: Insufficient Funds")
            return {"status": "failed", "reason": "Insufficient Funds"}

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        current_qty = self.holdings.get(symbol, 0)
        if current_qty >= quantity:
            exec_price = price if price > 0 else self.get_current_price(symbol)
            revenue = exec_price * quantity
            
            self.cash += revenue
            self.holdings[symbol] -= quantity
            
            trade = {
                "type": "sell",
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat()
            }
            self.trades.append(trade)
            self.log(f"SELL EXECUTED: {quantity} @ {exec_price}")
            return trade
        else:
            self.log("SELL FAILED: Insufficient Holdings")
            return {"status": "failed", "reason": "Insufficient Holdings"}

    def log(self, message: str):
        self.logs.append(f"[{self.get_time().strftime('%H:%M:%S')}] {message}")

    def update_equity(self):
        equity = self.cash
        current_price = self.get_current_price("TEST") # Assuming single symbol for now
        for symbol, qty in self.holdings.items():
            equity += qty * current_price
        
        self.equity_curve.append({
            "date": self.get_time().strftime("%Y-%m-%d %H:%M"),
            "equity": int(equity)
        })

class SyntheticDataGenerator:
    @staticmethod
    def generate_ohlcv(minutes=60, start_price=70000, volatility=0.002) -> List[Dict]:
        data = []
        current_price = start_price
        base_time = datetime.now() - timedelta(minutes=minutes)
        
        for i in range(minutes):
            open_p = current_price
            change = random.gauss(0, volatility)
            close_p = open_p * (1 + change)
            high_p = max(open_p, close_p) * (1 + abs(random.gauss(0, volatility/2)))
            low_p = min(open_p, close_p) * (1 - abs(random.gauss(0, volatility/2)))
            
            timestamp = (base_time + timedelta(minutes=i)).isoformat()
            
            data.append({
                "timestamp": timestamp,
                "open": int(open_p),
                "high": int(high_p),
                "low": int(low_p),
                "close": int(close_p),
                "volume": random.randint(1000, 5000)
            })
            current_price = close_p
            
        return data

class BacktestEngine:
    def __init__(self, strategy_class, config: Dict = None):
        self.strategy_class = strategy_class
        self.config = config or {}

    async def run(self, symbol: str = "TEST", duration_days: int = 1, from_date: str = None):
        # 1. Fetch Data (Async)
        from ..services.market_data import MarketDataService
        data_service = MarketDataService()
        data_feed = await data_service.get_candles(symbol, interval="1m", days=duration_days)
        
        if not data_feed:
            return {"logs": ["No data collected"]}

        # Filter by Start Date
        if from_date:
            try:
                # Assuming data_feed timestamp is ISO format string compatible with comparison
                # YYYY-MM-DD string comparison works if data is YYYY-MM-DD HH:MM:SS
                filtered_feed = [c for c in data_feed if c['timestamp'] >= from_date]
                if filtered_feed:
                    data_feed = filtered_feed
            except Exception as e:
                print(f"Date filter error: {e}")

        # 2. Setup Context
        context = BacktestContext(data_feed)
        
        # 3. Initialize Strategy
        # Inject Symbol into config if needed
        self.config['symbol'] = symbol
        strategy = self.strategy_class(context, self.config)
        strategy.initialize()
        
        # 4. Run Loop
        for i, candle in enumerate(data_feed):
            context.current_index = i
            strategy.on_data(candle)
            context.update_equity()
            
        # 5. Calculate Stats
        if not context.equity_curve:
             return {"logs": context.logs, "total_return": "0%", "win_rate": "0%", "max_drawdown": "0%", "chart_data": []}

        final_equity = context.equity_curve[-1]['equity']
        initial_equity = context.equity_curve[0]['equity']
        total_return = (final_equity - initial_equity) / initial_equity * 100
        
        return {
            "total_return": f"{total_return:.2f}%",
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "chart_data": context.equity_curve,
            "logs": context.logs[-50:], # Return last 50 logs
            **self._analyze_trades(context.trades) # Inject detailed trade stats
        }

    def _analyze_trades(self, trades: List[Dict]) -> Dict[str, Any]:
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": "0%",
                "avg_pnl": "0%",
                "max_profit": "0%",
                "max_loss": "0%"
            }

        # FIFO Trade Matching
        buy_queue = [] # List of {'price': float, 'quantity': int}
        completed_trades = [] # List of {'pnl': float, 'pnl_percent': float, 'volume': float}

        for t in trades:
            if t['type'] == 'buy':
                buy_queue.append({'price': t['price'], 'quantity': t['quantity']})
            elif t['type'] == 'sell':
                qty_to_sell = t['quantity']
                sell_price = t['price']
                
                while qty_to_sell > 0 and buy_queue:
                    # Match with oldest buy
                    buy_order = buy_queue[0]
                    matched_qty = min(qty_to_sell, buy_order['quantity'])
                    
                    # Calculate PnL for this chunk
                    cost = matched_qty * buy_order['price']
                    revenue = matched_qty * sell_price
                    profit = revenue - cost
                    profit_percent = (sell_price - buy_order['price']) / buy_order['price']
                    
                    completed_trades.append({
                        'pnl': profit,
                        'pnl_percent': profit_percent,
                        'volume': revenue
                    })
                    
                    # Update remaining quantities
                    qty_to_sell -= matched_qty
                    buy_order['quantity'] -= matched_qty
                    
                    if buy_order['quantity'] == 0:
                        buy_queue.pop(0)

        # Calculate Statistics
        if not completed_trades:
            return {
                "total_trades": 0,
                "win_rate": "0%",
                "avg_pnl": "0%",
                "max_profit": "0%",
                "max_loss": "0%"
            }

        total_count = len(completed_trades)
        wins = [t for t in completed_trades if t['pnl'] > 0]
        loss = [t for t in completed_trades if t['pnl'] <= 0]
        
        win_rate = len(wins) / total_count * 100
        
        avg_pnl_percent = sum(t['pnl_percent'] for t in completed_trades) / total_count * 100
        
        # Max Profit / Loss (in %)
        max_profit = max([t['pnl_percent'] for t in completed_trades]) * 100 if completed_trades else 0
        max_loss = min([t['pnl_percent'] for t in completed_trades]) * 100 if completed_trades else 0

        return {
            "total_trades": total_count,
            "win_rate": f"{win_rate:.1f}%",
            "avg_pnl": f"{avg_pnl_percent:.2f}%",
            "max_profit": f"{max_profit:.2f}%",
            "max_loss": f"{max_loss:.2f}%"
        }

    def _calc_mdd(self, equity_curve):
        if not equity_curve: return "0%"
        peak = equity_curve[0]['equity']
        max_dd = 0
        for point in equity_curve:
            val = point['equity']
            if val > peak: peak = val
            dd = (peak - val) / peak
            if dd > max_dd: max_dd = dd
        return f"-{max_dd*100:.2f}%"
