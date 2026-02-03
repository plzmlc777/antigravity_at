import os
import sys
from sqlalchemy import create_engine, text
import datetime

DB_USER = "antigravity_user"
DB_PASS = "antigravity_password"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "antigravity_db"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print(f"Connected to {DB_NAME}. Cleanup 1d started at {datetime.datetime.now()}.\n")
        
        # 1. Count
        query_count = text("SELECT COUNT(*) FROM ohlcv WHERE time_frame = '1d'")
        count = conn.execute(query_count).scalar()
        print(f"Found {count} records with time_frame = '1d'.")
        
        if count > 0:
            # 2. Delete
            query_delete = text("DELETE FROM ohlcv WHERE time_frame = '1d'")
            result = conn.execute(query_delete)
            conn.commit()
            print(f"Deleted {result.rowcount} records.")
        else:
            print("No 1d records found.")

except Exception as e:
    print(f"Error during cleanup: {e}")
