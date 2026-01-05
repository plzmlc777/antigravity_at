import sys
import os

# Add parent dir to path to find app module
sys.path.append(os.getcwd())

from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from sqlalchemy import text

def delete_30m_data():
    db = SessionLocal()
    print("Connecting to Database...")
    
    # 1. Count '30m' data
    count = db.query(OHLCV).filter(OHLCV.time_frame == '30m').count()
    print(f"Found {count} records with time_frame='30m'")
    
    if count == 0:
        print("No '30m' data found. Nothing to delete.")
        return

    # 2. Delete
    print("Deleting '30m' data to force re-fetch...")
    try:
        # Use execute for bulk delete efficiency
        db.execute(text("DELETE FROM ohlcv WHERE time_frame = '30m'"))
        db.commit()
        print("Deletion Complete. The system will now auto-fetch fresh data on next backtest.")
    except Exception as e:
        db.rollback()
        print(f"Error during deletion: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    delete_30m_data()
