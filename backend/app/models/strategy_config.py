from sqlalchemy import Column, String, Integer, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from ..db.base import Base

class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    tab_id = Column(String, primary_key=True, index=True)
    account_id = Column(Integer, index=True, nullable=False)  # 계좌 중심: 각 계좌별 설정 분리
    strategy_id = Column(String, index=True)  # Multi-Strategy Support
    rank = Column(Integer, index=True)
    is_active = Column(Boolean, default=True)
    tab_name = Column(String)
    config_json = Column(JSON)  # Stores: symbol, interval, capital, date, betting, etc.
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
