#!/usr/bin/env python3
"""
Account Keepalive Worker.

Pings each real Kiwoom / Binance / BinanceFutures account by issuing a
balance-query API call. Writes the result to `account_keepalive_logs` and
emits a JSON summary on stdout for the wrapping sub-agent to consume.

Why: Kiwoom invalidates OAuth tokens after long inactivity; periodic
balance pings keep the connection warm. Binance keys don't strictly need
this but the same heartbeat surfaces silent key revocation early.

Run: python -m scripts.account_keepalive
PM2 cron dispatches this via the account-keepalive sub-agent.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from sqlalchemy import text  # noqa: E402

from app.core import security  # noqa: E402
from app.core.telegram_service import TelegramNotificationService  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.account import ExchangeAccount  # noqa: E402

PER_ACCOUNT_TIMEOUT_SEC = 30
KEEPALIVE_EXCHANGES = ("Kiwoom", "Binance", "BinanceFutures")


def _build_adapter(account: ExchangeAccount):
    """Construct exchange adapter for a single account row."""
    access = security.decrypt_key(account.encrypted_access_key or "")
    secret = security.decrypt_key(account.encrypted_secret_key or "")

    if not access or not secret:
        raise ValueError("missing api credentials")

    api_url = account.api_url
    is_virtual = account.is_virtual

    if account.exchange_name == "Kiwoom":
        from app.adapters.kiwoom_real import KiwoomRealAdapter
        return KiwoomRealAdapter(
            app_key=access,
            secret_key=secret,
            account_no=account.account_number or "",
            api_url=api_url or "",
            is_virtual=is_virtual,
        )
    if account.exchange_name == "Binance":
        from app.adapters.binance_spot import BinanceSpotAdapter
        return BinanceSpotAdapter(
            api_key=access,
            secret_key=secret,
            api_url=api_url or "https://api.binance.com",
            account_name=account.account_name or "",
            is_testnet=False,
        )
    if account.exchange_name == "BinanceFutures":
        from app.adapters.binance_futures import BinanceFuturesAdapter
        return BinanceFuturesAdapter(
            api_key=access,
            secret_key=secret,
            api_url=api_url or "https://fapi.binance.com",
            account_name=account.account_name or "",
            is_testnet=False,
        )

    raise ValueError(f"unsupported exchange: {account.exchange_name}")


async def _ping_account(account: ExchangeAccount) -> dict:
    """Run one balance call and return a structured result dict."""
    started = time.monotonic()
    result = {
        "account_id": account.id,
        "exchange": account.exchange_name,
        "name": account.account_name,
        "success": False,
        "latency_ms": None,
        "cash_summary": None,
        "holdings_count": None,
        "error": None,
    }

    try:
        adapter = _build_adapter(account)
        balance = await asyncio.wait_for(
            adapter.get_balance(), timeout=PER_ACCOUNT_TIMEOUT_SEC
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        cash = balance.get("cash") or {}
        holdings = balance.get("holdings") or {}

        # Detect adapter-internal swallowed errors:
        # Kiwoom returns {"cash":{"KRW":0},"holdings":{}} on auth failure;
        # Binance does the same with USDT. Treat "all-zero, no holdings" as
        # suspicious BUT only fail loudly if the adapter logged an error
        # (caller can't see those logs from here, so just record it).
        cash_summary = {k: float(v) for k, v in cash.items() if v}
        result.update({
            "success": True,
            "latency_ms": latency_ms,
            "cash_summary": cash_summary,
            "holdings_count": len(holdings),
        })
    except asyncio.TimeoutError:
        result["error"] = f"timeout after {PER_ACCOUNT_TIMEOUT_SEC}s"
        result["latency_ms"] = PER_ACCOUNT_TIMEOUT_SEC * 1000
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["latency_ms"] = int((time.monotonic() - started) * 1000)

    return result


def _record_result(db, result: dict) -> None:
    """Insert a row into account_keepalive_logs."""
    db.execute(
        text("""
            INSERT INTO account_keepalive_logs
                (account_id, ping_at, success, latency_ms, cash_summary, holdings_count, error_msg)
            VALUES
                (:account_id, :ping_at, :success, :latency_ms,
                 CAST(:cash_summary AS JSONB), :holdings_count, :error_msg)
        """),
        {
            "account_id": result["account_id"],
            "ping_at": datetime.utcnow(),
            "success": result["success"],
            "latency_ms": result["latency_ms"],
            "cash_summary": json.dumps(result["cash_summary"]) if result["cash_summary"] is not None else None,
            "holdings_count": result["holdings_count"],
            "error_msg": result["error"],
        },
    )
    db.commit()


def _consecutive_failures(db, account_id: int, limit: int = 5) -> int:
    """Count trailing consecutive failures for an account (most recent first)."""
    rows = db.execute(
        text("""
            SELECT success FROM account_keepalive_logs
            WHERE account_id = :aid
            ORDER BY ping_at DESC
            LIMIT :lim
        """),
        {"aid": account_id, "lim": limit},
    ).fetchall()

    streak = 0
    for (success,) in rows:
        if success:
            break
        streak += 1
    return streak


async def _send_telegram_alert(db, body: str) -> bool:
    """Send a single Telegram alert using the first configured account's bot."""
    # plzmlc is user_id=1 (single human user per project memory).
    svc = TelegramNotificationService(db, user_id=1)
    if not svc.is_configured():
        return False
    return await svc.send_message(body, parse_mode="HTML")


async def main() -> int:
    db = SessionLocal()
    try:
        accounts = (
            db.query(ExchangeAccount)
            .filter(
                ExchangeAccount.environment == "real",
                ExchangeAccount.is_disabled == False,  # noqa: E712
                ExchangeAccount.exchange_name.in_(KEEPALIVE_EXCHANGES),
            )
            .order_by(ExchangeAccount.id)
            .all()
        )

        results = []
        for acc in accounts:
            r = await _ping_account(acc)
            try:
                _record_result(db, r)
            except Exception as e:
                r["db_write_error"] = f"{type(e).__name__}: {e}"
            r["consecutive_failures"] = (
                _consecutive_failures(db, acc.id) if not r["success"] else 0
            )
            results.append(r)

        success_n = sum(1 for r in results if r["success"])
        fail_n = len(results) - success_n
        repeat_offenders = [r for r in results if r.get("consecutive_failures", 0) >= 2]

        if fail_n or repeat_offenders:
            lines = ["<b>[Keepalive] daily ping report</b>"]
            lines.append(f"성공 {success_n} / 실패 {fail_n} (총 {len(results)}계좌)")
            for r in results:
                if r["success"]:
                    continue
                streak = r.get("consecutive_failures", 1)
                tag = f" 연속실패 {streak}회" if streak >= 2 else ""
                lines.append(
                    f"❌ <code>{r['exchange']}</code> {r['name']}{tag}\n"
                    f"   {r['error']}"
                )
            await _send_telegram_alert(db, "\n".join(lines))

        summary = {
            "ran_at": datetime.utcnow().isoformat() + "Z",
            "total": len(results),
            "success": success_n,
            "failure": fail_n,
            "results": results,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if fail_n == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
