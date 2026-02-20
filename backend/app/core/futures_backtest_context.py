"""
FuturesBacktestContext - BacktestContext extension for futures strategies.
Supports short positions, close_position, and simulated futures data (funding rate, liquidation price).
"""

from typing import Dict, Any, List, Callable
from .backtest_engine import BacktestContext


class FuturesBacktestContext(BacktestContext):
    """
    Extended BacktestContext for futures strategy backtesting.
    Adds short(), close_position(), and get_futures_data() support.

    Short positions are tracked separately from long holdings.
    Funding rate can be set externally for simulation.
    """

    def __init__(self, data_feed: List[Dict], initial_capital: float = 10000000,
                 leverage: int = 1, simulated_funding_rate: float = 0.0001):
        super().__init__(data_feed, initial_capital)

        # Short position tracking
        self._short_holdings: Dict[str, float] = {}  # {symbol: quantity (positive)}
        self._short_avg_prices: Dict[str, float] = {}  # {symbol: avg_entry_price}

        # Futures simulation parameters
        self._leverage = leverage
        self._simulated_funding_rate = simulated_funding_rate

    def short(self, symbol: str, quantity: float, price: float = 0,
              metadata: Dict[str, Any] = None, on_filled: Callable = None) -> Dict[str, Any]:
        """Open/add to a short position."""
        exec_price = price if price > 0 else self.get_current_price(symbol)
        notional = exec_price * quantity

        # Margin requirement: notional / leverage
        margin_required = notional / self._leverage
        self.cash -= margin_required

        # Track short position
        existing_qty = self._short_holdings.get(symbol, 0)
        existing_avg = self._short_avg_prices.get(symbol, 0)

        # Weighted average entry price
        if existing_qty > 0:
            total_cost = existing_avg * existing_qty + exec_price * quantity
            new_qty = existing_qty + quantity
            self._short_avg_prices[symbol] = total_cost / new_qty
        else:
            self._short_avg_prices[symbol] = exec_price

        self._short_holdings[symbol] = existing_qty + quantity

        trade = {
            "type": "short",
            "symbol": symbol,
            "price": exec_price,
            "quantity": quantity,
            "time": self.get_time().isoformat(),
            "metadata": metadata or {}
        }
        self.trades.append(trade)
        self.log(f"SHORT EXECUTED: {quantity} @ {exec_price}")

        if on_filled:
            try:
                on_filled(order_id=None, filled_qty=quantity,
                          filled_price=exec_price, metadata=metadata or {})
            except Exception:
                pass

        return trade

    def close_position(self, symbol: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Close entire position (both long and short)."""
        exec_price = self.get_current_price(symbol)
        result = {"status": "success", "trades": []}

        # Close long position
        long_qty = self.holdings.get(symbol, 0)
        if long_qty > 0:
            trade = self.sell(symbol, long_qty, exec_price, metadata=metadata)
            result["trades"].append(trade)

        # Close short position
        short_qty = self._short_holdings.get(symbol, 0)
        if short_qty > 0:
            avg_entry = self._short_avg_prices.get(symbol, exec_price)
            # PnL from short: (entry - exit) * qty
            pnl = (avg_entry - exec_price) * short_qty
            margin_returned = avg_entry * short_qty / self._leverage
            self.cash += margin_returned + pnl

            trade = {
                "type": "close_short",
                "symbol": symbol,
                "price": exec_price,
                "quantity": short_qty,
                "time": self.get_time().isoformat(),
                "pnl": pnl,
                "metadata": metadata or {}
            }
            self.trades.append(trade)
            self.log(f"CLOSE SHORT: {short_qty} @ {exec_price} (PnL: {pnl:+,.2f})")
            result["trades"].append(trade)

            del self._short_holdings[symbol]
            del self._short_avg_prices[symbol]

        return result

    def get_futures_data(self, symbol: str) -> Dict[str, Any]:
        """
        Return simulated futures data for strategy consumption.
        Calculates liquidation price based on position and leverage.
        """
        current_price = self.get_current_price(symbol)
        long_qty = self.holdings.get(symbol, 0)
        short_qty = self._short_holdings.get(symbol, 0)

        if long_qty > 0:
            avg_price = self._get_long_avg_price(symbol)
            # Simplified liquidation estimate: entry - (entry / leverage)
            liq_price = avg_price * (1 - 1.0 / self._leverage) if self._leverage > 1 else 0
            position_side = "LONG"
            position_qty = long_qty
            entry_price = avg_price
            unrealized_pnl = (current_price - avg_price) * long_qty
        elif short_qty > 0:
            avg_price = self._short_avg_prices.get(symbol, current_price)
            liq_price = avg_price * (1 + 1.0 / self._leverage) if self._leverage > 1 else float('inf')
            position_side = "SHORT"
            position_qty = short_qty
            entry_price = avg_price
            unrealized_pnl = (avg_price - current_price) * short_qty
        else:
            return {}

        return {
            "funding_rate": self._simulated_funding_rate,
            "liquidation_price": liq_price,
            "mark_price": current_price,
            "leverage": self._leverage,
            "unrealized_pnl": unrealized_pnl,
            "position_side": position_side,
            "position_qty": position_qty,
            "entry_price": entry_price,
            "adl_quantile": 0,
        }

    def _get_long_avg_price(self, symbol: str) -> float:
        """Calculate average buy price from trades (FIFO)."""
        total_cost = 0.0
        total_qty = 0.0
        for t in self.trades:
            if t.get("symbol") == symbol:
                if t["type"] == "buy":
                    total_cost += t["price"] * t["quantity"]
                    total_qty += t["quantity"]
                elif t["type"] == "sell":
                    if total_qty > 0:
                        avg = total_cost / total_qty
                        sell_qty = min(t["quantity"], total_qty)
                        total_cost -= avg * sell_qty
                        total_qty -= sell_qty
        return total_cost / total_qty if total_qty > 0 else 0

    def update_equity(self):
        """Override to include short position PnL in equity calculation."""
        equity = self.cash
        # Long positions
        for symbol, qty in self.holdings.items():
            equity += qty * self.get_current_price(symbol)
        # Short positions (margin + unrealized PnL)
        for symbol, qty in self._short_holdings.items():
            current_price = self.get_current_price(symbol)
            avg_entry = self._short_avg_prices.get(symbol, current_price)
            margin = avg_entry * qty / self._leverage
            unrealized_pnl = (avg_entry - current_price) * qty
            equity += margin + unrealized_pnl

        from .data_schemas import make_equity_point
        self.equity_curve.append(make_equity_point(
            self.get_time().strftime("%Y-%m-%d %H:%M"), equity
        ))
