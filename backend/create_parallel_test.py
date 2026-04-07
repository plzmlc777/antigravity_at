#!/usr/bin/env python3
"""
병행 비교 테스트용 세션 2개 생성.

1. python-test-001: rsi_martingale (Python 엔진 전략)
2. skill-test-001: noop (스킬 러너 전략)

두 세션 모두 동일한 종목/파라미터로 생성하고,
기존 실행 기록을 삭제하여 RSI 초기값을 동기화합니다.
"""
import json
import os
import sys
from pathlib import Path

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

SYMBOL = "RIVERUSDT"

# 동일 파라미터 (쉬운 트리거를 위해 trigger=55, reset=60)
config = {
    "interval": "1m",
    "engine_version": "v2",
    "leverage": 15,
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
}
config_json = json.dumps(config)

sessions = [
    {
        "id": "python-test-001",
        "strategy_name": "rsi_martingale",
        "desc": "Python engine strategy",
    },
    {
        "id": "skill-test-001",
        "strategy_name": "noop",
        "desc": "Skill runner strategy",
    },
]

with engine.connect() as conn:
    for s in sessions:
        sid = s["id"]
        sname = s["strategy_name"]

        # 1. 기존 실행 기록 삭제 (RSI 초기값 동기화를 위해)
        del_result = conn.execute(
            text("DELETE FROM live_trade_executions WHERE session_id = :id"),
            {"id": sid}
        )
        print(f"[{sid}] Deleted {del_result.rowcount} old executions")

        # 2. 기존 시그널 삭제 (테이블이 존재하는 경우만)
        try:
            conn.execute(text("SAVEPOINT sig_check"))
            del_sig = conn.execute(
                text("DELETE FROM live_trade_signals WHERE session_id = :id"),
                {"id": sid}
            )
            print(f"[{sid}] Deleted {del_sig.rowcount} old signals")
        except Exception:
            conn.execute(text("ROLLBACK TO SAVEPOINT sig_check"))

        # 3. 세션 생성/업데이트
        result = conn.execute(
            text("SELECT id FROM live_bot_sessions WHERE id = :id"),
            {"id": sid}
        )
        if result.fetchone():
            conn.execute(text("""
                UPDATE live_bot_sessions
                SET status = 'STOPPED', is_active = false,
                    symbol = :symbol,
                    strategy_name = :sname,
                    strategy_config = cast(:config as json),
                    initial_capital = 500,
                    is_paper = true,
                    started_at = NOW(),
                    original_symbol = :symbol,
                    ai_symbol_mode = 'static'
                WHERE id = :id
            """), {"id": sid, "symbol": SYMBOL, "sname": sname, "config": config_json})
            print(f"[{sid}] Updated: {sname} on {SYMBOL}")
        else:
            conn.execute(text("""
                INSERT INTO live_bot_sessions (
                    id, account_id, symbol, strategy_name, strategy_config,
                    initial_capital, is_paper, is_active, status, started_at,
                    interval, original_symbol, original_symbol_name, ai_symbol_mode
                ) VALUES (
                    :id, 8, :symbol, :sname, cast(:config as json),
                    500, true, false, 'STOPPED', NOW(),
                    '1m', :symbol, 'RIVER', 'static'
                )
            """), {"id": sid, "symbol": SYMBOL, "sname": sname, "config": config_json})
            print(f"[{sid}] Created: {sname} on {SYMBOL}")

    conn.commit()

print()
print("=" * 60)
print("Both sessions ready (STOPPED state).")
print(f"Symbol: {SYMBOL}")
print(f"Params: trigger={config['trigger_level']}, reset={config['reset_level']}")
print()
print("Next steps:")
print("  1. Restart backend: pm2 restart at-backend")
print("  2. Start python-test-001 from UI or API")
print("  3. Start skill-runner: pm2 start skill-runner")
print("  4. Both will preload same candle history → same initial RSI")
