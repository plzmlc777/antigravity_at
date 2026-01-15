import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.app.adapters.kiwoom_real import KiwoomRealAdapter
from backend.app.core.config import settings

async def main():
    print("Testing Kiwoom Get Price...")
    adapter = KiwoomRealAdapter()
    
    # Needs valid token, Adapter handles caching?
    # TokenManager needs env vars?
    # Assuming config/token manager works in this env
    
    symbol = "005930" # Samsung
    
    try:
        # We need to hack access_token or ensure ensure_token works
        # If running from script, TokenManager might need explicit init or reuse
        # But let's try calling get_current_price which calls _ensure_token
        
        # We might need to override settings if they are not loaded
        if not settings.HCP_KIWOOM_APP_KEY:
             print("Warning: Env vars might be missing. Ensure setup.")
             
        # Mock request library or just run it and see raw response by modifying Adapter?
        # Better: I will modify Adapter TEMPORARILY to print raw response.
        
        # Actually I can't modify adapter solely for debug script easily without affecting running app (which is using it).
        # But the app is running in different process. Safe to edit file? Yes.
        
        # Wait, I can try to use `get_current_price` and see if I can inspect internal fields?
        # No, it filters fields.
        
        # I'll create a standalone requests script using the same logic as Adapter but printing raw json.
        pass
    except Exception as e:
        print(e)
        
if __name__ == "__main__":
    # asyncio.run(main())
    pass
