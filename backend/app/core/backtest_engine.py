import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..strategies.base import IContext, BaseStrategy

class BacktestContext(IContext):
    def __init__(self, data_feed: List[Dict], initial_capital: int = 10000000):
        self.data_feed = data_feed
        self.current_index = 0
        self.cash = initial_capital
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
            ts = self.current_candle['timestamp']
            if isinstance(ts, datetime):
                return ts
            return datetime.fromisoformat(ts)
        return datetime.now()

    def get_current_price(self, symbol: str) -> float:
        if self.current_candle:
            return self.current_candle['close']
        return 0

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        exec_price = price if price > 0 else self.get_current_price(symbol)
        cost = exec_price * quantity
        
        # Simulation Mode: Allow negative cash to support "Fixed Betting" regardless of drawdown
        # if self.cash >= cost: 
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

    async def run(self, symbol: str = "TEST", duration_days: int = 1, from_date: str = None, interval: str = "1m", initial_capital: int = 10000000):
        # 1. Fetch Data (Async)
        from ..services.market_data import MarketDataService
        data_service = MarketDataService()
        data_feed = await data_service.get_candles(symbol, interval=interval, days=duration_days)
        
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
        context = BacktestContext(data_feed, initial_capital=initial_capital)
        
        # 3. Initialize Strategy
        # Inject Symbol and Initial Capital into config
        self.config['symbol'] = symbol
        self.config['initial_capital'] = initial_capital
        strategy = self.strategy_class(context, self.config)
        strategy.initialize()
        
        # 4. Run Loop
        for i, candle in enumerate(data_feed):
            context.current_index = i
            strategy.on_data(candle)
            context.update_equity()
            
        # 5. Calculate Stats
        # 5. Calculate Stats
        if not context.equity_curve:
             return {"logs": context.logs, "total_return": "0%", "win_rate": "0%", "max_drawdown": "0%", "chart_data": [], "activity_rate": "0%"}

        final_equity = context.equity_curve[-1]['equity']
        initial_equity = context.equity_curve[0]['equity']
        total_return = (final_equity - initial_equity) / initial_equity * 100
        
        # Activity Rate Calculation
        data_dates = set()
        for c in data_feed:
             try:
                 ts = c['timestamp']
                 if isinstance(ts, datetime):
                     dt = ts.date()
                 else:
                     dt = datetime.fromisoformat(ts).date()
                 data_dates.add(dt)
             except: pass
             
        traded_dates = set()
        for t in context.trades:
             try:
                 ts = t['time']
                 # Trades always use isoformat string from get_time, 
                 # BUT if get_time() crashed before, they might be empty/weird.
                 # Assuming get_time() fixed above returns valid datetime, then .isoformat() is string.
                 # So t['time'] is string.
                 dt = datetime.fromisoformat(ts).date()
                 traded_dates.add(dt)
             except: pass
        
        total_days = len(data_dates)
        traded_count = len(traded_dates)
        activity_rate = (traded_count / total_days * 100) if total_days > 0 else 0
        
        return {
            "total_return": f"{total_return:.2f}%",
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "activity_rate": f"{activity_rate:.1f}% ({traded_count}/{total_days} days)",
            "chart_data": self._resample_equity(context.equity_curve, 2000), # Resampled Equity for LineChart
            "ohlcv_data": self._resample_ohlcv(data_feed, 2000), # Resampled Candles for VisualBacktestChart
            "logs": context.logs[-50:], # Return last 50 logs
            "trades": context.trades, # List of trades for visual markers
            **self._analyze_trades(context.trades, data_feed[0]['timestamp'], data_feed[-1]['timestamp']) # Inject detailed trade stats
        }

    def _analyze_trades(self, trades: List[Dict], start_ts: Any = None, end_ts: Any = None) -> Dict[str, Any]:
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
                buy_queue.append({
                    'price': t['price'], 
                    'quantity': t['quantity'],
                    'time': t['time'] # Store time
                })
            elif t['type'] == 'sell':
                qty_to_sell = t['quantity']
                sell_price = t['price']
                sell_time = datetime.fromisoformat(t['time'])
                
                while qty_to_sell > 0 and buy_queue:
                    # Match with oldest buy
                    buy_order = buy_queue[0]
                    matched_qty = min(qty_to_sell, buy_order['quantity'])
                    
                    # Calculate PnL for this chunk
                    cost = matched_qty * buy_order['price']
                    revenue = matched_qty * sell_price
                    profit = revenue - cost
                    profit_percent = (sell_price - buy_order['price']) / buy_order['price']
                    
                    # Calculate Holding Time
                    buy_time = datetime.fromisoformat(buy_order['time'])
                    holding_seconds = (sell_time - buy_time).total_seconds()
                    
                    completed_trades.append({
                        'pnl': profit,
                        'pnl_percent': profit_percent,
                        'volume': revenue,
                        'holding_seconds': holding_seconds,
                        'time': t['time'] # Store Sell Time for Decile Analysis
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
                "max_loss": "0%",
                "profit_factor": "0.0",
                "sharpe_ratio": "0.0",
                "avg_holding_time": "0m",
                "decile_stats": []
            }

        total_count = len(completed_trades)
        wins = [t for t in completed_trades if t['pnl'] > 0]
        loss = [t for t in completed_trades if t['pnl'] <= 0]
        
        win_rate = len(wins) / total_count * 100
        
        avg_pnl_percent = sum(t['pnl_percent'] for t in completed_trades) / total_count * 100
        
        # Max Profit / Loss (in %)
        max_profit = max([t['pnl_percent'] for t in completed_trades]) * 100 if completed_trades else 0
        max_loss = min([t['pnl_percent'] for t in completed_trades]) * 100 if completed_trades else 0
        
        # Profit Factor
        gross_profit = sum(t['pnl'] for t in wins)
        gross_loss = abs(sum(t['pnl'] for t in loss))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99 # Infinite if no loss
        
        # Avg Holding Time
        total_holding_sec = sum(t.get('holding_seconds', 0) for t in completed_trades)
        avg_holding_sec = total_holding_sec / total_count if total_count > 0 else 0
        avg_holding_min = int(avg_holding_sec / 60)
        
        # Sharpe Ratio (Simplified Estimate using Trade Returns)
        # Ideally use daily returns, but trade-based Sharpe is a useful proxy for shorter-term strategies
        # Sharpe = (Mean Return / StdDev Return) * sqrt(Trades Per Year)
        # Check std deviation
        import statistics
        returns = [t['pnl_percent'] for t in completed_trades]
        if len(returns) > 1:
            stdev = statistics.stdev(returns)
            sharpe = (statistics.mean(returns) / stdev * (len(returns)**0.5)) if stdev > 0 else 0
        else:
            sharpe = 0

        # Calculate Activity Rate (Trades per Day)
        # Parse TS if string
        def parse_ts(t): return t if isinstance(t, datetime) else datetime.fromisoformat(str(t).replace('Z', '+00:00'))
        
        start_dt = parse_ts(start_ts)
        end_dt = parse_ts(end_ts)
        
        days = (end_dt - start_dt).days
        activity_rate = f"{total_count / days * 100:.1f}%" if days > 0 else "0%"

        # Calculate Monthly Stats & Stability
        decile_data = self._calc_deciles(completed_trades, start_ts, end_ts)

        return {
            "total_trades": total_count,
            "win_rate": f"{win_rate:.1f}%",
            "avg_pnl": f"{avg_pnl_percent:.2f}%",
            "max_profit": f"{max_profit:.2f}%",
            "max_loss": f"{max_loss:.2f}%",
            "profit_factor": f"{profit_factor:.2f}",
            "sharpe_ratio": f"{sharpe:.2f}",
            "activity_rate": activity_rate,
            "avg_holding_time": f"{avg_holding_min}m",
            "decile_stats": decile_data['monthly_stats'],
            "stability_score": str(decile_data['stability_score']),
            "acceleration_score": str(decile_data['acceleration_score'])
        }

    def _calc_deciles(self, trades: List[Dict], start_ts: Any, end_ts: Any) -> List[Dict]:
        """
        Calculates Periodic Stats (Monthly).
        Returns a list of stats for each month in the range.
        Key 'decile_stats' is kept for frontend compatibility but now represents 'Monthly Stats'.
        """
        # Helper to parse TS
        def parse(t): return t if isinstance(t, datetime) else datetime.fromisoformat(t)
        
        start_dt = parse(start_ts).date()
        end_dt = parse(end_ts).date()
        
        # Normalize to start of month
        curr = start_dt.replace(day=1)
        end_cap = end_dt.replace(day=1)
        
        stats = []
        block_idx = 1
        
        while curr <= end_cap:
            # Calculate Next Month
            if curr.month == 12:
                next_month = curr.replace(year=curr.year + 1, month=1)
            else:
                next_month = curr.replace(month=curr.month + 1)
                
            # Define Range [curr, next_month)
            # Filter trades
            chunk = []
            for t in trades:
                t_date = parse(t['time']).date()
                if curr <= t_date < next_month:
                    chunk.append(t)
            
            # Stats
            if chunk:
                # User requested Realized Return (Total PnL for the month)
                # We sum the PnL percentages to show the total monthly performance.
                total_pnl = sum(t['pnl_percent'] for t in chunk) * 100
                avg_pnl = total_pnl / len(chunk)
                
                wins = len([t for t in chunk if t['pnl'] > 0])
                win_rate = wins / len(chunk) * 100
            else:
                total_pnl = 0.0
                avg_pnl = 0.0
                win_rate = 0.0
                
            date_label = curr.strftime("%y-%m")
            
            stats.append({
                "block": date_label, 
                "avg_pnl": float(f"{avg_pnl:.2f}"), # Keep for legacy/tooltip if needed, or just use total
                "total_pnl": float(f"{total_pnl:.2f}"), # New Metric: Monthly Total Return
                "win_rate": float(f"{win_rate:.1f}"),
                "date_range": date_label,
                "count": len(chunk)
            })
            
            curr = next_month
            block_idx += 1
            
        # Calculate Stability Score (R-squared of Cumulative PnL)
        # This measures how close the equity curve is to a straight line (consistent growth).
        try:
            if stats:
                import numpy as np
                from scipy import stats as scipy_stats
                
                # Cumulative PnL Curve
                daily_returns = [s['total_pnl'] for s in stats]
                cumulative = np.cumsum(daily_returns)
                
                # Linear Regression vs Time Index
                x = np.arange(len(cumulative))
                slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, cumulative)
                
                # Stability Score
                if len(cumulative) > 1:
                    stability_score = r_value ** 2 
                else:
                    stability_score = 0.0

                # Calculate Profit Acceleration (Recent Slope / Total Slope)
                # Recent = Last 25% of data (min 5 points)
                n_recent = max(5, int(len(cumulative) * 0.25))
                
                if len(cumulative) >= 10: # Only calculate if we have enough data
                    recent_cum = cumulative[-n_recent:]
                    x_recent = np.arange(len(recent_cum))
                    slope_recent, _, _, _, _ = scipy_stats.linregress(x_recent, recent_cum)
                    
                    # Avoid division by zero
                    if abs(slope) > 0.0001:
                        acceleration_score = slope_recent / slope
                    else:
                        acceleration_score = 0.0 # Define as 0 if overall is flat
                else:
                    acceleration_score = 1.0 # Neutral if not enough data

            else:
                stability_score = 0.0
                acceleration_score = 0.0
        except Exception as e:
            print(f"Error calculating stats: {e}")
            stability_score = 0.0
            acceleration_score = 0.0

        return {
            "monthly_stats": stats,
            "stability_score": float(f"{stability_score:.2f}"),
            "acceleration_score": float(f"{acceleration_score:.2f}")
        }

    def _resample_ohlcv(self, data: List[Dict], target_count: int = 2000) -> List[Dict]:
        if not data: return []
        if len(data) <= target_count:
            return [{
                "time": int(datetime.fromisoformat(d['timestamp']).timestamp()), # Use Unix Timestamp for Intraday support
                "open": d['open'],
                "high": d['high'],
                "low": d['low'],
                "close": d['close']
            } for d in data]
            
        # Simple interval sampling
        import math
        step = math.ceil(len(data) / target_count)
        resampled = []
        
        for i in range(0, len(data), step):
            chunk = data[i:i+step]
            if not chunk: continue
            
            # Aggregate chunk
            o = chunk[0]['open']
            c = chunk[-1]['close']
            h = max(x['high'] for x in chunk)
            l = min(x['low'] for x in chunk)
            t = chunk[0]['timestamp']
            
            resampled.append({
                "time": int(datetime.fromisoformat(t).timestamp()), # Use Unix Timestamp
                "open": o,
                "high": h,
                "low": l,
                "close": c
            })
            
        return resampled

    def _resample_equity(self, data: List[Dict], target_count: int = 2000) -> List[Dict]:
        if not data: return []
        if len(data) <= target_count: return data
        
        import math
        step = math.ceil(len(data) / target_count)
        resampled = []
        for i in range(0, len(data), step):
            resampled.append(data[i])
        return resampled

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
