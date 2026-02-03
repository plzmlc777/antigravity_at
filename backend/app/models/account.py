from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from ..db.base import Base
from ..core.trading_env import (
    TradingEnvironment,
    get_env_config,
    get_api_url,
    get_ws_url,
    env_from_string
)
from typing import Optional


class ExchangeAccount(Base):
    __tablename__ = "exchange_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    exchange_name = Column(String) # e.g. "Kiwoom"
    account_name = Column(String)  # User defined alias e.g. "Main Account"

    # Encrypted fields
    encrypted_access_key = Column(String)
    encrypted_secret_key = Column(String)

    # Status
    is_active = Column(Boolean, default=False)
    is_disabled = Column(Boolean, default=False)  # 사용 안함 상태

    # Trading Environment (Single Source of Truth)
    # Values: "real", "virtual", "paper"
    # - real: 키움 실거래 서버 (api.kiwoom.com)
    # - virtual: 키움 모의투자 서버 (mockapi.kiwoom.com)
    # - paper: 로컬 페이퍼 트레이딩 (API 호출 없음)
    environment = Column(String, default=TradingEnvironment.REAL.value)

    # Kiwoom specific (optional)
    account_number = Column(String, nullable=True)

    # User Preferences (계좌별 환경설정)
    last_selected_strategy_id = Column(String, nullable=True)  # 마지막 선택 전략

    user = relationship("User", backref="accounts")

    # ==========================================
    # Computed Properties (for backward compatibility)
    # ==========================================

    @property
    def env_type(self) -> TradingEnvironment:
        """Get environment as enum type"""
        return env_from_string(self.environment or TradingEnvironment.REAL.value)

    @property
    def api_url(self) -> Optional[str]:
        """Derive API URL from environment (backward compatible)"""
        return get_api_url(self.env_type)

    @property
    def ws_url(self) -> Optional[str]:
        """Derive WebSocket URL from environment"""
        return get_ws_url(self.env_type)

    @property
    def is_virtual(self) -> bool:
        """Check if this is a virtual trading account (backward compatible)"""
        return self.env_type == TradingEnvironment.VIRTUAL

    @property
    def is_paper(self) -> bool:
        """Check if this is a paper trading account"""
        return self.env_type == TradingEnvironment.PAPER

    @property
    def is_simulation(self) -> bool:
        """Check if this is any kind of simulation (not real money)"""
        return get_env_config(self.env_type).is_simulation

    @property
    def display_name(self) -> str:
        """Get display name for the environment"""
        return get_env_config(self.env_type).display_name
