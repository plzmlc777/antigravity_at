from sqlalchemy import Column, String, Integer, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from ..db.base import Base

class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    tab_id = Column(String, primary_key=True, index=True)
    rank = Column(Integer, index=True)
    is_active = Column(Boolean, default=True)
    tab_name = Column(String)
    config_json = Column(JSON)  # Stores: symbol, interval, capital, date, betting, etc.
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
