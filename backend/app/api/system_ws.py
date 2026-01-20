from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from ..services.log_broadcaster import LogBroadcaster

router = APIRouter()

@router.websocket("/system-logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    broadcaster = LogBroadcaster.get_instance()
    queue = await broadcaster.subscribe()
    
    try:
        # Send initial connected message
        await websocket.send_text(json.dumps({
            "time": "",
            "source": "System",
            "msg": "System Log Stream Connected."
        }))
        
        while True:
            log_entry = await queue.get()
            await websocket.send_text(json.dumps(log_entry))
            
    except WebSocketDisconnect:
        broadcaster.unsubscribe(queue)
        print("System Log Client disconnected")
    except Exception as e:
        broadcaster.unsubscribe(queue)
        print(f"System Log Stream Error: {e}")
