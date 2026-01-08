import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..strategies.base import IContext, BaseStrategy

class BacktestContext(IContext):
    def __init__(self, feeds: Dict[str, List[Dict]], initial_capital: int = 10000000, primary_symbol: str = None):
        """
        Refactored Context for Multi-Symbol Support.
        :param feeds: Dictionary { "SYMBOL": [candle1, candle2, ...] }
        :param primary_symbol: The symbol driving the main loop (optional context)
        """
        self.feeds = feeds
        self.primary_symbol = primary_symbol or (list(feeds.keys())[0] if feeds else "UNKNOWN")
        
        self.current_index = 0
        self.current_timestamp = None # Explicit Time Tracking
        
        self.cash = initial_capital
        self.holdings = {} # {symbol: quantity}
        self.trades = []
        self.logs = []
        self.equity_curve = []

    @property
    def current_candle(self):
        # Legacy Support: Returns candle of the PRIMARY symbol
        if self.primary_symbol in self.feeds:
            feed = self.feeds[self.primary_symbol]
            if 0 <= self.current_index < len(feed):
                return feed[self.current_index]
        return None

    def get_time(self) -> datetime:
        # Use explicit timestamp from Engine if available, else fallback to primary candle
        if self.current_timestamp:
            ts = self.current_timestamp
            if isinstance(ts, datetime): return ts
            return datetime.fromisoformat(ts)
            
        if self.current_candle:
            ts = self.current_candle['timestamp']
            if isinstance(ts, datetime): return ts
            return datetime.fromisoformat(ts)
        return datetime.now()

    def get_current_price(self, symbol: str) -> float:
        # Multi-Symbol Lookup
        target_ts = self.current_timestamp
        
        # If Engine hasn't set explicit timestamp (Legacy Mode), use primary candle
        if not target_ts and self.current_candle:
            target_ts = self.current_candle['timestamp']
            
        if not target_ts: return 0
        
        # Optimize: Check primary matches
        if symbol == self.primary_symbol and self.current_candle:
            # Verify timestamp matches just in case
            c_ts = self.current_candle['timestamp']
            if c_ts == target_ts:
                return self.current_candle['close']
        
        # General Lookup
        if symbol in self.feeds:
            feed = self.feeds[symbol]
            # Heuristic: If feeds are aligned, index might match.
            # But safer to find. For performance in backtest, linear scan from last known index is best.
            # For now, simplistic scan.
            for c in feed:
                if c['timestamp'] == target_ts:
                    return c['close']
        return 0

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        # LEAGUE RULE: Single Position Enforcement
        # If we are holding ANY symbol that is NOT this one, reject.
        if len(self.holdings) > 0 and symbol not in self.holdings:
            self.log(f"BUY REJECTED: System holds {list(self.holdings.keys())}, cannot buy {symbol}.")
            return {"status": "failed", "reason": "System Occupied"}

        exec_price = price if price > 0 else self.get_current_price(symbol)
        if exec_price <= 0:
             self.log(f"BUY FAILED: Invalid Price for {symbol}")
             return {"status": "failed", "reason": "Invalid Price"}
             
        cost = exec_price * quantity
        
        # LEAGUE RULE: Cash Check (Shared Capital)
        if self.cash < cost:
             # Try adjusting quantity? Or just fail.
             # TimeMomentum calculates based on cash, so usually fine.
             # But if racing, cash might be gone.
             self.log(f"BUY FAILED: Insufficient Cash ({self.cash} < {cost})")
             return {"status": "failed", "reason": "Insufficient Cash"}

        self.cash -= cost
        self.holdings[symbol] = self.holdings.get(symbol, 0) + quantity
        
        # Record Trade
        trade = {
            "type": "buy",
            "symbol": symbol,
            "price": exec_price,
            "quantity": quantity,
            "time": self.get_time().isoformat()
        }
        self.trades.append(trade)
        self.log(f"BUY EXECUTED: {quantity} {symbol} @ {exec_price}")
        return trade

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        current_qty = self.holdings.get(symbol, 0)
        if current_qty >= quantity:
            exec_price = price if price > 0 else self.get_current_price(symbol)
            revenue = exec_price * quantity
            
            self.cash += revenue
            self.holdings[symbol] -= quantity
            if self.holdings[symbol] <= 0:
                del self.holdings[symbol]
            
            trade = {
                "type": "sell",
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat()
            }
            self.trades.append(trade)
            self.log(f"SELL EXECUTED: {quantity} {symbol} @ {exec_price}")
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

class WaterfallBacktestEngine:
    def __init__(self, strategy_class, config: Dict = None):
        self.strategy_class = strategy_class
        # This primary config might be Rank 1 or empty if using list
        self.config = config or {}

    async def run_integrated(self, strategies_config: List[Dict], global_symbol: str = "TEST", duration_days: int = 1, from_date: str = None, interval: str = "1m", initial_capital: int = 10000000):
        # 1. Prepare Symbols and Fetch Data
        from ..services.market_data import MarketDataService
        data_service = MarketDataService()
        
        unique_symbols = set()
        if global_symbol: unique_symbols.add(global_symbol)
        for cfg in strategies_config:
            if 'symbol' in cfg:
                unique_symbols.add(cfg['symbol'])
                
        feeds = {}
        # Fetch for all symbols
        for sym in unique_symbols:
            raw_feed = await data_service.get_candles(sym, interval=interval, days=duration_days)
            if raw_feed:
                # Filter Date
                if from_date:
                    raw_feed = [c for c in raw_feed if c['timestamp'] >= from_date]
                # Sort
                raw_feed.sort(key=lambda x: x['timestamp'])
                feeds[sym] = raw_feed
            else:
                print(f"Warning: No data for {sym}")

        if not feeds:
             return self._empty_result(["No data for any symbol"])

        # Determine Primary Symbol (Rank 1 typically)
        primary_symbol = strategies_config[0].get('symbol', global_symbol) if strategies_config else global_symbol
        
        # 2. Setup Shared Context
        context = BacktestContext(feeds, initial_capital=initial_capital, primary_symbol=primary_symbol)
        
        # 3. Initialize Strategies (League Participants)
        participants = []
        for rank_idx, cfg_raw in enumerate(strategies_config):
            # Each participant gets its own config override
            # Assuming 'cfg_raw' is the dict from request
            # Logic: We use SELF.strategy_class (TimeMomentum) for all.
            # Ideally strategy_class should come from config, but for now fixed.
            
            p_config = cfg_raw.copy()
            p_config['initial_capital'] = initial_capital # Share knowledge of cap
            
            # Create Instance
            strat = self.strategy_class(context, p_config)
            strat.initialize()
            
            participants.append({
                "rank": rank_idx + 1,
                "strategy": strat,
                "symbol": p_config.get("symbol", global_symbol)
            })
            
        print(f"DEBUG: League Initialized with {len(participants)} strategies.")
            
        # 4. League Loop (Time + Rank Priority)
        # Collect all timestamps
        all_ts = set()
        for f in feeds.values():
            for c in f:
                all_ts.add(c['timestamp'])
        sorted_ts = sorted(list(all_ts))
        
        for ts in sorted_ts:
            context.current_timestamp = ts # Sync verification clock
            
            # Update Context Index for Primary (Helper for legacy logic if needed)
            if primary_symbol in feeds:
                # Find index (Naive check: assuming contiguous - improving robustness later)
                # But Context.get_current_price uses generic lookup now, so explicit index less critical
                # unless using current_candle property.
                pass 
                
            # -- STRATEGY UPDATE PHASE --
            # Every strategy MUST receive on_data to update indicators.
            # Check Holdings to decide who executes.
             
            # "Occupancy Check": Is cash used?
            # Actually, we let the strategies TRY.
            # If cash is 0, they buy 0 or fail. 
            # If holding other symbol, Context.buy rejects.
            # So we iterate in RANK ORDER.
            
            for p in participants:
                strat = p['strategy']
                sym = p['symbol']
                
                # Get candle for THIS strategy's symbol at THIS time
                candle = None
                if sym in feeds:
                    # Optimized find? 
                    # For V1, simple find.
                    # TODO: Add index pointers for each feed for O(1)
                    matches = [c for c in feeds[sym] if c['timestamp'] == ts]
                    if matches: candle = matches[0]
                
                if candle:
                    # Run Strategy Logic
                    # This updates indicators.
                    # If it triggers BUY, Context checks constraints (Cash/Holding).
                    # If it triggers SELL (StopLoss), Context processes it.
                    strat.on_data(candle)
            
            # Update Equity Curve for this timestamp
            context.update_equity()
            
        # 5. Stats
        # Use Primary Feed for OHLCV visualization reference (or global)
        ref_feed = feeds.get(primary_symbol, list(feeds.values())[0])
        return self._generate_stats(context, ref_feed)

    # Legacy 'run' for backward compatibility if needed, maps to run_integrated
    async def run(self, symbol: str = "TEST", duration_days: int = 1, from_date: str = None, interval: str = "1m", initial_capital: int = 10000000):
        # Wrap single run into integrated format
        cfg = self.config.copy()
        cfg['symbol'] = symbol
        return await self.run_integrated(
            strategies_config=[cfg],
            global_symbol=symbol,
            duration_days=duration_days,
            from_date=from_date,
            interval=interval,
            initial_capital=initial_capital
        )

    # ... _generate_stats, _empty_result, etc. (Existing methods remain) ...
    def _generate_stats(self, context: BacktestContext, data_feed: List[Dict]):
        if not context.equity_curve:
             return self._empty_result(logs=context.logs)

        final_equity = context.equity_curve[-1]['equity']
        initial_equity = context.equity_curve[0]['equity']
        total_return = (final_equity - initial_equity) / initial_equity * 100
        
        # Activity Rate logic
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
        
        # DEBUG: Force Raw OHLCV inline
        raw_ohlcv = [
            {
                "time": int(datetime.fromisoformat(d['timestamp']).timestamp()),
                "open": d['open'],
                "high": d['high'],
                "low": d['low'],
                "close": d['close']
            } for d in data_feed
        ]
        
        return {
            "total_return": f"{total_return:.2f}%",
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "activity_rate": f"{activity_rate:.1f}%",
            "total_days": total_days,
            "chart_data": self._resample_equity(context.equity_curve, 50000),
            "ohlcv_data": raw_ohlcv,
            "logs": context.logs[-50:],
            "trades": context.trades,
            **self._analyze_trades(context.trades, data_feed[0]['timestamp'], data_feed[-1]['timestamp'])
        }

    def _empty_result(self, logs=None):
        return {
            "logs": logs or ["No data collected"],
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

    def _resample_ohlcv(self, data: List[Dict], target_count: int = 50000) -> List[Dict]:
        # User requested to REMOVE LIMIT. Returning all data.
        if not data: return []
        
        return [{
            "time": int(datetime.fromisoformat(d['timestamp']).timestamp()), # Use Unix Timestamp
            "open": d['open'],
            "high": d['high'],
            "low": d['low'],
            "close": d['close']
        } for d in data]

    def _resample_equity(self, data: List[Dict], target_count: int = 50000) -> List[Dict]:
        return data

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
