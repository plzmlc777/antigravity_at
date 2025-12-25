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
        self.start_hour = int(self.config.get("start_hour", 9)) # e.g., 9:00
        self.delay_minutes = int(self.config.get("delay_minutes", 10)) # e.g., 10 mins
        self.target_percent = float(self.config.get("target_percent", 0.02)) # e.g., 2% rise
        self.safety_stop_percent = float(self.config.get("safety_stop_percent", -0.03)) # -3% drop
        self.trailing_start_percent = float(self.config.get("trailing_start_percent", 0.05)) # 5% profit
        self.trailing_stop_drop = float(self.config.get("trailing_stop_drop", 0.02)) # 2% drop from peak
        self.stop_hour = int(self.config.get("stop_hour", 15)) # e.g., 15:00

        # State Variables
        self.reference_price = None
        self.has_bought = False
        self.peak_price = 0
        self.trailing_active = False

    def on_data(self, data: Dict[str, Any]):
        current_time = self.context.get_time()
        current_price = data['close']
        symbol = "TEST" # Configurable in real scenario

        # 1. Establish Reference Price (Start Time)
        # Assuming data comes in minute intervals.
        if current_time.hour == self.start_hour and current_time.minute == 0:
            self.reference_price = current_price
            self.context.log(f"Market Start. Reference Price: {self.reference_price}")

        # 2. Check Entry Condition (Start Time + Delay)
        check_time = datetime(current_time.year, current_time.month, current_time.day, self.start_hour, 0) + timedelta(minutes=self.delay_minutes)
        
        if not self.has_bought and self.reference_price and current_time >= check_time:
            # Check price change from Start Time
            change = (current_price - self.reference_price) / self.reference_price
            
            if change >= self.target_percent:
                self.context.buy(symbol, 10) # Buy 10 units for test
                self.has_bought = True
                self.peak_price = current_price
                self.context.log(f"Entry Triggered! Change: {change*100:.2f}% >= {self.target_percent*100:.2f}%")

        # 3. Manage Position (If bought)
        if self.has_bought:
            # Update Peak
            if current_price > self.peak_price:
                self.peak_price = current_price

            # Check Safety Stop
            entry_price = self.reference_price * (1 + self.target_percent) # Approximate
            current_return = (current_price - entry_price) / entry_price
            
            if current_return <= self.safety_stop_percent:
                 self.context.sell(symbol, 10)
                 self.has_bought = False
                 self.context.log("Safety Stop Hit!")
                 return

            # Trailing Stop Logic
            if not self.trailing_active:
                if current_return >= self.trailing_start_percent:
                    self.trailing_active = True
                    self.context.log("Trailing Stop Activated!")
            
            if self.trailing_active:
                drop_from_peak = (self.peak_price - current_price) / self.peak_price
                if drop_from_peak >= self.trailing_stop_drop:
                    self.context.sell(symbol, 10)
                    self.has_bought = False
                    self.context.log("Trailing Stop Hit!")
                    return

            # Time Stop (Force Sell at Stop Time)
            if current_time.hour >= self.stop_hour:
                 self.context.sell(symbol, 10)
                 self.has_bought = False
                 self.context.log("Time Stop (End of Day)")
