from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App Config
    APP_ENV: str = "dev"
    
    # Kiwoom API Config (User: HCP)
    HCP_KIWOOM_API_URL: str = "https://api.kiwoom.com"
    HCP_KIWOOM_APP_KEY: Optional[str] = None
    HCP_KIWOOM_SECRET_KEY: Optional[str] = None
    HCP_KIWOOM_ACCOUNT_NO: Optional[str] = None
    
    # Trading Mode (MOCK / REAL)
    TRADING_MODE: str = "MOCK"

    class Config:
        env_file = ".env"

settings = Settings()
