from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from sqlalchemy import func

def cleanup():
    db = SessionLocal()
    try:
        print("Connecting to database...")
        # 1. Report current status
        print("--- Current Data Distribution (Before) ---")
        counts = db.query(OHLCV.time_frame, func.count(OHLCV.id)).group_by(OHLCV.time_frame).all()
        
        total_non_1m = 0
        has_1m = False
        
        if not counts:
            print("Database is empty.")
            return
            
        for tf, count in counts:
            print(f"[{tf}]: {count} records")
            if tf == '1m':
                has_1m = True
            else:
                total_non_1m += count

        if not has_1m:
            print("\nWARNING: '1m' data not found! Proceeding will delete EVERYTHING (if any non-1m exists).")
            # For safety, let's still proceed as user explicitly asked to delete non-1m.
        
        if total_non_1m == 0:
            print("\nNo non-1m data found. Nothing to delete.")
            return

        print(f"\nFound {total_non_1m} records to delete (Timeframes other than '1m').")
        
        # 3. Execute Deletion
        print("Executing Deletion... (Safe Mode: Excluding '1m')")
        deleted_count = db.query(OHLCV).filter(OHLCV.time_frame != '1m').delete(synchronize_session=False)
        
        # 4. Commit
        db.commit()
        print(f"✅ Successfully deleted {deleted_count} records.")

        # 5. Verify
        print("\n--- Final Data Distribution (After) ---")
        final_counts = db.query(OHLCV.time_frame, func.count(OHLCV.id)).group_by(OHLCV.time_frame).all()
        for tf, count in final_counts:
            print(f"[{tf}]: {count} records")

    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    import os
    # Add project root to path for imports
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cleanup()
