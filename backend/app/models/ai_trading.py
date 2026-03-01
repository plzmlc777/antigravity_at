from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Boolean, Text, ForeignKey
from datetime import datetime
from ..db.base import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class AITradingProfile(Base):
    """
    AI-driven trading profile configuration.
    AI autonomously decides stocks and strategy parameters at each cycle.
    Flow: cycle complete → AI stock selection → optimization → final decision → session transition
    """
    __tablename__ = "ai_trading_profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(Integer, nullable=False, index=True)

    # Profile Identity
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Strategy
    strategy_name = Column(String, nullable=False)  # e.g., "dip_martingale"

    # Stock Source Configuration
    stock_source_mode = Column(String, default="AI_AUTO_SEARCH")  # FIXED / CANDIDATE_LIST / AI_AUTO_SEARCH
    fixed_symbols = Column(JSON, nullable=True)      # [{code, name}, ...]
    candidate_symbols = Column(JSON, nullable=True)  # [{code, name}, ...]
    search_conditions = Column(String, nullable=True)  # Natural language: "거래량 상위 + 외인 순매수"

    # Parameter Configuration
    param_ranges = Column(JSON, nullable=True)   # {param: {min, max, step}} or null = AI decides
    fixed_params = Column(JSON, nullable=True)   # Params locked from optimization

    # Backtest / Optimization Settings
    backtest_days = Column(Integer, default=30)
    backtest_interval = Column(String, default="1m")
    optimization_top_n = Column(Integer, default=5)
    max_optimization_combos = Column(Integer, default=500)

    # Execution Settings
    approval_mode = Column(String, default="AUTO")  # AUTO / MANUAL
    account_id = Column(Integer, nullable=True)
    initial_capital = Column(Float, default=10_000_000)
    is_paper = Column(Boolean, default=True)

    # Safety Constraints
    max_consecutive_losses = Column(Integer, default=5)
    cooldown_minutes = Column(Integer, default=0)

    # Runtime State
    is_active = Column(Boolean, default=True)
    is_running = Column(Boolean, default=False)
    current_session_id = Column(String, nullable=True)
    current_symbol = Column(String, nullable=True)
    cycles_completed = Column(Integer, default=0)
    consecutive_losses = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_decision_at = Column(DateTime, nullable=True)


class AITradingDecision(Base):
    """
    Log of each AI trading decision with full reasoning chain.
    Each cycle completion triggers a new decision record.
    """
    __tablename__ = "ai_trading_decisions"

    id = Column(String, primary_key=True, default=generate_uuid)
    profile_id = Column(String, ForeignKey("ai_trading_profiles.id"), nullable=False, index=True)

    # Trigger Context
    trigger_type = Column(String, default="initial_start")  # initial_start / manual / cycle_complete
    previous_session_id = Column(String, nullable=True)
    previous_symbol = Column(String, nullable=True)
    previous_cycle_pnl = Column(Float, nullable=True)

    # Step 1: Stock Selection (Claude CLI)
    stock_candidates = Column(JSON, nullable=True)
    stock_selection_model = Column(String, nullable=True)
    stock_selection_duration_ms = Column(Integer, nullable=True)

    # Step 2: Optimization (BacktestEngine)
    optimization_results = Column(JSON, nullable=True)
    optimization_duration_ms = Column(Integer, nullable=True)

    # Step 3: Final Decision (Claude CLI)
    final_decision_model = Column(String, nullable=True)
    final_decision_duration_ms = Column(Integer, nullable=True)

    # Chosen Result
    chosen_symbol = Column(String, nullable=True)
    chosen_symbol_name = Column(String, nullable=True)
    chosen_params = Column(JSON, nullable=True)
    chosen_score = Column(Float, nullable=True)
    chosen_reasoning = Column(Text, nullable=True)

    # Execution
    new_session_id = Column(String, nullable=True)
    status = Column(String, default="PENDING")  # PENDING/EXECUTING/COMPLETED/REJECTED/FAILED/SKIPPED
    error_message = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
