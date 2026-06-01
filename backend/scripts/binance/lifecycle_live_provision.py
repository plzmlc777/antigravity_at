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
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lifecycle_live_provision")

LINKS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "live_links.json"
STORE_ROOT = ROOT / "runs" / "paper_sessions"


def _noop_v2_config(*, leverage: int = 1) -> dict:
    """Minimal v2 noop config. noop emits no signals — only engine_version,
    leverage and short position_side matter for the injected lifecycle shorts."""
    return {
        "interval": "1d",
        "engine_version": "v2",
        "leverage": int(leverage),
        "position_side": "short",
        # CROSSED: account이 Multi-Assets 모드면 ISOLATED 설정이 -4168로 거부됨
        # (Phase 0 배관 점검에서 확인). leverage 1x라 격리 효과는 동일.
        "margin_type": "CROSSED",
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


def _scan_lifecycle_sessions(name_filter: str) -> list[dict]:
    """Scan System-2 paper-session store for active sessions whose name contains
    `name_filter`. Returns [{session_id, symbol, name}] (filesystem-only, no heavy import)."""
    out: list[dict] = []
    if not STORE_ROOT.exists():
        return out
    for d in sorted(STORE_ROOT.iterdir()):
        sj = d / "session.json"
        if not sj.is_file():
            continue
        try:
            s = json.loads(sj.read_text())
        except json.JSONDecodeError:
            continue
        if s.get("status") != "active":
            continue
        if name_filter not in (s.get("name") or ""):
            continue
        out.append({"session_id": s.get("session_id"), "symbol": s.get("symbol"),
                    "name": s.get("name")})
    return out


def _provision_one(*, system2_id: str, symbol: str, track: str, account_id: int,
                   notional: float, initial_capital: float, leverage: int,
                   session_id: Optional[str], commit: bool) -> int:
    """Provision one v2 noop live session for (system2_id, symbol, track) and link it.
    Idempotent: skips if the track is already linked for this system2_id."""
    is_paper = (track == "paper")
    links = _load_links()
    existing = links.get(system2_id, {})
    if existing.get(track):
        log.info("[SKIP] %s.%s already linked → %s", system2_id, track, existing[track])
        return 0

    sid = session_id or f"lifecycle-{track}-{symbol.lower()}-{uuid.uuid4().hex[:6]}"
    config = _noop_v2_config(leverage=leverage)
    log.info("Plan: session_id=%s symbol=%s track=%s is_paper=%s account_id=%s "
             "cap=%s lev=%s notional=%.2f link→system2=%s",
             sid, symbol, track, is_paper, account_id, initial_capital, leverage,
             notional, system2_id)

    if not commit:
        log.info("[DRY-RUN] no DB write, no link update.")
        return 0

    from sqlalchemy import text
    engine = _db_engine()
    with engine.connect() as conn:
        if conn.execute(text("SELECT id FROM live_bot_sessions WHERE id = :id"),
                        {"id": sid}).fetchone():
            log.error("Session %s already exists — aborting (idempotency guard).", sid)
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
                :leverage, 'CROSSED', 'ONE_WAY',
                :symbol, :symbol
            )
        """), {
            "id": sid, "account_id": account_id, "symbol": symbol,
            "config": json.dumps(config), "cap": initial_capital,
            "is_paper": is_paper, "leverage": leverage,
        })
        conn.commit()
    log.info("[COMMITTED] created live_bot_session %s", sid)

    links = _load_links()  # reload (avoid clobber if changed)
    entry = links.get(system2_id, {"symbol": symbol, "paper": None,
                                    "real": None, "notional_usdt": notional})
    entry["symbol"] = symbol
    entry["notional_usdt"] = notional
    entry[track] = sid
    links[system2_id] = entry
    _save_links(links)
    log.info("[LINKED] %s.%s = %s (notional=%.2f)", system2_id, track, sid, notional)
    return 0


def auto_link(args) -> int:
    """Scan System-2 lifecycle earlyexit_d14 sessions and provision+link a PAPER
    session for any not yet linked. Idempotent — safe to run every cycle.
    REAL track is never auto-provisioned (Phase 1, manual)."""
    sessions = _scan_lifecycle_sessions(args.name_filter)
    log.info("auto-link scan: %d active '%s' System-2 sessions", len(sessions), args.name_filter)
    rc = 0
    for s in sessions:
        if not s.get("session_id") or not s.get("symbol"):
            continue
        r = _provision_one(
            system2_id=s["session_id"], symbol=s["symbol"], track="paper",
            account_id=args.account_id, notional=args.notional,
            initial_capital=args.initial_capital, leverage=args.leverage,
            session_id=None, commit=args.commit)
        rc = rc or r
    return rc


def provision(args) -> int:
    if getattr(args, "auto_link", False):
        return auto_link(args)
    track = args.track.lower() if args.track else None
    if track not in ("paper", "real"):
        log.error("--track must be paper|real (or use --auto-link)")
        return 2
    if not args.system2_id or not args.symbol:
        log.error("--system2-id and --symbol required (or use --auto-link)")
        return 2
    return _provision_one(
        system2_id=args.system2_id, symbol=args.symbol, track=track,
        account_id=args.account_id, notional=args.notional,
        initial_capital=args.initial_capital, leverage=args.leverage,
        session_id=args.session_id, commit=args.commit)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Provision v2 noop live session(s) for lifecycle listings.")
    p.add_argument("--auto-link", dest="auto_link", action="store_true", default=False,
                   help="scan System-2 lifecycle earlyexit_d14 sessions and provision+link a PAPER "
                        "session for any not yet linked (idempotent; REAL never auto-provisioned)")
    p.add_argument("--name-filter", default="earlyexit_d14",
                   help="System-2 session name substring to auto-link (default: earlyexit_d14)")
    # single-provision args (ignored in --auto-link mode)
    p.add_argument("--system2-id", default=None, help="System-2 lifecycle paper session id to link")
    p.add_argument("--symbol", default=None, help="e.g. STARUSDT")
    p.add_argument("--track", default=None, choices=["paper", "real"])
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
