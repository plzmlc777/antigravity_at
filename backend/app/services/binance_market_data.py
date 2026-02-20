"""
Binance Market Data Service
- Fetches historical kline (candlestick) data from Binance REST API
- No API key required for public market data endpoints
- Stores 1m candles in OHLCV DB, derives higher intervals at runtime
- Supports: 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d
- 24/7 trading: 1440 minutes per day (vs Korean stocks: 390 minutes)
"""

import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from ..core.http_client import HttpClientManager
import logging

logger = logging.getLogger(__name__)

# Binance API base URLs
BINANCE_API_URL = "https://api.binance.com"
BINANCE_FUTURES_API_URL = "https://fapi.binance.com"

# Binance kline interval mapping (our notation -> Binance notation)
INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "60m": "1h", "4h": "4h", "8h": "8h", "12h": "12h", "1d": "1d",
}


class BinanceMarketDataService:
    """
    Service to fetch historical market data from Binance API.
    Follows the same DB-first pattern as MarketDataService (Kiwoom).
    """

    MAX_DAYS = 730  # 2 years (Binance provides much longer history)
    DEFAULT_DAYS = 365
    CANDLES_PER_REQUEST = 1000  # Binance max per request

    def __init__(self, is_futures: bool = False):
        self.http_manager = HttpClientManager.get_instance()
        self.is_futures = is_futures
        self.base_url = BINANCE_FUTURES_API_URL if is_futures else BINANCE_API_URL

    async def get_candles(self, symbol: str, interval: str = "1m", days: int = 730,
                          limit: int = 100000, to_date: str = None) -> List[Dict]:
        """
        Main entry point for getting candle data.

        Strategy: DB stores 1m data. All other intervals are derived from 1m at runtime.
        For Binance, we can also fetch native intervals directly from API (3m, 5m, etc.)
        but we maintain consistency with the Kiwoom pattern by storing only 1m.

        24/7 trading: 1d = 1440 minutes (not 390 like Korean stocks)
        """
        days = min(days, self.MAX_DAYS)
        symbol = symbol.upper()

        # Aggregation map: derive higher intervals from 1m
        aggregation_map = {
            "3m": ("1m", 3),
            "5m": ("1m", 5),
            "10m": ("1m", 10),
            "15m": ("1m", 15),
            "30m": ("1m", 30),
            "60m": ("1m", 60),
            "1h": ("1m", 60),
            "4h": ("1m", 240),
            "8h": ("1m", 480),
            "12h": ("1m", 720),
            "1d": ("1m", 1440),  # 24/7 crypto: 1440 minutes per day
        }

        if interval in aggregation_map:
            base_interval, multiplier = aggregation_map[interval]
            logger.info(f"Aggregating {symbol} from {base_interval} to {interval}")
            base_data = await self.get_candles(symbol, base_interval, days, limit * multiplier, to_date=to_date)
            aggregated = self._aggregate_candles(base_data, interval)
            logger.info(f"Aggregation: {len(base_data)} {base_interval} -> {len(aggregated)} {interval}")
            return aggregated

        # 1. Check DB for existing data
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV

        db = SessionLocal()
        try:
            if to_date:
                try:
                    end_ref = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
                except ValueError:
                    end_ref = datetime.utcnow()
            else:
                end_ref = datetime.utcnow()

            start_date = end_ref - timedelta(days=days)

            query_filters = [
                OHLCV.symbol == symbol,
                OHLCV.time_frame == interval,
                OHLCV.timestamp >= start_date
            ]
            if to_date:
                query_filters.append(OHLCV.timestamp < end_ref)

            db_candles = db.query(OHLCV).filter(
                *query_filters
            ).order_by(OHLCV.timestamp.asc()).all()

            # Check if data is sufficient for the requested period
            # 24/7 crypto: ~1440 candles per day at 1m interval
            expected_candles = days * 1440 if interval == "1m" else days * 24
            # Consider sufficient if we have at least 70% of expected data
            min_threshold = max(100, int(expected_candles * 0.7))

            if len(db_candles) >= min_threshold:
                logger.info(f"Loaded {len(db_candles)} {interval} candles from DB for {symbol}")
                return [
                    {
                        "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": c.open, "high": c.high, "low": c.low,
                        "close": c.close, "volume": c.volume
                    }
                    for c in db_candles
                ]
        finally:
            db.close()

        # 2. Fetch from Binance API (insufficient DB data)
        logger.info(f"Insufficient data for {symbol} {interval} (count={len(db_candles) if 'db_candles' in dir() else 0}). Fetching from Binance API...")
        await self.fetch_history(symbol, interval, days)

        # Re-read from DB with date filters
        db = SessionLocal()
        try:
            re_query_filters = [
                OHLCV.symbol == symbol,
                OHLCV.time_frame == interval,
                OHLCV.timestamp >= start_date
            ]
            if to_date:
                re_query_filters.append(OHLCV.timestamp < end_ref)

            db_candles = db.query(OHLCV).filter(
                *re_query_filters
            ).order_by(OHLCV.timestamp.asc()).all()

            logger.info(f"Loaded {len(db_candles)} {interval} candles from DB for {symbol} (after fetch)")
            return [
                {
                    "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": c.open, "high": c.high, "low": c.low,
                    "close": c.close, "volume": c.volume
                }
                for c in db_candles
            ][-limit:]
        finally:
            db.close()

    async def fetch_history(self, symbol: str, interval: str = "1m", days: int = 730,
                            limit: int = 100000, backfill: bool = False):
        """
        Fetch historical kline data from Binance REST API and save to DB.

        Binance API: GET /api/v3/klines
        - No authentication required
        - Max 1000 candles per request
        - Pagination via startTime/endTime (milliseconds)
        - Response: [[openTime, open, high, low, close, volume, closeTime, ...], ...]
        """
        days = min(days, self.MAX_DAYS)
        symbol = symbol.upper()

        # Only store 1m in DB, derive others at runtime
        if interval != "1m":
            logger.info(f"Interval {interval} derived from 1m. Fetching 1m base data...")
            return await self.fetch_history(symbol, "1m", days, limit)

        binance_interval = INTERVAL_MAP.get(interval, interval)
        logger.info(f"Fetching {symbol} {binance_interval} from Binance API ({days} days)...")

        # Determine API endpoint
        if self.is_futures:
            url = f"{self.base_url}/fapi/v1/klines"
        else:
            url = f"{self.base_url}/api/v3/klines"

        # Calculate time range
        end_ms = int(datetime.utcnow().timestamp() * 1000)
        start_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)

        # Check for existing data (smart incremental fetch)
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV

        db = SessionLocal()
        need_backfill = False
        try:
            first_record = db.query(OHLCV.timestamp).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == interval
            ).order_by(OHLCV.timestamp.asc()).first()

            last_record = db.query(OHLCV.timestamp).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == interval
            ).order_by(OHLCV.timestamp.desc()).first()

            if first_record and last_record and not backfill:
                first_ts_ms = int(first_record[0].timestamp() * 1000)
                last_ts_ms = int(last_record[0].timestamp() * 1000)

                if first_ts_ms > start_ms:
                    # Existing data doesn't cover the requested start → need backward fill
                    need_backfill = True
                    logger.info(f"Need backfill: DB starts at {first_record[0]}, requested from {datetime.utcfromtimestamp(start_ms / 1000)}")
                else:
                    # Existing data covers the start → incremental forward from last record
                    start_ms = last_ts_ms
                    logger.info(f"Incremental fetch from {last_record[0]}")
        except Exception as e:
            logger.error(f"Error checking existing data: {e}")

        client = self.http_manager.get_client()
        total_fetched = 0
        current_start = start_ms

        try:
            while current_start < end_ms and total_fetched < limit:
                params = {
                    "symbol": symbol,
                    "interval": binance_interval,
                    "startTime": current_start,
                    "endTime": end_ms,
                    "limit": self.CANDLES_PER_REQUEST,
                }

                try:
                    response = await client.get(url, params=params)
                except Exception as e:
                    logger.error(f"Binance API request failed: {e}")
                    break

                if response.status_code != 200:
                    error_msg = response.text[:200] if response.text else "Unknown error"
                    logger.error(f"Binance API error {response.status_code}: {error_msg}")
                    break

                klines = response.json()
                if not klines:
                    logger.info("No more data from Binance API")
                    break

                # Parse klines: [openTime, open, high, low, close, volume, closeTime, ...]
                batch_data = []
                for k in klines:
                    try:
                        open_time_ms = k[0]
                        dt = datetime.utcfromtimestamp(open_time_ms / 1000)

                        batch_data.append({
                            "symbol": symbol,
                            "timestamp": dt,
                            "time_frame": interval,
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                        })
                    except (IndexError, ValueError) as e:
                        logger.error(f"Error parsing kline: {e}")
                        continue

                # Bulk upsert to DB
                if batch_data:
                    from sqlalchemy.dialects.postgresql import insert
                    stmt = insert(OHLCV).values(batch_data)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uix_symbol_timestamp_tf",
                        set_={
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "volume": stmt.excluded.volume
                        }
                    )
                    db.execute(stmt)
                    db.commit()

                count = len(batch_data)
                total_fetched += count

                # Move start time forward
                last_kline_time = klines[-1][0]
                current_start = last_kline_time + 60000  # +1 minute to avoid overlap

                logger.info(f"Saved {count} candles. Total: {total_fetched}. "
                           f"Last: {datetime.utcfromtimestamp(last_kline_time / 1000)}")

                # If we got fewer than requested, we've reached the end
                if len(klines) < self.CANDLES_PER_REQUEST:
                    break

                # Rate limit: Binance allows 1200 requests/min for public endpoints
                await asyncio.sleep(0.1)

            # Backfill: fetch older data if DB didn't cover the requested start
            if need_backfill and first_record:
                backfill_end_ms = int(first_record[0].timestamp() * 1000) - 60000
                backfill_start_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
                current_start = backfill_start_ms

                logger.info(f"Backfilling {symbol} from {datetime.utcfromtimestamp(backfill_start_ms / 1000)} to {first_record[0]}")

                while current_start < backfill_end_ms and total_fetched < limit:
                    params = {
                        "symbol": symbol,
                        "interval": binance_interval,
                        "startTime": current_start,
                        "endTime": backfill_end_ms,
                        "limit": self.CANDLES_PER_REQUEST,
                    }

                    try:
                        response = await client.get(url, params=params)
                    except Exception as e:
                        logger.error(f"Backfill API request failed: {e}")
                        break

                    if response.status_code != 200:
                        break

                    klines = response.json()
                    if not klines:
                        break

                    batch_data = []
                    for k in klines:
                        try:
                            dt = datetime.utcfromtimestamp(k[0] / 1000)
                            batch_data.append({
                                "symbol": symbol, "timestamp": dt, "time_frame": interval,
                                "open": float(k[1]), "high": float(k[2]),
                                "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
                            })
                        except (IndexError, ValueError):
                            continue

                    if batch_data:
                        from sqlalchemy.dialects.postgresql import insert
                        stmt = insert(OHLCV).values(batch_data)
                        stmt = stmt.on_conflict_do_update(
                            constraint="uix_symbol_timestamp_tf",
                            set_={"open": stmt.excluded.open, "high": stmt.excluded.high,
                                   "low": stmt.excluded.low, "close": stmt.excluded.close,
                                   "volume": stmt.excluded.volume}
                        )
                        db.execute(stmt)
                        db.commit()

                    total_fetched += len(batch_data)
                    last_kline_time = klines[-1][0]
                    current_start = last_kline_time + 60000

                    logger.info(f"Backfill: {len(batch_data)} candles. Total: {total_fetched}. "
                               f"Last: {datetime.utcfromtimestamp(last_kline_time / 1000)}")

                    if len(klines) < self.CANDLES_PER_REQUEST:
                        break

                    await asyncio.sleep(0.1)

            logger.info(f"Fetch complete: {total_fetched} total candles for {symbol}")
            return total_fetched

        except Exception as e:
            logger.error(f"Fetch error: {e}")
            db.rollback()
            return 0
        finally:
            db.close()

    def _aggregate_candles(self, base_candles: List[Dict], target_interval: str) -> List[Dict]:
        """
        Aggregate base candles to target interval.
        Reuses the same logic as MarketDataService but with 24/7 aware daily aggregation.
        """
        if not base_candles:
            return []

        base_candles.sort(key=lambda x: x['timestamp'])

        if target_interval == "1d":
            return self._aggregate_to_daily(base_candles)

        minutes = 0
        hours = 0
        if target_interval.endswith("m"):
            minutes = int(target_interval[:-1])
        elif target_interval.endswith("h"):
            hours = int(target_interval[:-1])
        else:
            return []

        agg = []
        current_bucket = None
        bucket_end_time = None

        for c in base_candles:
            dt = datetime.strptime(c['timestamp'], "%Y-%m-%d %H:%M:%S")

            if minutes > 0:
                m_block = (dt.minute // minutes) * minutes
                bucket_start = dt.replace(minute=m_block, second=0)
            elif hours > 0:
                h_block = (dt.hour // hours) * hours
                bucket_start = dt.replace(hour=h_block, minute=0, second=0)

            bucket_duration = timedelta(minutes=minutes) if minutes > 0 else timedelta(hours=hours)
            bucket_end = bucket_start + bucket_duration

            if current_bucket is None or dt >= bucket_end_time:
                if current_bucket:
                    agg.append(current_bucket)
                current_bucket = {
                    "timestamp": bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": c["open"], "high": c["high"],
                    "low": c["low"], "close": c["close"], "volume": c["volume"]
                }
                bucket_end_time = bucket_end
            else:
                current_bucket["high"] = max(current_bucket["high"], c["high"])
                current_bucket["low"] = min(current_bucket["low"], c["low"])
                current_bucket["close"] = c["close"]
                current_bucket["volume"] += c["volume"]

        if current_bucket:
            agg.append(current_bucket)
        return agg

    def _aggregate_to_daily(self, base_candles: List[Dict]) -> List[Dict]:
        """Aggregate 1m candles to daily. Groups by UTC calendar date."""
        if not base_candles:
            return []

        daily_buckets = {}
        for c in base_candles:
            dt = datetime.strptime(c['timestamp'], "%Y-%m-%d %H:%M:%S")
            date_key = dt.date()

            if date_key not in daily_buckets:
                daily_buckets[date_key] = {
                    "timestamp": datetime.combine(date_key, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": c["open"], "high": c["high"],
                    "low": c["low"], "close": c["close"], "volume": c["volume"]
                }
            else:
                bucket = daily_buckets[date_key]
                bucket["high"] = max(bucket["high"], c["high"])
                bucket["low"] = min(bucket["low"], c["low"])
                bucket["close"] = c["close"]
                bucket["volume"] += c["volume"]

        sorted_dates = sorted(daily_buckets.keys())
        return [daily_buckets[d] for d in sorted_dates]
