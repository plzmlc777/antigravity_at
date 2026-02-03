import sys
import os
from sqlalchemy import text

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

# Load env vars
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../backend/.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

from app.db.session import SessionLocal

def fix_sequences():
    db = SessionLocal()
    try:
        print("Fixing usage of sequences...")
        # Check tables: users, trading_bots, exchange_accounts, conditional_orders
        tables = ['users', 'trading_bots', 'exchange_accounts', 'conditional_orders']
        
        for table in tables:
            try:
                # Find sequence name (standard convention)
                seq_name = f"{table}_id_seq"
                
                # Check max id
                result = db.execute(text(f"SELECT MAX(id) FROM {table}"))
                max_id = result.scalar() or 0
                print(f"Table {table}: Max ID is {max_id}")
                
                # Reset sequence
                new_val = max_id + 1
                db.execute(text(f"ALTER SEQUENCE {seq_name} RESTART WITH {new_val}"))
                db.commit()
                print(f" -> Reset {seq_name} to {new_val}")
                
            except Exception as e:
                print(f"Failed to reset {table}: {e}")
                db.rollback()

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fix_sequences()
