import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
# Adjust path to find app module
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__)))

from app.core.token_manager import KiwoomTokenManager

async def verify_reuse():
    print("--- Starting TokenManager Reuse Verification ---")
    
    # Reset singleton for clean test
    KiwoomTokenManager._instance = None
    manager = KiwoomTokenManager.get_instance()
    
    # Mock the HTTP call
    with patch("httpx.AsyncClient") as mock_client_cls:
        # The context manager returns the client instance
        mock_ctx = mock_client_cls.return_value.__aenter__.return_value
        
        # Prepare response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "MOCK_ACCESS_TOKEN_XYZ",
            "expires_in": 3600
        }
        mock_response.raise_for_status.return_value = None
        
        # Use AsyncMock for the post method
        mock_ctx.post = AsyncMock(return_value=mock_response)
        
        print("\n[Step 1] Requesting Token (1st time)...")
        t1 = await manager.get_token("dummy_app_key", "dummy_secret_key")
        print(f"Token Reuslt 1: {t1}")
        
        print("\n[Step 2] Requesting Token (2nd time)...")
        t2 = await manager.get_token("dummy_app_key", "dummy_secret_key")
        print(f"Token Result 2: {t2}")
        
        print("\n[Verification Results]")
        cache_success = (t1 == t2 == "MOCK_ACCESS_TOKEN_XYZ")
        call_count = mock_ctx.post.call_count
        
        if cache_success:
            print("✓ SUCCESS: Token matches cached value.")
        else:
            print("✗ FAILURE: Tokens do not match.")
            
        if call_count == 1:
            print("✓ SUCCESS: API was called exactly 1 time (Cached).")
        else:
            print(f"✗ FAILURE: API called {call_count} times.")

if __name__ == "__main__":
    asyncio.run(verify_reuse())
