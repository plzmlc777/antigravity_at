"""Incremental ka10080 backfill for KR 1m OHLCV.

Differs from swap_ohlcv.py which does DELETE+INSERT for a single symbol.
This script fetches recent minute bars for multiple symbols and INSERTs
only rows whose timestamp is strictly newer than the table's current max
for that symbol+time_frame. Safe to run repeatedly — never touches
existing history.

Pages are fetched until either max_pages is hit or the oldest fetched
timestamp goes below the table's current max (whichever comes first).

Usage:
    cd backend && source venv/bin/activate
    PYTHONPATH=. python3 kr_ohlcv_incremental_backfill.py \
        --symbols 005930,061090,122630 --max-pages 30
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.core.token_manager import KiwoomTokenManager
from app.core.http_client import HttpClientManager
from app.core import security
from app.core.trading_env import get_api_url, env_from_string
from app.db.session import SessionLocal, engine
from app.models.user import User  # noqa: F401
from app.models.account import ExchangeAccount
from app.adapters.kiwoom_real import _rate_limited_post


def _to_int(v):
    try:
        return abs(int(str(v).replace("+", "").replace("-", "")))
    except Exception:
        return 0


async def fetch_pages(token, base_url, symbol: str, max_pages: int, stop_before):
    """Fetch ka10080 pages newest-first until we go below stop_before."""
    rows = []
    cont_yn = "N"
    cont_key = ""
    for page in range(1, max_pages + 1):
        body = {"stk_cd": symbol, "tic_scope": "1", "upd_stkpc_tp": "1"}
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "cont-yn": cont_yn,
            "next-key": cont_key,
            "api-id": "ka10080",
        }
        resp = await _rate_limited_post(
            f"{base_url}/api/dostk/chart", headers=headers, json=body, timeout=15.0
        )
        if resp.status_code != 200:
            print(f"  [{symbol}/p{page}] HTTP {resp.status_code}: {resp.text[:200]}")
            break
        rj = resp.json()
        if rj.get("return_code") != 0:
            print(f"  [{symbol}/p{page}] API err: {rj.get('return_msg')}")
            break
        items = rj.get("stk_min_pole_chart_qry", []) or []
        if not items:
            print(f"  [{symbol}/p{page}] no items, stop")
            break

        added = 0
        for it in items:
            ts_str = it.get("cntr_tm")
            if not ts_str or len(ts_str) != 14:
                continue
            ts = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            if stop_before is not None and ts <= stop_before:
                continue
            rows.append({
                "symbol": symbol,
                "timestamp": ts,
                "time_frame": "1m",
                "open": _to_int(it.get("open_pric")),
                "high": _to_int(it.get("high_pric")),
                "low": _to_int(it.get("low_pric")),
                "close": _to_int(it.get("cur_prc")),
                "volume": int(it.get("trde_qty", 0)),
            })
            added += 1

        oldest_in_page = min(
            (datetime.strptime(it.get("cntr_tm"), "%Y%m%d%H%M%S")
             for it in items if it.get("cntr_tm") and len(it.get("cntr_tm")) == 14),
            default=None,
        )
        print(f"  [{symbol}/p{page}] items={len(items)} added={added} oldest={oldest_in_page} stop_before={stop_before}")

        if stop_before is not None and oldest_in_page is not None and oldest_in_page <= stop_before:
            print(f"  [{symbol}] reached stop_before, halt")
            break

        cont_yn = resp.headers.get("cont-yn", "N")
        cont_key = resp.headers.get("next-key", "")
        if cont_yn != "Y" or not cont_key:
            print(f"  [{symbol}] no more pages (cont-yn={cont_yn})")
            break

    return rows


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True)
    p.add_argument("--max-pages", type=int, default=30)
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"Symbols: {symbols} max_pages={args.max_pages}")

    db = SessionLocal()
    acct = (
        db.query(ExchangeAccount)
        .filter(ExchangeAccount.exchange_name.ilike("%kiwoom%"))
        .filter(ExchangeAccount.is_disabled == False)
        .filter(ExchangeAccount.environment == "real")
        .order_by(ExchangeAccount.id.desc())
        .first()
    )
    if not acct:
        print("ERROR: no kiwoom ExchangeAccount", file=sys.stderr)
        sys.exit(1)
    api_key = security.decrypt_key(acct.encrypted_access_key)
    api_secret = security.decrypt_key(acct.encrypted_secret_key)
    env = env_from_string(acct.environment or "real")
    base_url = get_api_url(env)
    print(f"EA: {acct.account_name}  URL: {base_url}")

    HttpClientManager.get_instance()
    tm = KiwoomTokenManager.get_instance()
    token = await tm.get_token(api_key, api_secret, base_url)
    if not token:
        print("ERROR: token issue", file=sys.stderr)
        sys.exit(1)
    print(f"Token OK (len={len(token)})")

    total_inserted = 0
    for sym in symbols:
        cur_max = db.execute(
            text("SELECT MAX(timestamp) FROM ohlcv WHERE symbol=:s AND time_frame='1m'"),
            {"s": sym},
        ).scalar()
        print(f"\n=== {sym} === current max={cur_max}")

        rows = await fetch_pages(token, base_url, sym, args.max_pages, cur_max)
        if not rows:
            print(f"  {sym}: nothing new")
            continue

        seen = set()
        deduped = []
        for r in rows:
            k = (r["symbol"], r["timestamp"], r["time_frame"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(r)
        print(f"  {sym}: {len(deduped)} new rows to insert")

        with engine.begin() as conn:
            insert_sql = text("""
                INSERT INTO ohlcv (symbol, timestamp, time_frame, open, high, low, close, volume, created_at)
                VALUES (:symbol, :timestamp, :time_frame, :open, :high, :low, :close, :volume, NOW())
            """)
            for i in range(0, len(deduped), 2000):
                conn.execute(insert_sql, deduped[i : i + 2000])
            total_inserted += len(deduped)
        print(f"  {sym}: inserted {len(deduped)}")

    print(f"\nGrand total inserted: {total_inserted}")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
