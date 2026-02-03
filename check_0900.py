import sys
import os
from sqlalchemy import text
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def check_data():
    symbol = "233740"
    target_date = "2025-01-10" # Checking Last Friday
    print(f"--- Checking 1m Data for {symbol} on {target_date} ---")
    
    with engine.connect() as conn:
        # Check specifically for 09:00
        ts_0900 = f"{target_date} 09:00:00"
        exists = conn.execute(text("""
            SELECT 1 FROM ohlcv 
            WHERE symbol = :sym 
            AND time_frame = '1m'
            AND timestamp = :ts
        """), {"sym": symbol, "ts": ts_0900}).scalar()
        
        if exists:
            print(f"RESULT: 09:00:00 data EXISTS for {target_date}.")
        else:
            print(f"RESULT: 09:00:00 data DOES NOT EXIST for {target_date}.")
            
        # Get the first record of the day
        first = conn.execute(text("""
            SELECT timestamp FROM ohlcv 
            WHERE symbol = :sym 
            AND time_frame = '1m'
            AND date(timestamp) = :d
            ORDER BY timestamp ASC
            LIMIT 1
        """), {"sym": symbol, "d": target_date}).scalar()
        
        if first:
            print(f"First available data time: {first}")
        else:
            print("No data found for this date.")

if __name__ == "__main__":
    check_data()
