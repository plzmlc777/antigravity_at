import os
import sys
from datetime import datetime
from sqlalchemy import text

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.app.db.session import SessionLocal

def check_today_data():
    db = SessionLocal()
    try:
        # Check for data on 2026-01-15 (Today provided by system prompt)
        # Verify timezone handling. DATE(timestamp) might be UTC.
        # 09:00 KST = 00:00 UTC.
        
        sql = text("SELECT count(*) FROM ohlcv WHERE timestamp >= '2026-01-15 00:00:00' AND timestamp < '2026-01-16 00:00:00'")
        result = db.execute(sql)
        count = result.scalar()
        print(f"Candles for 2026-01-15 (UTC 00:00+): {count}")
        
        # Check specific sample
        sql_sample = text("SELECT timestamp, open, close FROM ohlcv WHERE timestamp >= '2026-01-15 00:00:00' LIMIT 5")
        rows = db.execute(sql_sample).fetchall()
        for r in rows:
            print(r)

    except Exception as e:
        print(e)
    finally:
        db.close()

if __name__ == "__main__":
    check_today_data()
