from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from sqlalchemy import extract, and_

def check_1m_8am():
    db = SessionLocal()
    try:
        # Check source 1m data
        print("Checking 1m data for 08:xx timestamps...")
        records = db.query(OHLCV).filter(
            OHLCV.symbol == "005930",
            OHLCV.time_frame == "1m",
            extract('hour', OHLCV.timestamp) == 8
        ).limit(5).all()
        
        if records:
            print(f"FOUND {len(records)} records in 1m data with hour=8!")
            for r in records:
                print(f"  {r.timestamp} | Open: {r.open}")
        else:
            print("No 1m data found with hour=8. Source 1m seems clean.")
            
            # Check 8AM data in target interval (e.g. 15m/30m/60m)
            # Assuming Rank 2 was using 15m or similar? Let's check '15m'
            print("\nChecking 15m data for 08:00...")
            records_15 = db.query(OHLCV).filter(
                OHLCV.symbol == "005930",
                OHLCV.time_frame == "15m",
                extract('hour', OHLCV.timestamp) == 8
            ).limit(5).all()
            
            if records_15:
                 print(f"FOUND {len(records_15)} records in 15m data with hour=8!")
                 for r in records_15:
                    print(f"  {r.timestamp}")
            else:
                 print("No 15m data found with hour=8.")

    finally:
        db.close()

if __name__ == "__main__":
    check_1m_8am()
