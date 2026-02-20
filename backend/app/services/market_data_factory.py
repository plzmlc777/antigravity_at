"""
Market Data Service Factory
- Routes to the appropriate MarketDataService based on exchange_name
- Supports: Kiwoom, KIS, Binance, BinanceFutures
"""

import logging

logger = logging.getLogger(__name__)


def get_market_data_service(exchange_name: str = "Kiwoom"):
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

    else:
        # Default: Kiwoom/KIS (both use the same MarketDataService)
        from .market_data import MarketDataService
        return MarketDataService()
