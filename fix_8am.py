from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from sqlalchemy import extract

def fix_8am():
    db = SessionLocal()
    try:
        # Delete records where hour is 8
        stmt = db.query(OHLCV).filter(
            extract('hour', OHLCV.timestamp) == 8
        )
        count = stmt.delete(synchronize_session=False)
        db.commit()
        
        print(f"Deleted {count} records with 8 AM timestamp.")
            
    finally:
        db.close()

if __name__ == "__main__":
    fix_8am()
