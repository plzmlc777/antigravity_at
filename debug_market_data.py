import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.market_data import MarketDataService

async def main():
    try:
        service = MarketDataService()
        print("Fetching candles...")
        candles = await service.get_minute_candles("005930", 1, 1)
        print(f"Got {len(candles)} candles")
    except Exception as e:
        print("Caught Exception:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
