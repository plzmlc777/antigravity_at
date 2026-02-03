from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
import os

# Adjust path to find app module
sys.path.append('/home/admin-ubuntu/ai/antigravity/auto_trading/backend')

db_url = "sqlite:////home/admin-ubuntu/ai/antigravity/auto_trading/backend/sql_app.db"
engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

print(f"Connecting to DB: {db_url}")
try:
    result = session.execute(text("SELECT id, symbol, condition_type, status, created_at FROM conditional_orders"))
    orders = result.fetchall()
    print(f"Total Orders: {len(orders)}")
    for order in orders:
        print(order)
except Exception as e:
    print(f"Error: {e}")
finally:
    session.close()
