import sys
import os
from sqlalchemy import text
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def check_jan_2025():
    symbol = "233740"
    start_date = "2025-01-01"
    end_date = "2025-02-01"
    
    print(f"--- Analyzing 1m Data Counts for {symbol} (Jan 2025) ---")
    
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
        
        print(f"\n[Daily Analysis - Jan 2025]")
        for r in rows:
            d = r[0]
            count = r[1]
            status = "OK" if (count >= 380 and count <= 385) else "ABNORMAL"
            
            if status == "ABNORMAL":
                times = conn.execute(text("""
                    SELECT MIN(timestamp), MAX(timestamp) 
                    FROM ohlcv 
                    WHERE symbol = :sym 
                    AND time_frame = '1m'
                    AND date(timestamp) = :d
                """), {"sym": symbol, "d": d}).one()
                
                print(f"Date: {d} | Count: {count} | Range: {times[0].time()} ~ {times[1].time()} (ABNORMAL)")
                abnormal_days.append((d, count))
            else:
                normal_days += 1
                
        print(f"\nSummary (Jan 2025):")
        print(f"Total Trading Days Found: {total_days}")
        print(f"Normal Days: {normal_days}")
        print(f"Abnormal Days: {len(abnormal_days)}")

if __name__ == "__main__":
    check_jan_2025()
