#!/usr/bin/env python3
"""
Prepare Korean stock market context file for symbol-scout agent.
Fetches stock list + rankings via backend services (using Kiwoom account 1).
Outputs JSON in the same format as symbol-evaluator expects.

Usage:
    python prepare_kr_context.py --out /tmp/kr_ctx.json
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, "/home/hcpark/auto_trading/backend")
# Import all models so SQLAlchemy relationships resolve
from app.models import user, account, live_trading, ohlcv, strategy_info, strategy_config, strategy_request, strategy_result, bot, condition, analysis_report, system, new_orders

async def main(out_path: str):
    from app.core.ai_symbol_selection import AISymbolSelectionService
    from app.db.session import SessionLocal
    from app.models.account import ExchangeAccount

    db = SessionLocal()
    try:
        account = db.query(ExchangeAccount).filter(
            ExchangeAccount.exchange_name == "Kiwoom",
            ExchangeAccount.is_disabled == False,
            ExchangeAccount.environment == "real",
        ).order_by(ExchangeAccount.id).first()
        if not account:
            print("ERROR: no active Kiwoom account", file=sys.stderr)
            return 1
        account_id = account.id
    finally:
        db.close()

    svc = AISymbolSelectionService.get_instance()
    api_url, token = await svc._get_token(account_id)
    if not api_url or not token:
        print("ERROR: failed to obtain Kiwoom token", file=sys.stderr)
        return 1

    stocks, rankings = await svc._fetch_market_data(api_url, token)
    if stocks is None or rankings is None:
        print("ERROR: market data fetch failed", file=sys.stderr)
        return 1

    # Cap rankings to 100 per category (same as ai_symbol_selection does)
    trimmed = {k: (v or [])[:100] for k, v in rankings.items()}

    ctx = {
        "mode": "SCAN",
        "stocks": stocks,
        "rankings": trimmed,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False)
    print(f"OK wrote {out_path}: stocks={len(stocks)} ranking_categories={len(trimmed)}")
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.out)))
