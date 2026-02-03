
from typing import Dict, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class CandleRealAggregator:
    """
    Aggregates real-time ticks into 1-minute OHLCV candles.
    Essential for bridging Real-Time Data Stream (Ticks) -> Strategy Logic (Candles).
    """
    def __init__(self, symbol: str, interval_minutes: int = 1):
        self.symbol = symbol
        self.interval_minutes = interval_minutes
        
        # Current Candle State
        self.current_bucket_key: Optional[str] = None # e.g., "2023-01-01 10:00"
        self.open = 0.0
        self.high = 0.0
        self.low = 0.0
        self.close = 0.0
        self.volume = 0
        self.start_time: Optional[datetime] = None
        
        # Last finalized candle
        self.last_closed_candle: Optional[Dict] = None

    def add_tick(self, price: float, volume: int, timestamp: datetime) -> Tuple[Optional[Dict], Dict]:
        """
        Ingest a tick.
        Returns:
            (closed_candle, current_snapshot)
            - closed_candle: Dict if a candle just closed, else None.
            - current_snapshot: Dict of the current forming candle (for Frontend).
        """
        # 1. Determine Bucket (Truncate seconds to minute)
        # assuming timestamp is datetime object
        bucket_ts = timestamp.replace(second=0, microsecond=0)
        bucket_key = bucket_ts.strftime("%Y-%m-%d %H:%M:%S")
        
        closed_candle = None
        
        # 2. Check for new bucket
        if self.current_bucket_key is not None and bucket_key != self.current_bucket_key:
            # Previous candle closed!
            closed_candle = {
                "timestamp": self.start_time.isoformat(), # Use start of the minute
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close, # Close is the last price of that bucket
                "volume": self.volume,
                "symbol": self.symbol
            }
            self.last_closed_candle = closed_candle
            
            # Reset for new bucket
            self._reset_bucket(price, volume, bucket_ts, bucket_key)
            
        elif self.current_bucket_key is None:
            # First tick ever
            self._reset_bucket(price, volume, bucket_ts, bucket_key)
            
        else:
            # Same bucket, update stats
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.close = price
            # Volume in Kiwoom 'cur_prc' might be cumulative or tick volume?
            # Usually Kiwoom gives 'accumulated volume'. 
            # If input 'volume' is accumulated, we need to track delta?
            # For now assume input is 'current accum volume' or 'tick volume'?
            # Let's assume input is 'tick volume' for this aggregator logic.
            # If Kiwoom gives accum volume, the caller must diff it.
            # *Design Decision*: We assume the Caller passes 'Total Daily Volume'.
            # So we store that directly? No, Candle volume is volume *in that minute*.
            # This logic is tricky with Kiwoom.
            # Let's adjust: Aggregator expects 'tick_volume' (delta).
            # If caller sends 'accum_volume', caller calculates delta.
            self.volume += volume 

        # 3. Snapshot for Frontend (Real-time view)
        snapshot = {
            "timestamp": bucket_ts.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
            "is_closed": False
        }
        
        return closed_candle, snapshot

    def _reset_bucket(self, price, volume, timestamp, key):
        self.current_bucket_key = key
        self.start_time = timestamp
        self.open = price
        self.high = price
        self.low = price
        self.close = price
        self.volume = volume
