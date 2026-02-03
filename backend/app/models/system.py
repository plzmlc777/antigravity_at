from sqlalchemy import Column, String, DateTime, JSON
from datetime import datetime
from ..db.base import Base

class SystemMetadata(Base):
    __tablename__ = "system_metadata"

    key = Column(String, primary_key=True, index=True)
    value = Column(String)
    extra_data = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
