import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import create_engine, text
from app.core.config import settings

# Construct DB URL for PostgreSQL
db_url = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}/{settings.POSTGRES_DB}"
print(f"Connecting to DB: {db_url.replace(settings.POSTGRES_PASSWORD, '***')}")

engine = create_engine(db_url)

with engine.connect() as conn:
    print("Checking OHLCV Data...")
    
    # Check distinct time_frames
    result = conn.execute(text("SELECT DISTINCT time_frame, count(*) FROM ohlcv GROUP BY time_frame"))
    print("\nDistinct Time Frames:")
    for row in result:
        print(row)
        
    # Check 30m data specifically for the reported period (2024-12-02)
    print("\nInspecting '30m' Data around 2024-12-02:")
    result = conn.execute(text("SELECT timestamp, open, close FROM ohlcv WHERE time_frame = '30m' AND timestamp >= '2024-12-02 00:00:00' AND timestamp <= '2024-12-05 00:00:00' ORDER BY timestamp ASC LIMIT 20"))
    rows = list(result)
    if not rows:
        print("No '30m' data found for this period.")
    else:
        for row in rows:
            print(row)
            
    # Check Gap Analysis
    if len(rows) > 1:
        print("\nGap Analysis (Time Difference):")
        from datetime import datetime
        last_dt = None
        for row in rows:
            # Timestamp format might be string in sqlite
            ts_str = row[0]
            try:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                
            if last_dt:
                diff = last_dt - dt
                print(f"{last_dt} - {dt} = {diff}")
            last_dt = dt
