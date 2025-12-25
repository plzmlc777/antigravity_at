from typing import Dict, Any, Optional
import math

class OrderService:
    @staticmethod
    def calculate_quantity(
        mode: str,
        current_price: float,
        balance_info: Optional[Dict[str, Any]] = None,
        order_price: float = 0,
        price_type: str = "limit",
        quantity: Optional[float] = None,
        amount: Optional[float] = None,
        percent: Optional[float] = None,
        order_type: str = "buy",
        symbol: str = ""
    ) -> int:
        """
        Calculate the quantity of stocks to buy/sell based on the mode and parameters.
        Returns the calculated quantity as an integer.
        """
        
        # 1. Quantity Mode (Direct)
        if mode == "quantity":
            if quantity is None or quantity <= 0:
                 raise ValueError("Quantity is required for 'quantity' mode")
            return int(quantity)

        # 2. Amount Mode (Target KRW amount)
        elif mode == "amount":
            if amount is None or amount <= 0:
                raise ValueError("Amount is required for 'amount' mode")
            
            # Use current_price for market orders, specific order_price for limit orders
            calc_basis_price = current_price if price_type.lower() == "market" else order_price
            
            if calc_basis_price <= 0:
                 raise ValueError("Price must be > 0 for calculation")
                 
            return int(amount // calc_basis_price)

        # 3. Percent Cash Mode (Buy Only)
        elif mode == "percent_cash":
            if order_type.lower() != "buy":
                 raise ValueError("'percent_cash' is only valid for BUY orders")
                 
            if percent is None or not (0 < percent <= 1):
                 raise ValueError("Percent must be between 0 and 1")
            
            if not balance_info:
                raise ValueError("Balance info is required for 'percent_cash' mode")

            cash_data = balance_info.get("cash", {})
            current_cash = cash_data.get("KRW", 0)
            
            # Safety Margin
            # Market Order: Requires margin based on Upper Limit Price (+30%), so we use conservative 0.75
            # Limit Order: Based on specific price, so we use 0.98 for fees
            margin = 0.75 if price_type.lower() == "market" else 0.98
            
            target_amount = current_cash * percent * margin
            
            calc_basis_price = current_price if price_type.lower() == "market" else order_price
            if calc_basis_price <= 0:
                 raise ValueError("Price must be > 0 for calculation")
                 
            return int(target_amount // calc_basis_price)

        # 4. Percent Holding Mode (Sell Only)
        elif mode == "percent_holding":
            if order_type.lower() != "sell":
                 raise ValueError("'percent_holding' is only valid for SELL orders")

            if percent is None or not (0 < percent <= 1):
                 raise ValueError("Percent must be between 0 and 1")
                 
            if not balance_info:
                raise ValueError("Balance info is required for 'percent_holding' mode")

            holdings = balance_info.get("holdings", {})
            current_qty = holdings.get(symbol, 0)
            
            return int(current_qty * percent)

        else:
            raise ValueError(f"Unknown mode: {mode}")
