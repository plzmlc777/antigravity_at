from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, UniqueConstraint
from ..db.base import Base
from datetime import datetime

class OHLCV(Base):
    __tablename__ = "ohlcv"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    time_frame = Column(String, nullable=False, default="1m") # 1m, 3m, 5m, 1d...
    
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Prevent duplicate data for same candle
    __table_args__ = (
        UniqueConstraint('symbol', 'timestamp', 'time_frame', name='uix_symbol_timestamp_tf'),
    )
