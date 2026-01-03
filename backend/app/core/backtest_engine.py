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
        for symbol, qty in self.holdings.items():
            equity += qty * self.get_current_price(symbol)
        
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
            return {
                "logs": ["No data collected"],
                "total_return": "0%",
                "win_rate": "0%",
                "max_drawdown": "0%",
                "activity_rate": "0%",
                "total_trades": 0,
                "score": 0,
                "avg_pnl": "0%",
                "max_profit": "0%",
                "max_loss": "0%",
                "profit_factor": "0.00",
                "sharpe_ratio": "0.00",
                "avg_holding_time": "0m",
                "stability_score": "0.00",
                "acceleration_score": "0.00",
                "chart_data": [],
                "ohlcv_data": []
            }

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
             return {
                 "logs": context.logs, 
                 "total_return": "0%", 
                 "win_rate": "0%", 
                 "max_drawdown": "0%", 
                 "activity_rate": "0%",
                 "total_trades": 0,
                 "avg_pnl": "0%",
                 "max_profit": "0%",
                 "max_loss": "0%",
                 "profit_factor": "0.00",
                 "sharpe_ratio": "0.00",
                 "avg_holding_time": "0m",
                 "stability_score": "0.00",
                 "acceleration_score": "0.00",
                 "chart_data": [],
                 "ohlcv_data": []
             }

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
            "activity_rate": f"{activity_rate:.1f}%",
            "total_days": total_days, # Expose for UI
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
                "max_loss": "0%",
                "profit_factor": "0.00",
                "sharpe_ratio": "0.00",
                "avg_holding_time": "0m",
                "stability_score": "0.00",
                "acceleration_score": "0.00",
                "decile_stats": [],
                "activity_rate": "0%"
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
            # "activity_rate": activity_rate, # Removed to prevent overwrite
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
        return f"-{max_dd * 100:.2f}%"
    async def run_integrated_simulation(self, strategies_config: List[Dict], symbol: str = "TEST", duration_days: int = 1, from_date: str = None, interval: str = "1m", initial_capital: int = 10000000):
        # 1. Fetch Data (Multi-Symbol Support)
        from ..services.market_data import MarketDataService
        data_service = MarketDataService()
        
        # Identify all unique symbols needed
        needed_symbols = set()
        # Also include the default 'symbol' param as a fallback or if it represents the "Main" ticker
        needed_symbols.add(symbol) 
        
        for cfg in strategies_config:
            if 'symbol' in cfg:
                needed_symbols.add(cfg['symbol'])
                
        # Fetch all feeds
        # Dictionary: { "KRW-BTC": [candles...], "KRW-ETH": [candles...] }
        feeds = {}
        errors = []
        
        for sym in needed_symbols:
            feed = await data_service.get_candles(sym, interval=interval, days=duration_days)
            if feed:
                # Filter by Start Date individually (efficiency: could be done after)
                if from_date:
                    original_len = len(feed)
                    feed = [c for c in feed if c['timestamp'] >= from_date]
                    if len(feed) == 0:
                        errors.append(f"Data for {sym} exists but filtered out by from_date={from_date}. Range: {feed[0]['timestamp'] if original_len else 'N/A'}")
                feeds[sym] = feed
            else:
                errors.append(f"No data for {sym} from DataService")

        # Determine Primary Feed (Rank 1) logic
        # If strategies_config is not empty, Rank 1 (index 0) defines the master clock.
        # Otherwise use 'symbol' arg.
        
        primary_symbol = symbol # Default
        if strategies_config:
            # Rank 1 config
            rank1_config = strategies_config[0]
            if 'symbol' in rank1_config:
                primary_symbol = rank1_config['symbol']
        
        primary_feed = feeds.get(primary_symbol)
        
        if not primary_feed:
            feed_summary = {k: len(v) for k, v in feeds.items()}
            return {
                "logs": [f"Primary data feed missing for {primary_symbol}. Errors: {errors}. Available Feeds: {feed_summary}"],
                "total_return": "0%",
                "win_rate": "0%",
                "max_drawdown": "0%",
                "total_trades": 0,
                "avg_pnl": "0%",
                "max_profit": "0%",
                "max_loss": "0%",
                "profit_factor": "0.00",
                "sharpe_ratio": "0.00",
                "activity_rate": "0%",
                "total_days": 0,
                "avg_holding_time": "0m",
                "stability_score": "0.00",
                "acceleration_score": "0.00",
                "chart_data": [],
                "ohlcv_data": [],
                "trades": [],
                "decile_stats": []
            }
            
        # Debug Log for UI
        initial_logs = [f"Simulation Started. Primary: {primary_symbol} ({len(primary_feed)} candles)"]
        for s, f in feeds.items():
            if s != primary_symbol:
                initial_logs.append(f"Feed {s}: {len(f)} candles")
        if errors:
            initial_logs.append(f"Warnings: {errors}")

        # 2. Setup Context
        # Context needs 'data_feed' for get_current_price etc.
        # But Context is usually single-symbol?
        # We need a new "MultiSymbolContext" or hack the existing one.
        # Existing Context.get_current_price(symbol) checks self.current_candle for THAT symbol? 
        # NOT YET. Existing Context.get_current_price checks 'self.current_candle["close"]'.
        # We need to enhance Context to look up prices from 'feeds' dict using current timestamp.
        
        # Enhanced Context for Integrated Mode
        class IntegratedContext(BacktestContext):
            def __init__(self, primary_feed, feeds_map, initial_capital, primary_sym):
                super().__init__(primary_feed, initial_capital)
                self.feeds_map = feeds_map
                self.primary_sym = primary_sym
                # Pre-index feeds by timestamp for O(1) lookup
                self.feed_index = {} 
                for sym, feed in feeds_map.items():
                   self.feed_index[sym] = {c['timestamp']: c for c in feed}

            def get_current_price(self, symbol: str) -> float:
                # 1. Try to find candle for 'symbol' at 'current_candle.timestamp'
                if not self.current_candle: return 0
                
                curr_ts = self.current_candle['timestamp']
                
                # Check specific symbol feed
                if symbol in self.feed_index:
                    candle = self.feed_index[symbol].get(curr_ts)
                    if candle: return candle['close']
                
                # If symbol matches primary, or just fallback
                if symbol == self.primary_sym: # How do we know primary sym? 
                    return self.current_candle['close']
                    
                return 0 # Price missing

            # Override buy/sell to use specific prices?
            # existing buy() calls get_current_price(symbol). So it should work if we override get_current_price.
            
        context = IntegratedContext(primary_feed, feeds, initial_capital, primary_symbol)
        context.logs.extend(initial_logs)
        context.log(f"DEBUG: Context Initialized. Primary Sym: {primary_symbol}")
        
        # 3. Initialize Strategies
        from ..strategies.base import BaseStrategy
        from ..strategies.rsi import RSIStrategy
        from ..strategies.time_momentum import TimeMomentumStrategy
        
        active_strategies = []
        for cfg in strategies_config:
            # Ensure config has 'symbol'
            cfg_sym = cfg.get('symbol', symbol)
            
            # Inject context
            strat_name = cfg.get('strategy', 'time_momentum')
            
            if strat_name == 'rsi':
                strat_instance = RSIStrategy(context, cfg)
            else:
                strat_instance = TimeMomentumStrategy(context, cfg)
                
            strat_instance.initialize()
            active_strategies.append(strat_instance)
        
        # Debug Log: Active Strategies
        strategy_names = [s.config.get('tabName', f'Strat_{idx}') for idx, s in enumerate(active_strategies)]
        context.log(f"DEBUG: Waterfall Initialized with {len(active_strategies)} Strategies: {strategy_names}")

        # 4. Run Loop (Waterfall)
        trade_owner_idx = None 

        for i, candle in enumerate(primary_feed):
            context.current_index = i
            
            is_holding = sum(context.holdings.values()) > 0
            if not is_holding:
                trade_owner_idx = None 

            if is_holding and trade_owner_idx is not None:
                # Exit Logic: Owner Only
                owner_strat = active_strategies[trade_owner_idx]
                
                # We must ensure 'on_data' receives the candle for ITS symbol, not the primary candle?
                # TimeMomentum accesses data[-1], data[-2].
                # If we pass 'candle' (Primary), but the strategy is for 'ETH', it will analyze BTC price!
                # CRITICAL FIX: Pass the correct candle.
                
                owner_sym = owner_strat.config.get('symbol', symbol)
                owner_candle = context.feed_index.get(owner_sym, {}).get(candle['timestamp'])
                
                if owner_candle:
                    owner_strat.on_data(owner_candle)
                else:
                    # Data missing for this symbol at this time?
                    # Skip for safety
                    pass
                
            else:
                # Entry Logic: Waterfall
                for idx, strat in enumerate(active_strategies):
                    strat_sym = strat.config.get('symbol', symbol)
                    
                    # Look up data for this rank
                    strat_candle = context.feed_index.get(strat_sym, {}).get(candle['timestamp'])
                    
                    if not strat_candle:
                        # User Request: "If chart data is missing, exclude from order"
                        # Simply continue to next rank
                        continue
                        
                    trades_before = len(context.trades)
                    
                    try:
                        strat.on_data(strat_candle)
                    except Exception as e:
                        # Catch strategy errors (e.g. index out of bounds)
                        # print(f"Strat error: {e}")
                        pass
                    
                    trades_after = len(context.trades)
                    
                    if trades_after > trades_before:
                        trade_owner_idx = idx
                        context.trades[-1]['strategy_rank'] = idx + 1
                        break # Stop Waterfall

            context.update_equity()
            
        # 5. Stats
        return self._generate_stats(context, primary_feed)

    def _generate_stats(self, context, data_feed):
        # Reusing the logic from run() but detached to be dry
        # Copy-paste the stats generation block from run() or refactor run() to use this.
        # For minimal risk, I will just duplicate the stats logic helper or call the existing long block?
        # The existing logic is inside run(), heavily active.
        # Let's verify if I can refactor run() easily. 
        # Yes, I can extract `_calculate_final_stats(context, data_feed)`
        
        # ... (Duplicate for safety/speed without heavy refactor risks) ...
        # Or better: Extract _analyze_context(context, data_feed) 
        
        # Let's copy the logic part 5 from above for now to ensure robustness.
        final_equity = context.equity_curve[-1]['equity'] if context.equity_curve else 0
        initial_equity = context.equity_curve[0]['equity'] if context.equity_curve else 1
        
        if not context.equity_curve:
             return { "total_return": "0%", "logs": context.logs, "win_rate": "0%", "chart_data": [], "ohlcv_data": [] }

        total_return = (final_equity - initial_equity) / initial_equity * 100
        
        # .. (Activity Rate logic) ..
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

        return {
            "total_return": f"{total_return:.2f}%",
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "activity_rate": f"{activity_rate:.1f}%",
            "total_days": total_days,
            "chart_data": self._resample_equity(context.equity_curve, 2000),
            "ohlcv_data": self._resample_ohlcv(data_feed, 2000),
            "logs": context.logs, # Return all logs for debugging
            "trades": context.trades,
            **self._analyze_trades(context.trades, data_feed[0]['timestamp'], data_feed[-1]['timestamp'])
        }
