from sqlalchemy import create_engine, text
import sys

# Paths
current_db_url = "sqlite:////home/admin-ubuntu/ai/antigravity/auto_trading/backend/sql_app.db"
backup_db_url = "sqlite:////home/admin-ubuntu/ai/antigravity/auto_trading/backend/sql_app.db.bak"

def restore_accounts():
    print("Starting Account Restoration...")
    
    # Read from Backup
    backup_engine = create_engine(backup_db_url)
    with backup_engine.connect() as conn:
        print("Reading from Backup...")
        # Get columns explicitly to reconstruct insert
        result = conn.execute(text("SELECT user_id, exchange_name, account_name, encrypted_access_key, encrypted_secret_key, is_active, account_number FROM exchange_accounts"))
        accounts = result.fetchall()
        print(f"Found {len(accounts)} accounts in backup.")

    if not accounts:
        print("No accounts to restore.")
        return

    # Write to Current
    current_engine = create_engine(current_db_url)
    with current_engine.connect() as conn:
        print("Writing to Current DB...")
        for acc in accounts:
            # Prepare query
            # Assuming id is auto-increment, we skip it or let it regenerate
            sql = text("""
                INSERT INTO exchange_accounts (user_id, exchange_name, account_name, encrypted_access_key, encrypted_secret_key, is_active, account_number)
                VALUES (:user_id, :exchange_name, :account_name, :encrypted_access_key, :encrypted_secret_key, :is_active, :account_number)
            """)
            
            try:
                conn.execute(sql, {
                    "user_id": acc[0],
                    "exchange_name": acc[1],
                    "account_name": acc[2],
                    "encrypted_access_key": acc[3],
                    "encrypted_secret_key": acc[4],
                    "is_active": acc[5],
                    "account_number": acc[6]
                })
                print(f"Restored account: {acc[2]}")
            except Exception as e:
                print(f"Failed to insert {acc[2]}: {e}")
                
        conn.commit()
    print("Restoration Completed.")

if __name__ == "__main__":
    restore_accounts()
