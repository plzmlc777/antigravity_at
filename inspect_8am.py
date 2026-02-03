from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from sqlalchemy import extract

def check_8am():
    db = SessionLocal()
    try:
        # Find records where hour is 8
        records = db.query(OHLCV.symbol, OHLCV.timestamp).filter(
            extract('hour', OHLCV.timestamp) == 8
        ).limit(10).all()
        
        if records:
            print("Found 8 AM records:")
            for r in records:
                print(f"Symbol: {r.symbol}, Time: {r.timestamp}")
                
            # Count per symbol
            from sqlalchemy import func
            counts = db.query(OHLCV.symbol, func.count(OHLCV.timestamp)).filter(
                extract('hour', OHLCV.timestamp) == 8
            ).group_by(OHLCV.symbol).all()
            
            print("\nSummary by Symbol (8 AM counts):")
            for c in counts:
                print(f"{c[0]}: {c[1]}")
        else:
            print("No records found with 8 AM timestamp.")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_8am()
