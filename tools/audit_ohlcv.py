import os
import sys
from sqlalchemy import create_engine, text
import datetime

# Database credentials
DB_USER = "antigravity_user"
DB_PASS = "antigravity_password"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "antigravity_db"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print(f"Connected to {DB_NAME}. Audit started at {datetime.datetime.now()}.\n")
        
        # Query for non-1m data
        query = text("""
            SELECT symbol, time_frame, COUNT(*), MIN(timestamp), MAX(timestamp) 
            FROM ohlcv 
            WHERE time_frame != '1m' 
            GROUP BY symbol, time_frame 
            ORDER BY symbol, time_frame
        """)
        
        results = conn.execute(query).fetchall()
        
        if not results:
            print("No non-1m data found. The database is compliant.")
        else:
            print(f"{'SYMBOL':<10} | {'TIMEFRAME':<10} | {'COUNT':<8} | {'START':<20} | {'END':<20}")
            print("-" * 80)
            for row in results:
                sym, tf, cnt, start, end = row
                print(f"{sym:<10} | {tf:<10} | {cnt:<8} | {str(start):<20} | {str(end):<20}")

except Exception as e:
    print(f"Error during audit: {e}")
