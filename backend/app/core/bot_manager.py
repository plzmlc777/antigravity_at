import asyncio
import uuid
import logging
from typing import Dict, Any, List
from datetime import datetime
from ..strategies.base import BaseStrategy
from ..strategies.rsi import RSIStrategy
from ..adapters.kiwoom_real import KiwoomRealAdapter
import random

logger = logging.getLogger("BotManager")

class TradingBot:
    def __init__(self, bot_id: str, config: Dict[str, Any], adapter: Any = None):
        self.id = bot_id
        self.symbol = config['symbol']
        self.interval = config.get('interval', 60) # seconds
        self.amount = config.get('amount', 100000) # KRW
        self.is_running = False
        self.logs: List[Dict] = []
        
        # Simulation Mode: 'random', 'virtual', or None (Real)
        self.sim_mode = config.get('sim_mode', None)
        self.adapter = adapter
        
        # Paper Trading State
        self.held_quantity = 0
        self.avg_price = 0
        
        # Initialize Strategy
        strategy_config = config.get('strategy_config', {})
        if config['strategy'] == 'rsi':
            self.strategy = RSIStrategy(strategy_config)
        else:
            raise ValueError(f"Unknown strategy: {config['strategy']}")

    async def run_loop(self):
        self.is_running = True
        mode_str = f"Simulation ({self.sim_mode})" if self.sim_mode else "REAL TRADING"
        self.log(f"Bot started [{mode_str}]. Interval: {self.interval}s")
        
        # Initial Price History for RSI (Need at least 15+ points)
        # Seed with a random walk from a base price
        processed_prices = [70000]
        for _ in range(20):
             processed_prices.append(processed_prices[-1] + random.randint(-200, 200))
        
        last_random_price = processed_prices[-1]

        while self.is_running:
            # print(f"DEBUG: Bot {self.id} Loop Start. Interval: {self.interval}")
            try:
                current_price = 0
                
                # 1. Get Current Price
                if self.sim_mode == 'random':
                    # Random Walk Logic
                    change = random.randint(-500, 500)
                    last_random_price += change
                    current_price = abs(last_random_price)
                elif self.adapter:
                     # Virtual or Real
                    price_data = await self.adapter.get_current_price(self.symbol.replace("[TEST] ", "").replace("[V-SIM] ", ""))
                    current_price = price_data.get('price', 0)
                    if current_price == 0 and self.sim_mode == 'virtual':
                         current_price = processed_prices[-1] # Fallback
                else:
                    self.log("Error: No adapter config", is_error=True)
                    break
                
                processed_prices.append(current_price)
                if len(processed_prices) > 30: processed_prices.pop(0)

                # 2. Analyze
                market_data = {'price_history': processed_prices, 'current_price': current_price}
                signal = self.strategy.calculate_signals(market_data)
                
                rsi_val = getattr(self.strategy, 'last_rsi', 0)
                
                # Log Status
                holding_status = f"(Held: {self.held_quantity})" if self.held_quantity > 0 else "(No Position)"
                self.log(f"Price: {current_price:,.0f} | RSI: {rsi_val:.1f} | Signal: {signal} {holding_status}")

                # 3. Execute (Stateful Logic)
                if self.sim_mode == 'random' or self.sim_mode == 'virtual':
                    # Simulation Execution
                    if signal == 'buy':
                        if self.held_quantity == 0:
                            qty = int(self.amount / current_price)
                            if qty > 0:
                                self.held_quantity = qty
                                self.avg_price = current_price
                                self.log(f"[SIM] BUY EXECUTED! Qty: {qty} @ {current_price:,.0f}")
                        else:
                            self.log(f"[SIM] BUY Signal ignored (Already held).")
                    
                    elif signal == 'sell':
                        if self.held_quantity > 0:
                            profit = (current_price - self.avg_price) * self.held_quantity
                            self.log(f"[SIM] SELL EXECUTED! PnL: {profit:,.0f} KRW")
                            self.held_quantity = 0
                            self.avg_price = 0
                        else:
                            self.log(f"[SIM] SELL Signal ignored (No position).")
                else:
                    # Real Trading Execution (Placeholder)
                    if signal == 'buy':
                        self.log(f"REAL BUY Signal! (Not implemented)")
                        # await self.adapter.place_buy_order(...)
                    elif signal == 'sell':
                        self.log(f"REAL SELL Signal!")

            except Exception as e:
                self.log(f"Error in loop: {str(e)}", is_error=True)

            # Wait Loop
            for _ in range(self.interval):
                if not self.is_running: break
                await asyncio.sleep(1)

    def stop(self):
        self.is_running = False
        self.log("Bot stopping...")

    def log(self, message: str, is_error: bool = False):
        entry = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'message': message,
            'is_error': is_error
        }
        self.logs.insert(0, entry) # Prepend to show latest first
        if len(self.logs) > 50: self.logs.pop()

class BotManager:
    def __init__(self):
        self.bots: Dict[str, TradingBot] = {}
        self.adapter = KiwoomRealAdapter()

    def start_bot(self, config: Dict[str, Any]) -> str:
        bot_id = str(uuid.uuid4())[:8]
        bot = TradingBot(bot_id, config, adapter=self.adapter)
        self.bots[bot_id] = bot
        asyncio.create_task(bot.run_loop())
        return bot_id

    def stop_bot(self, bot_id: str):
        if bot_id in self.bots:
            self.bots[bot_id].stop()
    
    def remove_bot(self, bot_id: str):
        if bot_id in self.bots:
            self.bots[bot_id].stop()
            del self.bots[bot_id]

    def get_status(self) -> List[Dict]:
        return [{
            'id': b.id,
            'symbol': b.symbol,
            'strategy': b.strategy.name,
            'interval': b.interval,
            'amount': b.amount,
            'sim_mode': b.sim_mode,
            'is_running': b.is_running,
            'logs': b.logs
        } for b in self.bots.values()]

# Global instance
bot_manager = BotManager()
