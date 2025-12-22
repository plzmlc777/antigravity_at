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
    
    # Kiwoom specific (optional)
    account_number = Column(String, nullable=True) # Usually not secret, but can be encrypted if desired
    
    user = relationship("User", backref="accounts")
