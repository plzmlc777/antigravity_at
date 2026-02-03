
import asyncio
import sys
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WS-Tester")

async def test_websocket():
    # Use a dummy session ID, or one from previous logs if alive
    session_id = "test_session_dummy"
    uri = f"ws://localhost:8001/api/v1/live/ws/{session_id}"
    
    logger.info(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Connected!")
            
            # Wait for some messages
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"Received: {msg}")
            except asyncio.TimeoutError:
                logger.info("No message received in 5s (Expected if no bot running)")
            
    except Exception as e:
        logger.error(f"Connection Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
