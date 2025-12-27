from app.core.security import verify_password, get_password_hash, create_access_token
try:
    print("Testing Hash...")
    h = get_password_hash("test")
    print(f"Hash: {h}")
    print("Testing Verify...")
    v = verify_password("test", h)
    print(f"Verify: {v}")
    print("Testing JWT...")
    t = create_access_token("test@example.com")
    print(f"Token: {t}")
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
