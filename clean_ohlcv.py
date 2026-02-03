
from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV

def clean_db():
    db = SessionLocal()
    try:
        print("Deleting OHLCV data for 005930...")
        deleted = db.query(OHLCV).filter(OHLCV.symbol == '005930').delete()
        print(f"Deleted {deleted} records.")
        
        print("Deleting OHLCV data for 000660...")
        deleted_2 = db.query(OHLCV).filter(OHLCV.symbol == '000660').delete()
        print(f"Deleted {deleted_2} records.")
        
        db.commit()
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clean_db()
