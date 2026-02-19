from sqlalchemy import Column, Integer, String, Boolean, JSON
from ..db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)
    active_session_id = Column(String, nullable=True)

    # User Preferences
    last_selected_strategy_id = Column(String, nullable=True)
    last_selected_profile_id = Column(String, nullable=True)
    last_symbol = Column(String, nullable=True, default='005930')
    saved_symbols = Column(JSON, nullable=True)

    # AI API Keys
    encrypted_ai_api_key = Column(String, nullable=True)
    encrypted_google_api_key = Column(String, nullable=True)
    ai_model = Column(String, nullable=True, default="claude-sonnet-4-20250514")
