import asyncio
import os
import sys
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

from backend.app.adapters.kiwoom_real import KiwoomRealAdapter
from backend.app.core.config import settings

async def main():
    print("Testing Kiwoom Get Minute Candles...")
    # Ensure REAL mode just in case
    settings.TRADING_MODE = "REAL" 
    
    adapter = KiwoomRealAdapter()
    
    # Using the symbol user mentioned or default if unknown.
    # User previous logs showed '085310' (Enkay).
    symbol = "085310" 
    
    try:
        print(f"Fetching candles for {symbol}...")
        candles = await adapter.get_minute_candles(symbol, interval_minutes=1)
        
        print(f"Received {len(candles)} candles.")
        if candles:
            print("--- Last 10 Candles ---")
            for c in candles[-10:]:
                print(c)
                
            # specific check for > 15:30
            ghosts = [c for c in candles if "153000" < str(c['timestamp'])[8:]] 
            # timestamp format in adapter: varies.
            # Adapter: ts = item.get("cntr_tm") -> "20250917132000"
            
            print(f"--- Ghost Candles (>15:30) ---")
            ghosts_found = []
            for c in candles:
                ts_str = str(c['timestamp'])
                # Format YYYYMMDDHHMMSS
                if len(ts_str) == 14:
                    time_part = ts_str[8:]
                    if time_part > "153000":
                        ghosts_found.append(c)
                        
            for g in ghosts_found:
                print(g)
                
            if not ghosts_found:
                print("No API ghost candles found (Time > 15:30).")

    except Exception as e:
        print(e)
        
if __name__ == "__main__":
    asyncio.run(main())
