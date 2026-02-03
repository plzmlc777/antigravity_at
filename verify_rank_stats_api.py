
import asyncio
import httpx
import json

async def verify_api():
    url = "http://localhost:8001/api/v1/strategies/integrated/v2-backtest"
    payload = {
        "symbol": "005930",
        "interval": "1m",
        "days": 10,
        "initial_capital": 10000000,
        "configs": [
            {
                "symbol": "005930",
                "interval": "1m",
                "strategy": "Time Momentum",
                "is_active": True,
                "strategy_rank": 1
            },
             {
                "symbol": "000660",
                "interval": "1m",
                "strategy": "Time Momentum",
                "is_active": True,
                "strategy_rank": 2
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"Sending POST request to {url}...")
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                print("Response received successfully.")
                
                # Check for rank_stats_list
                if "rank_stats_list" in data:
                    print("✅ 'rank_stats_list' field FOUND in response.")
                    rank_stats = data['rank_stats_list']
                    print(f"Content of 'rank_stats_list' (Length: {len(rank_stats)}):")
                    print(json.dumps(rank_stats, indent=2))
                    
                    if len(rank_stats) > 0:
                        print("✅ 'rank_stats_list' contains data!")
                    else:
                        print("⚠️ 'rank_stats_list' is empty. (This might be normal if no trades occurred)")
                else:
                    print("❌ 'rank_stats_list' field MISSING in response.")
            else:
                print(f"❌ Error: {response.status_code}")
                print(response.text)

    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(verify_api())
