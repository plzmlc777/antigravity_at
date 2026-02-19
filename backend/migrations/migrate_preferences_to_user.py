"""
Migration: Move user preferences and AI keys from exchange_accounts to users table.

These settings belong to the user, not to a specific brokerage account:
- last_selected_strategy_id, last_selected_profile_id (UI state)
- last_symbol, saved_symbols (watchlist)
- encrypted_ai_api_key, encrypted_google_api_key, ai_model (AI config)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        # 1. Check existing columns in users table
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users'
        """))
        existing = {row[0] for row in result}

        # 2. Add new columns to users table
        new_columns = {
            'last_selected_strategy_id': 'VARCHAR',
            'last_selected_profile_id': 'VARCHAR',
            'last_symbol': "VARCHAR DEFAULT '005930'",
            'saved_symbols': 'JSONB',
            'encrypted_ai_api_key': 'VARCHAR',
            'encrypted_google_api_key': 'VARCHAR',
            'ai_model': "VARCHAR DEFAULT 'claude-sonnet-4-20250514'",
        }

        for col_name, col_type in new_columns.items():
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                print(f"  [ADD] users.{col_name}")
            else:
                print(f"  [SKIP] users.{col_name} already exists")

        # 3. Migrate data from exchange_accounts (is_active=true) to users
        # Only copy if users columns are still NULL (don't overwrite)
        migrated = conn.execute(text("""
            UPDATE users u
            SET
                last_selected_strategy_id = COALESCE(u.last_selected_strategy_id, ea.last_selected_strategy_id),
                last_selected_profile_id = COALESCE(u.last_selected_profile_id, ea.last_selected_profile_id),
                last_symbol = COALESCE(u.last_symbol, ea.last_symbol),
                saved_symbols = COALESCE(u.saved_symbols, ea.saved_symbols::jsonb),
                encrypted_ai_api_key = COALESCE(u.encrypted_ai_api_key, ea.encrypted_ai_api_key),
                encrypted_google_api_key = COALESCE(u.encrypted_google_api_key, ea.encrypted_google_api_key),
                ai_model = COALESCE(u.ai_model, ea.ai_model)
            FROM exchange_accounts ea
            WHERE ea.user_id = u.id
              AND ea.is_active = true
        """))
        print(f"  [MIGRATE] Copied data from active accounts to users ({migrated.rowcount} rows)")

        conn.commit()
        print("  [DONE] Migration complete")


if __name__ == "__main__":
    print("=== Migration: Move preferences to users table ===")
    migrate()
