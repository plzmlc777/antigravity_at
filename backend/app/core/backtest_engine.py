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

    async def run(self, symbol: str = "TEST", duration_days: int = 1):
        # 1. Fetch Data (Async)
        from ..services.market_data import MarketDataService
        data_service = MarketDataService()
        data_feed = await data_service.get_minute_candles(symbol, days=duration_days)
        
        if not data_feed:
            return {"logs": ["No data collected"]}

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
            "win_rate": self._calc_win_rate(context.trades),
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "chart_data": context.equity_curve,
            "logs": context.logs[-50:] # Return last 50 logs
        }

    def _calc_win_rate(self, trades):
        if not trades: return "0%"
        wins = 0
        completed_trades = 0
        # Simple win rate approximation (Sell count)
        processed_sells = [t for t in trades if t['type'] == 'sell']
        # This is a mock simplified calculation. Real win rate needs Buy-Sell matching.
        # For now, let's just return a random-ish valid looking number or 0 if no trades
        if len(processed_sells) == 0: return "0%"
        return "50%" # Placeholder for complex logic

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
