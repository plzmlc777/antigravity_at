import sys
import os
from sqlalchemy import text
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def verify_integrity():
    symbol = "233740"
    print(f"--- Verifying 1m Data Integrity for {symbol} ---")
    
    with engine.connect() as conn:
        # 1. Total Count
        total = conn.execute(text("SELECT COUNT(*) FROM ohlcv WHERE symbol = :sym AND time_frame = '1m'"), {"sym": symbol}).scalar()
        print(f"Total 1m Records: {total}")
        
        # 2. Distinct Days
        # PostgreSQL specific date truncation
        days = conn.execute(text("""
            SELECT DISTINCT date(timestamp) as d 
            FROM ohlcv 
            WHERE symbol = :sym AND time_frame = '1m'
            ORDER BY d DESC
        """), {"sym": symbol}).fetchall()
        
        print(f"Total Distinct Days: {len(days)}")
        
        # 3. Check for 09:00:00 per day
        # We want to find days that DO NOT have 09:00:00
        
        print("\n[Checking 09:00:00 presence]")
        bad_days = []
        good_days = 0
        
        for row in days:
            d = row[0]
            # Check 9:00 for this day
            # Construct start of day timestamp
            ts_start = f"{d} 09:00:00"
            ts_end = f"{d} 09:01:00" # Just check 09:00
            
            exists = conn.execute(text("""
                SELECT 1 FROM ohlcv 
                WHERE symbol = :sym AND time_frame = '1m'
                AND timestamp = :ts
            """), {"sym": symbol, "ts": ts_start}).scalar()
            
            if exists:
                good_days += 1
            else:
                # Double check if it's a holiday or late start? 
                # But we just want to know if it's missing.
                # Let's verify what IS the start time for this bad day.
                first_candle = conn.execute(text("""
                    SELECT timestamp FROM ohlcv 
                    WHERE symbol = :sym AND time_frame = '1m'
                    AND date(timestamp) = :d
                    ORDER BY timestamp ASC 
                    LIMIT 1
                """), {"sym": symbol, "d": d}).one()
                
                bad_days.append((d, first_candle[0]))

        print(f"Days WITH 09:00: {good_days}")
        print(f"Days WITHOUT 09:00: {len(bad_days)}")
        
        if bad_days:
            print("\n[Days Missing 09:00 (Top 10)]")
            for bd in bad_days[:10]:
                print(f"Date: {bd[0]}, First Candle: {bd[1]}")
                
        # 4. Deep check for 2025-01-14
        print(f"\n[Deep Check: 2025-01-14]")
        target_day = "2025-01-14"
        day_recs = conn.execute(text("""
            SELECT timestamp FROM ohlcv 
            WHERE symbol = :sym AND time_frame = '1m'
            AND date(timestamp) = :d 
            ORDER BY timestamp ASC
        """), {"sym": symbol, "d": target_day}).fetchall()
        
        if not day_recs:
            print("No records found for 2025-01-14")
        else:
            print(f"Records found: {len(day_recs)}")
            print(f"First 3: {[r[0] for r in day_recs[:3]]}")
            
if __name__ == "__main__":
    verify_integrity()
