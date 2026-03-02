"""
Migration: Add original_symbol columns to live_bot_sessions.
Adds: original_symbol, original_symbol_name
Populates from profile rank_configs when available, falls back to current symbol.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions'
        """))
        existing = {row[0] for row in result}

        if 'original_symbol' not in existing:
            conn.execute(text(
                "ALTER TABLE live_bot_sessions ADD COLUMN original_symbol VARCHAR"
            ))
            print("Added column: original_symbol")
        else:
            print("Skipped: original_symbol (already exists)")

        if 'original_symbol_name' not in existing:
            conn.execute(text(
                "ALTER TABLE live_bot_sessions ADD COLUMN original_symbol_name VARCHAR"
            ))
            print("Added column: original_symbol_name")
        else:
            print("Skipped: original_symbol_name (already exists)")

        # Populate original_symbol from profile rank_configs when profile_id exists.
        # Match using strategy_config->>'rank' field against rank_configs[].rank.
        # This is the correct approach: each session stores its rank index in strategy_config.
        updated = conn.execute(text("""
            WITH profile_expanded AS (
                SELECT sp.id AS profile_id,
                       (elem->>'rank')::int AS rank_idx,
                       elem->>'symbol' AS profile_symbol,
                       elem->>'symbol_name' AS profile_symbol_name
                FROM strategy_profiles sp,
                     jsonb_array_elements(sp.rank_configs) AS elem
            )
            UPDATE live_bot_sessions lbs
            SET original_symbol = pe.profile_symbol,
                original_symbol_name = COALESCE(pe.profile_symbol_name, lbs.strategy_config->>'symbol_name')
            FROM profile_expanded pe
            WHERE lbs.profile_id = pe.profile_id
              AND (lbs.strategy_config->>'rank')::int = pe.rank_idx
              AND lbs.original_symbol IS NULL
              AND lbs.profile_id IS NOT NULL
        """))
        print(f"Populated from profile: {updated.rowcount} rows")

        # Fallback: sessions without profile_id, set original_symbol = current symbol
        fallback = conn.execute(text("""
            UPDATE live_bot_sessions
            SET original_symbol = symbol,
                original_symbol_name = COALESCE(
                    original_symbol_name,
                    strategy_config->>'symbol_name'
                )
            WHERE original_symbol IS NULL
        """))
        print(f"Populated from current symbol (fallback): {fallback.rowcount} rows")

        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    migrate()
