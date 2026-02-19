"""
Adapter Factory - Exchange-aware adapter creation.
Single point of entry for creating exchange adapters.
Replaces all hardcoded KiwoomRealAdapter instantiations.
"""

import logging
from ..core.exchange_interface import ExchangeInterface

logger = logging.getLogger(__name__)


def create_adapter(exchange_name: str, app_key: str = None, secret_key: str = None,
                   account_no: str = None, account_name: str = "",
                   api_url: str = None, is_virtual: bool = False) -> ExchangeInterface:
    """
    Factory function to create the appropriate adapter based on exchange_name.

    Args:
        exchange_name: "Kiwoom", "KIS", etc.
        app_key: API key / App key
        secret_key: Secret key / App secret
        account_no: Account number (format varies by exchange)
        account_name: User-defined alias
        api_url: Override API URL (usually derived from environment)
        is_virtual: Whether this is a virtual/simulation account

    Returns:
        ExchangeInterface implementation
    """
    exchange = (exchange_name or "").strip().lower()

    if exchange in ("kiwoom", ""):
        from .kiwoom_real import KiwoomRealAdapter
        return KiwoomRealAdapter(
            app_key=app_key,
            secret_key=secret_key,
            account_no=account_no,
            account_name=account_name,
            api_url=api_url,
            is_virtual=is_virtual,
        )
    elif exchange in ("kis", "korean_investment", "한국투자", "한국투자증권"):
        from .kis_real import KISRealAdapter
        return KISRealAdapter(
            app_key=app_key,
            app_secret=secret_key,
            account_no=account_no,
            account_name=account_name,
            api_url=api_url,
            is_virtual=is_virtual,
        )
    else:
        logger.warning(f"Unknown exchange '{exchange_name}', falling back to Kiwoom")
        from .kiwoom_real import KiwoomRealAdapter
        return KiwoomRealAdapter(
            app_key=app_key,
            secret_key=secret_key,
            account_no=account_no,
            account_name=account_name,
            api_url=api_url,
            is_virtual=is_virtual,
        )
