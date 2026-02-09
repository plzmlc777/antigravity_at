from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey, Enum, Boolean, BigInteger, Text
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

class ErrorSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class ErrorType(str, enum.Enum):
    ORDER_FAILED = "ORDER_FAILED"           # 주문 실패
    API_ERROR = "API_ERROR"                 # Kiwoom API 오류
    STRATEGY_ERROR = "STRATEGY_ERROR"       # 전략 실행 오류
    WEBSOCKET_ERROR = "WEBSOCKET_ERROR"     # WebSocket 연결 오류
    BALANCE_SYNC_ERROR = "BALANCE_SYNC_ERROR"  # 잔고 동기화 오류
    TOKEN_ERROR = "TOKEN_ERROR"             # 토큰 만료/갱신 오류
    DB_ERROR = "DB_ERROR"                   # 데이터베이스 오류
    SYSTEM_ERROR = "SYSTEM_ERROR"           # 시스템 오류

def generate_uuid():
    return str(uuid.uuid4())

class LiveBotSession(Base):
    __tablename__ = "live_bot_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    account_id = Column(Integer, ForeignKey("exchange_accounts.id"), index=True, nullable=True)  # 계좌별 세션 분리

    # Configuration Snapshot (For Comparisons)
    symbol = Column(String, index=True, nullable=False)
    strategy_name = Column(String, nullable=False)
    strategy_config = Column(JSON, nullable=False) # Full parameters used
    interval = Column(String, nullable=False) # 1m, 30m, etc.
    
    # Lifecycle
    status = Column(String, default=SessionStatus.RUNNING)
    orders_enabled = Column(Boolean, default=True)
    is_paper = Column(Boolean, default=True) # Default to Paper for safety
    is_active = Column(Boolean, default=True) # To restore on server restart
    started_at = Column(DateTime, default=datetime.utcnow)
    stopped_at = Column(DateTime, nullable=True)
    
    # Performance (Cached for ease of access)
    initial_capital = Column(Float, default=0.0)
    current_capital = Column(Float, default=0.0)

    # Error Tracking
    error_log = Column(String, nullable=True)

    # AI Evaluation Settings (for auto-evaluation)
    ai_eval_enabled = Column(Boolean, default=False)  # 자동 평가 활성화 여부
    ai_eval_cycles = Column(Integer, default=10)      # N 사이클마다 자동 평가
    ai_eval_backtest_days = Column(Integer, default=30)  # 비교 백테스트 기간
    ai_eval_mode = Column(String, default="paper")    # 분석 대상 모드 (paper/real)

    # Relations
    executions = relationship("LiveTradeExecution", back_populates="session", cascade="all, delete-orphan")

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
    exchange_order_no = Column(String, index=True, nullable=True)  # Kiwoom 주문번호 (체결 매칭용)
    order_submitted_at = Column(DateTime, nullable=True)
    order_filled_at = Column(DateTime, nullable=True)

    executed_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=True)
    fees = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    
    # 3. Analysis Metrics
    slippage = Column(Float, default=0.0) # executed_price - theoretical_price
    slippage_percent = Column(Float, default=0.0)
    
    status = Column(String, default=ExecutionStatus.PENDING)
    error_reason = Column(String, nullable=True) # Logs if failed check or API error

    # 4. Mode & Metadata
    is_paper = Column(Boolean, default=True) # Paper or Real trade
    trade_metadata = Column(JSON, nullable=True) # Strategy metadata (cycle_id, level, etc.)

    # 5. Strategy Parameter Snapshot (for performance analysis by config)
    config_snapshot = Column(JSON, nullable=True)  # 거래 실행 시점의 전략 파라미터 스냅샷

    # Relation
    session = relationship("LiveBotSession", back_populates="executions")


class StrategyParameterVersion(Base):
    """
    Named parameter versions for strategy configurations.
    Allows users to save, compare, and restore parameter sets.
    """
    __tablename__ = "strategy_parameter_versions"

    id = Column(String, primary_key=True, default=generate_uuid)

    # Identification
    strategy_id = Column(String, index=True, nullable=False)  # e.g., "dip_martingale", "time_momentum"
    symbol = Column(String, index=True, nullable=True)  # Optional: symbol-specific version

    # Version Info
    version_name = Column(String, nullable=False)  # User-defined name (e.g., "Conservative", "Aggressive v2")
    description = Column(String, nullable=True)  # Optional description

    # Parameters
    params = Column(JSON, nullable=False)  # Full parameter snapshot
    config_hash = Column(String(12), index=True, nullable=True)  # For quick comparison

    # Performance Stats (optional, populated from analysis)
    performance_stats = Column(JSON, nullable=True)  # {cycles, win_rate, total_pnl, avg_pnl, ...}

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)  # Soft delete
    is_default = Column(Boolean, default=False)  # Mark as default version


class TradingErrorLog(Base):
    """
    Centralized error logging for live trading operations.
    Stores all errors permanently for analysis and debugging.
    """
    __tablename__ = "trading_error_logs"

    id = Column(String, primary_key=True, default=generate_uuid)

    # Context
    session_id = Column(String, index=True, nullable=True)  # 관련 세션 (없을 수 있음)
    symbol = Column(String, index=True, nullable=True)      # 관련 종목 (없을 수 있음)

    # Error Classification
    error_type = Column(String, index=True, nullable=False)  # ErrorType enum value
    severity = Column(String, index=True, default=ErrorSeverity.ERROR)  # ErrorSeverity enum value

    # Error Details
    error_message = Column(String, nullable=False)           # 오류 메시지
    stack_trace = Column(Text, nullable=True)                # 전체 스택 트레이스
    context_data = Column(JSON, nullable=True)               # 오류 발생 시점의 상태/데이터

    # Source
    source_file = Column(String, nullable=True)              # 오류 발생 파일
    source_function = Column(String, nullable=True)          # 오류 발생 함수

    # Resolution
    is_resolved = Column(Boolean, default=False)             # 해결 여부
    resolution_note = Column(String, nullable=True)          # 해결 메모

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)


class EvaluationType(str, enum.Enum):
    MANUAL = "MANUAL"       # 사용자가 수동으로 요청
    AUTO = "AUTO"           # 이벤트 기반 자동 평가 (N 사이클 완료 시)


class LiveAIEvaluation(Base):
    """
    AI evaluation of live trading performance.
    Compares live trading results with backtest results using current strategy config.
    """
    __tablename__ = "live_ai_evaluations"

    id = Column(String, primary_key=True, default=generate_uuid)

    # Context
    session_id = Column(String, ForeignKey("live_bot_sessions.id"), index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)

    # Trigger Info
    evaluation_type = Column(String, default=EvaluationType.MANUAL)  # MANUAL or AUTO
    is_paper = Column(Boolean, default=False)  # Paper mode or Real mode
    trigger_cycle_count = Column(Integer, default=0)  # N cycles that triggered this evaluation

    # Analysis Window
    analysis_start_time = Column(DateTime, nullable=True)  # Start of analysis period
    analysis_end_time = Column(DateTime, nullable=True)    # End of analysis period
    cycles_analyzed = Column(Integer, default=0)           # Number of cycles actually analyzed

    # Live Trading Stats (collected from live_trade_executions)
    live_stats = Column(JSON, nullable=True)  # {total_return, win_rate, avg_pnl, max_drawdown, ...}

    # Backtest Stats (run with current config for same period)
    backtest_stats = Column(JSON, nullable=True)  # Same format as live_stats

    # Strategy Config Snapshot
    strategy_config = Column(JSON, nullable=True)  # Full strategy parameters at evaluation time

    # Comparison Data (pre-computed differences)
    comparison_data = Column(JSON, nullable=True)  # {return_diff, win_rate_diff, slippage_impact, ...}

    # AI Response
    ai_model = Column(String, nullable=True)  # e.g., "gemini-2.0-flash-001"
    ai_prompt = Column(Text, nullable=True)   # The prompt sent to AI
    ai_response = Column(Text, nullable=True) # The AI's evaluation text

    # Quality Metrics
    evaluation_score = Column(Float, nullable=True)  # Overall score (0-100) if extractable from AI
    key_findings = Column(JSON, nullable=True)       # Extracted key points from AI response
    recommendations = Column(JSON, nullable=True)    # Extracted recommendations from AI

    # Status
    status = Column(String, default="pending")  # pending, completed, failed
    error_message = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
