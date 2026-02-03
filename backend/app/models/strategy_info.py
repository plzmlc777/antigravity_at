from sqlalchemy import Column, String, JSON, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from ..db.base import Base

class StrategyInfo(Base):
    __tablename__ = "strategy_info"

    id = Column(String, primary_key=True, index=True) # e.g., 'time_momentum'
    name = Column(String)
    description = Column(String)
    detailed_description = Column(Text) # Explicit Text for long Markdown
    code = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True) # List of strings
    parameter_schema = Column(JSONB, nullable=True) # UI parameter configuration
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

