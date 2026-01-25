from typing import Dict, Any, List, Optional
from datetime import datetime
from .base import BaseStrategy, IContext

class DipMartingaleStrategy(BaseStrategy):
    """
    Dip Martingale Strategy
    - Basic Idea: Buy when price dips from a reference point (e.g., daily open or peak).
    - Martingale: If price continues to drop, increase position size at fixed intervals to lower average price.
    - Profit Taking: Use Trailing Stop once a profit target is reached.
    - Risk Management: Max levels, HODL (Max Loss Protection)
    """

    def initialize(self):
        # Configuration parameters
        self.symbol = self.config.get("symbol", "UNKNOWN")
        self.dip_percent = self.config.get("dip_percent", 1.0) # Condition 1: Initial dip to enter (e.g., -1%)
        self.level_gap_percent = self.config.get("level_gap_percent", 2.0) # Condition 2: Gap between levels (e.g., -2%)
        self.max_levels = self.config.get("max_levels", 4) # Max levels (excluding level 0)
        self.lot_size_multiplier = self.config.get("lot_size_multiplier", 2.0) # Martingale multiplier (e.g., 1, 2, 4, 8)
        self.base_quantity = self.config.get("base_quantity", 1) # Starting quantity for Level 1
        
        self.trailing_start_percent = self.config.get("trailing_start_percent", 0.01) # 1% profit starts trailing
        self.trailing_stop_percent = self.config.get("trailing_stop_percent", 0.003) # 0.3% drop from peak triggers sell
        self.max_loss_percent = self.config.get("max_loss_percent", 0.10) # 10% total loss triggers HODL
        
        # State variables
        self.current_level = 0 # 0: None, 1: First Entry, 2: Second...
        self.reference_price = None # Point from which dip is measured (Cycle Start)
        self.peak_price = 0 # Highest price since entry for trailing stop
        self.average_price = 0
        self.total_quantity = 0
        self.trailing_active = False
        self.is_hodl = False
        self.last_trade_time = None
        self.current_trading_date = None
        self.entries = [] # List of entry records

    def on_data(self, data: Dict[str, Any]):
        """Called on every price update"""
        current_time = self.context.get_time()
        current_date = current_time.date()
        current_price = data['close']
        self.last_price = current_price # Store for state
        symbol = self.symbol
        
        # 1. Reset cycle on new day (if no position)
        if self.current_trading_date != current_date:
            self.current_trading_date = current_date
            if self.current_level == 0:
                self.reference_price = None
                self.context.log(f"[DipMartingale] New day {current_date}. Resetting reference price.")
        
        # 2. Set Reference Price (Cycle Start)
        if self.reference_price is None:
            self.reference_price = current_price
            self.context.log(f"[DipMartingale] Cycle started for {symbol}. Ref: {self.reference_price:,.0f}")
            return

        # 3. Position Management (If holding)
        if self.current_level > 0 and self.total_quantity > 0:
            current_return = (current_price - self.average_price) / self.average_price if self.average_price > 0 else 0
            
            # Update peak for trailing stop
            if current_price > self.peak_price:
                self.peak_price = current_price
            
            # 3a. Check Trailing Stop Activation
            if not self.trailing_active and current_return >= (self.trailing_start_percent / 100):
                self.trailing_active = True
                self.peak_price = current_price
                self.context.log(f"[DipMartingale] Trailing Stop ACTIVATED. Return: {current_return*100:.2f}%")
            
            # 3b. Check Trailing Stop Liquidation
            if self.trailing_active:
                drop_from_peak = (self.peak_price - current_price) / self.peak_price if self.peak_price > 0 else 0
                if drop_from_peak >= (self.trailing_stop_percent / 100):
                    self.context.log(f"[DipMartingale] Trailing Stop VOID! Sell at {current_price:,.0f} (Profit: {current_return*100:.2f}%)")
                    self._liquidate(current_price)
                    return

            # 3c. Check Max Loss Protection (HODL)
            if not self.is_hodl and current_return <= -(self.max_loss_percent / 100):
                self.is_hodl = True
                self.context.log(f"[DipMartingale] CRITICAL: Loss {current_return*100:.1f}%. HODL Mode Engaged.")
            
            # 3d. Check Martingale Multi-Entry (If price drops further)
            if self.current_level < self.max_levels and not self.trailing_active:
                next_level = self.current_level + 1
                # Target price = entry_price of current level - level_gap
                last_entry_price = self.entries[-1]['price']
                target_price = last_entry_price * (1 - self.level_gap_percent / 100)
                
                if current_price <= target_price:
                    qty = self._calculate_quantity(next_level)
                    if qty > 0:
                        self.context.buy(symbol, qty, metadata={"level": next_level})
                        self._add_position(current_price, qty, next_level)
                        self.context.log(f"[DipMartingale] L{next_level} Entry @ {current_price:,.0f}. Avg: {self.average_price:,.0f}")

        # 4. Initial Entry (Level 1)
        elif self.current_level == 0:
            dip_from_ref = (self.reference_price - current_price) / self.reference_price
            if dip_from_ref >= (self.dip_percent / 100):
                qty = self.base_quantity
                self.context.buy(symbol, qty, metadata={"level": 1})
                self._add_position(current_price, qty, 1)
                self.peak_price = current_price
                self.context.log(f"[DipMartingale] L1 Initial Entry @ {current_price:,.0f} (Dip: {dip_from_ref*100:.2f}%)")

    def _add_position(self, price: float, quantity: int, level: int):
        new_total_qty = self.total_quantity + quantity
        self.average_price = ((self.average_price * self.total_quantity) + (price * quantity)) / new_total_qty
        self.total_quantity = new_total_qty
        self.current_level = level
        self.entries.append({"level": level, "price": price, "quantity": quantity, "time": str(self.context.get_time())})

    def _liquidate(self, price: float):
        self.context.sell(self.symbol, self.total_quantity, metadata={"level": "CLOSE"})
        self.current_level = 0
        self.total_quantity = 0
        self.average_price = 0
        self.peak_price = 0
        self.trailing_active = False
        self.is_hodl = False
        self.reference_price = None # Reset cycle
        self.entries = []

    def _calculate_quantity(self, level: int) -> int:
        """Calculate quantity for next level based on lot_size_multiplier"""
        # Level 1: base_quantity
        # Level 2: base_quantity * multiplier
        # Level 3: base_quantity * multiplier^2 ...
        return int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))

    def get_state(self) -> Dict[str, Any]:
        cur_price = getattr(self, 'last_price', 0)
        dip_percent = (self.reference_price - cur_price) / self.reference_price if self.reference_price else 0
        profit_percent = (cur_price - self.average_price) / self.average_price if self.average_price > 0 else 0
        
        return {
            "current_level": self.current_level,
            "max_levels": self.max_levels,
            "average_price": self.average_price,
            "total_quantity": self.total_quantity,
            "peak_price": self.peak_price,
            "trailing_active": self.trailing_active,
            "is_hodl": self.is_hodl,
            "reference_price": self.reference_price,
            "symbol": self.symbol,
            "current_price": cur_price,
            "dip_percent": dip_percent,
            "profit_percent": profit_percent,
            "target_dip": self.dip_percent / 100.0,
            "target_profit": self.trailing_start_percent / 100.0
        }
