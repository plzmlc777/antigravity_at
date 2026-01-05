import sys
import os
from sqlalchemy import text
from datetime import datetime, timedelta

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def check_30_days():
    symbol = "233740"
    # Current system date is 2026-01-05.
    end_date = datetime(2026, 1, 6) # Inclusive of today
    start_date = end_date - timedelta(days=45) # Go back 45 days to be safe/sure covering 30 trading days
    
    print(f"--- Analyzing 1m Data Counts for {symbol} (Since {start_date.date()}) ---")
    print(f"Target Standard Count: 382")
    
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT date(timestamp) as d, COUNT(*) as c 
            FROM ohlcv 
            WHERE symbol = :sym 
            AND time_frame = '1m'
            AND timestamp >= :start_ts
            GROUP BY date(timestamp)
            ORDER BY d ASC
        """), {"sym": symbol, "start_ts": start_date}).fetchall()
        
        abnormal_days = []
        normal_days = 0
        
        print(f"\n[Daily Counts]")
        for r in rows:
            d = r[0]
            count = r[1]
            status = "OK" if count == 382 else "ABNORMAL"
            
            if count != 382:
                # Get start/end time for abnormal days
                times = conn.execute(text("""
                    SELECT MIN(timestamp), MAX(timestamp) 
                    FROM ohlcv 
                    WHERE symbol = :sym 
                    AND time_frame = '1m'
                    AND date(timestamp) = :d
                """), {"sym": symbol, "d": d}).one()
                
                print(f"Date: {d} | Count: {count} | Range: {times[0].time()} ~ {times[1].time()} ({status})")
                abnormal_days.append((d, count))
            else:
                normal_days += 1
                
        print(f"\nSummary:")
        print(f"Total Days Found: {len(rows)}")
        print(f"Normal Days (382): {normal_days}")
        print(f"Abnormal Days: {len(abnormal_days)}")

if __name__ == "__main__":
    check_30_days()
