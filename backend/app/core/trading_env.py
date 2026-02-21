"""
Trading Environment Configuration
- Single source of truth for trading environments
- Eliminates redundancy between is_virtual flag and api_url
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from .config import DEFAULT_EXCHANGE


class TradingEnvironment(str, Enum):
    """Trading environment types"""
    REAL = "real"           # 실거래 (Kiwoom 실서버)
    VIRTUAL = "virtual"     # 모의투자 (Kiwoom 모의서버)
    PAPER = "paper"         # 페이퍼 트레이딩 (로컬 시뮬레이션, API 호출 없음)


@dataclass(frozen=True)
class EnvironmentConfig:
    """Configuration for each trading environment"""
    api_url: Optional[str]
    ws_port: int
    display_name: str
    display_name_ko: str
    is_simulation: bool     # 실제 자금이 아닌 시뮬레이션 여부


# Central configuration mapping
ENV_CONFIGS: dict[TradingEnvironment, EnvironmentConfig] = {
    TradingEnvironment.REAL: EnvironmentConfig(
        api_url="https://api.kiwoom.com",
        ws_port=10000,
        display_name="KIWOOM (REAL)",
        display_name_ko="키움 (실거래)",
        is_simulation=False
    ),
    TradingEnvironment.VIRTUAL: EnvironmentConfig(
        api_url="https://mockapi.kiwoom.com",
        ws_port=10000,
        display_name="KIWOOM (VIRTUAL)",
        display_name_ko="키움 (모의투자)",
        is_simulation=True
    ),
    TradingEnvironment.PAPER: EnvironmentConfig(
        api_url=None,  # No external API calls
        ws_port=0,
        display_name="Paper Trading",
        display_name_ko="페이퍼 트레이딩",
        is_simulation=True
    ),
}


def get_env_config(env: TradingEnvironment) -> EnvironmentConfig:
    """Get configuration for the given environment"""
    return ENV_CONFIGS[env]


def get_api_url(env: TradingEnvironment) -> Optional[str]:
    """Get API URL for the given environment"""
    return ENV_CONFIGS[env].api_url


def get_ws_url(env: TradingEnvironment) -> Optional[str]:
    """Get WebSocket URL for the given environment"""
    config = ENV_CONFIGS[env]
    if not config.api_url:
        return None
    return f"{config.api_url.replace('https://', 'wss://')}:{config.ws_port}/api/dostk/websocket"


def get_display_name(env: TradingEnvironment) -> str:
    """Get display name for the given environment"""
    return ENV_CONFIGS[env].display_name


def is_simulation(env: TradingEnvironment) -> bool:
    """Check if the environment is a simulation (not real money)"""
    return ENV_CONFIGS[env].is_simulation


def env_from_string(value: str) -> TradingEnvironment:
    """Convert string to TradingEnvironment with fallback to REAL"""
    try:
        return TradingEnvironment(value)
    except ValueError:
        return TradingEnvironment.REAL


# ── Exchange-specific URL resolution ──

EXCHANGE_URLS: dict[str, dict[str, Optional[str]]] = {
    "Kiwoom": {
        "real": "https://api.kiwoom.com",
        "virtual": "https://mockapi.kiwoom.com",
        "paper": None,
    },
    "KIS": {
        "real": "https://openapi.koreainvestment.com:9443",
        "virtual": "https://openapivts.koreainvestment.com:29443",
        "paper": None,
    },
    "Binance": {
        "real": "https://api.binance.com",
        "virtual": "https://testnet.binance.vision",
        "paper": None,
    },
    "BinanceFutures": {
        "real": "https://fapi.binance.com",
        "virtual": "https://testnet.binancefuture.com",
        "paper": None,
    },
}


def get_api_url_for_exchange(exchange_name: str, env: TradingEnvironment) -> Optional[str]:
    """Get API URL for a given exchange and environment."""
    urls = EXCHANGE_URLS.get(exchange_name, EXCHANGE_URLS.get(DEFAULT_EXCHANGE, {}))
    return urls.get(env.value)
