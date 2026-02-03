from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from ..db.base import Base

class TradingBotModel(Base):
    __tablename__ = "trading_bots"

    id = Column(String, primary_key=True, index=True) # UUID
    symbol = Column(String, index=True)
    strategy = Column(String)
    config = Column(JSON) # Store full configuration
    is_running = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
