"""
OHLCV Data Maintenance Scheduler

Runs daily at a configurable time (default: 05:00 KST) to:
1. Detect gaps in all stored OHLCV data
2. Fill gaps by fetching missing data from exchange APIs
3. Perform incremental update to fetch latest candles

Supports: Kiwoom (Korean stocks), Binance Spot, Binance Futures
"""

import asyncio
import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Any, Optional, List

from sqlalchemy import text

from ..db.session import SessionLocal

logger = logging.getLogger("DataMaintenance")

# ── Configuration Constants ──────────────────────────────────────────
# Daily maintenance run time (KST = UTC+9)
MAINTENANCE_HOUR_KST = 5   # 새벽 5시
MAINTENANCE_MINUTE_KST = 0

# KST offset
KST_OFFSET = timedelta(hours=9)

# Minimum candles to consider a symbol worth checking (skip tiny/stale data)
MIN_CANDLES_FOR_CHECK = 100

# Symbols with fewer than this many days of data skip gap check (newly added)
MIN_DAYS_FOR_GAP_CHECK = 3

# Crypto symbol patterns
CRYPTO_SUFFIXES = ("USDT", "BUSD", "USDC", "BTC", "ETH", "BNB")


class DataMaintenanceScheduler:
    """Background scheduler for OHLCV data integrity checks and updates."""

    def __init__(self):
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._is_executing = False

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"DataMaintenanceScheduler started (daily at {MAINTENANCE_HOUR_KST:02d}:{MAINTENANCE_MINUTE_KST:02d} KST)")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DataMaintenanceScheduler stopped")

    def get_status(self) -> Dict[str, Any]:
        """Return current scheduler status for API."""
        now_kst = datetime.utcnow() + KST_OFFSET
        next_run = self._calc_next_run(now_kst)
        return {
            "is_running": self.is_running,
            "is_executing": self._is_executing,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run_kst": next_run.isoformat() if next_run else None,
            "last_result": self._last_result,
        }

    # ── Scheduler Loop ───────────────────────────────────────────────

    async def _scheduler_loop(self):
        """Main loop: check every 60 seconds if it's time to run."""
        while self.is_running:
            try:
                now_kst = datetime.utcnow() + KST_OFFSET

                if self._should_run(now_kst):
                    await self.run_maintenance()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in maintenance scheduler loop: {e}", exc_info=True)

            await asyncio.sleep(60)

    def _should_run(self, now_kst: datetime) -> bool:
        """Check if it's time for the daily run."""
        if self._is_executing:
            return False

        target_time = dt_time(MAINTENANCE_HOUR_KST, MAINTENANCE_MINUTE_KST)
        if now_kst.time().hour != target_time.hour or now_kst.time().minute != target_time.minute:
            return False

        # Don't run if already ran today
        if self._last_run:
            last_run_kst = self._last_run + KST_OFFSET
            if last_run_kst.date() == now_kst.date():
                return False

        return True

    def _calc_next_run(self, now_kst: datetime) -> Optional[datetime]:
        """Calculate next scheduled run time."""
        today_target = now_kst.replace(
            hour=MAINTENANCE_HOUR_KST, minute=MAINTENANCE_MINUTE_KST,
            second=0, microsecond=0
        )
        if now_kst >= today_target:
            return today_target + timedelta(days=1)
        return today_target

    # ── Main Maintenance Logic ───────────────────────────────────────

    async def run_maintenance(self) -> Dict[str, Any]:
        """
        Run full data maintenance cycle. Can be called manually via API.

        Returns:
            Summary dict with per-symbol results.
        """
        if self._is_executing:
            logger.warning("Maintenance already in progress, skipping")
            return {"status": "skipped", "reason": "already_running"}

        self._is_executing = True
        self._last_run = datetime.utcnow()
        start_time = datetime.utcnow()
        results = {"symbols_checked": 0, "gaps_found": 0, "gaps_filled": 0, "errors": [], "details": []}

        try:
            logger.info("=" * 60)
            logger.info("[DataMaintenance] Starting daily OHLCV integrity check...")
            logger.info("=" * 60)

            # 1. Get all unique symbols and their metadata from DB
            symbols_info = self._get_all_symbols()
            logger.info(f"[DataMaintenance] Found {len(symbols_info)} symbols to check")

            # 2. Process each symbol
            for info in symbols_info:
                try:
                    detail = await self._check_and_fix_symbol(info)
                    results["details"].append(detail)
                    results["symbols_checked"] += 1
                    results["gaps_found"] += detail.get("gaps_found", 0)
                    results["gaps_filled"] += detail.get("gaps_filled", 0)
                except Exception as e:
                    error_msg = f"{info['symbol']}: {str(e)[:200]}"
                    logger.error(f"[DataMaintenance] Error processing {info['symbol']}: {e}", exc_info=True)
                    results["errors"].append(error_msg)

            elapsed = (datetime.utcnow() - start_time).total_seconds()
            results["elapsed_seconds"] = round(elapsed, 1)
            results["status"] = "completed"

            logger.info("=" * 60)
            logger.info(
                f"[DataMaintenance] Completed: {results['symbols_checked']} symbols, "
                f"{results['gaps_found']} gaps found, {results['gaps_filled']} filled, "
                f"{len(results['errors'])} errors, {elapsed:.1f}s elapsed"
            )
            logger.info("=" * 60)

        except Exception as e:
            results["status"] = "error"
            results["error"] = str(e)
            logger.error(f"[DataMaintenance] Fatal error: {e}", exc_info=True)
        finally:
            self._is_executing = False
            self._last_result = results

        return results

    # ── Symbol Discovery ─────────────────────────────────────────────

    def _get_all_symbols(self) -> List[Dict[str, Any]]:
        """
        Get all unique symbols from OHLCV table with metadata.
        Returns list of {symbol, time_frame, count, earliest, latest, is_crypto}
        """
        db = SessionLocal()
        try:
            rows = db.execute(text("""
                SELECT symbol, time_frame, count(*) as cnt,
                       min(timestamp) as earliest, max(timestamp) as latest
                FROM ohlcv
                WHERE time_frame = '1m'
                GROUP BY symbol, time_frame
                HAVING count(*) >= :min_count
                ORDER BY symbol
            """), {"min_count": MIN_CANDLES_FOR_CHECK}).fetchall()

            result = []
            for row in rows:
                symbol = row[0]
                is_crypto = any(symbol.upper().endswith(s) for s in CRYPTO_SUFFIXES)
                days_of_data = (row[4] - row[3]).days if row[3] and row[4] else 0

                if days_of_data < MIN_DAYS_FOR_GAP_CHECK:
                    continue

                # Determine exchange type for market data service routing
                exchange_name = self._detect_exchange(symbol, is_crypto)

                result.append({
                    "symbol": symbol,
                    "time_frame": row[1],
                    "count": row[2],
                    "earliest": row[3],
                    "latest": row[4],
                    "is_crypto": is_crypto,
                    "exchange_name": exchange_name,
                    "days_of_data": days_of_data,
                })

            return result
        finally:
            db.close()

    def _detect_exchange(self, symbol: str, is_crypto: bool) -> str:
        """Detect exchange name from symbol pattern."""
        if not is_crypto:
            return "Kiwoom"

        # Check if this symbol is used by a BinanceFutures account
        db = SessionLocal()
        try:
            row = db.execute(text("""
                SELECT ea.exchange_name FROM live_bot_sessions lbs
                JOIN exchange_accounts ea ON ea.id = lbs.account_id
                WHERE lbs.symbol = :symbol
                ORDER BY lbs.id DESC LIMIT 1
            """), {"symbol": symbol}).fetchone()

            if row:
                return row[0]
        except Exception:
            pass
        finally:
            db.close()

        # Fallback: USDT pairs are likely futures
        if symbol.upper().endswith("USDT"):
            return "BinanceFutures"
        return "Binance"

    # ── Per-Symbol Check ─────────────────────────────────────────────

    async def _check_and_fix_symbol(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check a single symbol for gaps and fix them.

        Steps:
            1. Load 1m candles from DB
            2. Run gap detection
            3. If gaps found, trigger targeted backfill
            4. Incremental update (fetch latest candles)
        """
        symbol = info["symbol"]
        exchange_name = info["exchange_name"]
        is_crypto = info["is_crypto"]
        detail = {
            "symbol": symbol,
            "exchange": exchange_name,
            "candle_count": info["count"],
            "gaps_found": 0,
            "gaps_filled": 0,
            "updated": False,
        }

        from ..services.market_data_factory import get_market_data_service
        service = get_market_data_service(exchange_name)

        # 1. Load candles from DB for gap detection
        from ..models.ohlcv import OHLCV
        db = SessionLocal()
        try:
            candles = db.query(OHLCV).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == "1m",
            ).order_by(OHLCV.timestamp.asc()).all()

            if len(candles) < MIN_CANDLES_FOR_CHECK:
                detail["skipped"] = "too_few_candles"
                return detail

            # 2. Gap detection
            from ..services.gap_detector import detect_gaps
            gaps = detect_gaps(candles, interval="1m", is_24h_market=is_crypto)
            detail["gaps_found"] = len(gaps)

            if gaps:
                logger.info(f"[DataMaintenance] {symbol}: {len(gaps)} gap(s) detected")

                # 3. Fill gaps
                if is_crypto and hasattr(service, '_fill_gaps'):
                    # Binance: targeted gap fill
                    await service._fill_gaps(symbol, gaps)
                    detail["gaps_filled"] = len(gaps)
                else:
                    # Kiwoom: full backfill (API is newest-first, no targeted fill)
                    days_of_data = info.get("days_of_data", 365)
                    await service.fetch_history(symbol, "1m", days=min(days_of_data + 30, 730), backfill=True)
                    detail["gaps_filled"] = len(gaps)

                detail["updated"] = True
            else:
                logger.info(f"[DataMaintenance] {symbol}: no gaps ({info['count']} candles OK)")

        finally:
            db.close()

        # 4. Incremental update — fetch latest candles
        try:
            latest = info["latest"]
            now = datetime.utcnow()
            hours_behind = (now - latest).total_seconds() / 3600

            # Only update if data is more than 2 hours behind
            if hours_behind > 2:
                logger.info(f"[DataMaintenance] {symbol}: {hours_behind:.1f}h behind, fetching latest...")
                days_to_fetch = max(3, int(hours_behind / 24) + 2)
                await service.fetch_history(symbol, "1m", days=days_to_fetch)
                detail["updated"] = True
                detail["hours_behind"] = round(hours_behind, 1)
        except Exception as e:
            logger.warning(f"[DataMaintenance] {symbol}: incremental update failed: {e}")
            detail["incremental_error"] = str(e)[:100]

        return detail


# Singleton instance
data_maintenance_scheduler = DataMaintenanceScheduler()
