"""Read Telegram bot creds from DB (exchange_accounts) and emit shell exports.

Usage (in SAS wrapper/runner):
    eval "$(./venv/bin/python3 .claude/skills/at-orchestrator/scripts/sas/load_telegram_creds.py)"

Picks the first ExchangeAccount with telegram_enabled=TRUE that has both
encrypted_telegram_bot_token and telegram_chat_id. Decrypts the token using
the same Fernet key the backend uses (settings.SECRET_KEY).

Stays silent (exits 0 with no output) if nothing is configured — callers
treat empty TELEGRAM_BOT_TOKEN as "alerts disabled" already.

NEVER reads .env for credentials. NEVER prints the token to stdout/log.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend"))

try:
    from sqlalchemy import text
    from app.db.session import engine
    from app.core.security import decrypt_key
except Exception as e:
    sys.stderr.write(f"# load_telegram_creds: import failed: {e}\n")
    sys.exit(0)

def shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"

# Use raw SQL via the engine — avoids loading all SQLAlchemy ORM relationships
# which require every model module imported (PaperOrder, etc.).
try:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, encrypted_telegram_bot_token, telegram_chat_id
            FROM exchange_accounts
            WHERE telegram_enabled = TRUE
              AND encrypted_telegram_bot_token IS NOT NULL
              AND telegram_chat_id IS NOT NULL
            ORDER BY id ASC
            LIMIT 1
        """)).first()
except Exception as e:
    sys.stderr.write(f"# load_telegram_creds: db query failed: {type(e).__name__}\n")
    sys.exit(0)

if not row:
    sys.stderr.write("# load_telegram_creds: no enabled telegram on any exchange_account\n")
    sys.exit(0)

ea_id, enc_token, chat = row
try:
    token = decrypt_key(enc_token)
except Exception as e:
    sys.stderr.write(f"# load_telegram_creds: decrypt failed for ea_id={ea_id}: {type(e).__name__}\n")
    sys.exit(0)

if not token or not chat:
    sys.exit(0)
print(f"export TELEGRAM_BOT_TOKEN={shell_quote(token)}")
print(f"export TELEGRAM_CHAT_ID={shell_quote(str(chat))}")
