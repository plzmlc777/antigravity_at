import sys
import os
from sqlalchemy import text
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def check_today():
    symbol = "233740"
    target_date = "2026-01-05" 
    print(f"--- Checking 1m Data for {symbol} on {target_date} ---")
    
    with engine.connect() as conn:
        first = conn.execute(text("""
            SELECT timestamp FROM ohlcv 
            WHERE symbol = :sym 
            AND time_frame = '1m'
            AND date(timestamp) = :d
            ORDER BY timestamp ASC
            LIMIT 3
        """), {"sym": symbol, "d": target_date}).fetchall()
        
        if first:
            print(f"First candles for {target_date}:")
            for r in first:
                print(f"- {r[0]}")
        else:
            print("No data found for this date.")

if __name__ == "__main__":
    check_today()
