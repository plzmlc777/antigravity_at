import sys
import os
from sqlalchemy import text
from datetime import datetime, date, timedelta

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def check_q3_data():
    symbol = "233740"
    start_date = "2025-07-01"
    end_date = "2025-10-01" # Exclusive
    
    print(f"--- Analyzing 1m Data Counts for {symbol} (2025-07-01 ~ 2025-09-30) ---")
    print(f"Target Standard Count range: 380-385")
    
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT date(timestamp) as d, COUNT(*) as c 
            FROM ohlcv 
            WHERE symbol = :sym 
            AND time_frame = '1m'
            AND timestamp >= :start
            AND timestamp < :end
            GROUP BY date(timestamp)
            ORDER BY d ASC
        """), {"sym": symbol, "start": start_date, "end": end_date}).fetchall()
        
        abnormal_days = []
        normal_days = 0
        total_days = len(rows)
        
        print(f"\n[Daily Analysis]")
        for r in rows:
            d = r[0]
            count = r[1]
            
            # Strict check? Users seems to expect 382.
            # But let's check start/end for everyone just to be sure if < 380 or > 385
            is_abnormal = (count < 380 or count > 385)
            
            if is_abnormal:
                times = conn.execute(text("""
                    SELECT MIN(timestamp), MAX(timestamp) 
                    FROM ohlcv 
                    WHERE symbol = :sym 
                    AND time_frame = '1m'
                    AND date(timestamp) = :d
                """), {"sym": symbol, "d": d}).one()
                
                start_time = times[0].strftime("%H:%M")
                end_time = times[1].strftime("%H:%M")
                print(f"Date: {d} | Count: {count} | Range: {start_time} ~ {end_time} (ABNORMAL)")
                abnormal_days.append((d, count, start_time, end_time))
            else:
                normal_days += 1
                
        print(f"\nSummary (2025-07-01 ~ 09-30):")
        print(f"Total Trading Days Found: {total_days}")
        print(f"Normal Days (380~385): {normal_days}")
        print(f"Abnormal Days: {len(abnormal_days)}")
        
        if not abnormal_days and total_days > 0:
            print("PERFECT CONSISTENCY.")

if __name__ == "__main__":
    check_q3_data()
