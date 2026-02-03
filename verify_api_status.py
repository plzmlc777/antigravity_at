
import httpx
import asyncio

async def check():
    async with httpx.AsyncClient(base_url="http://localhost:8001") as client:
        print("Checking /health...")
        try:
            r = await client.get("/health")
            print(f"Health: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Health Check Failed: {e}")

        print("\nChecking /api/v1/live/status...")
        try:
            r = await client.get("/api/v1/live/status")
            print(f"Live Status: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Live Status Check Failed: {e}")

if __name__ == "__main__":
    asyncio.run(check())
