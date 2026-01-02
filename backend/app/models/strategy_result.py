from sqlalchemy import Column, String, JSON, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from ..db.base import Base

class StrategyAnalysisResult(Base):
    __tablename__ = "strategy_results"

    # Composite Key logic or simple ID?
    # Plan said: tab_id (Primary Key). 
    # But one tab can have 'backtest' AND 'optimization'.
    # So we need a Composite Key (tab_id, result_type) OR a surrogate ID.
    # Let's use surrogate ID (conceptually simple) or Composite PK. 
    # Composite PK is fine for lookup: get(tab_id, type).
    
    tab_id = Column(String, primary_key=True) # UUID of the tab
    result_type = Column(String, primary_key=True) # 'backtest' or 'optimization'
    
    data = Column(JSON)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # We don't strictly need a surrogate ID if (tab_id, result_type) is unique.
