from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import model_validator, ValidationError

class Settings(BaseSettings):
    # App Config
    APP_ENV: str = "dev"
    
    # Kiwoom API Config (User: HCP)
    HCP_KIWOOM_API_URL: str = "https://api.kiwoom.com"
    HCP_KIWOOM_APP_KEY: Optional[str] = None
    HCP_KIWOOM_SECRET_KEY: Optional[str] = None
    HCP_KIWOOM_ACCOUNT_NO: Optional[str] = None
    
    # Security
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" # Change this in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 1 day
    
    # Trading Mode (MOCK / REAL) - REQUIRED NO DEFAULT
    TRADING_MODE: str 

    @model_validator(mode='after')
    def validate_config(self):
        if self.TRADING_MODE.upper() == "REAL":
            missing = []
            if not self.HCP_KIWOOM_APP_KEY: missing.append("HCP_KIWOOM_APP_KEY")
            if not self.HCP_KIWOOM_SECRET_KEY: missing.append("HCP_KIWOOM_SECRET_KEY")
            if not self.HCP_KIWOOM_ACCOUNT_NO: missing.append("HCP_KIWOOM_ACCOUNT_NO")
            
            if missing:
                raise ValueError(f"REAL Mode requires environment variables: {', '.join(missing)}")
        return self

    def set_mode(self, mode: str):
        self.TRADING_MODE = mode.upper()
        # Re-validate
        self.validate_config()

    class Config:
        env_file = ".env"

settings = Settings()

