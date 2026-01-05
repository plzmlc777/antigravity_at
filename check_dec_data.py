import sys
import os
from sqlalchemy import text
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def check_dec_data():
    symbol = "233740"
    dates = ["2025-12-29", "2025-12-30", "2025-12-31"]
    
    print(f"--- Analyzing 1m Data for {symbol} (Dec 29-31) ---")
    
    with engine.connect() as conn:
        for d in dates:
            print(f"\n[Date: {d}]")
            # 1. Count
            count = conn.execute(text("""
                SELECT COUNT(*) FROM ohlcv 
                WHERE symbol = :sym 
                AND time_frame = '1m'
                AND date(timestamp) = :d
            """), {"sym": symbol, "d": d}).scalar()
            
            if count == 0:
                print("  -> NO DATA")
                continue
                
            print(f"  -> Count: {count}")
            
            # 2. Start/End Time
            times = conn.execute(text("""
                SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv 
                WHERE symbol = :sym 
                AND time_frame = '1m'
                AND date(timestamp) = :d
            """), {"sym": symbol, "d": d}).one()
            
            print(f"  -> Start: {times[0]}")
            print(f"  -> End  : {times[1]}")
            
            # 3. Check specific start slots
            start_check = conn.execute(text("""
                SELECT timestamp FROM ohlcv 
                WHERE symbol = :sym 
                AND time_frame = '1m'
                AND date(timestamp) = :d
                AND timestamp >= :start_ts
                ORDER BY timestamp ASC
                LIMIT 3
            """), {"sym": symbol, "d": d, "start_ts": f"{d} 09:00:00"}).fetchall()
            
            print(f"  -> First 3 Candles >= 09:00: {[r[0] for r in start_check]}")

if __name__ == "__main__":
    check_dec_data()
