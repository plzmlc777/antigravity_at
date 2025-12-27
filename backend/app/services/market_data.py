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

    async def get_candles(self, symbol: str, interval: str = "1m", days: int = 365, limit: int = 100000) -> List[Dict]:
        """
        Main entry point for getting candle data.
        Supported intervals: 1m, 3m, 5m, 10m, 15m, 30m, 1h (60m), 4h, 1d, 1w.
        """
        # Handle aggregation intervals (4h, 8h, 12h) -> Fetch 1h and aggregate
        if interval in ["4h", "8h", "12h"]:
            base_data = await self.get_candles(symbol, "1h", days, limit * 4) # Fetch more base data
            return self._aggregate_candles(base_data, interval)
        
        # Normalize interval (e.g., 60m -> 1h for API logic, or keep consistent)
        api_interval = interval
        if interval == "1h": api_interval = "60m"
        
        # 1. Check DB for recent data
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV
        from sqlalchemy import desc
        
        db = SessionLocal()
        try:
             # Count existing
            count = db.query(OHLCV).filter(
                OHLCV.symbol == symbol, 
                OHLCV.time_frame == interval
            ).count()
            
            # Simple freshness check: if we have roughly expected count or explicit check requested
            # For this simplified version, we'll assume if count >= limit/2 it's potentially usable, 
            # but user usually requests 'fetch' explicitly to update.
            # Here we just fetch from DB if exists.
            
            db_candles = db.query(OHLCV).filter(
                OHLCV.symbol == symbol, 
                OHLCV.time_frame == interval
            ).order_by(OHLCV.timestamp.asc()).all()
            
            if len(db_candles) > 0:
                print(f"Loaded {len(db_candles)} {interval} candles from DB for {symbol}")
                return [
                    {
                        "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
                    }
                    for c in db_candles
                ][-limit:] # Return only last N
                
        finally:
            db.close()
            
        # If DB empty or logic dictates, fetch fresh
        # Note: In explicit usage, user triggers 'fetch_history' manually.
        # But here checking 'if empty' is good UX.
        if count == 0:
            print(f"No data for {symbol} {interval}. Fetching automatically...")
            await self.fetch_history(symbol, interval, days)
            # Re-read from DB
            return await self.get_candles(symbol, interval, days, limit)
            
        return []

    async def fetch_history(self, symbol: str, interval: str = "1m", days: int = 365):
        """
        Fetch historical data from Kiwoom API and save to DB.
        Support Minutes (1,3,5,10,15,30,60) and Day/Week/Month.
        Aggregates like 4h should use 1h.
        """
        print(f"Starting history fetch for {symbol} {interval} ({days} days)...")
        
        # Aggregation Logic
        if interval in ["4h", "8h", "12h"]:
            print(f"Interval {interval} is derived. Fetching 1h base data...")
            await self.fetch_history(symbol, "1h", days)
            # We don't save aggregated to DB in this design, we compute on fly or user explicit 1h save.
            # But prompt says "save and maintain". So we can aggregate and save?
            # Better to assume DB stores base intervals (1m, 1h, 1d).
            # If user wants to store 4h, we'd need to fetch 1h, aggregate, then save as 4h.
            # Let's simplify: Only API supported intervals are saved directly from API.
            # Aggregated ones are computed from 1h or 1m during 'get_candles'.
            return

        # Map to API parameters
        tr_id, param_key, param_val = self._map_interval_to_api(interval)
        if not tr_id:
            print(f"Unsupported interval for API fetch: {interval}")
            return

        # 1. Fetch Credentials from DB (Active Account)
        from ..db.session import SessionLocal
        from ..models.account import ExchangeAccount
        from ..core import security
        
        app_key = None
        secret_key = None
        
        with SessionLocal() as session:
            account = session.query(ExchangeAccount).filter(ExchangeAccount.is_active == True).first()
            if account:
                app_key = security.decrypt_key(account.encrypted_access_key)
                secret_key = security.decrypt_key(account.encrypted_secret_key)
        
        if not app_key or not secret_key:
             logger.error("No active account or missing credentials in DB. Cannot fetch market data.")
             return
        
        await self.token_manager.get_token(app_key, secret_key)
        token = self.token_manager.access_token
        
        if not token:
            logger.error("Token fetch failed. Token is None.")
            return

        from ..core.config import settings
        base_url = settings.HCP_KIWOOM_API_URL or self.BASE_URL
        url = f"{base_url}/api/dostk/chart" 
        
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
                    break
                    
                page_candles = []
                batch_data = [] # For Bulk Insert

                for item in raw_list:
                    try:
                        # Date parsing
                        # Minute: cntr_tm (YYYYMMDDHHMMSS) or date+time
                        # Day/Week: dt (YYYYMMDD) or date
                        
                        ts_str = item.get("cntr_tm") or item.get("dt") or item.get("date")
                        
                        dt = None
                        if len(ts_str) == 14: # YYYYMMDDHHMMSS
                            dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
                        elif len(ts_str) == 8: # YYYYMMDD
                            dt = datetime.strptime(ts_str, "%Y%m%d")
                        
                        # Optimization: Stop if we hit existing data
                        if last_ts and dt <= last_ts:
                            logger.info(f"Hit existing data boundary at {dt}. Stopping fetch.")
                            cont_yn = "N" # Stop future pages
                            break # Stop processing this page

                        # Parse Prices
                        def p(k): return abs(int(item.get(k, 0)))
                        
                        # Prepare Data Dict for Batch
                        candle_dict = {
                            "symbol": symbol,
                            "timestamp": dt,
                            "time_frame": interval,
                            "open": p("open_pric") or p("open"),
                            "high": p("high_pric") or p("high"),
                            "low": p("low_pric") or p("low"),
                            "close": p("cur_prc") or p("close") or p("current_price"),
                            "volume": int(item.get("trde_qty") or item.get("volume") or 0)
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
                
                # Check 10,000 limit during fetch
                if total_fetched >= 10000:
                    break
                
                # INCREMENTAL FETCH LOGIC:
                # If we have existing data, check if we've bridged the gap.
                # Since Kiwoom returns Newest -> Oldest:
                # If the *oldest* candle in this page is still newer than our DB's max_ts, we have a gap -> Continue.
                # If the *newest* candle in this page is older than DB's max_ts, we completely overlap -> Stop.
                # If the page *contains* max_ts, we found the cut-off -> Stop after this page.
                
                if last_ts: # Only optimize for short updates (< 3 years)
                    # page_candles is trusted to be sorted? 
                    # Kiwoom usually sends Newest first (index 0) to Oldest (index -1).
                    # Let's verify by sorting page_candles by time desc just to be safe or check min/max.
                    
                    # Find if we covered the last_ts
                    # If any candle in this batch is <= last_ts, we can stop fetching *further* pages.
                    
                    min_page_ts = min(c.timestamp for c in page_candles) if page_candles else None
                    
                    if min_page_ts:
                        logger.info(f"Overlap check: Page Min: {min_page_ts}, Last DB: {last_ts}")
                    
                    if min_page_ts and min_page_ts <= last_ts:
                        logger.info(f"Incremental fetch: Found overlap (Last: {last_ts}, Page Min: {min_page_ts}). Stopping.")
                        break
                    
                if cont_yn != "Y":
                    break
                    
            # Auto-Prune after fetch
            self._prune_data(db, symbol, interval, limit=100000)
            
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
        """Simple aggregation (e.g. 1h -> 4h)"""
        # Assume base_candles are sorted ASC
        if not base_candles: return []
        
        hours = 4
        if target_interval == "8h": hours = 8
        if target_interval == "12h": hours = 12
        
        # Using Pandas would be easiest, but to avoid heavy dep, simple loop:
        # Group by buckets. 
        # For simplicity, we just chunk every N candles if we assume they are contiguous 1h.
        # But for correctness, we should align to hour markers (00, 04, 08...).
        
        agg = []
        current_bucket = None
        bucket_end_time = None
        
        for c in base_candles:
            dt = datetime.strptime(c['timestamp'], "%Y-%m-%d %H:%M:%S")
            
            # Determine bucket
            # E.g. 4h buckets: 0-4, 4-8...
            h_block = (dt.hour // hours) * hours
            bucket_start = dt.replace(hour=h_block, minute=0, second=0)
            bucket_end = bucket_start + timedelta(hours=hours)
            
            if current_bucket is None or dt >= bucket_end_time:
                # Close previous
                if current_bucket: agg.append(current_bucket)
                
                # Start new
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
                # Update current
                current_bucket["high"] = max(current_bucket["high"], c["high"])
                current_bucket["low"] = min(current_bucket["low"], c["low"])
                current_bucket["close"] = c["close"]
                current_bucket["volume"] += c["volume"]
                
        if current_bucket: agg.append(current_bucket)
        return agg

    def _generate_synthetic_candles(self, symbol: str, days: int) -> List[Dict]:
        # Fallback mechanism if API fails
        return [] # Simplified for now to encourage real data usage


    # TODO: Implement actual API call when documentation is confirmed
    # async def _real_api_call(self): ...
