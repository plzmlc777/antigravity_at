#!/usr/bin/env python3
"""
Phase 2 validation — create a new paper session (noop strategy + BTCUSDT) so that
the at-live-signal skill runner can drive it via submit-signal API.

This session is isolated from RIVERUSDT (skill-test-001) and GCP production sessions.
After insertion, PM2 restart at-backend to let LiveManager restore it from DB.
"""
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR.parent / ".env")

from sqlalchemy import text, create_engine

db_url = (
    f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ.get('POSTGRES_SERVER', 'localhost')}:5432/{os.environ['POSTGRES_DB']}"
)
engine = create_engine(db_url)

SESSION_ID = "skill-phase2-001"
SYMBOL = "BTCUSDT"

config = json.dumps({
    "symbol": SYMBOL,
    "interval": "1m",
    "engine_version": "v2",
    "leverage": 5,
    "qty_mode": "percent",
    "base_quantity": 5,
    "position_side": "long",
    "rsi_period": 14,
    "trigger_level": 55,
    "trigger_direction": "below",
    "reset_level": 60,
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
    # Clear any prior executions for this ID
    conn.execute(
        text("DELETE FROM live_trade_executions WHERE session_id = :id"),
        {"id": SESSION_ID},
    )

    existing = conn.execute(
        text("SELECT id FROM live_bot_sessions WHERE id = :id"),
        {"id": SESSION_ID},
    ).fetchone()

    if existing:
        conn.execute(text("""
            UPDATE live_bot_sessions
            SET status = 'RUNNING', is_active = true,
                symbol = :symbol,
                strategy_name = 'noop',
                strategy_config = cast(:config as json),
                initial_capital = 500,
                is_paper = true,
                started_at = NOW(),
                original_symbol = :symbol,
                ai_symbol_mode = 'static',
                position_snapshot = NULL
            WHERE id = :id
        """), {"id": SESSION_ID, "symbol": SYMBOL, "config": config})
        print(f"Updated existing: {SESSION_ID} noop on {SYMBOL}")
    else:
        conn.execute(text("""
            INSERT INTO live_bot_sessions (
                id, account_id, symbol, strategy_name, strategy_config,
                initial_capital, is_paper, is_active, status, started_at,
                interval, original_symbol, original_symbol_name, ai_symbol_mode
            ) VALUES (
                :id, 8, :symbol, 'noop', cast(:config as json),
                500, true, true, 'RUNNING', NOW(),
                '1m', :symbol, 'BTC', 'static'
            )
        """), {"id": SESSION_ID, "symbol": SYMBOL, "config": config})
        print(f"Created: {SESSION_ID} noop on {SYMBOL}")

    conn.commit()

print()
print("Next: wsl -e bash -c 'pm2 restart at-backend' (to let LiveManager restore this session)")
print(f"Then: python3 .claude/skills/at-live-signal/scripts/run_strategy.py --session-id {SESSION_ID} --strategy rsi_martingale --api-url http://localhost:8001 --mode ws")
