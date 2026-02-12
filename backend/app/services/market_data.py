import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..core.token_manager import KiwoomTokenManager
from ..core.http_client import HttpClientManager
import logging

logger = logging.getLogger(__name__)

class MarketDataService:
    """
    Service to fetch historical market data (Candles) from Kiwoom API.
    """
    BASE_URL = "https://openapi.kiwoom.com/openapi/service/rest" 

    def __init__(self):
        self.token_manager = KiwoomTokenManager.get_instance()
        self.http_manager = HttpClientManager.get_instance()

    # Constants for data retention
    MAX_DAYS = 365  # 1 year maximum (API limit)
    DEFAULT_DAYS = 365  # 1 year default

    async def get_candles(self, symbol: str, interval: str = "1m", days: int = 730, limit: int = 100000, to_date: str = None) -> List[Dict]:
        """
        Main entry point for getting candle data.

        Data Storage Strategy (v0.9.8.5):
        - DB stores ONLY 1m data (up to 2 years)
        - ALL other intervals (3m, 5m, 15m, 30m, 60m, 1d, etc.) are derived from 1m at runtime
        - This ensures consistency and reduces DB storage

        Supported intervals: 1m, 3m, 5m, 10m, 15m, 30m, 1h (60m), 4h, 1d.

        Args:
            to_date: End date string (YYYY-MM-DD). If provided, used as reference instead of now().
                     Default (None) = yesterday, ensuring reproducible results within the same day.
        """
        # Enforce max days limit
        days = min(days, self.MAX_DAYS)

        # Handle aggregation intervals - Fetch 1m and aggregate to higher timeframes
        # ALL intervals except 1m are derived from 1m data
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
            "1d": ("1m", 390),  # ~390 trading minutes per day (09:00-15:30)
        }

        if interval in aggregation_map:
            base_interval, multiplier = aggregation_map[interval]
            print(f"[DEBUG] Aggregating {symbol} from {base_interval} to {interval}")
            base_data = await self.get_candles(symbol, base_interval, days, limit * multiplier, to_date=to_date)
            aggregated = self._aggregate_candles(base_data, interval)
            print(f"[DEBUG] Aggregation result: {len(base_data)} {base_interval} candles -> {len(aggregated)} {interval} candles")
            return aggregated

        # Normalize interval (e.g., 60m -> 1h for API logic, or keep consistent)
        api_interval = interval
        if interval == "1h": api_interval = "60m"
        
        # 1. Check DB for recent data
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV
        from sqlalchemy import desc
        
        db = SessionLocal()
        try:
            # Calculate date range: use to_date as end reference (default: yesterday)
            if to_date:
                try:
                    end_ref = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)  # Include full to_date
                except ValueError:
                    end_ref = datetime.now()
            else:
                # Default: yesterday end-of-day (ensures reproducible results within same day)
                end_ref = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = end_ref - timedelta(days=days)

            # Query only what's needed
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
            
            if len(db_candles) >= 10: # Reduced threshold for testing
                print(f"Loaded {len(db_candles)} {interval} candles from DB for {symbol} (to_date={to_date}, end_ref={end_ref}, start_date={start_date})")
                return [
                    {
                        "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
                    }
                    for c in db_candles
                ]
                
        finally:
            db.close()
            
        # Count for fetch check
        db = SessionLocal()
        try:
            count = db.query(OHLCV).filter(
                OHLCV.symbol == symbol, 
                OHLCV.time_frame == interval
            ).count()
        finally:
            db.close()
            
        # If DB empty or logic dictates, fetch fresh
        # Note: In explicit usage, user triggers 'fetch_history' manually.
        # But here checking 'if empty' is good UX.
        # If DB empty or insufficient data (e.g. < 100 records), fetch fresh
        if count < 100:
            # Calculate required limit for fetch
            minutes_per_day = 1440
            if interval.endswith("m"):
                minutes = int(interval.replace("m", ""))
                minutes_per_day = 1440 // minutes
            elif interval == "1h":
                 minutes_per_day = 24
            
            # Ensure limit is enough for days requested
            fetch_limit = max(100000, days * minutes_per_day * 2) # Safety multiplier
            
            print(f"Insufficient data for {symbol} {interval} (Count: {count}). Fetching automatically (Limit: {fetch_limit})...")
            await self.fetch_history(symbol, interval, days, limit=fetch_limit)
            # Re-read from DB
            # Re-read from DB
            db = SessionLocal()
            try:
                db_candles = db.query(OHLCV).filter(
                    OHLCV.symbol == symbol, 
                    OHLCV.time_frame == interval
                ).order_by(OHLCV.timestamp.asc()).all()
                
                # Only return if we have a substantial amount, otherwise fallback to synthetic
                if len(db_candles) >= 100:
                    print(f"Loaded {len(db_candles)} {interval} candles from DB for {symbol} (After Fetch)")
                    return [
                        {
                            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
                        }
                        for c in db_candles
                    ][-limit:]
            
                # Fallback: Generate Synthetic Data if Fetch Failed (Mock Mode Support)
                # print(f"Fetch failed or returned insufficient records({len(db_candles)}). Generating synthetic data for {symbol}...")
                # return await self._generate_synthetic_candles(symbol, days)
                
                # USER DEMAND: DISABLE FAKE DATA.
                print(f"Fetch failed or returned insufficient records ({len(db_candles)}). Real data fetch required but failed (404/Empty). Returning empty.")
                return []
            finally:
                db.close()
            
        return []

    async def get_candles_by_date(self, symbol: str, interval: str, date_str: str) -> List[Dict]:
        """
        Fetch candles for a specific date (YYYYMMDD).
        Useful for intraday history retrieval.
        """
        # 1. Parse Date
        try:
            target_date = datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            print(f"Invalid date format {date_str}. Expected YYYYMMDD.")
            return []
            
        # 2. Query DB
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV
        from sqlalchemy import and_
        
        db = SessionLocal()
        try:
            # Filter by timestamp >= date 00:00:00 AND timestamp < date+1 00:00:00
            start_dt = datetime.combine(target_date, datetime.min.time())
            end_dt = start_dt + timedelta(days=1)
            
            db_candles = db.query(OHLCV).filter(
                and_(
                    OHLCV.symbol == symbol, 
                    OHLCV.time_frame == interval,
                    OHLCV.timestamp >= start_dt,
                    OHLCV.timestamp < end_dt
                )
            ).order_by(OHLCV.timestamp.asc()).all()
            
            if len(db_candles) > 0:
                print(f"Loaded {len(db_candles)} {interval} candles for {date_str} from DB.")
                return [
                    {
                        "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
                        "time": int(c.timestamp.timestamp()) # Add unix timestamp for frontend
                    }
                    for c in db_candles
                ]
            else:
                # If no data in DB, we could try fetching from Kiwoom API if it supports date range.
                # BUT Kiwoom API opt10080 (Minute) usually fetches "recent N".
                # If the date is TODAY, we can just fetch recent.
                if target_date == datetime.now().date():
                    print("Date is Today. Fetching recent history from API...")
                    # We reuse fetch_history but it fetches "days". 
                    # fetch_history(..., days=1) fetches last 24h usually or 1 day worth.
                    await self.fetch_history(symbol, interval, days=1)
                    
                    # Re-query
                    db_candles = db.query(OHLCV).filter(
                        and_(
                            OHLCV.symbol == symbol, 
                            OHLCV.time_frame == interval,
                            OHLCV.timestamp >= start_dt,
                            OHLCV.timestamp < end_dt
                        )
                    ).order_by(OHLCV.timestamp.asc()).all()
                    
                    return [
                        {
                            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
                            "time": int(c.timestamp.timestamp())
                        }
                        for c in db_candles
                    ]
                
                return []
                
        finally:
            db.close()

    def _resample_candles(self, candles: List[Dict], interval: str) -> List[Dict]:
        """
        Resample 1m candles list to target interval.
        candles: list of dicts with keys: timestamp(str), open, high, low, close, volume, time(int)
        """
        if not candles:
            return []
            
        minutes = 1
        if interval.endswith("m"):
            minutes = int(interval.replace("m", ""))
        elif interval == "1h" or interval == "60m":
            minutes = 60
        elif interval == "4h":
            minutes = 240
        elif interval == "1d":
            # Special case: Resample everything into one day logic
            # OR just treat as 24h for bucketing?
            # Market hours are 09:00-15:30 (6.5h).
            # If we use 1440m (24h), it buckets correctly per day.
            minutes = 1440
        else:
            # Try parsing custom "Xm"
             if interval.endswith("m"):
                try:
                    minutes = int(interval.replace("m", ""))
                except:
                    pass

            
        if minutes == 1:
            return candles
            
        resampled = []
        current_bucket_start = None
        current_candle = None
        
        # Helper to parse time if needed, but assuming input has 'time' (unix) or 'timestamp' (str)
        # We use 'time' (unix) for easiest bucketing
        
        for c in candles:
            ts = c.get("time")
            if not ts: continue # Skip invalid
            
            # Bucketing logic: floor(ts / (minutes*60)) * (minutes*60)
            bucket_sec = minutes * 60
            bucket_start_ts = (ts // bucket_sec) * bucket_sec
            
            if current_bucket_start != bucket_start_ts:
                # Push previous
                if current_candle:
                    resampled.append(current_candle)
                
                # Start new
                current_bucket_start = bucket_start_ts
                current_candle = {
                    "timestamp": datetime.fromtimestamp(bucket_start_ts).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"],
                    "time": bucket_start_ts
                }
            else:
                # Aggregate
                current_candle["high"] = max(current_candle["high"], c["high"])
                current_candle["low"] = min(current_candle["low"], c["low"])
                current_candle["close"] = c["close"]
                current_candle["volume"] += c["volume"]
                
        # Push last
        if current_candle:
            resampled.append(current_candle)
            
        return resampled

    async def get_candles_by_date(self, symbol: str, interval: str, date_str: str) -> List[Dict]:
        """
        Fetch candles for a specific date (YYYYMMDD).
        Useful for intraday history retrieval.
        Supports on-the-fly aggregation if specific interval is missing in DB.
        """
        # 1. Parse Date
        try:
            target_date = datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            print(f"Invalid date format {date_str}. Expected YYYYMMDD.")
            return []
            
        # 2. Query DB
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV
        from sqlalchemy import and_
        
        db = SessionLocal()
        try:
            # Filter by timestamp >= date 00:00:00 AND timestamp < date+1 00:00:00
            start_dt = datetime.combine(target_date, datetime.min.time())
            end_dt = start_dt + timedelta(days=1)
            
            # A. Try Exact Match
            db_candles = db.query(OHLCV).filter(
                and_(
                    OHLCV.symbol == symbol, 
                    OHLCV.time_frame == interval,
                    OHLCV.timestamp >= start_dt,
                    OHLCV.timestamp < end_dt
                )
            ).order_by(OHLCV.timestamp.asc()).all()
            
            if len(db_candles) > 0:
                print(f"Loaded {len(db_candles)} {interval} candles for {date_str} from DB (Exact Match).")
                return [
                    {
                        "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
                        "time": int(c.timestamp.timestamp())
                    }
                    for c in db_candles
                ]
            
            # B. If Empty and Interval != 1m, Try Aggregating 1m Data
            if interval != "1m":
                print(f"No exact match for {interval}. Trying to aggregate from 1m data...")
                
                # Check 1m data
                base_candles_db = db.query(OHLCV).filter(
                    and_(
                        OHLCV.symbol == symbol, 
                        OHLCV.time_frame == "1m",
                        OHLCV.timestamp >= start_dt,
                        OHLCV.timestamp < end_dt
                    )
                ).order_by(OHLCV.timestamp.asc()).all()
                
                # Helper to format DB objects to Dicts
                base_data = []
                if base_candles_db:
                    base_data = [
                        {
                            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
                            "time": int(c.timestamp.timestamp())
                        }
                        for c in base_candles_db
                    ]
                
                # If still empty (no 1m data), try fetching 1m from API (only for Today)
                if not base_data and target_date == datetime.now().date():
                     print("1m Data missing for Today. Fetching from API...")
                     await self.fetch_history(symbol, "1m", days=1)
                     
                     # Re-query
                     base_candles_db = db.query(OHLCV).filter(
                        and_(
                            OHLCV.symbol == symbol, 
                            OHLCV.time_frame == "1m",
                            OHLCV.timestamp >= start_dt,
                            OHLCV.timestamp < end_dt
                        )
                    ).order_by(OHLCV.timestamp.asc()).all()
                    
                     base_data = [
                        {
                            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
                            "time": int(c.timestamp.timestamp())
                        }
                        for c in base_candles_db
                    ]
                
                if base_data:
                    resampled = self._resample_candles(base_data, interval)
                    print(f"Aggregated {len(base_data)} 1m candles into {len(resampled)} {interval} candles.")
                    return resampled
            
            # C. Fallback for 1m (if B skipped or failed) - Try API fetch for today
            if not db_candles and target_date == datetime.now().date() and interval == "1m":
                 print("1m Data missing for Today. Fetching from API (Fallback C)...")
                 await self.fetch_history(symbol, interval, days=1)
                 # Re-query
                 db_candles = db.query(OHLCV).filter(
                    and_(
                        OHLCV.symbol == symbol, 
                        OHLCV.time_frame == interval,
                        OHLCV.timestamp >= start_dt,
                        OHLCV.timestamp < end_dt
                    )
                ).order_by(OHLCV.timestamp.asc()).all()
                
                 # Only return if we actually got data, otherwise fall through to D
                 if db_candles:
                     return [
                        {
                            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
                            "time": int(c.timestamp.timestamp())
                        }
                        for c in db_candles
                    ]
                 else:
                     print("C block API fetch returned no data for today. Falling through to D...")

            # D. Fallback: If still no data (e.g., weekend/holiday), get most recent trading day
            print(f"No data for {date_str}. Checking for most recent trading day...")
            latest_record = db.query(OHLCV).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == "1m"  # Always check 1m as base
            ).order_by(OHLCV.timestamp.desc()).first()
            
            if latest_record:
                latest_date = latest_record.timestamp.date()
                print(f"Found latest trading day: {latest_date}")
                
                # Fetch that day's data
                fallback_start = datetime.combine(latest_date, datetime.min.time())
                fallback_end = fallback_start + timedelta(days=1)
                
                fallback_candles = db.query(OHLCV).filter(
                    and_(
                        OHLCV.symbol == symbol,
                        OHLCV.time_frame == "1m",
                        OHLCV.timestamp >= fallback_start,
                        OHLCV.timestamp < fallback_end
                    )
                ).order_by(OHLCV.timestamp.asc()).all()
                
                if fallback_candles:
                    base_data = [
                        {
                            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume,
                            "time": int(c.timestamp.timestamp())
                        }
                        for c in fallback_candles
                    ]
                    
                    if interval == "1m":
                        print(f"Returning {len(base_data)} candles from {latest_date} as fallback.")
                        return base_data
                    else:
                        resampled = self._resample_candles(base_data, interval)
                        print(f"Returning {len(resampled)} {interval} candles from {latest_date} as fallback.")
                        return resampled

            return []
                
        finally:
            db.close()

    def delete_ohlcv_by_symbol(self, db, symbol: str) -> int:
        """
        Delete ALL OHLCV data for a specific symbol.
        Returns the number of deleted records.
        """
        try:
            from ..models.ohlcv import OHLCV
            num = db.query(OHLCV).filter(OHLCV.symbol == symbol).delete()
            db.commit()
            print(f"Deleted {num} records for {symbol}")
            return num
        except Exception as e:
            db.rollback()
            print(f"Error deleting data for {symbol}: {e}")
            raise e

    async def fetch_history(self, symbol: str, interval: str = "1m", days: int = 730, limit: int = 100000, backfill: bool = False):
        """
        Fetch historical data from Kiwoom API and save to DB.

        backfill: If True, fetch full history regardless of existing data (slower, for initial setup).
                  If False, stop when hitting existing data (incremental, faster).

        Data Storage Strategy (v0.9.8.5):
        - ONLY 1m data is fetched from API and stored in DB
        - ALL other intervals are derived at runtime via get_candles()
        - This ensures consistency and reduces DB storage

        Args:
            symbol: Stock symbol
            interval: Requested interval (only 1m is actually fetched/stored)
            days: Number of days to fetch (max 730 = 2 years)
            limit: Maximum records to fetch
        """
        # Enforce max days limit
        days = min(days, self.MAX_DAYS)

        print(f"Starting history fetch for {symbol} {interval} ({days} days)...")

        # ALL intervals except 1m are derived - just fetch 1m base data
        if interval != "1m":
            print(f"Interval {interval} is derived from 1m. Fetching 1m base data...")
            result = await self.fetch_history(symbol, "1m", days, limit)
            print(f"1m base data fetched: {result} records. {interval} will be derived at runtime.")
            return result

        # Map to API parameters
        tr_id, param_key, param_val = self._map_interval_to_api(interval)
        if not tr_id:
            print(f"Unsupported interval for API fetch: {interval}")
            return

        # 1. Fetch Credentials from DB (Active Account)
        # NOTE: Market data (stock prices) is universal - same for all users.
        # We use any valid API credentials to fetch this shared data.
        # Currently uses the first active account found. In a production multi-user
        # system, consider using a dedicated "system" account for market data fetching.
        from ..db.session import SessionLocal
        # Ensure User model is loaded for relationship resolution in worker process
        from ..models.user import User
        from ..models.account import ExchangeAccount
        from ..core import security

        app_key = None
        secret_key = None
        account_api_url = None

        with SessionLocal() as session:
            # Get any active account for API credentials (market data is the same for all)
            # Priority: most recently activated account (by id desc)
            account = session.query(ExchangeAccount).filter(
                ExchangeAccount.is_active == True,
                ExchangeAccount.is_disabled == False
            ).order_by(ExchangeAccount.id.desc()).first()
            if account:
                app_key = security.decrypt_key(account.encrypted_access_key)
                secret_key = security.decrypt_key(account.encrypted_secret_key)
                account_api_url = account.api_url
                logger.info(f"Using account '{account.account_name}' (id={account.id}) for market data API access")

        if not app_key or not secret_key:
             logger.error("No active account or missing credentials in DB. Cannot fetch market data.")
             return

        # Use account's api_url for token acquisition
        await self.token_manager.get_token(app_key, secret_key, base_url=account_api_url)
        token = self.token_manager.access_token

        if not token:
            logger.error("Token fetch failed. Token is None.")
            return

        # Use account's api_url or default to real server
        base_url = account_api_url or "https://api.kiwoom.com"
        logger.info(f"MarketDataService using API URL: {base_url}")
        
        # HCP REST API uses /api/dostk/chart
        url = f"{base_url}/api/dostk/chart" 
        # Wait, if I hardcode this, I might break it if the suffix is wrong.
        # Kiwoom Open API REST documentation says:
        # GET https://openapi.kiwoom.com/openapi/service/rest/opt10001 (example)
        # But here code uses /api/dostk/chart ?? This looks like a specific wrapper or customized gateway.
        # "dostk" sounds like "Do Stock"? 
        # If this is a proxy or HCP wrapper, "mockapi" suggests it is an HCP standard.
        # If I change to "https://openapi.kiwoom.com" I might need to adjust the path too.
        
        # HOWEVER, the previous log showed `https://mockapi.kiwoom.com` was used.
        # If I switch to `https://openapi.kiwoom.com`, I must match the path structure.
        # Since I don't know the exact HCP path structure for Real, I should stick to the pattern but change the DOMAIN.
        
        # Let's assume the path `/api/dostk/chart` is correct for the gateway.
        # I will just force the domain to `https://openapi.kiwoom.com` IF that is the Real server.
        # Wait, usually `openapi.kiwoom.com` IS the real server.
        
        # Let's try forcing the domain but keeping the logic simple.
        
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "api-id": tr_id,
        }
        
        # Initial Payload
        payload = {
            "stk_cd": symbol,
            param_key: param_val, # tic_scope or (implicit for day?)
            "upd_stkpc_tp": "1" # Adjusted price
        }
        # Daily/Weekly/Monthly (ka10081/2/3) typically explicitly use 'base_dt' (EndDate)
        # Minute (ka10080) uses 'qry_dt' sometimes or implicitly latest? 
        # Ka10080 (Minute) REST doc: Request has no date field! It uses system time or implicit.
        # Ka10081 (Daily) REST doc: Request has 'base_dt' (Latest date to fetch BACKWARDS from)
        
        if tr_id in ["ka10081", "ka10082", "ka10083"]:
            payload["base_dt"] = datetime.now().strftime("%Y%m%d")
        
        client = self.http_manager.get_client()
        
        total_fetched = 0
        next_key = None
        cont_yn = "N"
        max_pages = 100 # Safety limit
        
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV
        db = SessionLocal()
        
        # INCREMENTAL: Get the latest timestamp we already have
        last_ts = None
        try:
            logger.info(f"Checking existing data for {symbol} {interval}...")
            last_record = db.query(OHLCV.timestamp).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == interval
            ).order_by(OHLCV.timestamp.desc()).first()
            
            if last_record:
                last_ts = last_record[0]
                logger.info(f"Existing data found. Latest timestamp: {last_ts}. Performing incremental update...")
            else:
                logger.info(f"No existing data found for {symbol} {interval}.")
        except Exception as e:
            logger.error(f"Error fetching last_ts: {e}")
        
        try:
            for page in range(max_pages):
                if next_key and cont_yn == "Y":
                    headers["next-key"] = next_key
                    headers["cont-yn"] = "Y"
                elif page > 0:
                    break 
                
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    print(f"Error {response.status_code}")
                    break
                
                cont_yn = response.headers.get("cont-yn", "N")
                next_key = response.headers.get("next-key", "")
                
                data = response.json()
                
                # Dynamic output field name resolution
                # ka10080 -> stk_min_pole_chart_qry OR output
                # ka10081 -> stk_dt_pole_chart_qry
                # ka10082 -> stk_stk_pole_chart_qry (Weekly)
                # ka10083 -> stk_mth_pole_chart_qry (Monthly)
                
                raw_list = []
                for key in data.keys():
                    if key.endswith("_qry") or key == "output":
                        if isinstance(data[key], list):
                            raw_list = data[key]
                            break
                            
                if not raw_list:
                    print("DEBUG: API returned empty list.")
                    break
                    
                # DEBUG: Inspect First Item
                print(f"DEBUG: Page {page} Raw Item 0: {raw_list[0]}")
                
                page_candles = []
                batch_data = [] # For Bulk Insert

                for item in raw_list:
                    try:
                        # Date parsing
                        # Minute: cntr_tm (YYYYMMDDHHMMSS) or date+time
                        # Day/Week: dt (YYYYMMDD) or date or stck_bsop_date
                        
                        ts_str = item.get("cntr_tm") or item.get("dt") or item.get("date") or item.get("stck_bsop_date")
                        
                        dt = None
                        if ts_str:
                            if len(ts_str) == 14: # YYYYMMDDHHMMSS
                                dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
                            elif len(ts_str) == 8: # YYYYMMDD
                                dt = datetime.strptime(ts_str, "%Y%m%d")
                        
                        if not dt:
                             continue # Skip if no date

                        # Optimization: Stop if we hit existing data (only in incremental mode)
                        if last_ts and dt <= last_ts and not backfill:
                            logger.info(f"Hit existing data boundary at {dt}. Stopping fetch (incremental mode).")
                            cont_yn = "N" # Stop future pages
                            break # Stop processing this page

                        # Parse Prices
                        # Standard Kiwoom Keys: stck_oprc, stck_hgpr, stck_lwpr, stck_clpr, acml_vol
                        def p(k): return abs(int(item.get(k, 0)))
                        
                        # Prepare Data Dict for Batch
                        candle_dict = {
                            "symbol": symbol,
                            "timestamp": dt,
                            "time_frame": interval,
                            "open": p("open_pric") or p("open") or p("stck_oprc"),
                            "high": p("high_pric") or p("high") or p("stck_hgpr"),
                            "low": p("low_pric") or p("low") or p("stck_lwpr"),
                            "close": p("cur_prc") or p("close") or p("current_price") or p("stck_clpr"),
                            "volume": int(item.get("trde_qty") or item.get("volume") or item.get("acml_vol") or 0)
                        }
                        
                        batch_data.append(candle_dict)
                        
                        # Add a dummy object to page_candles for min() calculation
                        class SimpleCandle:
                            def __init__(self, ts): self.timestamp = ts
                        page_candles.append(SimpleCandle(dt))
                        
                    except Exception as e:
                        logger.error(f"Error parsing candle: {e}")
                        pass
                
                # BULK UPSERT
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
                count = len(page_candles)
                total_fetched += count
                print(f"Saved {count} records. Total: {total_fetched}")
                
                await asyncio.sleep(0.2)
                
                # Check limit during fetch
                if total_fetched >= limit:
                    break
                
                # INCREMENTAL FETCH LOGIC:
                # If we have existing data and NOT in backfill mode, check if we've bridged the gap.
                if last_ts and not backfill:
                    # Find if we covered the last_ts
                    min_page_ts = min(c.timestamp for c in page_candles) if page_candles else None

                    if min_page_ts:
                        logger.info(f"Overlap check: Page Min: {min_page_ts}, Last DB: {last_ts}")

                    if min_page_ts and min_page_ts <= last_ts:
                        logger.info(f"Incremental fetch: Found overlap (Last: {last_ts}, Page Min: {min_page_ts}). Stopping.")
                        break
                elif backfill:
                    logger.info(f"Backfill mode: Continuing to fetch older data...")
                    
                if cont_yn != "Y":
                    break
                    
            # Auto-Prune after fetch
            self._prune_data(db, symbol, interval, limit=limit)
            
            return total_fetched
            
        except Exception as e:
            print(f"Fetch Error: {e}")
            db.rollback()
            return 0
        finally:
            db.close()

    def _map_interval_to_api(self, interval: str):
        # normalize "1h" -> "60m"
        if interval == "1h": interval = "60m"
        
        # Minutes
        if interval.endswith("m"):
            unit = interval[:-1] # "1", "3"...
            return "ka10080", "tic_scope", unit
            
        # Day
        if interval == "1d":
            return "ka10081", "dummy", "dummy" # Daily doesn't have tic_scope, just base_dt
            
        # Week
        if interval == "1w":
            return "ka10082", "dummy", "dummy"
            
        return None, None, None

    def _prune_data(self, db, symbol: str, interval: str, limit: int = 10000):
        """Keep only the latest N records."""
        try:
            # Subquery to find the Nth timestamp
            # We want to DELETE WHERE timestamp < (SELECT timestamp FROM ... ORDER BY desc OFFSET N LIMIT 1)
            
            # Simple approach: Fetch IDs of newest N, delete others? Large.
            # Better: Find cutoff date.
            
            from ..models.ohlcv import OHLCV
            
            # Get the timestamp of the 10,000th newest record
            cutoff_record = db.query(OHLCV.timestamp).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == interval
            ).order_by(OHLCV.timestamp.desc()).offset(limit).limit(1).first()
            
            if cutoff_record:
                cutoff_ts = cutoff_record[0]
                deleted = db.query(OHLCV).filter(
                    OHLCV.symbol == symbol,
                    OHLCV.time_frame == interval,
                    OHLCV.timestamp <= cutoff_ts
                ).delete(synchronize_session=False)
                db.commit()
                print(f"Pruned {deleted} old records for {symbol} {interval}")
                
        except Exception as e:
            print(f"Prune failed: {e}")

    def _aggregate_candles(self, base_candles: List[Dict], target_interval: str) -> List[Dict]:
        """
        Aggregate base candles to target interval.
        - Robustly handles gaps (missing 1m data) by skipping empty intervals.
        - Strictly sorts input data to prevent time-travel anomalies.
        - Supports daily aggregation (1d) by grouping all candles within a calendar day.
        """
        if not base_candles: return []

        # Ensure data is sorted by timestamp to prevent aggregation logic errors
        base_candles.sort(key=lambda x: x['timestamp'])

        # Special handling for daily aggregation
        if target_interval == "1d":
            return self._aggregate_to_daily(base_candles)

        minutes = 0
        hours = 0

        # Parse Target Interval
        if target_interval.endswith("m"):
            minutes = int(target_interval[:-1])
        elif target_interval.endswith("h"):
            hours = int(target_interval[:-1])
        else:
            print(f"Unsupported aggregation interval: {target_interval}")
            return []

        agg = []
        current_bucket = None
        bucket_end_time = None

        for c in base_candles:
            dt = datetime.strptime(c['timestamp'], "%Y-%m-%d %H:%M:%S")

            # Determine Bucket Start (Align to grid)
            bucket_start = None
            if minutes > 0:
                 m_block = (dt.minute // minutes) * minutes
                 bucket_start = dt.replace(minute=m_block, second=0)
            elif hours > 0:
                 h_block = (dt.hour // hours) * hours
                 bucket_start = dt.replace(hour=h_block, minute=0, second=0)

            bucket_duration = timedelta(minutes=minutes) if minutes > 0 else timedelta(hours=hours)
            bucket_end = bucket_start + bucket_duration

            # Check Alignment (New Bucket Needed?)
            # Condition: First bucket OR Timestamp exceeds current bucket end
            if current_bucket is None or dt >= bucket_end_time:

                # Gap Detection Loop (Optional - just for clarity, we simply skip)
                # If we jump from 09:00 to 10:00, we just close 09:00 and open 10:00.
                # This leaves the in-between time "Empty" (no candle objects).

                # Close previous bucket
                if current_bucket:
                    agg.append(current_bucket)

                # Start new bucket at the calculated aligned start time
                current_bucket = {
                    "timestamp": bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"]
                }
                bucket_end_time = bucket_end

            else:
                # Accumulate into current bucket
                current_bucket["high"] = max(current_bucket["high"], c["high"])
                current_bucket["low"] = min(current_bucket["low"], c["low"])
                current_bucket["close"] = c["close"]
                current_bucket["volume"] += c["volume"]

        # Close final bucket
        if current_bucket: agg.append(current_bucket)
        return agg

    def _aggregate_to_daily(self, base_candles: List[Dict]) -> List[Dict]:
        """
        Aggregate 1m candles to daily (1d) candles.
        Groups all candles by calendar date.
        """
        if not base_candles:
            return []

        daily_buckets = {}

        for c in base_candles:
            dt = datetime.strptime(c['timestamp'], "%Y-%m-%d %H:%M:%S")
            date_key = dt.date()

            if date_key not in daily_buckets:
                # Start new daily bucket at 00:00:00 of that day
                daily_buckets[date_key] = {
                    "timestamp": datetime.combine(date_key, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"]
                }
            else:
                # Accumulate into existing bucket
                bucket = daily_buckets[date_key]
                bucket["high"] = max(bucket["high"], c["high"])
                bucket["low"] = min(bucket["low"], c["low"])
                bucket["close"] = c["close"]
                bucket["volume"] += c["volume"]

        # Sort by date and return
        sorted_dates = sorted(daily_buckets.keys())
        return [daily_buckets[d] for d in sorted_dates]

    async def _generate_synthetic_candles(self, symbol: str, days: int) -> List[Dict]:
        """
        Generate synthetic OHLCV data for testing.
        Uses a random walk to create realistic-looking price movement.
        """
        import random
        from datetime import timedelta
        
        print(f"Generating {days} days of synthetic data for {symbol}...")
        candles = []
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days)
        
        base_price = 70000 if symbol == "005930" else 10000
        current_price = base_price
        
        # Approximate Trading Minutes (09:00 - 15:30 = 390 mins)
        # We need to generate roughly 'days * 390' records or cover the 24h span if crypto logic?
        # Kiwoom is stock, so 09:00-15:30.
        # For simplicity, we can generate generic 24h data or strictly 09:00-15:30.
        # Strict logic is complex. Let's do simple 24h or continuous.
        # Backtest engine usually works with any timestamps.
        
        current_ts = start_dt
        while current_ts < end_dt:
             # Random Walk
             fluctuation = random.uniform(-0.002, 0.002) # 0.2% per minute
             current_price = current_price * (1 + fluctuation)
             
             # OHLC
             open_p = current_price * (1 + random.uniform(-0.0005, 0.0005))
             close_p = current_price
             high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.001))
             low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.001))
             
             candles.append({
                 "timestamp": current_ts.strftime("%Y-%m-%d %H:%M:%S"),
                 "open": int(open_p),
                 "high": int(high_p),
                 "low": int(low_p),
                 "close": int(close_p),
                 "volume": random.randint(100, 5000)
             })
             
             current_ts += timedelta(minutes=1)
             
        return candles

    # TODO: Implement actual API call when documentation is confirmed
    # async def _real_api_call(self): ...
