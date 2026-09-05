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
# Import User before Account so the relationship('User') back-ref on
# ExchangeAccount.user resolves at mapper-configure time. Standalone scripts
# don't import the FastAPI app graph, so the User class would otherwise be
# unknown and the first ExchangeAccount query would raise InvalidRequestError.
from app.models.user import User  # noqa: E402,F401
from app.models.account import ExchangeAccount  # noqa: E402

PER_ACCOUNT_TIMEOUT_SEC = 30
KEEPALIVE_EXCHANGES = ("Kiwoom", "Binance", "BinanceFutures")

# ── 앱키 나이 추적 ──
#
# 2026-09-04, 키움이 계좌 1·13·4 의 앱키를 "3개월 미사용"으로 해지했다.
# keepalive 는 정상 동작했고 해지 당일 새벽까지 ok=True 였다 — 즉 **막히기
# 전에는 아무 신호도 없다.** 사후에 알면 늦으므로 키가 몇 살인지 세어
# 미리 알린다.
#
# 키 자체는 저장하지 않는다. **지문(해시)만** 남기고, 지문이 바뀌면 그날을
# 새 등록일로 본다. 따로 기록할 필요 없이 교체가 자동 감지된다.
KEY_AGE_FILE = BACKEND_DIR / "runs" / "api_key_ages.json"
KEY_AGE_WARN_DAYS = 60      # 3개월 기준이면 한 달 전에 알린다
KEY_AGE_URGENT_DAYS = 80
# 미사용 해지 정책이 확인된 곳만 경보한다. 바이낸스는 그런 사례가 없고,
# 오탐이 섞이면 경보 자체가 무시된다. 기록은 모든 계좌에 대해 남긴다.
KEY_AGE_ALERT_EXCHANGES = ("Kiwoom", "KiwoomUS")


def _key_fingerprint(account) -> str:
    """앱키의 지문. 평문은 남기지 않는다."""
    import hashlib

    from app.core import security as _sec
    raw = _sec.decrypt_key(account.encrypted_access_key or "") or ""
    return hashlib.sha256(raw.encode()).hexdigest()[:16] if raw else ""


def _track_key_ages(accounts) -> list:
    """계좌별 앱키 나이를 갱신하고, 오래된 것만 돌려준다."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        store = json.loads(KEY_AGE_FILE.read_text()) if KEY_AGE_FILE.exists() else {}
    except Exception:
        store = {}

    aged = []
    for acc in accounts:
        fp = _key_fingerprint(acc)
        if not fp:
            continue
        key = str(acc.id)
        rec = store.get(key)
        if not rec or rec.get("fingerprint") != fp:
            # 처음 보거나 키가 바뀌었다 → 오늘을 기준일로.
            # ⚠ 이건 **최초 관측일**이지 발급일이 아니다. 추적을 시작하기 전에
            #   이미 쓰던 키는 실제보다 어리게 잡힌다 — 나이가 과소평가되는
            #   방향이라 경보가 늦을 수는 있어도 오탐은 안 난다.
            store[key] = {"fingerprint": fp, "first_seen": today,
                          "name": acc.account_name, "exchange": acc.exchange_name}
            continue
        try:
            first = datetime.strptime(rec["first_seen"], "%Y-%m-%d")
        except Exception:
            continue
        age = (datetime.now() - first).days
        if age >= KEY_AGE_WARN_DAYS and acc.exchange_name in KEY_AGE_ALERT_EXCHANGES:
            aged.append({"id": acc.id, "name": acc.account_name,
                         "exchange": acc.exchange_name, "age_days": age,
                         "since": rec["first_seen"],
                         "urgent": age >= KEY_AGE_URGENT_DAYS})
    try:
        KEY_AGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_AGE_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2))
    except Exception:
        pass
    return aged


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
    """Run one balance call and return a structured result dict.

    Auth failure must surface as `success=False`. The adapter `get_balance()`
    methods swallow exceptions and return zero-balance dicts on failure, so
    we route through endpoints that raise instead:

    - Binance / BinanceFutures: use `test_connection()` from BinanceBaseAdapter,
      which calls the signed account endpoint and raises BinanceAPIError on
      `-2015 Invalid API-key/IP` and similar auth failures. It also returns a
      cash + holdings_count summary, so we don't need a second call.
    - Kiwoom: call `_ensure_token()` and verify `access_token` is populated
      afterward. The token manager logs but doesn't raise on failure, so a
      None access_token after this call means the credentials were rejected.
      Once the token is good, the swallowing `get_balance()` is safe to use.
    """
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

        if account.exchange_name == "Kiwoom":
            await asyncio.wait_for(
                adapter._ensure_token(), timeout=PER_ACCOUNT_TIMEOUT_SEC
            )
            if not adapter.access_token:
                raise RuntimeError(
                    "kiwoom token issuance failed (invalid app_key/secret or server rejection)"
                )
            balance = await asyncio.wait_for(
                adapter.get_balance(), timeout=PER_ACCOUNT_TIMEOUT_SEC
            )
            cash = balance.get("cash") or {}
            holdings = balance.get("holdings") or {}
            cash_summary = {k: float(v) for k, v in cash.items() if v}
            holdings_count = len(holdings)
        else:
            # Binance / BinanceFutures — test_connection raises on auth failure
            summary = await asyncio.wait_for(
                adapter.test_connection(), timeout=PER_ACCOUNT_TIMEOUT_SEC
            )
            cash = summary.get("cash") or {}
            cash_summary = {k: float(v) for k, v in cash.items() if v}
            holdings_count = int(summary.get("holdings_count", 0))

        latency_ms = int((time.monotonic() - started) * 1000)
        result.update({
            "success": True,
            "latency_ms": latency_ms,
            "cash_summary": cash_summary,
            "holdings_count": holdings_count,
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

        aged_keys = _track_key_ages(accounts)

        if fail_n or repeat_offenders or aged_keys:
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
            if aged_keys:
                lines.append("")
                lines.append("<b>🔑 앱키가 오래됐다 — 갱신 검토</b>")
                for a in aged_keys:
                    mark = "🚨" if a["urgent"] else "⚠️"
                    lines.append(
                        f"{mark} <code>{a['exchange']}</code> {a['name']} "
                        f"— {a['age_days']}일 (최초 관측 {a['since']})")
                lines.append("<i>키움은 미사용 기간이 길면 앱키를 해지한다"
                             " (2026-09-04 계좌 1·13·4 실제 해지)</i>")
            await _send_telegram_alert(db, "\n".join(lines))

        summary = {
            "ran_at": datetime.utcnow().isoformat() + "Z",
            "total": len(results),
            "success": success_n,
            "failure": fail_n,
            "aged_keys": aged_keys,
            "results": results,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if fail_n == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
