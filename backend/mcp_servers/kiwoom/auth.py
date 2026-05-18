"""
MCP Kiwoom auth helper — exchange_accounts → KiwoomRealAdapter factory.

Per [[feedback_credentials_in_db]]. Kiwoom 실거래/모의투자 분기는
exchange_accounts.environment ("real" / "virtual") 으로 결정.
MCP_FORCE_VIRTUAL=true 시 강제로 mockapi 어댑터를 생성한다.
"""
import os
import logging
from typing import Optional

from app.adapters.kiwoom_real import KiwoomRealAdapter
from app.core.security import decrypt_key
from app.db.session import db_scope
from app.models.account import ExchangeAccount

logger = logging.getLogger(__name__)


class MCPAuthError(Exception):
    pass


REAL_API_URL = "https://api.kiwoom.com"
VIRTUAL_API_URL = "https://mockapi.kiwoom.com"


def load_account(account_id: int) -> ExchangeAccount:
    with db_scope() as db:
        row = db.query(ExchangeAccount).filter(ExchangeAccount.id == account_id).first()
        if row is None:
            raise MCPAuthError(f"exchange_account id={account_id} not found")
        if row.is_disabled:
            raise MCPAuthError(f"exchange_account id={account_id} is_disabled=True")
        if (row.exchange_name or "").strip().lower() not in ("kiwoom", ""):
            raise MCPAuthError(
                f"exchange_account id={account_id} exchange_name='{row.exchange_name}' "
                "is not Kiwoom — refusing to load"
            )
        db.expunge(row)
        return row


def make_adapter(account: ExchangeAccount, *, force_virtual: bool) -> KiwoomRealAdapter:
    app_key = decrypt_key(account.encrypted_access_key)
    secret_key = decrypt_key(account.encrypted_secret_key)
    if not app_key or not secret_key:
        raise MCPAuthError(f"credentials decryption empty for account id={account.id}")

    if force_virtual:
        is_virtual = True
        api_url = VIRTUAL_API_URL
    else:
        env = (account.environment or "real").strip().lower()
        is_virtual = env in ("virtual", "paper")
        api_url = VIRTUAL_API_URL if is_virtual else REAL_API_URL

    return KiwoomRealAdapter(
        app_key=app_key,
        secret_key=secret_key,
        account_no=account.account_number,
        account_name=account.account_name or "",
        api_url=api_url,
        is_virtual=is_virtual,
    )


def allow_real_trades() -> bool:
    return os.environ.get("MCP_ALLOW_REAL_TRADES", "false").strip().lower() == "true"


def resolve_account_id() -> int:
    raw = os.environ.get("MCP_EXCHANGE_ACCOUNT_ID")
    if not raw:
        raise MCPAuthError("MCP_EXCHANGE_ACCOUNT_ID env var not set")
    try:
        return int(raw)
    except ValueError as exc:
        raise MCPAuthError(f"MCP_EXCHANGE_ACCOUNT_ID='{raw}' is not an integer") from exc
