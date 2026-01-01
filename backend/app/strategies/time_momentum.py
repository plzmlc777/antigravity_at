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
        # Helper for robust parsing
        def get_param(key, default, cast_type=float):
            val = self.config.get(key)
            if val is None or val == "":
                return default
            try:
                return cast_type(val)
            except (ValueError, TypeError):
                return default

        # Parameters from config
        self.start_time_str = self.config.get("start_time") or "09:00"
        self.stop_time_str = self.config.get("stop_time") or "15:00"
        
        # Parse times
        try:
            self.start_time = datetime.strptime(self.start_time_str, "%H:%M").time()
        except ValueError:
             self.start_time = datetime.strptime("09:00", "%H:%M").time()
             
        try:
            self.stop_time = datetime.strptime(self.stop_time_str, "%H:%M").time()
        except ValueError:
             self.stop_time = datetime.strptime("15:00", "%H:%M").time()
        
        self.delay_minutes = get_param("delay_minutes", 10, int)
        
        # Direction Logic: 'rise' (Momentum) or 'fall' (Dip)
        self.direction = self.config.get("direction", "rise")  
        
        # User input is expected to be integer percentage (e.g. 2 for 2%)
        # standardizing input: float(val) / 100.0
        raw_target = get_param("target_percent", 2.0, float)
        self.target_percent = abs(raw_target) / 100.0 # Force positive
        
        # User input is positive percentage (e.g. 3 for 3% loss)
        raw_stop = get_param("safety_stop_percent", 3.0, float)
        self.safety_stop_percent = -(abs(raw_stop) / 100.0) # Force negative
        
        self.trailing_start_percent = get_param("trailing_start_percent", 5.0, float) / 100.0
        self.trailing_stop_drop = get_param("trailing_stop_drop", 2.0, float) / 100.0 
        
        # State Variables
        self.reference_price = None
        self.has_bought = False
        self.peak_price = 0
        self.trailing_active = False
        self.last_trade_date = None
        self.entry_price = 0 # Fix: Store actual entry price
        self.checked_today = False # Fix: Ensure we only check trigger ONCE per day
        self.current_trading_date = None # Fix: Track Date for Reset

    def on_data(self, data: Dict[str, Any]):
        current_time = self.context.get_time()
        current_date_obj = current_time.date()
        current_price = data['close']
        symbol = "TEST" # Configurable in real scenario
        
        # Reset daily state on new day
        if self.current_trading_date != current_date_obj:
             self.current_trading_date = current_date_obj
             self.reference_price = None # Reset reference
             self.checked_today = False # Reset trigger check
             self.entry_price = 0
             self.has_bought = False # Ensure buy state is reset (though sell logic handles it, safety net)
             # Note: has_bought is strictly for 'holding position'. 
             # If we are holding over-night, we shouldn't reset has_bought?
             # Strategy implies Intraday mostly, but if we hold overnight, we shouldn't reset has_bought.
             # BUT 'Activity Rate' implies daily trades.
             # If we are holding, we cannot buy again anyway due to 'if not self.has_bought'.
             # So 'reference_price = None' is fine.
             
        # 1. Establish Reference Price (Start Time or First Candle After)
        if current_time.time() >= self.start_time and self.reference_price is None:
            self.reference_price = current_price
            self.context.log(f"Market Start (or First Data). Reference Price: {self.reference_price} at {current_time.time()}")
            
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
                    self.entry_price = current_price # Fix: Record Actual Entry Price
                    self.peak_price = current_price
                    self.trailing_active = False # Fix: Reset trailing state on new trade
                    self.last_trade_date = current_time.date() # Mark as traded today
                    target_display = -self.target_percent if self.direction == "fall" else self.target_percent
                    self.context.log(f"Entry Triggered ({self.direction} | {betting_mode})! Change: {change*100:.2f}% vs Target {target_display*100:.2f}% | Qty: {quantity}")
                elif should_buy:
                     # Only log if we WANTED to buy but couldn't (e.g. cash, or calculation error)
                    try:
                        mode_debug = self.config.get("betting_strategy", "fixed")
                        cap_debug = self.config.get("initial_capital", "N/A")
                        cash_debug = self.context.cash
                        price_debug = current_price
                        qty_calc = quantity
                        self.context.log(f"Entry FAILED (Insufficient Cash?). Qty: {qty_calc}. Mode: {mode_debug}, InitCap: {cap_debug}, Cash: {cash_debug}, Price: {price_debug}")
                    except:
                        self.context.log("Entry Signal FAILED and Logging crashed.")
                else:
                    # Log when condition failed (Negative Confirmation)
                    self.context.log(f"Entry Condition Failed. Change: {change*100:.2f}%, TargetCond: {self.direction}, TargetPct: {self.target_percent*100:.2f}%")

        # 3. Manage Position (If bought)
        if self.has_bought:
            # Update Peak
            if current_price > self.peak_price:
                self.peak_price = current_price

            # Check Safety Stop
            # Fix: Use stored entry_price instead of recalculating incorrectly
            entry_price = self.entry_price if self.entry_price > 0 else self.reference_price * (1 + self.target_percent)
            current_return = (current_price - entry_price) / entry_price
            
            if current_return <= self.safety_stop_percent:
                 qty = self.context.holdings.get(symbol, 0)
                 if qty > 0:
                     self.context.sell(symbol, qty)
                     self.has_bought = False
                     self.trailing_active = False # Fix: Reset state
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
                        self.trailing_active = False # Fix: Reset state
                        self.context.log(f"Trailing Stop Hit! Sold {qty}")
                    return

            if current_time.time() >= self.stop_time:
                 qty = self.context.holdings.get(symbol, 0)
                 if qty > 0:
                     self.context.sell(symbol, qty)
                     self.has_bought = False
                     self.trailing_active = False # Fix: Reset state
                     self.context.log(f"Time Stop (End of Day). Sold {qty}")

        # DEBUG: Check for skipped days at market close
        # Adjust check time to be slightly before actual end of data logic if needed, 
        # but 15:20 is safe for Korea market (15:30 close).
        if current_time.time() >= datetime.strptime("15:20", "%H:%M").time() and not self.checked_today:
             # Only log once per day to avoid spam
             if not getattr(self, "logged_skip_today", False):
                 self.context.log(f"WARNING: Day Skipped! RefPrice: {self.reference_price}, HasBought: {self.has_bought}, CheckedToday: {self.checked_today}")
                 self.logged_skip_today = True
        
        # Reset skip log flag on new day
        if self.current_trading_date != current_date_obj:
            self.logged_skip_today = False

