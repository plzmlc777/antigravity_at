"""
MCP server auth helper — load exchange_accounts row + decrypt credentials + adapter factory.

Per [[feedback_credentials_in_db]] — credentials are Fernet-encrypted in DB,
never in env files. The MCP server process decrypts at startup and keeps
plaintext in memory only.
"""
import os
import logging
from typing import Optional

from app.adapters.binance_futures import BinanceFuturesAdapter
from app.core.security import decrypt_key
from app.db.session import db_scope
from app.models.account import ExchangeAccount

logger = logging.getLogger(__name__)


class MCPAuthError(Exception):
    pass


def load_account(account_id: int) -> ExchangeAccount:
    with db_scope() as db:
        row = db.query(ExchangeAccount).filter(ExchangeAccount.id == account_id).first()
        if row is None:
            raise MCPAuthError(f"exchange_account id={account_id} not found")
        if row.is_disabled:
            raise MCPAuthError(f"exchange_account id={account_id} is_disabled=True")
        if (row.exchange_name or "").strip().lower() not in ("binancefutures", "binance_futures"):
            raise MCPAuthError(
                f"exchange_account id={account_id} exchange_name='{row.exchange_name}' "
                "is not Binance Futures — refusing to load"
            )
        db.expunge(row)
        return row


def make_adapter(account: ExchangeAccount, *, force_paper: bool) -> BinanceFuturesAdapter:
    api_key = decrypt_key(account.encrypted_access_key)
    secret_key = decrypt_key(account.encrypted_secret_key)
    if not api_key or not secret_key:
        raise MCPAuthError(f"credentials decryption empty for account id={account.id}")

    if force_paper:
        is_testnet = True
        api_url = "https://testnet.binancefuture.com"
    else:
        env = (account.environment or "real").strip().lower()
        is_testnet = env in ("virtual", "paper", "testnet")
        api_url = "https://testnet.binancefuture.com" if is_testnet else "https://fapi.binance.com"

    return BinanceFuturesAdapter(
        api_key=api_key,
        secret_key=secret_key,
        api_url=api_url,
        account_name=account.account_name or "",
        is_testnet=is_testnet,
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
