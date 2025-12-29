from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from sqlalchemy import func

def check_data(symbol, interval):
    db = SessionLocal()
    try:
        count = db.query(OHLCV).filter(OHLCV.symbol == symbol, OHLCV.time_frame == interval).count()
        print(f"[{symbol} - {interval}] Total Records: {count}")
        
        if count > 0:
            min_ts = db.query(func.min(OHLCV.timestamp)).filter(OHLCV.symbol == symbol, OHLCV.time_frame == interval).scalar()
            max_ts = db.query(func.max(OHLCV.timestamp)).filter(OHLCV.symbol == symbol, OHLCV.time_frame == interval).scalar()
            print(f"  Range: {min_ts} ~ {max_ts}")
            
            # Show last 5
            last_5 = db.query(OHLCV).filter(OHLCV.symbol == symbol, OHLCV.time_frame == interval).order_by(OHLCV.timestamp.desc()).limit(5).all()
            print("  Last 5 records:")
            for c in last_5:
                print(f"    {c.timestamp} | {c.close}")
        else:
            print("  No records found.")
            
    finally:
        db.close()

if __name__ == "__main__":
    print("Checking 'SEC' (Symbol used in internal logic)...")
    check_data("SEC", "1m")
    
    print("\nChecking '005930' (Real Code)...")
    check_data("005930", "1m")
