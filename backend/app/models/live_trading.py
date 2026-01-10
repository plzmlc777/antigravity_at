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
    started_at = Column(DateTime, default=datetime.utcnow)
    stopped_at = Column(DateTime, nullable=True)
    
    # Performance (Cached for ease of access)
    initial_capital = Column(Float, default=0.0)
    current_capital = Column(Float, default=0.0)
    
    # Relations
    executions = relationship("LiveTradeExecution", back_populates="session", cascade="all, delete-orphan")

class LiveTradeExecution(Base):
    """
    Records the 'Gap' between Signal (Theory) and Execution (Reality).
    """
    __tablename__ = "live_trade_executions"

    id = Column(String, primary_key=True, default=generate_uuid)
    
    session_id = Column(String, ForeignKey("live_bot_sessions.id"), nullable=False)
    
    # 1. Theoretical Signal
    signal_type = Column(String, nullable=False) # BUY / SELL
    signal_timestamp = Column(DateTime, nullable=False) # Chart Time (e.g. 09:00)
    theoretical_price = Column(Float, nullable=False) # Close Price of Signal Candle
    
    # 2. Actual Execution
    order_submitted_at = Column(DateTime, nullable=True)
    order_filled_at = Column(DateTime, nullable=True)
    
    executed_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=True)
    fees = Column(Float, default=0.0)
    
    # 3. Analysis Metrics
    slippage = Column(Float, default=0.0) # executed_price - theoretical_price
    slippage_percent = Column(Float, default=0.0)
    
    status = Column(String, default=ExecutionStatus.PENDING)
    error_reason = Column(String, nullable=True) # Logs if failed check or API error
    
    # Relation
    session = relationship("LiveBotSession", back_populates="executions")
