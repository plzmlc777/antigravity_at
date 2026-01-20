import asyncio
import os
import sys
import random
from datetime import datetime, timedelta

# Add parent directory to sys.path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.db.session import SessionLocal
from backend.app.models.live_trading import LiveBotSession, LiveTradeExecution, ExecutionStatus, LiveRealizedTrade
from backend.app.core.live_context import LiveContext

def seed_session(db, symbol, name):
    print(f"--- Seeding Dummy Trades for {name} ({symbol}) ---")
    
    # Create a unique session per run
    session_id = f"test-{symbol}-{datetime.now().strftime('%H%M%S')}"
    print(f"Creating new dummy session: {session_id}")
    
    session = LiveBotSession(
        id=session_id,
        symbol=symbol,
        strategy_name="seed_strategy",
        strategy_config={"symbol": symbol},
        initial_capital=10000000,
        current_capital=10000000,
        status="RUNNING",
        started_at=datetime.now() - timedelta(hours=5),
        interval="1m",
        orders_enabled=True
    )
    db.add(session)
    db.commit()
        
    # Generate 10 Trades
    base_price = 70000 if symbol == "005930" else 150000
    current_time = datetime.now() - timedelta(hours=4)
    
    total_pnl = 0
    wins = 0
    
    for i in range(10):
        # Time progression
        entry_time = current_time + timedelta(minutes=i*30)
        exit_time = entry_time + timedelta(minutes=15)
        
        # Random Price Action
        entry_price = base_price + random.uniform(-1000, 1000)
        is_win = random.choice([True, True, False]) # 66% win rate bias
        pnl_percent = random.uniform(0.005, 0.02) if is_win else random.uniform(-0.01, -0.005)
        exit_price = entry_price * (1 + pnl_percent)
        
        quantity = 10
        pnl = (exit_price - entry_price) * quantity
        
        total_pnl += pnl
        if pnl > 0: wins += 1
        
        # Create Executions
        buy_exec = LiveTradeExecution(
            session_id=session_id,
            symbol=symbol,
            signal_type="BUY",
            signal_timestamp=entry_time,
            order_filled_at=entry_time,
            theoretical_price=entry_price,
            executed_price=entry_price,
            requested_quantity=quantity,
            filled_quantity=quantity,
            remaining_quantity=0,
            status=ExecutionStatus.FILLED
        )
        db.add(buy_exec)
        db.commit()
        
        sell_exec = LiveTradeExecution(
            session_id=session_id,
            symbol=symbol,
            signal_type="SELL",
            signal_timestamp=exit_time,
            order_filled_at=exit_time,
            theoretical_price=exit_price,
            executed_price=exit_price,
            requested_quantity=quantity,
            filled_quantity=quantity,
            status=ExecutionStatus.FILLED
        )
        db.add(sell_exec)
        db.commit()
        
        # Create Realized Trade
        realized = LiveRealizedTrade(
            session_id=session_id,
            symbol=symbol,
            entry_exec_id=buy_exec.id,
            exit_exec_id=sell_exec.id,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_time=entry_time,
            exit_time=exit_time,
            quantity=quantity,
            pnl=pnl,
            pnl_percent=pnl_percent,
            holding_seconds=(exit_time - entry_time).total_seconds()
        )
        db.add(realized)
        
    session.total_trades = 10
    session.total_pnl = total_pnl
    session.current_capital = 10000000 + total_pnl
    session.win_rate = (wins / 10) * 100
    
    db.commit()
    print(f"Seed Complete for {symbol}! Session ID: {session_id}")

def main():
    db = SessionLocal()
    try:
        seed_session(db, "005930", "삼성전자")
        seed_session(db, "000660", "SK하이닉스")
    finally:
        db.close()

if __name__ == "__main__":
    main()
