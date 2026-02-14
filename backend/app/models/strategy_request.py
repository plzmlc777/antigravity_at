from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey
from datetime import datetime
from ..db.base import Base
import uuid


def _generate_uuid():
    return str(uuid.uuid4())


class StrategyRequest(Base):
    __tablename__ = "strategy_requests"

    id = Column(String, primary_key=True, default=_generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    # Step 1: Basic info
    name = Column(String, nullable=False)
    strategy_id = Column(String, nullable=True)       # snake_case registry ID (set on implementation)
    description = Column(String, nullable=True)

    # Step 2: Entry condition
    entry_type = Column(String, default="price")      # price / time / indicator / composite
    entry_condition = Column(Text, nullable=False)
    indicators = Column(JSON, nullable=True)           # ["rsi", "ma", "bollinger", ...]

    # Step 3: Additional entry & exit
    entry_mode = Column(String, default="single")     # single / multi
    additional_entry = Column(Text, nullable=True)
    exit_condition = Column(Text, nullable=True)

    # Step 4: Custom parameters
    custom_parameters = Column(JSON, nullable=True)    # [{name, type, default, min, max, description}]
    default_overrides = Column(JSON, nullable=True)    # {max_buy_count: 1, ...}

    # Step 5: Notes
    notes = Column(Text, nullable=True)

    # Status management
    status = Column(String, default="draft", index=True)  # draft / submitted / implemented / active
    implemented_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
