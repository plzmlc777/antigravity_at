from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import model_validator, ValidationError
import os
from dotenv import load_dotenv

# Explicitly load .env files to ensure Environment Variables are set
# Check paths relative to current working directory (backend) or root
load_dotenv(".env")            # strict local
load_dotenv("../.env")         # parent (root)
load_dotenv("backend/.env")    # child (if running from root)

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    PROJECT_NAME: str = "My Auto Trading"
    PROJECT_VERSION: str = "1.5.36.0"
    BACKEND_PORT: int = 8001
    FRONTEND_PORT: int = 5173
    
    # Kiwoom API Config (User: HCP)
    HCP_KIWOOM_API_URL: str = "https://api.kiwoom.com"
    HCP_KIWOOM_APP_KEY: Optional[str] = None
    HCP_KIWOOM_SECRET_KEY: Optional[str] = None
    HCP_KIWOOM_ACCOUNT_NO: Optional[str] = None
    
    # Naver Search API
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None

    # Security
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" # Change this in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    MAX_CONNECTIONS_COUNT: int = 10
    MIN_CONNECTIONS_COUNT: int = 10

    # PostgreSQL
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    # Kill Switch (KPI guard) — DEFAULT OFF.
    # See feedback_backwards_compatible_defaults.md: new behavior must be opt-in
    # so existing live sessions are never broken by an upgrade.
    # Enable by setting KILL_SWITCH_ENABLED=true in .env after validation.
    KILL_SWITCH_ENABLED: bool = False
    KILL_SWITCH_INTERVAL_SEC: int = 300        # check every 5 min
    KILL_SWITCH_MONTHLY_PCT: float = -10.0      # ≤ -10% / month → stop all
    KILL_SWITCH_SESSION_PCT: float = -20.0      # ≤ -20% / session → stop one
    KILL_SWITCH_DAILY_PCT: float = -5.0         # ≤ -5% / day → pause orders

    class Config:
        model_config = {
            "env_file": [".env", "backend/.env", "../.env"],
            "env_file_encoding": "utf-8",
            "extra": "ignore"
        }

settings = Settings()

# ── 거래소 기본값 (폴백용 상수) ──
DEFAULT_EXCHANGE = "Kiwoom"
DEFAULT_INITIAL_CAPITAL = 10000000  # 키움 기준 1,000만 원
DEFAULT_DAYS = 365                 # 키움 API 제한 1년


def get_claude_cli_path() -> str:
    """Find Claude CLI binary path with fallback locations.

    shutil.which() depends on PATH, which may not include npm global bin
    inside PM2/venv environments. This checks common install locations.
    """
    import shutil
    path = shutil.which("claude")
    if path:
        return path
    # Fallback: check common npm global bin locations
    for candidate in [
        os.path.expanduser("~/.npm-global/bin/claude"),
        os.path.expanduser("~/bin/claude"),
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")
