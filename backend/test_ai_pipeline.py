"""Test AI Symbol Selection Pipeline - score calculation fix verification.
Skips EVALUATE step to directly test FIND + COMPARE with score calculation.
"""
import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# Configure logging to see all AISymbol logs
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')

# Must import all models to initialize SQLAlchemy mappers
from app.models.user import User
from app.models.account import ExchangeAccount
from app.models.live_trading import LiveBotSession, LiveTradeExecution
from app.models.strategy_config import StrategyConfig
from app.models.strategy_result import StrategyAnalysisResult
from app.models.ohlcv import OHLCV

from app.core.ai_symbol_selection import AISymbolSelectionService


async def main():
    service = AISymbolSelectionService()

    # Step 1: Get token
    api_url, token = await service._get_token(1)
    if not token:
        print("ERROR: Failed to get token")
        return

    # Step 2: Fetch market data
    stock_data, ranking_data = await service._fetch_market_data(api_url, token)
    if not stock_data:
        print("ERROR: Failed to fetch market data")
        return
    print(f"Fetched {len(stock_data)} stocks, {len(ranking_data)} ranking categories")

    # Step 3: Find candidates (skip EVALUATE, go directly to FIND)
    search_conditions = "최근 거래량이 급등했으나 가격 변동이 적고 잦은 소폭 진동이 있는 종목"
    candidates = await service._find_candidates(
        "003310", search_conditions, stock_data, ranking_data
    )
    print(f"\nFound {len(candidates)} candidates: {candidates}")

    if not candidates:
        print("No candidates found. Exiting.")
        return

    # Step 4: Compare via backtest (score calculation fix test)
    strategy_config = {
        "rsi_period": 14,
        "rsi_trigger_level": 30,
        "rsi_reset_level": 50,
        "initial_invest_ratio": 0.1,
        "martingale_multiplier": 2.0,
        "max_level": 4,
        "trailing_stop_pct": 1.5,
        "interval": "1m",
    }

    best = await service._compare_symbols(
        candidates, "rsi_martingale", strategy_config, 10000000
    )

    print(f"\n{'='*60}")
    if best:
        print(f"BEST SYMBOL: {best}")
    else:
        print("NO SYMBOL OUTPERFORMED")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
