from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import random
from datetime import datetime

router = APIRouter()

@router.websocket("/test-logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        count = 0
        while True:
            # Send 100 messages quickly
            for i in range(100):
                count += 1
                msg = {
                    "time": datetime.now().isoformat(),
                    "source": "TestStream",
                    "msg": f"High frequency test log message #{count} - Random Value: {random.randint(0, 9999)}"
                }
                await websocket.send_text(json.dumps(msg))
            
            # Wait for 1 second before next burst
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print("Test Log Client disconnected")
