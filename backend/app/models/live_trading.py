from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey, Enum, Boolean, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from ..db.base import Base
import uuid

# Enums
class SessionStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

class ExecutionStatus(str, enum.Enum):
    PENDING = "PENDING"     # Signal Generation -> Pre-check
    SUBMITTED = "SUBMITTED" # Sent to Exchange
    FILLED = "FILLED"       # Confirmed Execution
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIAL = "PARTIAL"

class SignalType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

def generate_uuid():
    return str(uuid.uuid4())

class LiveBotSession(Base):
    __tablename__ = "live_bot_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    
    # Configuration Snapshot (For Comparisons)
    symbol = Column(String, index=True, nullable=False)
    strategy_name = Column(String, nullable=False)
    strategy_config = Column(JSON, nullable=False) # Full parameters used
    interval = Column(String, nullable=False) # 1m, 30m, etc.
    
    # Lifecycle
    status = Column(String, default=SessionStatus.RUNNING)
    orders_enabled = Column(Boolean, default=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    stopped_at = Column(DateTime, nullable=True)
    
    initial_capital = Column(Float, default=0.0)
    current_capital = Column(Float, default=0.0)
    
    # Performance Stats
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    
    # Relations
    executions = relationship("LiveTradeExecution", back_populates="session", cascade="all, delete-orphan")
    realized_trades = relationship("LiveRealizedTrade", back_populates="session", cascade="all, delete-orphan")
    equity_snapshots = relationship("LiveEquitySnapshot", back_populates="session", cascade="all, delete-orphan")

class LiveTradeExecution(Base):
    """
    Records the 'Gap' between Signal (Theory) and Execution (Reality).
    """
    __tablename__ = "live_trade_executions"

    id = Column(String, primary_key=True, default=generate_uuid)
    
    session_id = Column(String, ForeignKey("live_bot_sessions.id"), nullable=False)
    symbol = Column(String, index=True, nullable=False)
    
    # 1. Theoretical Signal
    signal_type = Column(String, nullable=False) # BUY / SELL
    signal_timestamp = Column(DateTime, nullable=False) # Chart Time (e.g. 09:00)
    theoretical_price = Column(Float, nullable=False) # Close Price of Signal Candle
    requested_quantity = Column(Integer, default=0)
    
    # 2. Actual Execution
    order_submitted_at = Column(DateTime, nullable=True)
    order_filled_at = Column(DateTime, nullable=True)
    
    executed_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=True)
    remaining_quantity = Column(Float, nullable=True) # For FIFO matching
    fees = Column(Float, default=0.0)
    
    # 3. Analysis Metrics
    slippage = Column(Float, default=0.0) # executed_price - theoretical_price
    slippage_percent = Column(Float, default=0.0)
    
    status = Column(String, default=ExecutionStatus.PENDING)
    error_reason = Column(String, nullable=True) # Logs if failed check or API error
    
    # Relation
    session = relationship("LiveBotSession", back_populates="executions")

class LiveRealizedTrade(Base):
    """
    Stores paired Buy/Sell trades for performance analysis.
    """
    __tablename__ = "live_realized_trades"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("live_bot_sessions.id"), nullable=False)
    symbol = Column(String, index=True, nullable=False)
    
    entry_exec_id = Column(String, ForeignKey("live_trade_executions.id"), nullable=True)
    exit_exec_id = Column(String, ForeignKey("live_trade_executions.id"), nullable=True)
    
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=False)
    quantity = Column(Float, nullable=False)
    
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    holding_seconds = Column(Float, default=0.0)
    
    # Relation
    session = relationship("LiveBotSession", back_populates="realized_trades")

class LiveEquitySnapshot(Base):
    """
    Periodic snapshot of total value for equity curve plotting.
    """
    __tablename__ = "live_equity_snapshots"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("live_bot_sessions.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    holdings_value = Column(Float, nullable=False)
    drawdown = Column(Float, default=0.0)
    
    # Relation
    session = relationship("LiveBotSession", back_populates="equity_snapshots")
