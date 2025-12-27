from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import model_validator, ValidationError

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    BACKEND_PORT: int = 8001
    FRONTEND_PORT: int = 5173
    
    # Kiwoom API Config (User: HCP)
    HCP_KIWOOM_API_URL: str = "https://api.kiwoom.com"
    HCP_KIWOOM_APP_KEY: Optional[str] = None
    HCP_KIWOOM_SECRET_KEY: Optional[str] = None
    HCP_KIWOOM_ACCOUNT_NO: Optional[str] = None
    
    # Security
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" # Change this in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 1 day
    MAX_CONNECTIONS_COUNT: int = 10
    MIN_CONNECTIONS_COUNT: int = 10

    # PostgreSQL
    POSTGRES_SERVER: str 
    POSTGRES_USER: str 
    POSTGRES_PASSWORD: str 
    POSTGRES_DB: str 

    # Trading Mode (MOCK / REAL) - REQUIRED NO DEFAULT
    TRADING_MODE: str 

    @model_validator(mode='after')
    def validate_config(self):
        if self.TRADING_MODE.upper() == "REAL":
            missing = []
            if not self.HCP_KIWOOM_APP_KEY: missing.append("HCP_KIWOOM_APP_KEY")
            if not self.HCP_KIWOOM_SECRET_KEY: missing.append("HCP_KIWOOM_SECRET_KEY")
            # if not self.HCP_KIWOOM_ACCOUNT_NO: missing.append("HCP_KIWOOM_ACCOUNT_NO") # Account No might be needed or verified later
            
            if missing:
                # We now allow missing keys because they might be provided via DB.
                # Just log a warning or pass.
                pass 
        return self

    def set_mode(self, mode: str):
        self.TRADING_MODE = mode.upper()
        # Re-validate
        self.validate_config()

    class Config:
        model_config = {
            "env_file": [".env", "backend/.env", "../.env"],
            "env_file_encoding": "utf-8",
            "extra": "ignore"
        }

settings = Settings()
