from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from ..db.base import Base

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

    # Virtual account flag (가상 계좌 / 모의투자 계좌)
    # True = Kiwoom 모의투자 서버 (mockapi.kiwoom.com)
    # False = Kiwoom 실거래 서버 (api.kiwoom.com)
    # Note: This is different from is_paper which simulates orders locally
    is_virtual = Column(Boolean, default=False)

    # API URL for this account (allows per-account endpoint configuration)
    # If None, uses the global HCP_KIWOOM_API_URL from settings
    api_url = Column(String, nullable=True)

    # Kiwoom specific (optional)
    account_number = Column(String, nullable=True) # Usually not secret, but can be encrypted if desired

    user = relationship("User", backref="accounts")
