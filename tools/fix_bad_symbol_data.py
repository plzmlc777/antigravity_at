import sys
import os
import asyncio
from sqlalchemy import create_engine, text

sys.path.append(os.getcwd())
# Direct DB access to delete
from backend.app.db.session import engine

def delete_data():
    symbol = "233740"
    print(f"Deleting data for {symbol}...")
    
    with engine.connect() as conn:
        # Delete ALL data for this symbol (all timeframes) from 'ohlcv' table
        res = conn.execute(text("DELETE FROM ohlcv WHERE symbol = :sym"), {"sym": symbol})
        print(f"Deleted {res.rowcount} rows from ohlcv (all intervals).")
        
        conn.commit()
    
    print("Cleanup Complete. Next Backtest will trigger fresh fetch.")

if __name__ == "__main__":
    delete_data()
