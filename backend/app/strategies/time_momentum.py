from datetime import datetime, timedelta
from typing import Dict, Any
from .base import BaseStrategy

class TimeMomentumStrategy(BaseStrategy):
    """
    User Requested Strategy:
    1. Start Time + Delay => Check Price Change.
    2. If change > target_percent => BUY.
    3. If price rises > trailing_start_percent => Activate Trailing Stop.
    4. Force Sell at Stop Time or if Stop Loss hit.
    """
    def initialize(self):
        # Parameters from config
        self.start_time_str = self.config.get("start_time", "09:00")
        self.stop_time_str = self.config.get("stop_time", "15:00")
        
        # Parse times
        self.start_time = datetime.strptime(self.start_time_str, "%H:%M").time()
        self.stop_time = datetime.strptime(self.stop_time_str, "%H:%M").time()
        
        self.delay_minutes = int(self.config.get("delay_minutes", 10)) # e.g., 10 mins
        
        # Direction Logic: 'rise' (Momentum) or 'fall' (Dip)
        self.direction = self.config.get("direction", "rise")  
        
        # User input is expected to be integer percentage (e.g. 2 for 2%)
        # standardizing input: float(val) / 100.0
        raw_target = float(self.config.get("target_percent", 2.0))
        self.target_percent = abs(raw_target) / 100.0 # Force positive
        
        # User input is positive percentage (e.g. 3 for 3% loss)
        raw_stop = float(self.config.get("safety_stop_percent", 3.0))
        self.safety_stop_percent = -(abs(raw_stop) / 100.0) # Force negative
        
        self.trailing_start_percent = float(self.config.get("trailing_start_percent", 5.0)) / 100.0
        self.trailing_stop_drop = float(self.config.get("trailing_stop_drop", 2.0)) / 100.0 
        
        # State Variables
        self.reference_price = None
        self.has_bought = False
        self.peak_price = 0
        self.trailing_active = False
        self.last_trade_date = None
        self.checked_today = False # Fix: Ensure we only check trigger ONCE per day

    def on_data(self, data: Dict[str, Any]):
        current_time = self.context.get_time()
        current_price = data['close']
        symbol = "TEST" # Configurable in real scenario
        
        # Reset daily state on new day
        if self.last_trade_date != current_time.date() and self.last_trade_date is not None:
             # If we moved to a new day, reset checks (unless we handle this via last_trade_date check below)
             # Better: Detect date change to reset 'checked_today'
             pass

        # Since on_data runs sequential, we can detect new day easily
        # But simplify: We store 'checked_date'.
        
        # 1. Establish Reference Price (Start Time)
        if current_time.time() == self.start_time:
            self.reference_price = current_price
            self.checked_today = False # Reset for new day
            self.context.log(f"Market Start. Reference Price: {self.reference_price}")

        # 2. Check Entry Condition (Start Time + Delay)
        # Construct trigger time for today
        trigger_time = datetime.combine(current_time.date(), self.start_time) + timedelta(minutes=self.delay_minutes)
        
        # Check if we already traded today
        already_traded = False
        if self.last_trade_date == current_time.date():
             already_traded = True
        
        # STRICT SNAPSHOT CHECK:
        # Buy ONLY if current_time >= trigger_time AND we haven't checked yet today.
        # This ensures we don't buy at 14:00 if condition was met late.
        if not self.has_bought and not already_traded and self.reference_price:
             if current_time >= trigger_time and not self.checked_today:
                
                self.checked_today = True # Mark as checked immediately
                
                # Check price change from Start Time
                change = (current_price - self.reference_price) / self.reference_price
                
                should_buy = False
                
                if self.direction == "fall":
                    # Dip Buying: Buy if price dropped MORE than target (e.g. change <= -0.02)
                    if change <= -self.target_percent:
                        should_buy = True
                else:
                    # Rise Buying (Momentum): Buy if price rose MORE than target (e.g. >= 0.02)
                    if change >= self.target_percent:
                        should_buy = True
                
                quantity = 0

                if should_buy:
                    # Betting Strategy
                    betting_mode = self.config.get("betting_strategy", "fixed")
                    initial_capital = self.config.get("initial_capital", 10000000)
                    
                    cash = self.context.cash
                    
                    if betting_mode == "fixed":
                        bet_amount = initial_capital * 0.99
                        quantity = int(bet_amount / current_price)
                    else:
                        quantity = int((max(0, cash) * 0.99) / current_price)

                if quantity > 0:
                    self.context.buy(symbol, quantity)
                    self.has_bought = True
                    self.peak_price = current_price
                    self.last_trade_date = current_time.date() # Mark as traded today
                    target_display = -self.target_percent if self.direction == "fall" else self.target_percent
                    self.context.log(f"Entry Triggered ({self.direction} | {betting_mode})! Change: {change*100:.2f}% vs Target {target_display*100:.2f}% | Qty: {quantity}")
                else:
                    self.context.log("Entry Signal, but insufficient cash (or 0 qty).")

        # 3. Manage Position (If bought)
        if self.has_bought:
            # Update Peak
            if current_price > self.peak_price:
                self.peak_price = current_price

            # Check Safety Stop
            entry_price = self.reference_price * (1 + self.target_percent) # Approximate
            current_return = (current_price - entry_price) / entry_price
            
            if current_return <= self.safety_stop_percent:
                 qty = self.context.holdings.get(symbol, 0)
                 if qty > 0:
                     self.context.sell(symbol, qty)
                     self.has_bought = False
                     self.context.log(f"Safety Stop Hit! Sold {qty}")
                 return

            # Trailing Stop Logic
            if not self.trailing_active:
                if current_return >= self.trailing_start_percent:
                    self.trailing_active = True
                    self.context.log("Trailing Stop Activated!")
            
            if self.trailing_active:
                drop_from_peak = (self.peak_price - current_price) / self.peak_price
                if drop_from_peak >= self.trailing_stop_drop:
                    qty = self.context.holdings.get(symbol, 0)
                    if qty > 0:
                        self.context.sell(symbol, qty)
                        self.has_bought = False
                        self.context.log(f"Trailing Stop Hit! Sold {qty}")
                    return

            # Time Stop (Force Sell at Stop Time)
            if current_time.time() >= self.stop_time:
                 qty = self.context.holdings.get(symbol, 0)
                 if qty > 0:
                     self.context.sell(symbol, qty)
                     self.has_bought = False
                     self.context.log(f"Time Stop (End of Day). Sold {qty}")
