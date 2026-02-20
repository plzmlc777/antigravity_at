"""
FuturesMonitorService - Real-time monitoring for futures positions.
Runs as an asyncio task per futures session.
- Polls position risk every 5 seconds
- Checks liquidation proximity (10% → 5% → 2%)
- Checks ADL quantile risk
- Sends Telegram alerts and WebSocket events
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable, List

logger = logging.getLogger(__name__)

# Alert levels for liquidation proximity
ALERT_LEVELS = {
    "CRITICAL": 0.02,   # 2% from liquidation
    "WARNING": 0.05,    # 5% from liquidation
    "CAUTION": 0.10,    # 10% from liquidation
}


class FuturesMonitorService:
    """
    Monitors futures position risk for a single session.
    Created by LiveEngine when adapter is FuturesInterface.
    """

    def __init__(self, session_id: str, symbol: str, adapter,
                 context=None, tick_listeners: List[Callable] = None,
                 user_id: int = None, account_id: int = None,
                 strategy_name: str = None):
        self.session_id = session_id
        self.symbol = symbol
        self.adapter = adapter
        self.context = context
        self.tick_listeners = tick_listeners or []
        self._user_id = user_id
        self._account_id = account_id
        self._strategy_name = strategy_name

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._poll_interval = 5  # seconds

        # Alert dedup: prevent repeat alerts for same level
        self._last_liq_alert_level: Optional[str] = None
        self._last_adl_alert_level: int = 0

    async def start(self):
        """Start the monitoring loop as an asyncio task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"FuturesMonitor started for session {self.session_id} ({self.symbol})")

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info(f"FuturesMonitor stopped for session {self.session_id}")

    async def _monitor_loop(self):
        """Main monitoring loop - polls position data and checks risk."""
        while self._running:
            try:
                await self._refresh_and_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"FuturesMonitor error ({self.session_id}): {e}")

            await asyncio.sleep(self._poll_interval)

    async def _refresh_and_check(self):
        """Fetch position data, update cache, and run risk checks."""
        try:
            position = await self.adapter.get_position(self.symbol)
            funding_rate = await self.adapter.get_funding_rate(self.symbol)

            # Build futures data cache
            futures_data = {
                "funding_rate": funding_rate,
                "liquidation_price": position.get("liquidation_price", 0),
                "mark_price": position.get("mark_price", 0),
                "leverage": position.get("leverage", 1),
                "unrealized_pnl": position.get("unrealized_pnl", 0),
                "position_side": position.get("side", "NONE"),
                "position_qty": position.get("quantity", 0),
                "entry_price": position.get("entry_price", 0),
                "adl_quantile": 0,
            }

            # Get ADL quantile if adapter supports it
            if hasattr(self.adapter, 'get_adl_quantile'):
                try:
                    adl = await self.adapter.get_adl_quantile(self.symbol)
                    futures_data["adl_quantile"] = adl
                except Exception:
                    pass

            # Update context cache
            if self.context:
                self.context.update_futures_data(self.symbol, futures_data)

            # Skip risk checks if no position
            if futures_data["position_qty"] == 0:
                self._last_liq_alert_level = None
                self._last_adl_alert_level = 0
                return

            # Run risk checks
            await self._check_liquidation_proximity(futures_data)
            await self._check_adl_risk(futures_data)

            # Emit futures risk data to WebSocket listeners
            self._emit_futures_risk(futures_data)

        except Exception as e:
            logger.error(f"FuturesMonitor refresh error: {e}")

    async def _check_liquidation_proximity(self, data: Dict[str, Any]):
        """
        Check how close mark price is to liquidation price.
        Alerts at 10%, 5%, 2% proximity thresholds.
        """
        mark_price = data.get("mark_price", 0)
        liq_price = data.get("liquidation_price", 0)

        if mark_price <= 0 or liq_price <= 0:
            return

        # Calculate distance to liquidation
        if data.get("position_side") == "LONG":
            distance_pct = (mark_price - liq_price) / mark_price
        elif data.get("position_side") == "SHORT":
            distance_pct = (liq_price - mark_price) / mark_price
        else:
            return

        # Check alert thresholds (most severe first)
        current_level = None
        for level, threshold in sorted(ALERT_LEVELS.items(), key=lambda x: x[1]):
            if distance_pct <= threshold:
                current_level = level
                break

        if not current_level:
            # Reset if we moved away from danger
            self._last_liq_alert_level = None
            return

        # Dedup: don't re-alert same level
        if current_level == self._last_liq_alert_level:
            return

        self._last_liq_alert_level = current_level
        logger.warning(f"LIQUIDATION {current_level}: {self.symbol} "
                       f"mark={mark_price:.2f} liq={liq_price:.2f} "
                       f"distance={distance_pct*100:.2f}%")

        # Send Telegram alert
        await self._send_liquidation_alert(current_level, data, distance_pct)

    async def _check_adl_risk(self, data: Dict[str, Any]):
        """
        Check ADL (Auto-Deleveraging) quantile risk.
        Alert when quantile >= 4 (out of 5).
        """
        adl = data.get("adl_quantile", 0)

        if adl >= 4 and adl > self._last_adl_alert_level:
            self._last_adl_alert_level = adl
            logger.warning(f"ADL RISK: {self.symbol} quantile={adl}/5")
            await self._send_adl_alert(data)
        elif adl < 4:
            self._last_adl_alert_level = 0

    async def _send_liquidation_alert(self, level: str, data: Dict[str, Any], distance_pct: float):
        """Send liquidation proximity alert via Telegram."""
        if not self._user_id:
            return

        level_emoji = {"CRITICAL": "\U0001f6a8", "WARNING": "\u26a0\ufe0f", "CAUTION": "\u2139\ufe0f"}
        emoji = level_emoji.get(level, "\u26a0\ufe0f")

        message = f"""{emoji} <b>Liquidation Alert [{level}]</b>

\U0001f4ca <b>{self.symbol}</b>
\u251c Mark Price: {data.get('mark_price', 0):,.2f}
\u251c Liquidation: {data.get('liquidation_price', 0):,.2f}
\u251c Distance: {distance_pct*100:.2f}%
\u251c Leverage: {data.get('leverage', 1)}x
\u251c Side: {data.get('position_side', 'N/A')}
\u2514 Qty: {abs(data.get('position_qty', 0)):.4f}"""

        if level == "CRITICAL":
            message += "\n\n\U0001f6d1 <b>Immediate action required!</b>"

        try:
            from ..db.session import SessionLocal
            from ..core.telegram_service import send_telegram_notification
            db = SessionLocal()
            try:
                await send_telegram_notification(
                    db=db, user_id=self._user_id,
                    notification_type="error",
                    account_id=self._account_id,
                    error_type=f"Liquidation {level}",
                    message=f"{self.symbol}: {distance_pct*100:.2f}% from liquidation",
                    symbol=self.symbol,
                    strategy_name=self._strategy_name
                )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to send liquidation alert: {e}")

    async def _send_adl_alert(self, data: Dict[str, Any]):
        """Send ADL risk alert via Telegram."""
        if not self._user_id:
            return

        adl = data.get("adl_quantile", 0)
        bar = "\u2588" * adl + "\u2591" * (5 - adl)

        try:
            from ..db.session import SessionLocal
            from ..core.telegram_service import send_telegram_notification
            db = SessionLocal()
            try:
                await send_telegram_notification(
                    db=db, user_id=self._user_id,
                    notification_type="error",
                    account_id=self._account_id,
                    error_type="ADL Risk",
                    message=f"{self.symbol}: ADL [{bar}] {adl}/5. Consider reducing position.",
                    symbol=self.symbol,
                    strategy_name=self._strategy_name
                )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to send ADL alert: {e}")

    def _emit_futures_risk(self, data: Dict[str, Any]):
        """Emit futures risk data to WebSocket listeners."""
        event = {
            "type": "futures_risk",
            "data": {
                "symbol": self.symbol,
                "funding_rate": data.get("funding_rate", 0),
                "liquidation_price": data.get("liquidation_price", 0),
                "mark_price": data.get("mark_price", 0),
                "leverage": data.get("leverage", 1),
                "unrealized_pnl": data.get("unrealized_pnl", 0),
                "position_side": data.get("position_side", "NONE"),
                "position_qty": data.get("position_qty", 0),
                "entry_price": data.get("entry_price", 0),
                "adl_quantile": data.get("adl_quantile", 0),
            }
        }
        for listener in self.tick_listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception:
                pass
