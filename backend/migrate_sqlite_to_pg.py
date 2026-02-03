import sys
import os
from sqlalchemy import create_engine, text
from app.db.base import Base
from app.models.account import ExchangeAccount
from app.models.condition import ConditionalOrder
from app.core.config import settings

from app.models.user import User

# Configurations
SQLITE_DB_PATH = "/home/admin-ubuntu/ai/antigravity/auto_trading/backend/sql_app.db.pre_pg_migration"
# Use settings for PG
PG_DB_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}/{settings.POSTGRES_DB}"

def migrate():
    print(f"Starting Migration: {SQLITE_DB_PATH} -> PostgreSQL")
    
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"Error: Source SQLite DB not found at {SQLITE_DB_PATH}")
        return

    sqlite_engine = create_engine(f"sqlite:///{SQLITE_DB_PATH}")
    pg_engine = create_engine(PG_DB_URL)
    
    # 1. Create Tables (Idempotent)
    print("Creating tables in PostgreSQL...")
    Base.metadata.create_all(pg_engine)

    # 1.1 Migrate Users (Required for Foreign Keys)
    print("\n--- Migrating Users ---")
    with sqlite_engine.connect() as sl_conn:
        try:
            users = sl_conn.execute(text("SELECT * FROM users")).fetchall()
        except:
            users = []
            print("users table not found in SQLite.")

    if users:
        with pg_engine.connect() as pg_conn:
            # Clear target table
            pg_conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
            pg_conn.commit()
            
            with pg_conn.begin():
                for u in users:
                    # SQLite: We select specific columns to be safe
                    # But u is from SELECT * which might have more cols if schema changed.
                    # We assume id=0, email=1, hashed_password=2 based on model order.
                    # If SQLite has more cols, we just ignore them if we can identify indices.
                    # Safest: SELECT id, email, hashed_password FROM users in the fetch query.
                    pass

    # Re-fetch with specific columns to ensure safety against schema drift
    print("Re-fetching Users with specific columns...")
    with sqlite_engine.connect() as sl_conn:
        try:
             # explicit select
             users_secure = sl_conn.execute(text("SELECT id, email, hashed_password FROM users")).fetchall()
        except Exception as e:
             print(f"Error fetching users: {e}")
             users_secure = []

    # Fallback to backup if users missing (Critical for FK)
    if not users_secure:
        print("Users missing in current DB. Attempting to restore from backup (sql_app.db.bak)...")
        BACKUP_DB_PATH = "/home/admin-ubuntu/ai/antigravity/auto_trading/backend/sql_app.db.bak"
        if os.path.exists(BACKUP_DB_PATH):
            bk_engine = create_engine(f"sqlite:///{BACKUP_DB_PATH}")
            with bk_engine.connect() as bk_conn:
                try:
                    users_secure = bk_conn.execute(text("SELECT id, email, hashed_password FROM users")).fetchall()
                    print(f"Recovered {len(users_secure)} users from backup.")
                except Exception as e:
                    print(f"Error fetching users from backup: {e}")

    if users_secure:
        with pg_engine.connect() as pg_conn:
             pg_conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
             pg_conn.commit()
             with pg_conn.begin():
                 for u in users_secure:
                     stmt = text("""
                        INSERT INTO users (id, email, hashed_password)
                        VALUES (:id, :email, :hp)
                     """)
                     pg_conn.execute(stmt, {
                        "id": u[0],
                        "email": u[1],
                        "hp": u[2]
                     })
        print(f"Migrated {len(users_secure)} users.")

    # 2. Migrate Exchange Accounts
    print("\n--- Migrating Exchange Accounts ---")
    with sqlite_engine.connect() as sl_conn:
        accounts = sl_conn.execute(text("SELECT * FROM exchange_accounts")).fetchall()
        
    if accounts:
        with pg_engine.connect() as pg_conn:
            # Clear target table
            pg_conn.execute(text("TRUNCATE TABLE exchange_accounts RESTART IDENTITY CASCADE"))
            pg_conn.commit()
            
            with pg_conn.begin():
                for acc in accounts:
                    # SQLite Row: (id, user_id, exchange_name, account_name, enc_acc, enc_sec, is_active, acct_no)
                    # We skip ID to let PG autoincrement, OR we preserve it? 
                    # Preserving ID is safer for relationships.
                    
                    stmt = text("""
                        INSERT INTO exchange_accounts (id, user_id, exchange_name, account_name, encrypted_access_key, encrypted_secret_key, is_active, account_number)
                        VALUES (:id, :uid, :ename, :aname, :eak, :esk, :act, :ano)
                    """)
                    pg_conn.execute(stmt, {
                        "id": acc[0],
                        "uid": acc[1], 
                        "ename": acc[2],
                        "aname": acc[3],
                        "eak": acc[4],
                        "esk": acc[5],
                        "act": bool(acc[6]), # Cast integer to boolean
                        "ano": acc[7] if len(acc) > 7 else None
                    })
        print(f"Migrated {len(accounts)} accounts.")

    # 3. Migrate Conditional Orders
    print("\n--- Migrating Conditional Orders ---")
    with sqlite_engine.connect() as sl_conn:
        try:
             orders = sl_conn.execute(text("SELECT * FROM conditional_orders")).fetchall()
        except:
             orders = []
             print("conditional_orders table not found in SQLite.")

    if orders:
        with pg_engine.connect() as pg_conn:
             pg_conn.execute(text("TRUNCATE TABLE conditional_orders RESTART IDENTITY CASCADE"))
             pg_conn.commit()
             
             with pg_conn.begin():
                 for ord in orders:
                     # SQLite row usually matches model definition order if created by SQLAlchemy.
                     # (id, symbol, condition_type, trigger_price, order_type, price_type, order_price, quantity, status, ref_order_id, created_at, updated_at, triggered_at, highest_price, trailing_percent, mode)
                     # We MUST use explicit naming if we are not 100% sure of tuple index.
                     # But raw fetchall is tuples. 
                     # Let's assume standard SQLAlchemy creation order.
                     
                     stmt = text("""
                        INSERT INTO conditional_orders (
                            id, symbol, condition_type, trigger_price, order_type, price_type, order_price, quantity, status, 
                            ref_order_id, created_at, updated_at, triggered_at, highest_price, trailing_percent, mode
                        ) VALUES (
                            :id, :sym, :ctype, :trig, :otype, :ptype, :oprice, :qty, :stat, 
                            :ref, :cat, :uat, :tat, :hp, :tp, :mode
                        )
                     """)
                     
                     # CAUTION: The index mapping depends on SQLite column order.
                     # Use 'PRAGMA table_info(conditional_orders)' to be sure? 
                     # For now, we map based on the model definition order seen in file.
                     pg_conn.execute(stmt, {
                        "id": ord[0],
                        "sym": ord[1],
                        "ctype": ord[2],
                        "trig": ord[3],
                        "otype": ord[4],
                        "ptype": ord[5],
                        "oprice": ord[6],
                        "qty": ord[7],
                        "stat": ord[8],
                        "ref": ord[9],
                        "cat": ord[10],
                        "uat": ord[11],
                        "tat": ord[12],
                        "hp": ord[13],
                        "tp": ord[14],
                        "mode": ord[15] if len(ord) > 15 else 'MOCK'
                     })
                     
        print(f"Migrated {len(orders)} orders.")
    
    print("\nMigration Completed.")

if __name__ == "__main__":
    migrate()
