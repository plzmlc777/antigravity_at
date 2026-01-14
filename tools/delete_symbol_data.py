from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from backend.app.core.config import settings

def delete_symbol_data(symbol: str):
    print(f"DEBUG: Connecting to DB: {settings.POSTGRES_DB} at {settings.POSTGRES_SERVER}")
    db = SessionLocal()
    try:
        count = db.query(OHLCV).filter(OHLCV.symbol == symbol).count()
        print(f"Found {count} records for {symbol}.")
        
        if count > 0:
            deleted = db.query(OHLCV).filter(OHLCV.symbol == symbol).delete()
            db.commit()
            print(f"Deleted {deleted} records for {symbol}.")
        else:
            print(f"No records found for {symbol}.")
            
            # DEBUG: Print all symbols
            all_syms = db.query(OHLCV.symbol).distinct().all()
            print(f"Available symbols in DB: {[s[0] for s in all_syms]}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    delete_symbol_data("000660")
