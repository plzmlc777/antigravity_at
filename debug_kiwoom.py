import asyncio
import httpx
import os
from dotenv import load_dotenv

# Load env manually
load_dotenv()

# API_URL from env might be wrong. Let's force test the doc's url.
URLS_TO_TEST = [
    "https://openapi.kiwoom.com", 
    "https://api.kiwoom.com"
]
APP_KEY = os.getenv("HCP_KIWOOM_APP_KEY")
SECRET_KEY = os.getenv("HCP_KIWOOM_SECRET_KEY")

async def test_kiwoom():
    print(f"[-] Starting Debug Script...")
    
    if not APP_KEY or not SECRET_KEY:
        print("[!] Missing Message: API Credentials not found in .env")
        return

    for base_url in URLS_TO_TEST:
        print(f"\n[-] Testing Base URL: {base_url}...")
        
        # 1. Get Token
        token = None
        async with httpx.AsyncClient() as client:
            print("[-] Requesting Access Token (au10001)...")
            try:
                resp = await client.post(
                    f"{base_url}/oauth2/token",
                    headers={
                        "Content-Type": "application/json;charset=UTF-8",
                        "api-id": "au10001"
                    },
                    json={
                        "grant_type": "client_credentials",
                        "appkey": APP_KEY,
                        "secretkey": SECRET_KEY
                    }
                )
                print(f"[-] Token Response Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    token = resp.json().get("token")
                    print(f"[-] SUCCESS! Token Acquired: {token[:10]}...")
                    # Found the correct URL, break and use it for Price
                    API_URL = base_url
                    break
                else:
                    print(f"[!] Failed. Status: {resp.status_code}, Body: {resp.text[:200]}")

            except Exception as e:
                print(f"[!] Error: {e}")
                continue
    
    if not token:
        print("[!] Could not acquire token from any URL.")
        return

    # 2. Get Price
    print("\n[-] Requesting Price for Samsung Elec (005930) (ka10001)...")
    async with httpx.AsyncClient() as client:
        try:
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": f"Bearer {token}",
                "appkey": APP_KEY,
                "appsecret": SECRET_KEY,
                "tr_id": "ka10001", 
                "api-id": "ka10001"
            }
            
            payload = {"stk_cd": "005930"}
            
            resp = await client.post(
                f"{API_URL}/api/dostk/stkinfo",
                headers=headers,
                json=payload
            )
            
            print(f"[-] Price Response Status: {resp.status_code}")
            print(f"[-] Price Response Headers: {resp.headers}")
            print(f"[-] Price Response Body: {resp.text}")

        except Exception as e:
            print(f"[!] Price Request Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_kiwoom())
