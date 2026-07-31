"""
Market Data Service Factory
- Routes to the appropriate MarketDataService based on exchange_name
- Supports: Kiwoom, KIS, Binance, BinanceFutures
"""

from ..core.config import DEFAULT_EXCHANGE
import logging

logger = logging.getLogger(__name__)


def get_market_data_service(exchange_name: str = DEFAULT_EXCHANGE):
    """
    Factory function to get the appropriate MarketDataService.

    Args:
        exchange_name: "Kiwoom", "KIS", "Binance", "BinanceFutures"

    Returns:
        MarketDataService instance (Kiwoom or Binance)
    """
    exchange = (exchange_name or "").strip().lower()

    if exchange in ("binance", "binancespot"):
        from .binance_market_data import BinanceMarketDataService
        return BinanceMarketDataService(is_futures=False)

    elif exchange in ("binancefutures",):
        from .binance_market_data import BinanceMarketDataService
        return BinanceMarketDataService(is_futures=True)

    elif exchange in ("kiwoomus", "kiwoom_us", "kiwoom-us"):
        # 미국주식: ET naive 타임스탬프 + 정규장 분봉만 저장 (모듈 docstring 참조)
        from .us_market_data_service import USMarketDataService
        return USMarketDataService()

    else:
        # Default: Kiwoom/KIS (both use the same MarketDataService)
        from .market_data import MarketDataService
        return MarketDataService()
