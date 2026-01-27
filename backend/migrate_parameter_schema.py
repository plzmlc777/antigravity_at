#!/usr/bin/env python3
"""
Migration: Sync parameter_schema from Strategy classes (Single Source of Truth) to DB.

Reads PARAMETER_SCHEMA from each registered strategy class via StrategyRegistry
and writes it to the strategy_info.parameter_schema JSONB column.

Usage:
    python migrate_parameter_schema.py
"""

import os
import sys
import json

# Add the project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.core.strategy_registry import StrategyRegistry


def run_migration():
    db = SessionLocal()

    try:
        # Step 1: Add column if not exists
        print("Step 1: Adding parameter_schema column...")
        db.execute(text("""
            ALTER TABLE strategy_info
            ADD COLUMN IF NOT EXISTS parameter_schema JSONB;
        """))
        db.commit()
        print("  Done")

        # Step 2: Read schemas from strategy classes (Single Source of Truth)
        print("\nStep 2: Reading PARAMETER_SCHEMA from strategy classes...")
        schemas = StrategyRegistry.get_all_parameter_schemas()
        print(f"  Found {len(schemas)} strategies with schemas: {list(schemas.keys())}")

        # Step 3: Write to DB
        print("\nStep 3: Writing parameter_schema to DB...")
        for strategy_id, schema in schemas.items():
            result = db.execute(text("""
                UPDATE strategy_info
                SET parameter_schema = :schema
                WHERE id = :id
            """), {"id": strategy_id, "schema": json.dumps(schema)})

            if result.rowcount > 0:
                field_count = len(schema.get("fields", []))
                print(f"  Updated {strategy_id} ({field_count} fields)")
            else:
                print(f"  Strategy '{strategy_id}' not found in DB (skipped)")

        db.commit()

        # Step 4: Verify
        print("\nStep 4: Verification...")
        result = db.execute(text("""
            SELECT id,
                   CASE WHEN parameter_schema IS NOT NULL THEN 'YES' ELSE 'NO' END as has_schema,
                   COALESCE(jsonb_array_length(parameter_schema->'fields'), 0) as field_count
            FROM strategy_info
            ORDER BY id
        """))

        rows = result.fetchall()
        for row in rows:
            print(f"  {row[0]}: schema={row[1]}, fields={row[2]}")

        print("\nMigration completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
