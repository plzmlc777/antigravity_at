import sys
import os
from sqlalchemy import text
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.db.session import engine

def check_dates():
    symbol = "233740"
    print(f"--- Checking Dates for {symbol} in Jan 2025 ---")
    
    with engine.connect() as conn:
        # distinct days in Jan 2025
        rows = conn.execute(text("""
            SELECT DISTINCT date(timestamp) as d 
            FROM ohlcv 
            WHERE symbol = :sym 
            AND time_frame = '1m'
            AND timestamp >= '2026-01-01' 
            AND timestamp < '2026-02-01'
            ORDER BY d ASC
        """), {"sym": symbol}).fetchall()
        
        print(f"Days found in Jan 2025: {len(rows)}")
        for r in rows:
            print(f"- {r[0]}")
            
if __name__ == "__main__":
    check_dates()
