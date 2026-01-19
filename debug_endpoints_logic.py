import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from backend.app.db.session import SessionLocal
from backend.app.models.strategy_config import StrategyConfig
from backend.app.services.market_data import MarketDataService

async def verify_logic():
    db = SessionLocal()
    try:
        print("1. Querying StrategyConfig...")
        db_configs = db.query(StrategyConfig).filter(StrategyConfig.is_active == True).order_by(StrategyConfig.rank).all()
        
        strategies_config = []
        involved_symbols = set()
        
        for c in db_configs:
            cfg = c.config_json
            if cfg and isinstance(cfg, dict) and 'symbol' in cfg:
                strategies_config.append(cfg)
                involved_symbols.add(cfg['symbol'])
        
        print(f"   Found {len(strategies_config)} configs.")
        print(f"   Involved Symbols: {involved_symbols}")
        
        if not involved_symbols:
            print("   ERROR: No symbols found in active config.")
            return

        print("2. Fetching Market Data using MarketDataService...")
        md_service = MarketDataService()
        
        # Test Default Interval
        interval = '30m'
        if strategies_config:
            interval = strategies_config[0].get('interval', '30m')
            
        print(f"   Using Interval: {interval}")
        
        multi_ohlcv_data = {}
        for sym in involved_symbols:
            print(f"   Fetching for {sym}...")
            try:
                candles = await md_service.get_candles(sym, interval=interval, days=400)
                count = len(candles) if candles else 0
                print(f"   -> {sym}: {count} candles.")
                if count > 0:
                    print(f"      First: {candles[0]}")
                    print(f"      Last: {candles[-1]}")
                multi_ohlcv_data[sym] = candles
            except Exception as e:
                print(f"   -> {sym}: FAILED ({e})")
        
        print("\n--- SUMMARY ---")
        print(f"Total Symbols: {len(multi_ohlcv_data)}")
        for sym, data in multi_ohlcv_data.items():
            print(f"{sym}: {len(data) if data else 0} records")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_logic())
