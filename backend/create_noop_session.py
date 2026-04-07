#!/usr/bin/env python3
"""Create a noop session for skill strategy testing."""
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import text, create_engine

db_url = (
    f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ.get('POSTGRES_SERVER', 'localhost')}:5432/{os.environ['POSTGRES_DB']}"
)
engine = create_engine(db_url)

SESSION_ID = "skill-test-001"

# Relaxed RSI martingale params for easy trade triggering
config = json.dumps({
    "interval": "1m",
    "engine_version": "v2",
    "leverage": 15,
    "qty_mode": "percent",
    "base_quantity": 5,
    "position_side": "long",
    "rsi_period": 14,
    "trigger_level": 50,
    "trigger_direction": "below",
    "reset_level": 70,
    "reset_direction": "above",
    "trailing_start_percent": 0.1,
    "trailing_stop_percent": 0,
    "additional_buy_step": 0.3,
    "additional_buy_mode": "step",
    "max_buy_count": 4,
    "lot_size_multiplier": 2,
    "use_martingale": "on",
    "max_loss_percent": 3,
    "cycle_max_hours": 0,
    "betting_strategy": "compound",
    "last_level_allin": "off",
    "require_lower_price": "off",
    "liquidation_floor_pct": 3,
    "safety_margin_percent": 1,
    "additional_buy_step_ref": "last_entry",
})

with engine.connect() as conn:
    # Check if session already exists
    result = conn.execute(
        text("SELECT id FROM live_bot_sessions WHERE id = :id"),
        {"id": SESSION_ID}
    )
    if result.fetchone():
        # Update existing
        conn.execute(text("""
            UPDATE live_bot_sessions
            SET status = 'RUNNING', is_active = true,
                strategy_name = 'noop',
                strategy_config = cast(:config as json),
                started_at = NOW()
            WHERE id = :id
        """), {"id": SESSION_ID, "config": config})
        print(f"Updated existing session: {SESSION_ID}")
    else:
        # Insert new
        conn.execute(text("""
            INSERT INTO live_bot_sessions (
                id, account_id, symbol, strategy_name, strategy_config,
                initial_capital, is_paper, is_active, status, started_at,
                interval, original_symbol, original_symbol_name
            ) VALUES (
                :id, 8, 'RIVERUSDT', 'noop', cast(:config as json),
                500, true, true, 'RUNNING', NOW(),
                '1m', 'RIVERUSDT', 'RIVER'
            )
        """), {"id": SESSION_ID, "config": config})
        print(f"Created new session: {SESSION_ID}")

    conn.commit()

print(f"Session ready: {SESSION_ID}")
print(f"Strategy: noop (skill-only)")
print(f"Symbol: RIVERUSDT")
print(f"Params: trigger_level=50, trailing_start=0.1%, add_step=0.3%")
