#!/usr/bin/env python3
"""Provision v2 noop live sessions (PAPER/REAL) for a lifecycle short listing.

`.claude/plans/lifecycle_short_real_deploy.md` §5 Phase 0, component 2.

신규 상장 1건당 시그널-only 라이브 세션을 생성하고 System-2(BACKTEST) 세션과
링크한다. 세션은 `strategy_name="noop"` + `engine_version="v2"`라 자체 시그널을
내지 않으며, `lifecycle_live_signal_driver.py`가 주입하는 외부 시그널만 실행한다.

  PAPER 트랙: is_paper=true  — 실계좌 연결 + 실시간 + 체결만 시뮬
  REAL  트랙: is_paper=false — 실주문 (소액 notional)

DB INSERT는 destructive하지 않으나 production(Mint) 상태를 바꾸므로
`--commit` 없이는 기록만 출력한다(dry-run 기본).

사용:
  # PAPER 세션만 생성 + System-2 세션과 링크 (dry-run)
  python -m scripts.binance.lifecycle_live_provision \\
      --system2-id f3e9da4a-2b6 --symbol STARUSDT --track paper \\
      --account-id 8 --notional 200

  # 실제 생성
  python -m scripts.binance.lifecycle_live_provision ... --commit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lifecycle_live_provision")

LINKS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "live_links.json"


def _noop_v2_config(*, leverage: int = 1) -> dict:
    """Minimal v2 noop config. noop emits no signals — only engine_version,
    leverage and short position_side matter for the injected lifecycle shorts."""
    return {
        "interval": "1d",
        "engine_version": "v2",
        "leverage": int(leverage),
        "position_side": "short",
        "margin_type": "ISOLATED",
        "qty_mode": "external",  # quantity comes from submitted signals
        "orders_enabled": True,
    }


def _db_engine():
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    load_dotenv(ROOT / ".env")
    db_url = (
        f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_SERVER', 'localhost')}:5432/{os.environ['POSTGRES_DB']}"
    )
    return create_engine(db_url)


def _load_links() -> dict:
    if not LINKS_PATH.exists():
        return {}
    try:
        return json.loads(LINKS_PATH.read_text())
    except json.JSONDecodeError:
        log.error("Corrupt %s — refusing to overwrite. Fix manually.", LINKS_PATH)
        raise


def _save_links(links: dict) -> None:
    LINKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LINKS_PATH.write_text(json.dumps(links, indent=2))


def provision(args) -> int:
    track = args.track.lower()
    if track not in ("paper", "real"):
        log.error("--track must be paper|real")
        return 2
    is_paper = (track == "paper")

    session_id = args.session_id or f"lifecycle-{track}-{args.symbol.lower()}-{uuid.uuid4().hex[:6]}"
    config = _noop_v2_config(leverage=args.leverage)
    name = f"lifecycle_{track}_{args.symbol}"

    log.info("Plan: session_id=%s symbol=%s track=%s is_paper=%s account_id=%s "
             "initial_capital=%s leverage=%s notional=%.2f link→system2=%s",
             session_id, args.symbol, track, is_paper, args.account_id,
             args.initial_capital, args.leverage, args.notional, args.system2_id)
    log.info("config=%s", json.dumps(config))

    if not args.commit:
        log.info("[DRY-RUN] no DB write, no link update. Re-run with --commit to apply.")
        return 0

    from sqlalchemy import text
    engine = _db_engine()
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT id FROM live_bot_sessions WHERE id = :id"), {"id": session_id}
        ).fetchone()
        if exists:
            log.error("Session %s already exists — aborting (idempotency guard).", session_id)
            return 1
        conn.execute(text("""
            INSERT INTO live_bot_sessions (
                id, account_id, symbol, strategy_name, strategy_config,
                "interval", initial_capital, current_capital,
                is_paper, is_active, orders_enabled, status, started_at,
                leverage, margin_type, position_mode,
                original_symbol, original_symbol_name
            ) VALUES (
                :id, :account_id, :symbol, 'noop', cast(:config as json),
                '1d', :cap, :cap,
                :is_paper, true, true, 'RUNNING', NOW(),
                :leverage, 'ISOLATED', 'ONE_WAY',
                :symbol, :symbol
            )
        """), {
            "id": session_id, "account_id": args.account_id, "symbol": args.symbol,
            "config": json.dumps(config), "cap": args.initial_capital,
            "is_paper": is_paper, "leverage": args.leverage,
        })
        conn.commit()
    log.info("[COMMITTED] created live_bot_session %s", session_id)

    # Update link registry
    links = _load_links()
    entry = links.get(args.system2_id, {"symbol": args.symbol, "paper": None,
                                         "real": None, "notional_usdt": args.notional})
    entry["symbol"] = args.symbol
    entry["notional_usdt"] = args.notional
    entry[track] = session_id
    links[args.system2_id] = entry
    _save_links(links)
    log.info("[LINKED] %s.%s = %s (notional=%.2f) → %s", args.system2_id, track,
             session_id, args.notional, LINKS_PATH)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Provision a v2 noop live session for a lifecycle listing.")
    p.add_argument("--system2-id", required=True, help="System-2 lifecycle paper session id (BACKTEST track) to link")
    p.add_argument("--symbol", required=True, help="e.g. STARUSDT")
    p.add_argument("--track", required=True, choices=["paper", "real"])
    p.add_argument("--account-id", type=int, required=True, help="exchange_accounts.id to bind")
    p.add_argument("--notional", type=float, default=200.0, help="USDT notional per short (link config)")
    p.add_argument("--initial-capital", dest="initial_capital", type=float, default=1_000_000.0,
                   help="session equity baseline (PAPER: match System-2 1e6; REAL: small)")
    p.add_argument("--leverage", type=int, default=1)
    p.add_argument("--session-id", default=None, help="override generated session id")
    p.add_argument("--commit", action="store_true", default=False, help="actually write to DB + links")
    return p


if __name__ == "__main__":
    sys.exit(provision(build_parser().parse_args()))
