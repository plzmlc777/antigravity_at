from sqlalchemy import create_engine, text, inspect
import sys

# Paths
current_db_url = "sqlite:////home/admin-ubuntu/ai/antigravity/auto_trading/backend/sql_app.db"
backup_db_url = "sqlite:////home/admin-ubuntu/ai/antigravity/auto_trading/backend/sql_app.db.bak"

def check_db(name, url):
    print(f"--- Checking {name} ---")
    try:
        engine = create_engine(url)
        inspector = inspect(engine)
        if not inspector.has_table("exchange_accounts"): # Check table name! usually plural
             # Let's check tablenames
             print(f"Tables: {inspector.get_table_names()}")
             if 'exchange_accounts' not in inspector.get_table_names():
                 print("Table 'exchange_accounts' not found.")
                 return

        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM exchange_accounts"))
            rows = result.fetchall()
            print(f"Count: {len(rows)}")
            for row in rows:
                print(row)
    except Exception as e:
        print(f"Error: {e}")

check_db("Current DB", current_db_url)
check_db("Backup DB", backup_db_url)
