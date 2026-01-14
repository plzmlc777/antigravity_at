import asyncio
from backend.app.services.market_data import MarketDataService

async def main():
    service = MarketDataService()
    symbol = "000660" # SK Hynix
    
    print(f"Fetching REAL candles for {symbol}...")
    # Fetch 1m data for 1 day
    candles = await service.get_candles(symbol, interval="1m", days=1, limit=390)
    
    print(f"Received {len(candles)} candles.")
    if candles:
        print(f"First Candle: {candles[0]}")
        print(f"Last Candle: {candles[-1]}")
    else:
        print("FAILED: No candles returned.")

if __name__ == "__main__":
    asyncio.run(main())
