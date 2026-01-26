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
        self._holdings = {} # {symbol: quantity}
        self.trades = []
        self.logs = []
        self.equity_curve = []
        self.last_known_prices = {} # {symbol: price}
        self.current_rank = 0 # Track which rank is currently executing
        self.optimize_mode = False # Performance flag
        
        # Optimize: Pre-index feeds for O(1) price lookup
        self.price_map = {}
        for sym, feed in feeds.items():
            self.price_map[sym] = {c['timestamp']: c['close'] for c in feed}

    @property
    def holdings(self) -> Dict[str, int]:
        return self._holdings

    @property
    def is_paper(self) -> bool:
        return True

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
        
        # General Lookup if not found yet (Optimized O(1))
        if price == 0 and symbol in self.price_map:
             price = self.price_map[symbol].get(target_ts, 0)
        
        if price > 0:
            self.last_known_prices[symbol] = price
            return price
        else:
            # Return last known price if available
            return self.last_known_prices.get(symbol, 0)

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        # LEAGUE RULE: Single Position Enforcement
        # If we are holding ANY symbol that is NOT this one, reject.
        if len(self._holdings) > 0 and symbol not in self._holdings:
            self.log(f"BUY REJECTED: System holds {list(self._holdings.keys())}, cannot buy {symbol}.")
            return {"status": "failed", "reason": "System Occupied"}

        exec_price = price if price > 0 else self.get_current_price(symbol)
        if exec_price <= 0:
             self.log(f"BUY FAILED: Invalid Price for {symbol}")
             return {"status": "failed", "reason": "Invalid Price"}
             
        # [REFACTOR] Use Order Class Logic
        try:
            order = StockOrder(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                price=exec_price if price > 0 else None,
                order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET
            )
            
            order.validate()
            
            cost = exec_price * quantity
            self.cash -= cost
            self._holdings[symbol] = self._holdings.get(symbol, 0) + quantity
            
            order.add_fill(
                fill_price=exec_price,
                fill_qty=quantity,
                fill_id=f"SIM_BUY_{len(self.trades)+1}"
            )
            
            trade = {
                "type": "buy",
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat(),
                "strategy_rank": self.current_rank,
                "order_id": order.id,
                "metadata": metadata or {}
            }
            self.trades.append(trade)
            self.log(f"BUY EXECUTED: {quantity} {symbol} @ {exec_price}")
            return trade
            
        except Exception as e:
            self.log(f"BUY ERROR: {e}")
            return {"status": "failed", "reason": str(e)}

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        current_qty = self._holdings.get(symbol, 0)
        if current_qty >= quantity:
            exec_price = price if price > 0 else self.get_current_price(symbol)
            
            try:
                order = StockOrder(
                    symbol=symbol, 
                    side=OrderSide.SELL, 
                    quantity=quantity,
                    price=exec_price if price > 0 else None,
                    order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET
                )
                
                order.validate()
                
                revenue = exec_price * quantity
                self.cash += revenue
                self._holdings[symbol] -= quantity
                if self._holdings[symbol] <= 0:
                    del self._holdings[symbol]
                
                order.add_fill(
                    fill_price=exec_price,
                    fill_qty=quantity,
                    fill_id=f"SIM_SELL_{len(self.trades)+1}"
                )
                
                trade = {
                    "type": "sell",
                    "symbol": symbol,
                    "price": exec_price,
                    "quantity": quantity,
                    "time": self.get_time().isoformat(),
                    "strategy_rank": self.current_rank,
                    "order_id": order.id,
                    "metadata": metadata or {}
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
        if self.optimize_mode: return
        self.logs.append(f"[{self.get_time().strftime('%H:%M:%S')}] {message}")

    def update_equity(self):
        equity = self.cash
        for symbol, qty in self._holdings.items():
            equity += qty * self.get_current_price(symbol)
        
        self.equity_curve.append({
            "date": self.get_time().strftime("%Y-%m-%d %H:%M"),
            "equity": int(equity)
        })

async def fetch_visualization_feeds(strategies_config: List[Dict], global_symbol: str, interval: str, duration_days: int, from_date: str = None, preloaded_feeds: Dict[str, List] = None) -> Dict[str, List]:
    """
    Independent helper to fetch OHLCV data for Visualization (Background Charts).
    Can reuse preloaded_feeds (Simulation Data) if intervals match to save bandwidth.
    """
    from ..services.market_data import MarketDataService
    data_service = MarketDataService()
    
    viz_feeds = {}
    
    # 1. Identify Symbols and Target Intervals
    unique_symbols = set()
    symbol_interval_map = {} 
    
    # Global default
    if global_symbol: 
        unique_symbols.add(global_symbol)
        symbol_interval_map[global_symbol] = interval
        
    for cfg in strategies_config:
        if 'symbol' in cfg:
            sym = cfg['symbol']
            unique_symbols.add(sym)
            symbol_interval_map[sym] = cfg.get('interval', interval)

    # 2. Fetch Data
    for sym in unique_symbols:
        target_interval = symbol_interval_map.get(sym, interval)
        
        # Optimization: Reuse preloaded simulation data if available and matches interval
        if preloaded_feeds and sym in preloaded_feeds and target_interval == interval:
             viz_feeds[sym] = preloaded_feeds[sym]
        else:
            # Fetch from DB/API
            v_feed = await data_service.get_candles(sym, interval=target_interval, days=duration_days)
            if v_feed:
                if from_date:
                    v_feed = [c for c in v_feed if c['timestamp'] >= from_date]
                v_feed.sort(key=lambda x: x['timestamp'])
                viz_feeds[sym] = v_feed
                
    return viz_feeds

class WaterfallBacktestEngine:
    def __init__(self, strategy_class, config: Dict = None):
        self.strategy_class = strategy_class
        # This primary config might be Rank 1 or empty if using list
        self.config = config or {}

    async def run_integrated(self, strategies_config: List[Dict], global_symbol: str = "TEST", duration_days: int = 1, from_date: str = None, interval: str = "1m", initial_capital: int = 10000000, optimize_mode: bool = False):
        import time
        t_start = time.time()
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
            print(f"[DEBUG] WaterfallEngine fetching {sym} with interval={interval}, days={duration_days}")
            raw_feed = await data_service.get_candles(sym, interval=interval, days=duration_days)
            if raw_feed:
                # Filter Date (Safe String Comparison)
                if from_date:
                    raw_feed = [c for c in raw_feed if c['timestamp'] >= from_date]
                raw_feed.sort(key=lambda x: x['timestamp'])
                feeds[sym] = raw_feed
                print(f"[DEBUG] WaterfallEngine loaded {len(raw_feed)} candles for {sym} at {interval}")
            else:
                print(f"Warning: No Simulation data for {sym}")

        if not feeds:
             return self._empty_result(["No data for any symbol"])
             
        t_data = time.time()
        print(f"[{'LITE' if optimize_mode else 'FULL'}] Data Fetch: {t_data - t_start:.4f}s")

        # --- [VISUALIZATION DATA] (Refactored to Independent Function) ---
        # Skip if optimize_mode is True (Save memory/time)
        viz_feeds = {}
        if not optimize_mode:
            viz_feeds = await fetch_visualization_feeds(
                strategies_config=strategies_config,
                global_symbol=global_symbol,
                interval=interval,
                duration_days=duration_days,
                from_date=from_date,
                preloaded_feeds=feeds # Pass simulation feeds for optimization
            )

        # Determine Primary Symbol (Rank 1 typically)
        primary_symbol = strategies_config[0].get('symbol', global_symbol) if strategies_config else global_symbol
        
        # 2. Setup Shared Context
        context = BacktestContext(feeds, initial_capital=initial_capital, primary_symbol=primary_symbol)
        context.optimize_mode = optimize_mode
        
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
            
        print(f"DEBUG: League Initialized with {len(participants)} strategies.")
            
        # 4. League Loop (Time + Rank Priority)
        # [OPTIMIZATION] Fast Loop for Single-Strategy Optimization
        if optimize_mode and len(participants) == 1 and len(feeds) == 1:
            # Bypass Set/Sort overhead. Iterate directly on feed.
            p = participants[0]
            strat = p['strategy']
            sym = p['symbol']
            feed = feeds[sym]
            
            context.current_rank = p['rank']
            
            for candle in feed:
                # Direct Injection
                context.current_timestamp = candle['timestamp']
                context.price_map[sym][candle['timestamp']] = candle['close'] # Ensure recent price is set (though O(1) map handles it)
                # Actually, price_map is static. But we need to update 'current_candle' if logic uses it.
                # But 'get_current_price' uses price_map now.
                
                # Update Context State (Minimal)
                # We need to simulate 'current_candle' update for the engine?
                # The engine implementation of 'current_candle' property reads from... where?
                # It uses self.data_feeds or similar? No, 'current_candle' property is not in Context.
                # Actually, context doesn't need 'current_candle' if strategy receives it.
                # But strategy.on_data(candle) is what matters.
                
                try:
                    strat.on_data(candle)
                    
                    # Update Equity (Lightweight)
                    # Inline update_equity optimization?
                    # context.update_equity() -> heavy?
                    # Let's use the optimized one.
                    context.update_equity()
                except Exception as e:
                     pass # similar to main loop error handling
                     
        else:
            # [LEGACY / MULTI-STRATEGY] Full Time-Sync Loop - OPTIMIZED O(N*M)
            all_ts = set()
            feed_indices = {} # {symbol: {timestamp: candle}}
            for sym, f in feeds.items():
                feed_indices[sym] = {c['timestamp']: c for c in f}
                for c in f:
                    all_ts.add(c['timestamp'])
            
            sorted_ts = sorted(list(all_ts))
            
            for ts in sorted_ts:
                context.current_timestamp = ts 
                
                for p in participants:
                    sym = p['symbol']
                    context.current_rank = p['rank']
                    
                    # O(1) Lookup
                    candle = feed_indices.get(sym, {}).get(ts)
                
                    if candle:
                        try:
                            p['strategy'].on_data(candle)
                        except Exception as e:
                            pass
            
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
                    
        t_exec = time.time()
        print(f"[{'LITE' if optimize_mode else 'FULL'}] Execution: {t_exec - t_data:.4f}s")

        # 5. Stats
        ref_feed = feeds.get(primary_symbol, list(feeds.values())[0])
        stats = self._generate_stats(context, ref_feed, optimize_mode=optimize_mode)

        # [Visual Analysis Support]
        if not optimize_mode:
            stats['equity_curve'] = context.equity_curve
            stats['chart_data'] = context.equity_curve
            stats['multi_ohlcv_data'] = viz_feeds # Use VIZ feeds for Popup
        else:
             stats['multi_ohlcv_data'] = {}
        
        t_stats = time.time()
        perf_msg = f"[{'LITE' if optimize_mode else 'FULL'}] Data Fetch: {t_data - t_start:.4f}s | Exec: {t_exec - t_data:.4f}s | Stats: {t_stats - t_exec:.4f}s | Total: {t_stats - t_start:.4f}s"
        print(perf_msg)
        stats['perf_log'] = perf_msg


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
    # ... _generate_stats, _empty_result, etc. (Existing methods remain) ...
    def _generate_stats(self, context: BacktestContext, data_feed: List[Dict], optimize_mode: bool = False):
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
        raw_ohlcv = []
        if not optimize_mode:
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
            "total_days": total_days,
            "chart_data": self._resample_equity(context.equity_curve, 50000) if not optimize_mode else [],
            "ohlcv_data": raw_ohlcv,
            "logs": context.logs[-50:],
            "trades": context.trades,
            **self._analyze_trades(context.trades, data_feed[0]['timestamp'], data_feed[-1]['timestamp'], total_days=total_days, initial_capital=initial_equity, optimize_mode=optimize_mode)
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
            "ohlcv_data": [],
            "rank_stats_list": [],
            "decile_stats": []
        }

    def _analyze_trades(self, trades: List[Dict], start_ts: Any = None, end_ts: Any = None, total_days: int = 0, calc_ranks: bool = True, initial_capital: float = 10000000, optimize_mode: bool = False) -> Dict[str, Any]:
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
                        'time': t['time'], # Store Sell Time for Decile Analysis
                        'strategy_rank': t.get('strategy_rank', 0), # Preserve tag
                        'metadata': t.get('metadata', {}) # Store sell metadata (for cycle detection)
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
        # OPTIMIZED: Now fast enough to run even in optimize_mode (O(N) algorithm)
        decile_data = self._calc_deciles(completed_trades, start_ts, end_ts)
        stability_score = decile_data['stability_score']
        acceleration_score = decile_data['acceleration_score']

        # Monthly stats only needed for detailed view (not optimization)
        if not optimize_mode:
            monthly_stats = decile_data['monthly_stats']
        else:
            monthly_stats = []

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
            "decile_stats": monthly_stats,
            "stability_score": stability_score,
            "acceleration_score": acceleration_score,
            "total_cycles": base_stats.get('total_cycles'),  # Martingale cycle count
            "avg_pnl_per_cycle": base_stats.get('avg_pnl_per_cycle'),  # Avg PnL per cycle
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

        # Debug log for optimization
        if completed_trades:
            print(f"[DEBUG] Max Profit: {max_profit:.2f}%, Max Loss: {max_loss:.2f}% (from {len(completed_trades)} trades)")
        
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

        # Martingale Cycle Statistics (for strategies using multi-level entries)
        # A cycle is identified by unique cycle_id in metadata
        cycle_trades = [t for t in completed_trades if t.get('metadata', {}).get('level') == 'CLOSE']

        # Group trades by cycle_id to count unique cycles and sum PnL per cycle
        cycle_pnl_map = {}  # {cycle_id: total_pnl_percent}
        for t in cycle_trades:
            cycle_id = t.get('metadata', {}).get('cycle_id', 0)
            pnl_pct = t.get('pnl_percent', 0) * 100  # Convert to %
            if cycle_id in cycle_pnl_map:
                cycle_pnl_map[cycle_id] += pnl_pct
            else:
                cycle_pnl_map[cycle_id] = pnl_pct

        total_cycles = len(cycle_pnl_map) if cycle_pnl_map else 0
        avg_pnl_per_cycle = 0.0

        if total_cycles > 0:
            # Average PnL per unique cycle
            total_cycle_pnl_percent = sum(cycle_pnl_map.values())
            avg_pnl_per_cycle = total_cycle_pnl_percent / total_cycles
            print(f"[DEBUG] Martingale Cycles: {total_cycles} unique cycles, Avg PnL per cycle: {avg_pnl_per_cycle:.2f}%")

        return {
            "win_rate": win_rate,
            "avg_pnl": avg_pnl_percent,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "avg_holding_time": avg_holding_min,
            "total_cycles": total_cycles if total_cycles > 0 else None,  # None if not martingale strategy
            "avg_pnl_per_cycle": avg_pnl_per_cycle if total_cycles > 0 else None
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

        OPTIMIZED: O(N + M) instead of O(M × N)
        - N = number of trades
        - M = number of months
        """
        import time
        from collections import defaultdict

        start_time = time.time()

        # Helper to parse TS
        def parse(t): return t if isinstance(t, datetime) else datetime.fromisoformat(t)

        start_dt = parse(start_ts).date()
        end_dt = parse(end_ts).date()

        # Normalize to start of month
        curr = start_dt.replace(day=1)
        end_cap = end_dt.replace(day=1)

        # OPTIMIZATION: Group trades by month in O(N) instead of O(M × N)
        monthly_trades = defaultdict(list)
        for t in trades:
            t_date = parse(t['time']).date()  # Parse only once per trade
            month_key = t_date.strftime("%Y-%m")
            monthly_trades[month_key].append(t)

        stats = []
        block_idx = 1

        # Iterate through months and lookup pre-grouped trades in O(1)
        while curr <= end_cap:
            month_key = curr.strftime("%Y-%m")
            chunk = monthly_trades.get(month_key, [])  # O(1) lookup

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

            # Calculate next month
            if curr.month == 12:
                curr = curr.replace(year=curr.year + 1, month=1)
            else:
                curr = curr.replace(month=curr.month + 1)

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

        elapsed_ms = (time.time() - start_time) * 1000
        print(f"[PERF] _calc_deciles: {len(trades)} trades, {len(stats)} months → {elapsed_ms:.2f}ms")

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
