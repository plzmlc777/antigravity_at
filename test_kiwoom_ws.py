import asyncio
import websockets
import json
import sys
import os

# Add backend to path to import manager
sys.path.append(os.getcwd() + '/backend')

from app.core.token_manager import KiwoomTokenManager
from app.core.config import settings

SOCKET_URL = 'wss://api.kiwoom.com:10000/api/dostk/websocket'

async def main():
    mgr = KiwoomTokenManager.get_instance()
    # Mock settings for standalone if needed, or use existing
    token = await mgr.get_token(settings.HCP_KIWOOM_APP_KEY, settings.HCP_KIWOOM_SECRET_KEY)
    if not token:
        print("Failed to get token")
        return

    print(f"Using Token: {token[:10]}...")

    async with websockets.connect(SOCKET_URL) as ws:
        # 1. Login
        login_pkt = {
            "trnm": "LOGIN",
            "token": token
        }
        await ws.send(json.dumps(login_pkt))
        print("Login sent")

        # 2. Receive Loop
        async def listen():
            try:
                while True:
                    msg = await ws.recv()
                    print(f"RECV: {msg}")
            except Exception as e:
                print(f"Listen error: {e}")

        listen_task = asyncio.create_task(listen())

        await asyncio.sleep(2)
        
        # 3. Register symbol
        reg_pkt = {
            "trnm": "REG",
            "grp_no": "1",
            "refresh": "1",
            "data": [{
                "item": ["005930"], # Samsung
                "type": ["0B"]
            }]
        }
        await ws.send(json.dumps(reg_pkt))
        print("REG sent for 005930")

        await asyncio.sleep(10)
        print("Test finished")

if __name__ == "__main__":
    asyncio.run(main())
