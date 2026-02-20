"""
HedgeCoordinator - Manages simultaneous Spot Long + Futures Short positions
for funding rate arbitrage (cash-and-carry trade).

Ensures atomic-like execution of hedge pairs and handles:
- Simultaneous open/close of both legs
- Position drift detection and rebalancing
- Emergency unwind on partial fills
"""

import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class HedgeCoordinator:
    """
    Coordinates hedge positions across Spot and Futures adapters.
    Used by SpotFuturesHedge strategy.
    """

    def __init__(self, spot_adapter, futures_adapter, symbol: str):
        self.spot_adapter = spot_adapter
        self.futures_adapter = futures_adapter
        self.symbol = symbol

        # Position state
        self.spot_qty: float = 0
        self.futures_qty: float = 0  # Positive = short position size
        self.spot_entry_price: float = 0
        self.futures_entry_price: float = 0
        self.is_hedged: bool = False

    async def open_hedge(self, notional: float, price: float) -> Dict[str, Any]:
        """
        Open a hedge: Buy spot + Short futures simultaneously.
        Args:
            notional: USDT amount for each leg
            price: Current price for qty calculation
        Returns:
            Dict with status and details of both legs
        """
        qty = notional / price if price > 0 else 0
        if qty <= 0:
            return {"status": "failed", "message": "Invalid quantity"}

        logger.info(f"Opening hedge: {self.symbol} qty={qty:.4f} @ {price:.2f}")

        # Execute both legs concurrently
        try:
            spot_task = self.spot_adapter.place_buy_order(self.symbol, 0, qty)
            futures_task = self.futures_adapter.place_short_order(self.symbol, 0, qty)

            spot_result, futures_result = await asyncio.gather(
                spot_task, futures_task, return_exceptions=True
            )

            # Check for exceptions
            if isinstance(spot_result, Exception):
                spot_result = {"status": "failed", "message": str(spot_result)}
            if isinstance(futures_result, Exception):
                futures_result = {"status": "failed", "message": str(futures_result)}

            spot_ok = spot_result.get("status") == "success"
            futures_ok = futures_result.get("status") == "success"

            if spot_ok and futures_ok:
                self.spot_qty = float(spot_result.get("quantity", qty))
                self.futures_qty = float(futures_result.get("quantity", qty))
                self.spot_entry_price = float(spot_result.get("price", price))
                self.futures_entry_price = float(futures_result.get("price", price))
                self.is_hedged = True
                logger.info(f"Hedge opened: spot={self.spot_qty} @ {self.spot_entry_price:.2f}, "
                           f"futures={self.futures_qty} @ {self.futures_entry_price:.2f}")
                return {"status": "success", "spot": spot_result, "futures": futures_result}
            else:
                # Partial fill - emergency unwind
                logger.warning(f"Hedge partial: spot={spot_ok}, futures={futures_ok}")
                await self._emergency_unwind(
                    spot_filled=spot_ok, futures_filled=futures_ok,
                    spot_qty=float(spot_result.get("quantity", 0)) if spot_ok else 0,
                    futures_qty=float(futures_result.get("quantity", 0)) if futures_ok else 0,
                )
                return {"status": "partial", "spot": spot_result, "futures": futures_result}

        except Exception as e:
            logger.error(f"Hedge open error: {e}")
            return {"status": "failed", "message": str(e)}

    async def close_hedge(self) -> Dict[str, Any]:
        """
        Close the hedge: Sell spot + Close futures short simultaneously.
        """
        if not self.is_hedged:
            return {"status": "success", "message": "No hedge to close"}

        logger.info(f"Closing hedge: {self.symbol}")

        try:
            tasks = []
            if self.spot_qty > 0:
                tasks.append(self.spot_adapter.place_sell_order(self.symbol, 0, self.spot_qty))
            else:
                tasks.append(asyncio.coroutine(lambda: {"status": "success", "message": "no spot"})())

            if self.futures_qty > 0:
                tasks.append(self.futures_adapter.close_position(self.symbol))
            else:
                tasks.append(asyncio.coroutine(lambda: {"status": "success", "message": "no futures"})())

            results = await asyncio.gather(*tasks, return_exceptions=True)

            spot_result = results[0] if not isinstance(results[0], Exception) else {"status": "failed", "message": str(results[0])}
            futures_result = results[1] if not isinstance(results[1], Exception) else {"status": "failed", "message": str(results[1])}

            self.spot_qty = 0
            self.futures_qty = 0
            self.is_hedged = False

            return {"status": "success", "spot": spot_result, "futures": futures_result}

        except Exception as e:
            logger.error(f"Hedge close error: {e}")
            return {"status": "failed", "message": str(e)}

    def check_drift(self) -> Dict[str, Any]:
        """
        Check position imbalance between spot and futures legs.
        Returns drift info.
        """
        if not self.is_hedged:
            return {"drifted": False, "drift_pct": 0}

        if self.spot_qty <= 0 or self.futures_qty <= 0:
            return {"drifted": True, "drift_pct": 100, "reason": "one_leg_zero"}

        drift = abs(self.spot_qty - self.futures_qty) / max(self.spot_qty, self.futures_qty)
        return {
            "drifted": drift > 0.05,  # 5% threshold
            "drift_pct": drift * 100,
            "spot_qty": self.spot_qty,
            "futures_qty": self.futures_qty,
        }

    async def _emergency_unwind(self, spot_filled: bool, futures_filled: bool,
                                 spot_qty: float, futures_qty: float):
        """Emergency: unwind partially filled hedge to avoid naked exposure."""
        logger.warning(f"Emergency unwind: spot_filled={spot_filled} ({spot_qty}), "
                       f"futures_filled={futures_filled} ({futures_qty})")
        try:
            if spot_filled and spot_qty > 0:
                await self.spot_adapter.place_sell_order(self.symbol, 0, spot_qty)
                logger.info(f"Unwound spot: sold {spot_qty}")
            if futures_filled and futures_qty > 0:
                await self.futures_adapter.close_position(self.symbol)
                logger.info(f"Unwound futures: closed position")
        except Exception as e:
            logger.error(f"Emergency unwind failed: {e}")

        self.spot_qty = 0
        self.futures_qty = 0
        self.is_hedged = False
