
import sys
import os
import traceback

# Add project root to sys.path
sys.path.append(os.getcwd())

print("Attempting to import backend.app.main...")
try:
    from backend.app.main import app
    print("SUCCESS: backend.app.main imported.")
except Exception as e:
    print(f"FAILURE: Could not import backend.app.main. Error: {e}")
    traceback.print_exc()

print("\nAttempting to import live_manager...")
try:
    from backend.app.core.live_manager import live_manager
    print("SUCCESS: live_manager imported.")
except Exception as e:
    print(f"FAILURE: Could not import live_manager. Error: {e}")
    traceback.print_exc()
