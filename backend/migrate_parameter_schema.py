#!/usr/bin/env python3
"""
Migration: Add parameter_schema column to strategy_info table and seed data.
Phase 1 of UI Refactoring.
"""

import os
import sys
import json

# Add the project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.db.session import SessionLocal

# Define parameter schemas for each strategy
PARAMETER_SCHEMAS = {
    "time_momentum": {
        "fields": [
            {
                "name": "start_time",
                "type": "time",
                "label": "Start Time",
                "default": "09:05",
                "description": "Time to start monitoring"
            },
            {
                "name": "delay_minutes",
                "type": "number",
                "label": "Delay (Minutes)",
                "default": 5,
                "min": 0,
                "max": 60,
                "description": "Wait time before entry"
            },
            {
                "name": "jump_percent",
                "type": "number",
                "label": "Jump Threshold (%)",
                "default": 3.0,
                "min": 0.1,
                "max": 20,
                "step": 0.1,
                "description": "Minimum price jump to trigger buy"
            },
            {
                "name": "trailing_start_percent",
                "type": "number",
                "label": "Trailing Start (%)",
                "default": 1.0,
                "min": 0.1,
                "max": 10,
                "step": 0.1,
                "description": "Profit threshold to activate trailing stop"
            },
            {
                "name": "trailing_stop_drop",
                "type": "number",
                "label": "Trailing Stop Drop (%)",
                "default": 0.5,
                "min": 0.1,
                "max": 5,
                "step": 0.1,
                "description": "Drop from peak to trigger sell"
            },
            {
                "name": "stop_time",
                "type": "time",
                "label": "Stop Time",
                "default": "15:20",
                "description": "Force exit time"
            }
        ]
    },
    "rsi_strategy": {
        "fields": [
            {
                "name": "rsi_period",
                "type": "number",
                "label": "RSI Period",
                "default": 14,
                "min": 2,
                "max": 50,
                "description": "Lookback period for RSI calculation"
            },
            {
                "name": "rsi_oversold",
                "type": "number",
                "label": "Oversold Level",
                "default": 30,
                "min": 10,
                "max": 40,
                "description": "RSI level to trigger buy"
            },
            {
                "name": "rsi_overbought",
                "type": "number",
                "label": "Overbought Level",
                "default": 70,
                "min": 60,
                "max": 90,
                "description": "RSI level to trigger sell"
            }
        ]
    },
    "golden_cross": {
        "fields": [
            {
                "name": "short_ma_period",
                "type": "number",
                "label": "Short MA Period",
                "default": 20,
                "min": 5,
                "max": 50,
                "description": "Fast moving average period"
            },
            {
                "name": "long_ma_period",
                "type": "number",
                "label": "Long MA Period",
                "default": 60,
                "min": 20,
                "max": 200,
                "description": "Slow moving average period"
            }
        ]
    },
    "volatility_breakout": {
        "fields": [
            {
                "name": "k_value",
                "type": "number",
                "label": "K Value",
                "default": 0.5,
                "min": 0.1,
                "max": 1.0,
                "step": 0.1,
                "description": "Range multiplier for breakout threshold"
            },
            {
                "name": "entry_time",
                "type": "time",
                "label": "Entry Time",
                "default": "09:00",
                "description": "Time to calculate target price"
            }
        ]
    }
}

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
        print("  ✓ Column added (or already exists)")
        
        # Step 2: Seed data for each strategy
        print("\nStep 2: Seeding parameter_schema data...")
        for strategy_id, schema in PARAMETER_SCHEMAS.items():
            result = db.execute(text("""
                UPDATE strategy_info 
                SET parameter_schema = :schema
                WHERE id = :id
            """), {"id": strategy_id, "schema": json.dumps(schema)})
            
            if result.rowcount > 0:
                print(f"  ✓ Updated {strategy_id}")
            else:
                print(f"  ⚠ Strategy '{strategy_id}' not found in DB")
        
        db.commit()
        
        # Step 3: Verify
        print("\nStep 3: Verification...")
        result = db.execute(text("""
            SELECT id, 
                   CASE WHEN parameter_schema IS NOT NULL THEN 'YES' ELSE 'NO' END as has_schema
            FROM strategy_info
        """))
        
        rows = result.fetchall()
        for row in rows:
            print(f"  - {row[0]}: parameter_schema = {row[1]}")
        
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
