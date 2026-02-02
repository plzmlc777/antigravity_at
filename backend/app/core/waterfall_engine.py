import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..strategies.base import IContext, BaseStrategy
from ..models.new_orders import StockOrder, OrderSide, OrderType, OrderStatus
from .data_schemas import make_equity_point, EQUITY_DATE_KEY, EQUITY_VALUE_KEY

# --- SINGLE SOURCE OF TRUTH: Performance Stat Keys ---
# All stat keys that should appear in rank_stats_list and aggregated results.
# Adding a key here auto-includes it in rank_stats_list extraction.
PERFORMANCE_STAT_KEYS = [
    "total_return",
    "profit_factor",
    "win_rate",
    "sharpe_ratio",
    "total_trades",
    "stability_score",
    "acceleration_score",
    "activity_rate",
    "avg_pnl",
    "avg_holding_time",
    "max_profit",
    "max_loss",
    # Cycle metrics (None when no cycles)
    "cycle_count",
    "cycle_avg_pnl",
    "cycle_avg_hold",
    "cycle_max_hold",
    "cycle_min_hold",
    # Always last
    "max_drawdown",
]

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

        self.initial_capital = initial_capital  # Store for Fixed betting mode reset
        self.cash = initial_capital
        self._holdings = {} # {symbol: quantity}
        self.trades = []
        self.logs = []
        self.equity_curve = []
        self.last_known_prices = {} # {symbol: price}
        self.current_rank = 0 # Track which rank is currently executing
        self.optimize_mode = False # Performance flag
        self.realized_pnl = 0  # Track realized P&L for Fixed mode
        
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

            # Capital Check: Ensure sufficient funds before buying
            if self.cash < cost:
                self.log(f"BUY REJECTED: Insufficient capital. Need {cost:,.0f}, have {self.cash:,.0f}")
                return {"status": "failed", "reason": "Insufficient Capital"}

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

    def reset_cycle_capital(self):
        """
        Reset cash to initial_capital for Fixed betting mode.
        Called at the start of each new cycle.
        Realized P&L is preserved separately (not lost).
        """
        # Calculate realized P&L before reset
        cycle_pnl = self.cash - self.initial_capital
        self.realized_pnl += cycle_pnl
        # Reset to initial capital for next cycle
        self.cash = self.initial_capital
        self.log(f"[Fixed Mode] Cycle Reset. PnL: {cycle_pnl:,.0f}, Total Realized: {self.realized_pnl:,.0f}, Cash Reset to: {self.cash:,.0f}")

    def update_equity(self):
        # Include realized_pnl for Fixed betting mode (accumulated P&L from completed cycles)
        equity = self.cash + self.realized_pnl
        for symbol, qty in self._holdings.items():
            equity += qty * self.get_current_price(symbol)

        self.equity_curve.append(make_equity_point(
            self.get_time().strftime("%Y-%m-%d %H:%M"), equity
        ))

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

    async def run_single_backtest(
        self,
        config: Dict,
        feed: List[Dict],
        initial_capital: int,
        symbol: str,
        optimize_mode: bool = False,
        rank: int = 1
    ) -> Dict:
        """
        ATOMIC SINGLE STRATEGY BACKTEST - SINGLE SOURCE OF TRUTH

        This is the core execution unit that BOTH individual backtest AND
        parallel mode use. This ensures consistent results across all modes.

        Args:
            config: Strategy configuration dict
            feed: List of OHLCV candles (already filtered by date)
            initial_capital: Starting capital for this run
            symbol: Stock symbol
            optimize_mode: If True, skip chart/visualization data
            rank: Rank identifier (for logging)

        Returns:
            Complete backtest result with stats, trades, equity_curve
        """
        if not feed:
            return self._empty_result(["No data provided"])

        # 1. Create Independent Context
        feeds = {symbol: feed}
        context = BacktestContext(feeds, initial_capital=initial_capital, primary_symbol=symbol)
        context.current_rank = rank
        context.optimize_mode = optimize_mode

        # 2. Create and Initialize Strategy
        p_config = config.copy()
        p_config['initial_capital'] = initial_capital
        p_config['symbol'] = symbol

        strat = self.strategy_class(context, p_config)
        if hasattr(strat, 'initialize'):
            strat.initialize()

        # 3. Run Simulation - Direct Feed Loop (consistent execution path)
        for candle in feed:
            context.current_timestamp = candle['timestamp']
            try:
                strat.on_data(candle)
                context.update_equity()
            except Exception as e:
                pass  # Continue on error

        # 4. Force Liquidation at End (close all open positions)
        positions = {}
        for t in context.trades:
            sym = t['symbol']
            qty = t['quantity']
            if sym not in positions:
                positions[sym] = 0
            if t['type'] == 'buy':
                positions[sym] += qty
            elif t['type'] == 'sell':
                positions[sym] -= qty

        for sym, qty in positions.items():
            if qty > 0:
                last_price = context.get_current_price(sym)
                if last_price <= 0:
                    last_price = feed[-1]['close'] if feed else 100000
                context.sell(sym, qty, price=last_price)

        # 5. Calculate Statistics using unified _generate_stats
        stats = self._generate_stats(context, feed, optimize_mode=optimize_mode)

        # 6. Add metadata
        final_equity = context.equity_curve[-1][EQUITY_VALUE_KEY] if context.equity_curve else initial_capital
        stats['symbol'] = symbol
        stats['initial_capital'] = initial_capital
        stats['final_equity'] = final_equity
        stats['return_pct'] = ((final_equity - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
        stats['pnl'] = final_equity - initial_capital
        stats['trades_count'] = len(context.trades)
        stats['equity_curve'] = context.equity_curve
        stats['rank'] = rank
        stats['config'] = p_config

        return stats

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
        # [FIX] Fast Loop for Single-Strategy (ALWAYS use this path for 1 participant)
        # This ensures individual backtest matches parallel mode execution (same as run_parallel)
        if len(participants) == 1 and len(feeds) == 1:
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

    async def run_parallel(self, strategies_config: List[Dict], global_symbol: str = "TEST", duration_days: int = 1, from_date: str = None, interval: str = "1m", initial_capital: int = 10000000):
        """
        Parallel Execution Mode: Each Rank runs independently with equal capital split.
        All ranks operate simultaneously without affecting each other.

        Capital Distribution: initial_capital / num_ranks (equal split)
        """
        import time
        t_start = time.time()

        if not strategies_config:
            return self._empty_result(["No strategies provided"])

        num_ranks = len(strategies_config)
        # PARALLEL MODE: Frontend sends totalCapital = rank1Capital * num_ranks
        # So we divide to get per-rank capital (same as individual backtest's rank1Capital)
        capital_per_rank = initial_capital // num_ranks  # Equal split - each rank gets rank1Capital
        total_capital_deployed = initial_capital  # Total is what frontend sent (not multiplied again)

        # Initialize combined_logs early for debug logging
        combined_logs = []
        combined_logs.append(f"=== PARALLEL EXECUTION MODE ===")
        combined_logs.append(f"Capital Per Rank: {capital_per_rank:,} | Ranks: {num_ranks} | Total Deployed: {total_capital_deployed:,}")
        combined_logs.append(f"Interval: {interval}, Duration: {duration_days} days, From: {from_date}")

        # 1. Fetch Data Once (Shared across all ranks)
        from ..services.market_data import MarketDataService
        data_service = MarketDataService()

        unique_symbols = set()
        if global_symbol:
            unique_symbols.add(global_symbol)
        for cfg in strategies_config:
            if 'symbol' in cfg:
                unique_symbols.add(cfg['symbol'])

        feeds = {}
        for sym in unique_symbols:
            raw_feed = await data_service.get_candles(sym, interval=interval, days=duration_days)
            if raw_feed:
                if from_date:
                    raw_feed = [c for c in raw_feed if c['timestamp'] >= from_date]
                raw_feed.sort(key=lambda x: x['timestamp'])
                feeds[sym] = raw_feed
                combined_logs.append(f"Loaded {len(raw_feed)} candles for {sym}")

        if not feeds:
            return self._empty_result(["No data for any symbol"])

        t_data = time.time()

        # Fetch visualization feeds
        viz_feeds = await fetch_visualization_feeds(
            strategies_config=strategies_config,
            global_symbol=global_symbol,
            interval=interval,
            duration_days=duration_days,
            from_date=from_date,
            preloaded_feeds=feeds
        )

        primary_symbol = strategies_config[0].get('symbol', global_symbol)

        # 2. Run Each Rank Using SINGLE SOURCE (run_single_backtest)
        # This ensures EXACT same execution path as individual backtest
        rank_results = []
        all_trades = []
        combined_equity_curve = []
        # combined_logs already initialized above

        for rank_idx, cfg_raw in enumerate(strategies_config):
            rank_capital = capital_per_rank
            rank_symbol = cfg_raw.get("symbol", global_symbol)
            feed = feeds.get(rank_symbol, list(feeds.values())[0])

            # DEBUG: Log config
            combined_logs.append(f"[Rank {rank_idx+1}] === USING run_single_backtest() ===")
            combined_logs.append(f"[Rank {rank_idx+1}] symbol={rank_symbol}, capital={rank_capital:,}")
            combined_logs.append(f"[Rank {rank_idx+1}] dip_percent={cfg_raw.get('dip_percent')}, trailing_start={cfg_raw.get('trailing_start_percent')}, max_levels={cfg_raw.get('max_levels')}")

            # *** SINGLE SOURCE OF TRUTH ***
            # Use run_single_backtest() - same function used by individual backtest endpoint
            rank_result = await self.run_single_backtest(
                config=cfg_raw,
                feed=feed,
                initial_capital=rank_capital,
                symbol=rank_symbol,
                optimize_mode=True,  # Skip chart data for performance
                rank=rank_idx + 1
            )

            # Tag trades with rank info for aggregation
            for t in rank_result.get('trades', []):
                t['strategy_rank'] = rank_idx + 1
                t['allocated_capital'] = rank_capital

            # Build rank_results in expected format
            rank_results.append({
                "rank": rank_idx + 1,
                "symbol": rank_symbol,
                "allocated_capital": rank_capital,
                "final_equity": rank_result.get('final_equity', rank_capital),
                "return_pct": rank_result.get('return_pct', 0),
                "pnl": rank_result.get('pnl', 0),
                "trades_count": rank_result.get('trades_count', 0),
                "equity_curve": rank_result.get('equity_curve', []),
                "config": rank_result.get('config', cfg_raw),
                "full_stats": rank_result  # Full stats from run_single_backtest
            })

            all_trades.extend(rank_result.get('trades', []))
            combined_logs.extend([f"[Rank {rank_idx + 1}] {log}" for log in rank_result.get('logs', [])[-20:]])
            combined_logs.append(f"[Rank {rank_idx + 1}] === RESULT: {rank_capital:,} -> {rank_result.get('final_equity', 0):,.0f} ({rank_result.get('return_pct', 0):+.2f}%), Trades: {rank_result.get('trades_count', 0)} ===")

        t_exec = time.time()

        # 3. Aggregate Results
        total_final_equity = sum(r['final_equity'] for r in rank_results)
        # Use total_capital_deployed as base (each rank got full initial_capital)
        total_return = ((total_final_equity - total_capital_deployed) / total_capital_deployed * 100) if total_capital_deployed > 0 else 0
        total_pnl = total_final_equity - total_capital_deployed
        # Also calculate sum of individual rank returns (for display)
        sum_of_rank_returns = sum(r['return_pct'] for r in rank_results)

        # Build Combined Equity Curve (sum of all ranks at each timestamp)
        all_timestamps = set()
        for r in rank_results:
            for pt in r['equity_curve']:
                all_timestamps.add(pt[EQUITY_DATE_KEY])

        sorted_ts = sorted(all_timestamps)
        combined_equity_curve = []

        # Build lookup for each rank's equity at each timestamp
        rank_equity_lookup = []
        for r in rank_results:
            lookup = {pt[EQUITY_DATE_KEY]: pt[EQUITY_VALUE_KEY] for pt in r['equity_curve']}
            rank_equity_lookup.append(lookup)

        last_values = [r['allocated_capital'] for r in rank_results]
        for ts in sorted_ts:
            combined = 0
            for i, lookup in enumerate(rank_equity_lookup):
                if ts in lookup:
                    last_values[i] = lookup[ts]
                combined += last_values[i]
            combined_equity_curve.append(make_equity_point(ts, combined))

        # Calculate Combined MDD
        max_dd = self._calc_mdd(combined_equity_curve) if combined_equity_curve else 0

        # Sort all trades by time
        all_trades.sort(key=lambda x: x.get('time', ''))

        # Calculate Activity Rate
        ref_feed = feeds.get(primary_symbol, list(feeds.values())[0])
        data_dates = set()
        for c in ref_feed:
            try:
                data_dates.add(datetime.fromisoformat(c['timestamp']).date())
            except:
                pass
        traded_dates = set()
        for t in all_trades:
            try:
                traded_dates.add(datetime.fromisoformat(t['time']).date())
            except:
                pass

        total_days = len(data_dates)
        traded_count = len(traded_dates)
        activity_rate = (traded_count / total_days * 100) if total_days > 0 else 0

        # Build resampled OHLCV data for visualization (performance optimization)
        resampled_ohlcv = self._resample_ohlcv(ref_feed, 3000)

        t_stats = time.time()
        perf_msg = f"[PARALLEL] Data: {t_data - t_start:.4f}s | Exec: {t_exec - t_data:.4f}s | Stats: {t_stats - t_exec:.4f}s | Total: {t_stats - t_start:.4f}s"
        print(perf_msg)

        # Build rank_stats_list from full_stats using PERFORMANCE_STAT_KEYS (auto-extraction)
        print(f"[DEBUG] Building rank_stats_list from {len(rank_results)} rank_results")
        rank_stats_list = []
        for r in rank_results:
            fs = r.get('full_stats', {})
            print(f"[DEBUG] Rank {r['rank']}: full_stats keys = {list(fs.keys())[:10]}")
            rank_stat = {"rank": r['rank'], "symbol": r['symbol']}
            for key in PERFORMANCE_STAT_KEYS:
                rank_stat[key] = fs.get(key)
            # Override total_return from rank result if not in full_stats
            if rank_stat.get('total_return') is None:
                rank_stat['total_return'] = r.get('return_pct', 0)
            rank_stats_list.append(rank_stat)
        print(f"[DEBUG] rank_stats_list built with {len(rank_stats_list)} items")

        # Calculate combined trade stats by AGGREGATING per-rank stats (NOT by mixing trades from different symbols)
        # This is correct for parallel mode where each rank runs independently
        combined_trade_stats = self._aggregate_rank_stats(rank_results, total_days, initial_capital)

        # Calculate decile_stats (Monthly Analysis) from all_trades
        # Use _analyze_trades to get FIFO-matched completed trades and decile stats
        ref_feed = feeds.get(primary_symbol, list(feeds.values())[0])
        start_ts = ref_feed[0]['timestamp'] if ref_feed else None
        end_ts = ref_feed[-1]['timestamp'] if ref_feed else None

        trade_analysis = self._analyze_trades(
            all_trades, start_ts, end_ts,
            total_days=total_days,
            calc_ranks=False,  # Already have rank_stats_list
            initial_capital=initial_capital,
            optimize_mode=False,  # Include monthly_stats
            equity_curve=combined_equity_curve
        )
        decile_stats = trade_analysis.get('decile_stats', [])
        print(f"[DEBUG] Combined stats aggregated from {len(rank_results)} ranks: win_rate={combined_trade_stats.get('win_rate')}, total_trades={combined_trade_stats.get('total_trades')}")

        # Return comprehensive result
        # NOTE: **combined_trade_stats goes FIRST so our specific values can override
        result = {
            # Trade analysis aggregated from per-rank stats - spread first
            **combined_trade_stats,
            # Override with our calculated values
            "total_return": total_return,
            "max_drawdown": max_dd,
            "activity_rate": activity_rate,
            "total_days": total_days,
            "total_trades": combined_trade_stats.get('total_trades', sum(r.get('full_stats', {}).get('total_trades', 0) for r in rank_results)),
            "chart_data": combined_equity_curve,
            "equity_curve": combined_equity_curve,
            "ohlcv_data": resampled_ohlcv,
            "multi_ohlcv_data": viz_feeds,
            "trades": all_trades,
            "logs": combined_logs[-100:],
            "perf_log": perf_msg,
            # Parallel-specific data
            "execution_mode": "parallel",
            "rank_results": rank_results,
            "rank_stats_list": rank_stats_list,  # Uses full_stats from _generate_stats (overrides empty from combined_trade_stats)
            "decile_stats": decile_stats,  # Monthly Analysis chart data
            "sum_of_rank_returns": sum_of_rank_returns,  # Sum of individual rank returns (for display)
            "capital_allocation": {
                "total": total_capital_deployed,  # Total deployed = initial_capital * num_ranks
                "per_rank": capital_per_rank,
                "num_ranks": num_ranks,
                "initial_capital": initial_capital,
                "distribution": [{"rank": r['rank'], "capital": r['allocated_capital'], "return_pct": r['return_pct'], "pnl": r['pnl']} for r in rank_results]
            },
        }

        return result

    def _analyze_trades_parallel(self, trades: List[Dict], start_date: str, end_date: str, total_days: int, initial_capital: float):
        """Analyze trades for parallel execution mode"""
        if not trades:
            return {
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
                "profit_factor": 0.0,
                "avg_holding_time": 0,
                "total_profit": 0.0,
                "total_loss": 0.0,
                "score": 0
            }

        # Pair buy/sell trades by rank
        rank_cycles = {}
        for t in trades:
            rank = t.get('strategy_rank', 0)
            if rank not in rank_cycles:
                rank_cycles[rank] = {"buys": [], "sells": []}
            if t['type'] == 'buy':
                rank_cycles[rank]["buys"].append(t)
            else:
                rank_cycles[rank]["sells"].append(t)

        pnls = []
        holding_times = []

        for rank, cycles in rank_cycles.items():
            buys = sorted(cycles["buys"], key=lambda x: x.get('time', ''))
            sells = sorted(cycles["sells"], key=lambda x: x.get('time', ''))

            # Simple pairing: each sell closes accumulated buys
            buy_queue = []
            for trade in buys + sells:
                if trade['type'] == 'buy':
                    buy_queue.append(trade)
                elif trade['type'] == 'sell' and buy_queue:
                    # Close all pending buys
                    total_buy_cost = sum(b['price'] * b['quantity'] for b in buy_queue)
                    total_qty = sum(b['quantity'] for b in buy_queue)
                    avg_buy_price = total_buy_cost / total_qty if total_qty > 0 else 0

                    sell_price = trade['price']
                    pnl = (sell_price - avg_buy_price) * total_qty
                    pnls.append(pnl)

                    # Holding time from first buy
                    if buy_queue:
                        try:
                            buy_time = datetime.fromisoformat(buy_queue[0]['time'])
                            sell_time = datetime.fromisoformat(trade['time'])
                            holding_minutes = (sell_time - buy_time).total_seconds() / 60
                            holding_times.append(holding_minutes)
                        except:
                            pass

                    buy_queue = []

        if not pnls:
            return {
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
                "profit_factor": 0.0,
                "avg_holding_time": 0,
                "total_profit": 0.0,
                "total_loss": 0.0,
                "score": 0
            }

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_profit = sum(wins)
        total_loss = abs(sum(losses))

        win_rate = (len(wins) / len(pnls) * 100) if pnls else 0
        avg_pnl_raw = sum(pnls) / len(pnls) if pnls else 0
        max_profit_raw = max(pnls) if pnls else 0
        max_loss_raw = min(pnls) if pnls else 0

        # Convert to percentage of initial capital
        avg_pnl = (avg_pnl_raw / initial_capital * 100) if initial_capital > 0 else 0
        max_profit = (max_profit_raw / initial_capital * 100) if initial_capital > 0 else 0
        max_loss = (max_loss_raw / initial_capital * 100) if initial_capital > 0 else 0

        profit_factor = (total_profit / total_loss) if total_loss > 0 else float('inf') if total_profit > 0 else 0
        avg_holding = sum(holding_times) / len(holding_times) if holding_times else 0

        # Simple score
        score = int(win_rate * 0.3 + min(profit_factor * 10, 30) + min(len(pnls), 40))

        return {
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "profit_factor": profit_factor,
            "avg_holding_time": int(avg_holding),
            "total_profit": total_profit,
            "total_loss": total_loss,
            "score": score
        }

    # ... _generate_stats, _empty_result, etc. (Existing methods remain) ...
    # ... _generate_stats, _empty_result, etc. (Existing methods remain) ...
    def _generate_stats(self, context: BacktestContext, data_feed: List[Dict], optimize_mode: bool = False):
        if not context.equity_curve:
             return self._empty_result(logs=context.logs)

        final_equity = context.equity_curve[-1][EQUITY_VALUE_KEY]
        initial_equity = context.equity_curve[0][EQUITY_VALUE_KEY]
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

        return {
            "total_return": total_return,
            "max_drawdown": self._calc_mdd(context.equity_curve),
            "activity_rate": activity_rate,
            "total_days": total_days,
            "chart_data": self._resample_equity(context.equity_curve, 3000) if not optimize_mode else [],
            "ohlcv_data": self._resample_ohlcv(data_feed, 3000) if not optimize_mode else [],
            "logs": context.logs[-50:],
            "trades": context.trades,
            **self._analyze_trades(context.trades, data_feed[0]['timestamp'], data_feed[-1]['timestamp'], total_days=total_days, initial_capital=initial_equity, optimize_mode=optimize_mode, equity_curve=context.equity_curve)
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

    def _analyze_trades(self, trades: List[Dict], start_ts: Any = None, end_ts: Any = None, total_days: int = 0, calc_ranks: bool = True, initial_capital: float = 10000000, optimize_mode: bool = False, equity_curve: List[Dict] = None) -> Dict[str, Any]:
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
            bucket_stats = decile_data['bucket_stats']
        else:
            monthly_stats = []
            bucket_stats = []

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
            "bucket_stats": bucket_stats,  # N-bucket stats for UI
            "stability_score": stability_score,
            "acceleration_score": acceleration_score,
            "cycle_count": base_stats.get('cycle_count'),
            "cycle_avg_pnl": base_stats.get('cycle_avg_pnl'),
            "cycle_avg_hold": base_stats.get('cycle_avg_hold'),
            "cycle_max_hold": base_stats.get('cycle_max_hold'),
            "cycle_min_hold": base_stats.get('cycle_min_hold'),
            "rank_stats_list": self._calc_rank_stats(completed_trades, total_days, start_ts, end_ts, initial_capital, equity_curve=equity_curve, raw_trades=trades) if calc_ranks else []
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
        # Group ALL trades by cycle_id (not just CLOSE) to compute hold times
        cycle_data = {}  # {cycle_id: {"pnl": float, "max_hold_sec": float}}
        for t in completed_trades:
            meta = t.get('metadata', {})
            cycle_id = meta.get('cycle_id')
            if cycle_id is None:
                continue
            if cycle_id not in cycle_data:
                cycle_data[cycle_id] = {"pnl": 0.0, "max_hold_sec": 0.0}
            # Only sum PnL from CLOSE-level trades (sell trades)
            if meta.get('level') == 'CLOSE':
                cycle_data[cycle_id]["pnl"] += t.get('pnl_percent', 0) * 100
            # Max holding_seconds in cycle = time from first buy to sell (cycle duration)
            hold_sec = t.get('holding_seconds', 0)
            if hold_sec > cycle_data[cycle_id]["max_hold_sec"]:
                cycle_data[cycle_id]["max_hold_sec"] = hold_sec

        total_cycles = len(cycle_data) if cycle_data else 0
        cycle_stats = {
            "cycle_count": None,
            "cycle_avg_pnl": None,
            "cycle_avg_hold": None,
            "cycle_max_hold": None,
            "cycle_min_hold": None,
        }

        if total_cycles > 0:
            total_cycle_pnl = sum(c["pnl"] for c in cycle_data.values())
            cycle_hold_times = [c["max_hold_sec"] for c in cycle_data.values()]
            avg_cycle_hold_min = int((sum(cycle_hold_times) / total_cycles) / 60)
            max_cycle_hold_min = int(max(cycle_hold_times) / 60)
            min_cycle_hold_min = int(min(cycle_hold_times) / 60)
            avg_pnl_per_cycle = total_cycle_pnl / total_cycles

            cycle_stats = {
                "cycle_count": total_cycles,
                "cycle_avg_pnl": round(avg_pnl_per_cycle, 2),
                "cycle_avg_hold": avg_cycle_hold_min,
                "cycle_max_hold": max_cycle_hold_min,
                "cycle_min_hold": min_cycle_hold_min,
            }
            print(f"[DEBUG] Martingale Cycles: {total_cycles} cycles, "
                  f"Avg PnL: {avg_pnl_per_cycle:.2f}%, "
                  f"Hold(avg/max/min): {avg_cycle_hold_min}/{max_cycle_hold_min}/{min_cycle_hold_min}m")

        return {
            "win_rate": win_rate,
            "avg_pnl": avg_pnl_percent,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "avg_holding_time": avg_holding_min,
            **cycle_stats,
        }

    def _aggregate_rank_stats(self, rank_results: List[Dict], total_days: int, initial_capital: float) -> Dict[str, Any]:
        """
        Aggregate statistics from per-rank results for parallel execution mode.
        This is more accurate than mixing trades from different symbols and doing FIFO matching.

        Each rank's stats come from _generate_stats which does proper FIFO matching per symbol.
        We aggregate these to get combined portfolio statistics.
        """
        if not rank_results:
            empty = {key: None for key in PERFORMANCE_STAT_KEYS}
            empty.update({"total_trades": 0, "rank_stats_list": []})
            return empty

        # Collect stats from each rank's full_stats
        all_win_rates = []
        all_avg_pnls = []
        all_max_profits = []
        all_max_losses = []
        all_profit_factors = []
        all_sharpe_ratios = []
        all_holding_times = []
        all_trade_counts = []
        all_stability_scores = []
        all_acceleration_scores = []

        total_gross_profit = 0
        total_gross_loss = 0

        # Cycle stats aggregation
        total_cycles_sum = 0
        total_cycle_pnl_sum = 0.0
        total_cycle_hold_sum = 0.0  # sum of (avg_hold * count) for weighted avg
        all_cycle_max_holds = []
        all_cycle_min_holds = []
        has_any_cycles = False

        for r in rank_results:
            fs = r.get('full_stats', {})
            # Use completed (FIFO-matched) trade count, not raw buy+sell count
            trade_count = fs.get('total_trades', 0)
            if trade_count == 0:
                trade_count = r.get('trades_count', 0)  # fallback to raw

            if trade_count == 0:
                continue

            all_trade_counts.append(trade_count)

            # Extract stats (handle both numeric and string formats)
            def parse_pct(v):
                if isinstance(v, str):
                    return float(v.replace('%', '').strip())
                return float(v) if v else 0.0

            win_rate = parse_pct(fs.get('win_rate', 0))
            avg_pnl = parse_pct(fs.get('avg_pnl', 0))
            max_profit = parse_pct(fs.get('max_profit', 0))
            max_loss = parse_pct(fs.get('max_loss', 0))

            pf = fs.get('profit_factor', 0)
            profit_factor = float(pf) if pf else 0.0

            sr = fs.get('sharpe_ratio', 0)
            sharpe_ratio = float(sr) if sr else 0.0

            ht = fs.get('avg_holding_time', 0)
            holding_time = float(ht) if ht else 0.0

            ss = fs.get('stability_score', 0)
            stability_score = float(ss) if ss else 0.0

            accel = fs.get('acceleration_score', 1.0)
            acceleration_score = float(accel) if accel else 1.0

            all_win_rates.append((win_rate, trade_count))
            all_avg_pnls.append((avg_pnl, trade_count))
            all_max_profits.append(max_profit)
            all_max_losses.append(max_loss)
            all_profit_factors.append(profit_factor)
            all_sharpe_ratios.append((sharpe_ratio, trade_count))
            all_holding_times.append((holding_time, trade_count))
            all_stability_scores.append((stability_score, trade_count))
            all_acceleration_scores.append((acceleration_score, trade_count))

            # Cycle stats from each rank
            rank_cycles = fs.get('cycle_count')
            if rank_cycles is not None and rank_cycles > 0:
                has_any_cycles = True
                total_cycles_sum += rank_cycles
                rank_avg_pnl = fs.get('cycle_avg_pnl', 0) or 0
                total_cycle_pnl_sum += rank_avg_pnl * rank_cycles
                rank_avg_hold = fs.get('cycle_avg_hold', 0) or 0
                total_cycle_hold_sum += rank_avg_hold * rank_cycles
                if fs.get('cycle_max_hold') is not None:
                    all_cycle_max_holds.append(fs['cycle_max_hold'])
                if fs.get('cycle_min_hold') is not None:
                    all_cycle_min_holds.append(fs['cycle_min_hold'])

            # Estimate gross profit/loss from rank PnL and win rate
            rank_pnl = r.get('pnl', 0)
            if rank_pnl > 0:
                total_gross_profit += rank_pnl
            else:
                total_gross_loss += abs(rank_pnl)

        total_trades = sum(all_trade_counts) if all_trade_counts else 0

        if total_trades == 0:
            empty = {key: None for key in PERFORMANCE_STAT_KEYS}
            empty.update({"total_trades": 0, "rank_stats_list": []})
            return empty

        # Weighted averages by trade count
        def weighted_avg(values_with_weights):
            total_weight = sum(w for _, w in values_with_weights)
            if total_weight == 0:
                return 0.0
            return sum(v * w for v, w in values_with_weights) / total_weight

        combined_win_rate = weighted_avg(all_win_rates)
        combined_avg_pnl = weighted_avg(all_avg_pnls)
        combined_sharpe = weighted_avg(all_sharpe_ratios)
        combined_holding_time = int(weighted_avg(all_holding_times))
        combined_stability = weighted_avg(all_stability_scores)
        combined_acceleration = weighted_avg(all_acceleration_scores)

        # Max/Min across all ranks
        combined_max_profit = max(all_max_profits) if all_max_profits else 0.0
        combined_max_loss = min(all_max_losses) if all_max_losses else 0.0

        # Profit factor from aggregated gross profit/loss
        combined_profit_factor = (total_gross_profit / total_gross_loss) if total_gross_loss > 0 else 99.99

        result = {
            "win_rate": round(combined_win_rate, 1),
            "avg_pnl": round(combined_avg_pnl, 2),
            "max_profit": round(combined_max_profit, 2),
            "max_loss": round(combined_max_loss, 2),
            "profit_factor": round(combined_profit_factor, 2),
            "sharpe_ratio": round(combined_sharpe, 2),
            "avg_holding_time": combined_holding_time,
            "total_trades": total_trades,
            "stability_score": round(combined_stability, 2),
            "acceleration_score": round(combined_acceleration, 2),
            "rank_stats_list": []  # Will be overridden by explicit rank_stats_list
        }

        # Add cycle stats if any rank had cycles
        if has_any_cycles and total_cycles_sum > 0:
            result["cycle_count"] = total_cycles_sum
            result["cycle_avg_pnl"] = round(total_cycle_pnl_sum / total_cycles_sum, 2)
            result["cycle_avg_hold"] = int(total_cycle_hold_sum / total_cycles_sum)
            result["cycle_max_hold"] = max(all_cycle_max_holds) if all_cycle_max_holds else None
            result["cycle_min_hold"] = min(all_cycle_min_holds) if all_cycle_min_holds else None

        return result

    def _calc_rank_stats(self, trades: List[Dict], total_days: int, start_ts: Any, end_ts: Any, initial_capital: float, equity_curve: List[Dict] = None, raw_trades: List[Dict] = None) -> List[Dict]:
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

            # 3. Activity Rate (use raw trades for buy+sell days, matching OVERVIEW)
            if total_days > 0 and raw_trades:
                rank_raw_trades = [t for t in raw_trades if t.get('strategy_rank') == r]
                uniq_days = len(set(t['time'][:10] for t in rank_raw_trades)) if rank_raw_trades else 0
                activity_rate = (uniq_days / total_days * 100)
            elif total_days > 0 and r_trades:
                # Fallback: completed trades only
                uniq_days = len(set(t['time'][:10] for t in r_trades))
                activity_rate = (uniq_days / total_days * 100)
            else:
                activity_rate = 0.0

            # 4. Max Drawdown (Unrealized + Realized)
            # Use equity curve to capture unrealized DD during martingale phases.
            # For single-rank or exclusive mode, the equity curve directly reflects
            # this rank's unrealized P&L. For multi-rank, we extract active periods.
            max_dd_pct = 0.0
            max_dd_val = 0.0

            if equity_curve and raw_trades:
                # Get all unique ranks from raw trades
                all_ranks = set(t.get('strategy_rank', 0) for t in raw_trades)
                num_active_ranks = len([rr for rr in all_ranks if rr > 0])

                if num_active_ranks <= 1:
                    # Single rank: equity curve IS this rank's curve → use directly
                    max_dd_pct = self._calc_mdd(equity_curve)
                else:
                    # Multi-rank (exclusive): extract active periods for this rank
                    rank_raw = sorted(
                        [t for t in raw_trades if t.get('strategy_rank') == r],
                        key=lambda x: x['time']
                    )

                    # Build active periods (when this rank holds positions)
                    position_qty = 0
                    active_start = None
                    active_periods = []  # [(start_idx, end_idx), ...]

                    # Normalize trade timestamps to equity curve format for comparison
                    # Equity curve uses "%Y-%m-%d %H:%M", trades use ISO format
                    def normalize_ts(ts_str):
                        """Convert any timestamp to '%Y-%m-%d %H:%M' for matching."""
                        try:
                            dt = datetime.fromisoformat(ts_str) if 'T' in ts_str else datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
                            return dt.strftime("%Y-%m-%d %H:%M")
                        except:
                            return ts_str

                    trade_events = []  # [(normalized_ts, delta_qty)]
                    for t in rank_raw:
                        norm_ts = normalize_ts(t['time'])
                        if t['type'] == 'buy':
                            trade_events.append((norm_ts, t['quantity']))
                        elif t['type'] == 'sell':
                            trade_events.append((norm_ts, -t['quantity']))

                    # Walk equity curve, tracking position state
                    sorted_eq = sorted(equity_curve, key=lambda p: p[EQUITY_DATE_KEY])
                    event_idx = 0
                    pos_qty = 0
                    peak_val = initial_capital
                    rank_max_dd_ratio = 0.0

                    for pt in sorted_eq:
                        eq_ts = pt[EQUITY_DATE_KEY]
                        val = pt[EQUITY_VALUE_KEY]

                        # Process any trade events at or before this timestamp
                        while event_idx < len(trade_events) and trade_events[event_idx][0] <= eq_ts:
                            pos_qty += trade_events[event_idx][1]
                            event_idx += 1

                        if pos_qty > 0:
                            # This rank has a position → track DD
                            if val > peak_val:
                                peak_val = val
                            dd_val_cur = peak_val - val
                            if dd_val_cur > 0 and peak_val > 0:
                                dd_ratio = dd_val_cur / peak_val
                                if dd_ratio > rank_max_dd_ratio:
                                    rank_max_dd_ratio = dd_ratio
                                    max_dd_val = dd_val_cur
                        else:
                            # No position → reset peak to current (capital may have changed)
                            peak_val = max(peak_val, val)

                    max_dd_pct = -(rank_max_dd_ratio * 100)
            else:
                # Fallback: realized-only DD
                max_dd_pct = self._calc_rank_dd_realized(r_trades, initial_capital)

            rank_stats.append({
                "rank": r,
                "total_return": float(f"{total_return_pct:.2f}"), # Total Return %
                "total_pnl_value": int(total_pnl_value),
                "activity_rate": float(f"{activity_rate:.1f}"),
                "max_drawdown": float(f"{max_dd_pct:.2f}"),
                "max_drawdown_value": int(max_dd_val),
                **base_stats
            })

        return rank_stats

    def _calc_rank_dd_realized(self, r_trades: List[Dict], initial_capital: float) -> float:
        """Fallback: DD from realized PnL only (legacy method)."""
        sorted_trades = sorted(r_trades, key=lambda x: x['time'])
        virtual_equity = initial_capital
        peak_equity = initial_capital
        max_dd_ratio = 0.0
        for t in sorted_trades:
            virtual_equity += t['pnl']
            if virtual_equity > peak_equity:
                peak_equity = virtual_equity
            dd_val = peak_equity - virtual_equity
            if dd_val > 0 and peak_equity > 0:
                dd_ratio = dd_val / peak_equity
                if dd_ratio > max_dd_ratio:
                    max_dd_ratio = dd_ratio
        return -(max_dd_ratio * 100) if initial_capital > 0 else 0.0

    def _calc_deciles(self, trades: List[Dict], start_ts: Any, end_ts: Any, n_buckets: int = 12) -> List[Dict]:
        """
        Calculates Periodic Stats using N-bucket approach (CENTRALIZED).

        Uses stats_utils.calc_stability_stats for stability/acceleration calculation.
        Also generates monthly_stats for UI chart display (legacy support).

        Args:
            trades: List of completed trades
            start_ts: Start timestamp
            end_ts: End timestamp
            n_buckets: Number of buckets for stability calculation (default: 12)
        """
        import time
        from collections import defaultdict
        from .stats_utils import calc_stability_stats

        start_time = time.time()

        # --- 1. Calculate Stability/Acceleration using N-bucket approach (CENTRALIZED) ---
        stability_data = calc_stability_stats(trades, n_buckets=n_buckets)
        stability_score = stability_data['stability_score']
        acceleration_score = stability_data['acceleration_score']
        bucket_stats = stability_data['bucket_stats']  # N-bucket stats for UI

        # --- 2. Generate Monthly Stats for UI Chart (Legacy Support) ---
        def parse(t): return t if isinstance(t, datetime) else datetime.fromisoformat(t)

        start_dt = parse(start_ts).date()
        end_dt = parse(end_ts).date()

        curr = start_dt.replace(day=1)
        end_cap = end_dt.replace(day=1)

        monthly_trades = defaultdict(list)
        for t in trades:
            t_date = parse(t['time']).date()
            month_key = t_date.strftime("%Y-%m")
            monthly_trades[month_key].append(t)

        monthly_stats = []
        while curr <= end_cap:
            month_key = curr.strftime("%Y-%m")
            chunk = monthly_trades.get(month_key, [])

            if chunk:
                total_pnl = sum(t['pnl_percent'] for t in chunk) * 100
                avg_pnl = total_pnl / len(chunk)
                wins = len([t for t in chunk if t['pnl'] > 0])
                win_rate = wins / len(chunk) * 100
            else:
                total_pnl = 0.0
                avg_pnl = 0.0
                win_rate = 0.0

            date_label = curr.strftime("%y-%m")
            monthly_stats.append({
                "block": date_label,
                "avg_pnl": float(f"{avg_pnl:.2f}"),
                "total_pnl": float(f"{total_pnl:.2f}"),
                "win_rate": float(f"{win_rate:.1f}"),
                "date_range": date_label,
                "count": len(chunk)
            })

            if curr.month == 12:
                curr = curr.replace(year=curr.year + 1, month=1)
            else:
                curr = curr.replace(month=curr.month + 1)

        elapsed_ms = (time.time() - start_time) * 1000
        print(f"[PERF] _calc_deciles: {len(trades)} trades, {n_buckets} buckets → {elapsed_ms:.2f}ms")

        return {
            "monthly_stats": monthly_stats,
            "bucket_stats": bucket_stats,  # N-bucket stats for UI
            "stability_score": stability_score,
            "acceleration_score": acceleration_score
        }

    def _resample_ohlcv(self, data: List[Dict], target_count: int = 3000) -> List[Dict]:
        """Resample OHLCV data to target_count for chart performance."""
        if not data:
            return []

        # If data is small enough, return all
        if len(data) <= target_count:
            return [{
                "time": int(datetime.fromisoformat(d['timestamp']).timestamp()),
                "open": d['open'],
                "high": d['high'],
                "low": d['low'],
                "close": d['close']
            } for d in data]

        # Resample by picking every N-th candle
        step = len(data) / target_count
        result = []
        for i in range(target_count):
            idx = int(i * step)
            d = data[idx]
            result.append({
                "time": int(datetime.fromisoformat(d['timestamp']).timestamp()),
                "open": d['open'],
                "high": d['high'],
                "low": d['low'],
                "close": d['close']
            })

        # Always include the last candle for accurate end time
        last = data[-1]
        if result[-1]["time"] != int(datetime.fromisoformat(last['timestamp']).timestamp()):
            result.append({
                "time": int(datetime.fromisoformat(last['timestamp']).timestamp()),
                "open": last['open'],
                "high": last['high'],
                "low": last['low'],
                "close": last['close']
            })

        return result

    def _resample_equity(self, data: List[Dict], target_count: int = 3000) -> List[Dict]:
        """Resample equity curve data to target_count for chart performance."""
        if not data or len(data) <= target_count:
            return data

        step = len(data) / target_count
        result = [data[int(i * step)] for i in range(target_count)]

        # Always include the last point
        if result[-1] != data[-1]:
            result.append(data[-1])

        return result

    def _calc_mdd(self, equity_curve):
        if not equity_curve: return 0.0
        peak = equity_curve[0][EQUITY_VALUE_KEY]
        max_dd = 0.0
        for point in equity_curve:
            val = point[EQUITY_VALUE_KEY]
            if val > peak: peak = val
            dd = (peak - val) / peak
            if dd > max_dd: max_dd = dd
        return -(max_dd * 100)
