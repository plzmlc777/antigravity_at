import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..strategies.base import IContext, BaseStrategy
from ..models.new_orders import StockOrder, OrderSide, OrderType, OrderStatus

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
        self.last_known_prices = {} # {symbol: price}
        self.current_rank = 0 # Track which rank is currently executing

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
            
        if not target_ts: 
            return self.last_known_prices.get(symbol, 0)
        
        price = 0
        
        # Optimize: Check primary matches
        if symbol == self.primary_symbol and self.current_candle:
            # Verify timestamp matches just in case
            c_ts = self.current_candle['timestamp']
            if c_ts == target_ts:
                price = self.current_candle['close']
        
        # General Lookup if not found yet
        if price == 0 and symbol in self.feeds:
            feed = self.feeds[symbol]
            # Heuristic: If feeds are aligned, index might match.
            # But safer to find. For performance in backtest, linear scan from last known index is best.
            # For now, simplistic scan.
            for c in feed:
                if c['timestamp'] == target_ts:
                    price = c['close']
                    break
        
        if price > 0:
            self.last_known_prices[symbol] = price
            return price
        else:
            # Return last known price if available
            return self.last_known_prices.get(symbol, 0)

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
             
        # [REFACTOR] Use Order Class Logic
        try:
            # 1. Create Order Object
            order = StockOrder(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                price=exec_price if price > 0 else None,
                order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET
            )
            
            # 2. Validate
            order.validate()
            
            # 3. Execution (Simulation)
            cost = exec_price * quantity
            self.cash -= cost
            self.holdings[symbol] = self.holdings.get(symbol, 0) + quantity
            
            # 4. Fill Update
            order.add_fill(
                fill_price=exec_price,
                fill_qty=quantity,
                fill_id=f"SIM_BUY_{len(self.trades)+1}"
            )
            
            # 5. Legacy Mapping (for _analyze_trades compatibility)
            trade = {
                "type": "buy",
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat(),
                "strategy_rank": self.current_rank,
                "order_id": order.id # Track Object ID
            }
            self.trades.append(trade)
            self.log(f"BUY EXECUTED: {quantity} {symbol} @ {exec_price}")
            return trade
            
        except Exception as e:
            self.log(f"BUY ERROR: {e}")
            return {"status": "failed", "reason": str(e)}

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        current_qty = self.holdings.get(symbol, 0)
        if current_qty >= quantity:
            exec_price = price if price > 0 else self.get_current_price(symbol)
            
            # [REFACTOR] Use Order Class Logic
            try:
                # 1. Create Order Object
                order = StockOrder(
                    symbol=symbol, 
                    side=OrderSide.SELL, 
                    quantity=quantity,
                    price=exec_price if price > 0 else None,
                    order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET
                )
                
                # 2. Validate
                order.validate()
                
                # 3. Execution (Simulation)
                revenue = exec_price * quantity
                self.cash += revenue
                self.holdings[symbol] -= quantity
                if self.holdings[symbol] <= 0:
                    del self.holdings[symbol]
                
                # 4. Fill Update
                order.add_fill(
                    fill_price=exec_price,
                    fill_qty=quantity,
                    fill_id=f"SIM_SELL_{len(self.trades)+1}"
                )
                
                # 5. Legacy Mapping
                trade = {
                    "type": "sell",
                    "symbol": symbol,
                    "price": exec_price,
                    "quantity": quantity,
                    "time": self.get_time().isoformat(),
                    "strategy_rank": self.current_rank,
                    "order_id": order.id
                }
                self.trades.append(trade)
                self.log(f"SELL EXECUTED: {quantity} {symbol} @ {exec_price}")
                return trade
                
            except Exception as e:
                self.log(f"SELL ERROR: {e}")
                return {"status": "failed", "reason": str(e)}
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
        
        # Identify Symbols and Intervals
        unique_symbols = set()
        symbol_interval_map = {} # Key: Symbol, Value: Interval

        # Global override check
        if global_symbol: 
            unique_symbols.add(global_symbol)
            symbol_interval_map[global_symbol] = interval
        if global_symbol: unique_symbols.add(global_symbol)
        for cfg in strategies_config:
            if 'symbol' in cfg:
                unique_symbols.add(cfg['symbol'])

        # --- [SIMULATION DATA] ---
        # Fetch using GLOBAL interval to preserve v0.8.9.9 Simulation Logic & Results
        feeds = {}
        for sym in unique_symbols:
            raw_feed = await data_service.get_candles(sym, interval=interval, days=duration_days)
            if raw_feed:
                # Filter Date (Safe String Comparison)
                if from_date:
                    raw_feed = [c for c in raw_feed if c['timestamp'] >= from_date]
                raw_feed.sort(key=lambda x: x['timestamp'])
                feeds[sym] = raw_feed
            else:
                print(f"Warning: No Simulation data for {sym}")

        if not feeds:
             return self._empty_result(["No data for any symbol"])

        # --- [VISUALIZATION DATA] (Task 1 Fix) ---
        # Fetch using CORRECT Per-Strategy Interval for Popup/Drill-down
        viz_feeds = {}
        symbol_interval_map = {}
        if global_symbol: symbol_interval_map[global_symbol] = interval
        for cfg in strategies_config:
            if 'symbol' in cfg:
                symbol_interval_map[cfg['symbol']] = cfg.get('interval', interval)

        for sym in unique_symbols:
            target_interval = symbol_interval_map.get(sym, interval)
            # Optimize: If target match global, reuse `feeds`
            if target_interval == interval and sym in feeds:
                viz_feeds[sym] = feeds[sym]
            else:
                # Fetch specific interval
                v_feed = await data_service.get_candles(sym, interval=target_interval, days=duration_days)
                if v_feed:
                    if from_date:
                        v_feed = [c for c in v_feed if c['timestamp'] >= from_date]
                    v_feed.sort(key=lambda x: x['timestamp'])
                    viz_feeds[sym] = v_feed

        # Determine Primary Symbol (Rank 1 typically)
        primary_symbol = strategies_config[0].get('symbol', global_symbol) if strategies_config else global_symbol
        
        # 2. Setup Shared Context
        context = BacktestContext(feeds, initial_capital=initial_capital, primary_symbol=primary_symbol)
        
        # 3. Initialize Strategies (League Participants)
        participants = []
        for rank_idx, cfg_raw in enumerate(strategies_config):
            p_config = cfg_raw.copy()
            p_config['initial_capital'] = initial_capital 
            
            # Create Instance (v0.8.9.9 Structure)
            strat = self.strategy_class(context, p_config)
            if hasattr(strat, 'initialize'):
                strat.initialize()
            
            participants.append({
                "rank": rank_idx + 1,
                "strategy": strat,
                "symbol": p_config.get("symbol", global_symbol)
            })
            
        print(f"DEBUG: League Initialized with {len(participants)} strategies.")
            
        # 4. League Loop (Time + Rank Priority)
        all_ts = set()
        for f in feeds.values():
            for c in f:
                all_ts.add(c['timestamp'])
        sorted_ts = sorted(list(all_ts))
        
        for ts in sorted_ts:
            context.current_timestamp = ts 
            
            for p in participants:
                strat = p['strategy']
                sym = p['symbol']
                context.current_rank = p['rank']  # Set context rank before execution
                
                candle = None
                if sym in feeds:
                    matches = [c for c in feeds[sym] if c['timestamp'] == ts]
                    if matches: candle = matches[0]
                
                if candle:
                    strat.on_data(candle)
            
            context.update_equity()

        # [FORCED LIQUIDATION] (2026-01-11)
        # To ensure Total Return (Equity) and Rank Sums (Realized PnL) match exactly,
        # we must close all open positions at the end.
        
        # 1. Calculate Net Position per Rank
        rank_positions = {} # { rank_id: { symbol: qty } }
        for t in context.trades:
            r = t.get('strategy_rank', 0)
            sym = t['symbol']
            qty = t['quantity']
            
            if r not in rank_positions: rank_positions[r] = {}
            if sym not in rank_positions[r]: rank_positions[r][sym] = 0
            
            if t['type'] == 'buy':
                rank_positions[r][sym] += qty
            elif t['type'] == 'sell':
                rank_positions[r][sym] -= qty
                
        # 2. Execute Forced Sells
        print("DEBUG: Executing Forced Liquidation at end of simulation...")
        for r, syms in rank_positions.items():
            for sym, qty in syms.items():
                if qty > 0:
                    context.current_rank = r
                    # Get Last Price
                    last_price = context.get_current_price(sym)
                    if last_price <= 0:
                         # Fallback if no price found (should rare)
                         last_price = 100000 
                         
                    print(f"DEBUG: Force Closing Rank {r}: {qty} {sym} @ {last_price}")
                    context.sell(sym, qty, price=last_price)
                    
        # 5. Stats
        ref_feed = feeds.get(primary_symbol, list(feeds.values())[0])
        stats = self._generate_stats(context, ref_feed)
        
        # [Visual Analysis Support]
        stats['equity_curve'] = context.equity_curve
        stats['chart_data'] = context.equity_curve 
        stats['multi_ohlcv_data'] = viz_feeds # Use VIZ feeds for Popup
        
        return stats

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
            "total_return": total_return,
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "activity_rate": activity_rate,
            "total_days": total_days,
            "chart_data": self._resample_equity(context.equity_curve, 50000),
            "ohlcv_data": raw_ohlcv,
            "logs": context.logs[-50:],
            "trades": context.trades,
            **self._analyze_trades(context.trades, data_feed[0]['timestamp'], data_feed[-1]['timestamp'], total_days=total_days, initial_capital=initial_equity)
        }

    def _empty_result(self, logs=None):
        return {
            "logs": logs or ["No data collected"],
            "total_return": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "activity_rate": 0.0,
            "total_trades": 0,
            "score": 0,
            "avg_pnl": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "avg_holding_time": 0, # minutes
            "stability_score": 0.0,
            "acceleration_score": 0.0,
            "chart_data": [],
            "ohlcv_data": []
        }

    def _analyze_trades(self, trades: List[Dict], start_ts: Any = None, end_ts: Any = None, total_days: int = 0, calc_ranks: bool = True, initial_capital: float = 10000000) -> Dict[str, Any]:
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": "0%",
                "avg_pnl": "0%",
                "max_profit": "0%",
                "max_loss": "0%",
                "profit_factor": "0.00",
                "sharpe_ratio": "0.00",
                "avg_holding_time": 0,
                "stability_score": 0.0,
                "acceleration_score": 0.0,
                "decile_stats": [],
                "rank_stats_list": [],
                "activity_rate": 0.0
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
                        'volume': revenue,
                        'holding_seconds': holding_seconds,
                        'time': t['time'], # Store Sell Time for Decile Analysis
                        'strategy_rank': t.get('strategy_rank', 0) # Preserve tag
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
                "avg_holding_time": 0,
                "decile_stats": [],
                "rank_stats_list": []
            }

        # Stats Calculation via Helper
        base_stats = self._compute_stats_from_completed(completed_trades)
        
        # Extract for return
        win_rate = base_stats['win_rate']
        avg_pnl_percent = base_stats['avg_pnl']
        max_profit = base_stats['max_profit']
        max_loss = base_stats['max_loss']
        profit_factor = base_stats['profit_factor']
        sharpe = base_stats['sharpe_ratio']
        avg_holding_min = base_stats['avg_holding_time']

        # Calculate Monthly Stats & Stability
        decile_data = self._calc_deciles(completed_trades, start_ts, end_ts)

        return {
            "total_trades": len(completed_trades),
            "win_rate": win_rate,
            "avg_pnl": avg_pnl_percent,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            # "activity_rate": activity_rate, # Removed to prevent overwrite
            "avg_holding_time": avg_holding_min, # minutes
            "decile_stats": decile_data['monthly_stats'],
            "stability_score": decile_data['stability_score'],
            "acceleration_score": decile_data['acceleration_score'],
            "rank_stats_list": self._calc_rank_stats(completed_trades, total_days, start_ts, end_ts, initial_capital) if calc_ranks else []
        }

    def _compute_stats_from_completed(self, completed_trades: List[Dict]) -> Dict[str, Any]:
        """
        Helper: Calculates WinRate, Sharpe, ProfitFactor, etc. from ALREADY MATCHED trades.
        """
        if not completed_trades:
             return {
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "avg_holding_time": 0
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
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99 
        
        # Avg Holding Time
        total_holding_sec = sum(t.get('holding_seconds', 0) for t in completed_trades)
        avg_holding_sec = total_holding_sec / total_count if total_count > 0 else 0
        avg_holding_min = int(avg_holding_sec / 60)
        
        # Sharpe Ratio
        import statistics
        returns = [t['pnl_percent'] for t in completed_trades]
        if len(returns) > 1:
            stdev = statistics.stdev(returns)
            sharpe = (statistics.mean(returns) / stdev * (len(returns)**0.5)) if stdev > 0 else 0
        else:
            sharpe = 0
            
        return {
            "win_rate": win_rate,
            "avg_pnl": avg_pnl_percent,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "avg_holding_time": avg_holding_min
        }

    def _calc_rank_stats(self, trades: List[Dict], total_days: int, start_ts: Any, end_ts: Any, initial_capital: float) -> List[Dict]:
        """
        Calculates full suite of statistics for each Rank, matching Overview metrics.
        """
        ranks = sorted(list(set(t.get('strategy_rank', 0) for t in trades)))
        rank_stats = []
        
        for r in ranks:
            if r == 0: continue # Skip if rank 0
            
            r_trades = [t for t in trades if t.get('strategy_rank') == r]
            if not r_trades: continue
            
            # 1. Base Stats via Helper
            
            decile_data_rank = self._calc_deciles(r_trades, start_ts, end_ts)
            base_stats = self._compute_stats_from_completed(r_trades)
            
            # Merge decile-based stability into base_stats
            base_stats['stability_score'] = decile_data_rank['stability_score']
            base_stats['acceleration_score'] = decile_data_rank['acceleration_score']
            base_stats['total_trades'] = len(r_trades)
            
            # 2. Total PnL (Value) and Return % (Contribution to Total)
            total_pnl_value = sum(t['pnl'] for t in r_trades)
            # Use Initial Capital as denominator to show contribution % to overall return
            total_return_pct = (total_pnl_value / initial_capital * 100) if initial_capital > 0 else 0.0
            
            # 3. Activity Rate
            if total_days > 0 and r_trades:
                # Use first 10 chars of ISO string for Date YYYY-MM-DD
                uniq_days = len(set(t['time'][:10] for t in r_trades))
                activity_rate = (uniq_days / total_days * 100)
            else:
                activity_rate = 0.0
                
            # 4. Max Drawdown (Standardized Calculation)
            # To match Overview exactly, we must treat this Rank as a virtual sub-account.
            # Virtual Equity = Initial Capital + Cumulative PnL
            # MDD = (Peak Virtual Equity - Current Virtual Equity) / Peak Virtual Equity
            
            # Sort by time to ensure curve is correct
            sorted_trades = sorted(r_trades, key=lambda x: x['time'])
            
            virtual_equity = initial_capital
            peak_equity = initial_capital
            max_dd_ratio = 0.0
            max_dd_val = 0.0 # Keep tracking value for potential debug
            
            for t in sorted_trades:
                virtual_equity += t['pnl']
                
                if virtual_equity > peak_equity:
                    peak_equity = virtual_equity
                
                dd_val = peak_equity - virtual_equity
                if dd_val > 0:
                    dd_ratio = dd_val / peak_equity
                    if dd_ratio > max_dd_ratio:
                        max_dd_ratio = dd_ratio
                        max_dd_val = dd_val # Max DD Value

            # MDD % (Negative)
            max_dd_pct = -(max_dd_ratio * 100) if initial_capital > 0 else 0.0
            
            
            rank_stats.append({
                "rank": r,
                "total_return": float(f"{total_return_pct:.2f}"), # Total Return %
                "total_pnl_value": int(total_pnl_value),
                "activity_rate": float(f"{activity_rate:.1f}"),
                "max_drawdown": float(f"{max_dd_pct:.2f}"), # % relative to Peak Profit
                "max_drawdown_value": int(max_dd_val), # Value for tooltip/debug
                **base_stats 
            })
            
        return rank_stats

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
            "stability_score": stability_score,
            "acceleration_score": acceleration_score
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
        if not equity_curve: return 0.0
        peak = equity_curve[0]['equity']
        max_dd = 0.0
        for point in equity_curve:
            val = point['equity']
            if val > peak: peak = val
            dd = (peak - val) / peak
            if dd > max_dd: max_dd = dd
        return -(max_dd * 100)
