import asyncio
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal

def check_ghost_candles():
    db = SessionLocal()
    try:
        # Assuming symbol is active one. Let's list all symbols with data > 16:00 today.
        today = datetime.now().strftime("%Y-%m-%d")
        cutoff = f"{today} 16:00:00"
        
        sql = text(f"SELECT symbol, time_frame, timestamp, close, volume FROM ohlcv WHERE timestamp > '{cutoff}' ORDER BY timestamp DESC")
        result = db.execute(sql)
        rows = result.fetchall()
        
        print(f"--- Ghost Candles after {cutoff} ---")
        for row in rows:
            print(row)
            
        if not rows:
            print("No ghost candles found.")
            
    except Exception as e:
        print(e)
    finally:
        db.close()

if __name__ == "__main__":
    check_ghost_candles()
