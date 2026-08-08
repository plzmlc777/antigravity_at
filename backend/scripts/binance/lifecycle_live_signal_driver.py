#!/usr/bin/env python3
"""Lifecycle decay short — live signal driver (3-track parallel, STATE-RECONCILE).

설계 (`.claude/plans/lifecycle_short_real_deploy.md` §3.5):
  하나의 결정 소스(System-2 lifecycle paper 세션 = BACKTEST 트랙)의 **현재 포지션
  상태**를, 페어링된 v2 noop 라이브 세션(PAPER + REAL)에 `/submit-signal`로
  맞춰 동기화한다. 시그널 계산은 검증된 `BinanceLifecycleDecayEarlyExitSource` +
  `LifecycleDecayEarlyExitPolicy`가 이미 daily 사이클에서 수행하므로 재구현이 없다
  (트랙 B 사망원인인 backtest→live divergence를 구조적으로 제거).

왜 transition이 아니라 state reconcile인가:
  진입 전이(flat→short)는 상장 Day-1에 1회만 발생 → 그 순간 라이브 세션 엔진이
  로드돼 있지 않으면(신규 INSERT는 백엔드 재시작 전 미로드) 영구히 놓친다. 또한
  세션을 포지션 보유 도중에 편입하면(예: STAR 파일럿) 진입을 못 잡는다.
  대신 매 사이클 "System-2의 현재 side"와 "각 라이브 세션에 내가 의도한 side"를
  비교해 불일치만 보정하면: 놓친 진입을 다음 사이클에 catch-up, 재시도 안전,
  도중 편입도 정상 진입.

상태:
  desired = System-2 최신 CycleResult.side_after ("short"이면 short, 그 외 flat)
  intended[track] = 내가 그 트랙에 마지막으로 성사시킨 side (live_signal_state.json)
  desired != intended → 보정:
    desired short, intended flat  → side="short"          (entry / catch-up)
    desired flat,  intended short → side="close_position"  (exit)
  intended은 **제출 성공 시에만** 갱신 → 404(엔진 미로드)/실패 시 다음 사이클 재시도.

실행: PM2 binance-paper-cycle가 `paper_session_cli run --all` 직후 본 드라이버
  `--submit` 실행 (run_binance_paper_cycle.sh).

안전장치:
  - 기본 --dry-run: POST 안 함, 의도만 출력.
  - --submit 있어야 실제 POST. REAL 세션은 추가로 --include-real 필요.

링크 레지스트리 (runs/research_track/lifecycle_phase/live_links.json):
  { "<system2_session_id>": {"symbol","paper","real","notional_usdt"}, ... }
상태 파일 (live_signal_state.json):
  { "<system2_session_id>": {"paper": "short"|"flat", "real": "short"|"flat"} }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import requests

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lifecycle_live_signal_driver")

STORE_ROOT = ROOT / "runs" / "paper_sessions"
LINKS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "live_links.json"
STATE_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "live_signal_state.json"
TELEGRAM_CHATS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "telegram_chats.json"

SIGNAL_SOURCE = "skill:lifecycle_decay_d14"
MIN_REAL_NOTIONAL = 5.0  # Binance Futures min notional (~$5); skip below this
REAL_MARGIN_FRACTION = 0.97  # deploy 97% of available margin (3% buffer: taker fee + price drift between size-time and fill)

# Per-symbol margin cap, as a fraction of TOTAL WALLET BALANCE (not available
# margin — available shrinks as positions open, so capping off it lets the first
# entry take everything and starve every later listing).
#
# Why: full-compound sizing put 86% of the account into a single name
# (GRVTUSDT 2026-08-02, 654 of 758 USDT) and drove availableBalance to 0, so no
# new listing could be entered for the rest of that position's 30-day hold. The
# paradigm's edge is diversification across many Day-1 listings — R-3 measures
# it per-listing on a 129-symbol cohort — and a single-name all-in throws that
# away while adding a fat left tail.
#
# Value from notional_cap_portfolio_sim.py (129-listing calendar, 1x, SL 50%,
# 30d hold, $593 seed). Return is NOT usable for choosing the cap — the best
# cap by return flips between 100% / 30% / 25% across time splits (single path,
# heavy overlap). These three axes are monotone in every split:
#   cap    포착률   MDD      최악 단일거래
#   100%    27.9%  -66.1%   -372.50   ← 129개 중 93개를 자본이 없어 못 잡음
#    30%    48.8%  -52.8%    -89.16
#    20%    60.5%  -37.7%    -73.67   ← MDD 플래토 진입점
#    15%    68.2%  -36.4%    -61.91
#    10%    82.9%  -41.0%    -33.82   ← MDD 다시 악화
# 15~20%가 MDD 플래토다. R-3 방법론(단일 최적 대신 플래토 채택)을 따라 20%.
# 잔여 -37.7% MDD는 상한으로 못 없앤다 — 패러다임 고유의 두꺼운 왼쪽 꼬리다.
REAL_MAX_SYMBOL_FRACTION = 0.20

# Hard final-exit after the lifecycle hold window. The decay source oscillates
# short↔flat every bar (vol_cliff early-exit fires then re-enters); the daily
# reconcile only sees the LAST bar, so a position whose last bar is short reads
# "in sync (short)" and is NEVER closed — it sits open past Day-30 with the P&L
# stuck unrealized (incident 2026-07-27: REU/ARX/OUSDT held 32-38d). Once a
# driving session is older than this, force flat AND retire the link so it can
# never re-enter. 30 = baseline hold; +1 grace bar.
HARD_EXIT_DAYS = 31

_ASYNC_LOOP = None


def _run_async(coro):
    """Run a coroutine on a persistent event loop reused across all calls in this
    process. The Binance async adapter binds a global HTTP client to the running
    loop; asyncio.run() closes its loop each call, so a 2nd adapter call hits
    'Event loop is closed'. Reusing one loop keeps the client valid for the whole
    driver run (balance + per-symbol position queries)."""
    global _ASYNC_LOOP
    if _ASYNC_LOOP is None or _ASYNC_LOOP.is_closed():
        _ASYNC_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_ASYNC_LOOP)
    return _ASYNC_LOOP.run_until_complete(coro)


def _real_available_usdt(account_id: int) -> float:
    """Query a real account's available USDT margin (shared cross-margin pool).
    Builds an adapter from the account row (decrypts keys) — Mint-only path."""
    import asyncio
    try:
        from app.db.session import SessionLocal
        from app.models.account import ExchangeAccount
        from app.api.endpoints import create_adapter_from_account
    except Exception as exc:  # not on backend host / import unavailable
        log.error("REAL balance import failed (%s) — cannot size REAL", exc)
        return 0.0
    db = SessionLocal()
    try:
        acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == int(account_id)).first()
        if not acc:
            log.error("REAL account_id=%s not found", account_id)
            return 0.0
        adapter = create_adapter_from_account(acc)
        bal = _run_async(adapter.get_balance())
        return float((bal or {}).get("cash", {}).get("USDT", 0.0))
    except Exception as exc:
        log.error("REAL balance query failed for account %s: %s", account_id, exc)
        return 0.0
    finally:
        db.close()


def _real_equity_usdt(account_id: int) -> float:
    """Total wallet balance (USD) for a real futures account.

    This is the base for REAL_MAX_SYMBOL_FRACTION. get_balance() only surfaces
    availableBalance, which drops toward 0 as positions open — useless as a cap
    denominator. Reads totalWalletBalance off /fapi/v2/account directly.
    Returns 0.0 on any failure so the caller can fall back to the uncapped path.
    """
    try:
        from app.db.session import SessionLocal
        from app.models.account import ExchangeAccount
        from app.api.endpoints import create_adapter_from_account
    except Exception as exc:
        log.error("REAL equity import failed (%s)", exc)
        return 0.0
    db = SessionLocal()
    try:
        acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == int(account_id)).first()
        if not acc:
            log.error("REAL account_id=%s not found", account_id)
            return 0.0
        adapter = create_adapter_from_account(acc)
        if not hasattr(adapter, "_signed_get"):
            log.warning("adapter for account %s exposes no _signed_get — equity unavailable", account_id)
            return 0.0
        _run_async(adapter._ensure_time_sync())
        data = _run_async(adapter._signed_get("/fapi/v2/account"))
        return float((data or {}).get("totalWalletBalance") or 0.0)
    except Exception as exc:
        log.error("REAL equity query failed for account %s: %s", account_id, exc)
        return 0.0
    finally:
        db.close()


def _real_notify_chats(default_chat: Optional[str]) -> list:
    """REAL alert destination chat_ids. Reads telegram_chats.json (list) for
    multi-group fan-out; falls back to the account's single chat_id."""
    try:
        if TELEGRAM_CHATS_PATH.exists():
            chats = [str(c) for c in json.loads(TELEGRAM_CHATS_PATH.read_text()) if c]
            if chats:
                return chats
    except Exception as exc:
        log.error("telegram_chats.json read failed (%s) — fallback to account chat", exc)
    return [str(default_chat)] if default_chat else []


def _telegram_notify(account_id: int, text: str) -> None:
    """Send a Telegram message to ALL configured REAL chats (multi-group). Uses the
    account's bot token; destinations from telegram_chats.json (or account chat_id).
    No-op if unconfigured. REAL-track only. Mint-only path."""
    import urllib.request
    import urllib.parse
    try:
        from app.db.session import SessionLocal
        from app.models.user import User  # noqa: F401 — resolves ExchangeAccount.user mapper
        from app.models.account import ExchangeAccount
        from app.core import security
    except Exception as exc:
        log.error("telegram import failed (%s)", exc)
        return
    db = SessionLocal()
    try:
        acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == int(account_id)).first()
        if not acc or not acc.encrypted_telegram_bot_token:
            log.info("telegram not configured for account %s — skip notify", account_id)
            return
        token = security.decrypt_key(acc.encrypted_telegram_bot_token)
        chats = _real_notify_chats(acc.telegram_chat_id)
    finally:
        db.close()
    if not token or not chats:
        log.info("telegram token/chats missing — skip notify")
        return
    for cid in chats:
        try:
            data = urllib.parse.urlencode(
                {"chat_id": cid, "text": text, "parse_mode": "HTML"}).encode()
            resp = urllib.request.urlopen(
                urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data),
                timeout=12)
            log.info("telegram sent → %s", cid)
            try:
                import json as _json
                from app.core.telegram_sent_log import record_sent, extract_message_id
                mid = extract_message_id(_json.loads(resp.read().decode()))
                record_sent(cid, mid, text, source="lifecycle_notify")
            except Exception:
                pass
        except Exception as exc:
            log.error("telegram send failed → %s: %s", cid, exc)


def _real_trade_result(session_id: str) -> Optional[tuple]:
    """(last_cover_realized_pnl, current_capital, initial_capital) for a REAL session."""
    try:
        from app.db.session import SessionLocal
        from sqlalchemy import text as sqltext
    except Exception:
        return None
    db = SessionLocal()
    try:
        row = db.execute(sqltext(
            "SELECT realized_pnl FROM live_trade_executions WHERE session_id=:s "
            "AND status='FILLED' AND signal_type='BUY' ORDER BY signal_timestamp DESC LIMIT 1"
        ), {"s": session_id}).fetchone()
        cap = db.execute(sqltext(
            "SELECT initial_capital, current_capital FROM live_bot_sessions WHERE id=:s"
        ), {"s": session_id}).fetchone()
        last = float(row[0]) if row and row[0] is not None else None
        init = float(cap[0]) if cap and cap[0] is not None else None
        cur = float(cap[1]) if cap and cap[1] is not None else None
        return (last, cur, init)
    except Exception:
        return None
    finally:
        db.close()


def _real_symbol_state(account_id: int, symbol: str) -> tuple[float, float]:
    """(mark_price, signed_position_qty) for a symbol on a REAL account.

    mark_price ← PUBLIC premiumIndex (no auth) — reliable for live-price sizing
    even when flat (positionRisk returns markPrice 0 for a flat symbol, so it
    can't be used for sizing). position_qty ← signed positionRisk via the account
    adapter (neg=short → double-entry guard + fill confirmation; 0.0 = flat).
    mark_price 0.0 only on public-endpoint failure → caller skips. Mint-only path."""
    # 1) live mark price (public, no auth)
    mark = 0.0
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex",
                         params={"symbol": symbol}, timeout=10)
        r.raise_for_status()
        mark = float(r.json().get("markPrice") or 0.0)
    except Exception as exc:
        log.error("mark price fetch failed for %s: %s", symbol, exc)
    # 2) signed position quantity
    qty = 0.0
    try:
        from app.db.session import SessionLocal
        from app.models.account import ExchangeAccount
        from app.api.endpoints import create_adapter_from_account
        db = SessionLocal()
        try:
            acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == int(account_id)).first()
            if acc:
                adapter = create_adapter_from_account(acc)
                pos = _run_async(adapter.get_position(symbol))
                qty = float((pos or {}).get("quantity") or 0.0)
            else:
                log.error("REAL account_id=%s not found", account_id)
        finally:
            db.close()
    except Exception as exc:
        log.error("REAL position query failed for %s/%s: %s", account_id, symbol, exc)
    return (mark, qty)


def _real_realized_since(adapter, symbol: str, minutes: int = 15) -> float:
    """Sum REALIZED_PNL income for a symbol over the last N minutes (exchange
    is the source of truth for realized P&L on a direct close)."""
    try:
        import time as _time
        from app.adapters.binance_futures import FAPI
        start_ms = int((_time.time() - minutes * 60) * 1000)
        inc = _run_async(adapter._signed_get(
            f"{FAPI}/income",
            {"incomeType": "REALIZED_PNL", "symbol": symbol, "startTime": start_ms, "limit": 100}))
        return sum(float(i.get("income", 0)) for i in (inc or []))
    except Exception as exc:
        log.warning("realized income lookup failed for %s: %s", symbol, exc)
        return 0.0


def _real_direct_close(account_id: int, symbol: str, session_id: str) -> Optional[float]:
    """Close a REAL position DIRECTLY on the exchange (engine-independent) and
    record the fill into live_trade_executions so reports stay accurate.

    Why not the engine: these lifecycle sessions are qty_mode=external, so the
    engine keeps no position_snapshot; after a backend restart it forgets the
    position and its close_position is a no-op ('No position to close') while
    the exchange short is orphaned (incident 2026-07-27). Closing via the
    adapter uses the exchange's own position, so it always works.

    Returns realized_pnl (USDT), 0.0 if already flat, None on failure."""
    from datetime import datetime as _dt
    from app.db.session import SessionLocal
    from app.models.account import ExchangeAccount
    from app.models.live_trading import LiveTradeExecution
    from app.api.endpoints import create_adapter_from_account
    db = SessionLocal()
    try:
        acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == int(account_id)).first()
        if not acc:
            log.error("direct close: account %s not found", account_id)
            return None
        adapter = create_adapter_from_account(acc)
        pos = _run_async(adapter.get_position(symbol))
        qty = float((pos or {}).get("quantity") or 0.0)
        if qty == 0:
            return 0.0  # already flat on the exchange
        res = _run_async(adapter.close_position(symbol))
        if res.get("status") != "success":
            log.error("direct close failed %s: %s", symbol, res)
            return None
        exec_price = float(res.get("price") or 0.0)
        fqty = float(res.get("quantity") or abs(qty))
        realized = _real_realized_since(adapter, symbol)
        row = LiveTradeExecution(
            session_id=session_id, symbol=symbol,
            signal_type="BUY" if qty < 0 else "SELL",  # cover a short = BUY
            signal_timestamp=_dt.utcnow(), theoretical_price=exec_price or 0.0,
            requested_quantity=fqty, order_submitted_at=_dt.utcnow(),
            order_filled_at=_dt.utcnow(), executed_price=exec_price,
            filled_quantity=fqty, realized_pnl=realized, status="FILLED",
            is_paper=False, position_side="SHORT" if qty < 0 else "LONG",
            trade_metadata={"driver": "lifecycle_direct_close", "source": "adapter_close_position"},
        )
        db.add(row)
        db.commit()
        log.info("[DIRECT-CLOSE] real %s closed on exchange qty=%.6f realized=%.2f (recorded)",
                 symbol, fqty, realized)
        return realized
    except Exception as exc:
        log.error("direct close error %s/%s: %s", account_id, symbol, exc)
        db.rollback()
        return None
    finally:
        db.close()


def _read_last_cycle(session_id: str) -> Optional[dict[str, Any]]:
    """Return the last CycleResult dict from a System-2 session's predictions.jsonl."""
    path = STORE_ROOT / session_id / "predictions.jsonl"
    if not path.exists():
        log.warning("No predictions.jsonl for %s", session_id)
        return None
    last = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                last = line
    if not last:
        return None
    try:
        return json.loads(last)
    except json.JSONDecodeError as exc:
        log.error("Bad JSONL tail for %s: %s", session_id, exc)
        return None


def _desired_side(cycle: dict[str, Any]) -> str:
    """System-2 current position side → desired live side. 'short' or 'flat'."""
    after = (cycle.get("side_after") or "flat").lower()
    return "short" if after == "short" else "flat"


def _session_age_days(session_id: str) -> Optional[int]:
    """Days since the driving System-2 session's FIRST bar (≈ Day-1 entry).
    None if unreadable. Uses UTC date of the first predictions.jsonl row."""
    path = STORE_ROOT / session_id / "predictions.jsonl"
    if not path.exists():
        return None
    try:
        from datetime import date as _date, datetime as _dt
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ts = json.loads(line).get("timestamp", "")[:10]
                    if ts:
                        y, m, d = map(int, ts.split("-"))
                        return (_dt.utcnow().date() - _date(y, m, d)).days
                    break
    except Exception as exc:
        log.warning("age lookup failed for %s: %s", session_id, exc)
    return None


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        log.error("Corrupt JSON at %s — treating as empty", path)
        return default


def _submit(api_url: str, live_session_id: str, *, side: str, symbol: str,
            quantity: float, metadata: dict, timeout: float = 15.0) -> dict:
    url = f"{api_url.rstrip('/')}/api/v1/live/session/{live_session_id}/submit-signal"
    payload = {
        "side": side,
        "symbol": symbol,
        "quantity": float(quantity),
        "price": 0,            # market
        "order_type": "market",
        "source": SIGNAL_SOURCE,
        "metadata": metadata,
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def run(args) -> int:
    links: dict[str, dict] = _load_json(LINKS_PATH, {})
    if not links:
        log.warning("No live links registered at %s — nothing to mirror.", LINKS_PATH)
        return 0
    state: dict[str, dict] = _load_json(STATE_PATH, {})

    # REAL full-compound sizing: deploy the shared account's available margin.
    # Fetched once per account per run; decremented as we fund REAL shorts so
    # concurrent entries in one cycle don't over-allocate the shared pool.
    real_budget: dict[int, float] = {}
    real_equity: dict[int, float] = {}  # totalWalletBalance — cap denominator

    n_actions = 0
    for s2_id, link in links.items():
        cycle = _read_last_cycle(s2_id)
        if cycle is None:
            continue
        desired = _desired_side(cycle)
        symbol = link.get("symbol") or cycle.get("symbol") or ""
        ref_price = float(cycle.get("bar_close") or 0.0)
        notional = float(link.get("notional_usdt", 0.0))

        link_state = state.setdefault(s2_id, {})
        # migrate any legacy non-dict state value
        if not isinstance(link_state, dict):
            link_state = {}
            state[s2_id] = link_state

        # Hard final-exit: once past the lifecycle hold window, force flat and
        # retire the link permanently so the oscillating source can never
        # re-enter. A retired link stays flat for the rest of its life.
        if link_state.get("retired"):
            desired = "flat"
        else:
            age = _session_age_days(s2_id)
            if age is not None and age >= HARD_EXIT_DAYS and desired == "short":
                log.warning("%s (%s): age %dd >= %dd hold cap — force final exit + retire",
                            s2_id, symbol, age, HARD_EXIT_DAYS)
                desired = "flat"
                link_state["retired"] = True

        targets: list[tuple[str, str]] = []
        if link.get("paper"):
            targets.append(("paper", link["paper"]))
        if link.get("real"):
            if args.include_real:
                targets.append(("real", link["real"]))
            else:
                log.info("%s: REAL target present but --include-real not set — skipping REAL", s2_id)

        for track, live_id in targets:
            intended = link_state.get(track, "flat")
            if intended == desired:
                log.info("%s %s (%s): in sync (side=%s)", s2_id, track, symbol, desired)
                continue

            margin_used = 0.0  # REAL: how much of the shared budget this short consumes
            if desired == "short":
                side = "short"
                if track == "real":
                    # full-compound: deploy the shared account's available margin,
                    # sized on the LIVE exchange mark price (not the stale System-2
                    # ref_price) so a post-signal pump can't blow through the 3%
                    # buffer and trigger -2019. Idempotency-guard against double entry.
                    acc_id = link.get("real_account_id")
                    lev = int(link.get("real_leverage", 1) or 1)
                    if acc_id is None:
                        log.error("%s real: missing real_account_id in link — skip", s2_id)
                        continue
                    mark_price, pos_qty = _real_symbol_state(int(acc_id), symbol)
                    if pos_qty < 0:
                        # already short on the exchange (state desync or prior fill)
                        # → mark in-sync, never re-enter (double-entry guard).
                        log.info("%s real (%s): already short on exchange (qty=%.6f) — mark in-sync, skip re-entry",
                                 s2_id, symbol, pos_qty)
                        link_state[track] = "short"
                        continue
                    if mark_price <= 0:
                        log.info("%s real (%s): live mark/position unavailable — skip, retry next cycle",
                                 s2_id, symbol)
                        continue
                    if acc_id not in real_budget:
                        real_budget[acc_id] = _real_available_usdt(int(acc_id))
                        real_equity[acc_id] = _real_equity_usdt(int(acc_id))
                        log.info("REAL account %s: available %.2f / wallet %.2f USDT",
                                 acc_id, real_budget[acc_id], real_equity[acc_id])
                    avail = real_budget[acc_id]
                    if avail < MIN_REAL_NOTIONAL:
                        log.info("%s real (%s): available %.2f < min %.2f — skip, retry next cycle",
                                 s2_id, symbol, avail, MIN_REAL_NOTIONAL)
                        continue
                    # max purchasable on LIVE mark price: deploy (almost all) margin × lev.
                    # 3% buffer absorbs taker fee + ms-scale fill drift from mark.
                    margin_used = avail * REAL_MARGIN_FRACTION
                    # Per-symbol cap off total wallet balance. equity 0.0 means the
                    # query failed — fall back to uncapped rather than sizing to 0.
                    equity = real_equity.get(acc_id, 0.0)
                    if equity > 0:
                        cap = equity * REAL_MAX_SYMBOL_FRACTION
                        if margin_used > cap:
                            log.info("%s real (%s): margin %.2f capped to %.2f "
                                     "(%.0f%% of wallet %.2f)",
                                     s2_id, symbol, margin_used, cap,
                                     REAL_MAX_SYMBOL_FRACTION * 100, equity)
                            margin_used = cap
                    else:
                        log.warning("%s real (%s): wallet balance unavailable — "
                                    "per-symbol cap NOT applied", s2_id, symbol)
                    if margin_used < MIN_REAL_NOTIONAL:
                        log.info("%s real (%s): capped margin %.2f < min %.2f — skip",
                                 s2_id, symbol, margin_used, MIN_REAL_NOTIONAL)
                        continue
                    qty = (margin_used * lev) / mark_price
                else:  # paper: fixed notional from link
                    qty = (notional / ref_price) if ref_price > 0 else 0.0
            else:  # flat
                side = "close_position"
                qty = 0.0

            # REAL transient flat (source oscillated to flat but NOT retired):
            # hold the position through it — checked BEFORE dry-run logging so
            # both dry-run and live behave identically. Do NOT route to the
            # engine (its close is a no-op for external-qty → 'No position to
            # close') which would flip link_state and fire a FALSE '🟢 REAL 청산'
            # telegram while the exchange short stays open (incident 2026-07-30:
            # spurious DATAIP close notice). Keep intended=short; real exits only
            # at Day-31 via the retired direct-close below.
            if track == "real" and desired == "flat" and not link_state.get("retired"):
                log.info("%s real (%s): transient flat (not retired) — holding, no action",
                         s2_id, symbol)
                continue

            metadata = {
                "driver": "lifecycle_decay_d14",
                "track": track,
                "system2_session": s2_id,
                "cycle_ts": str(cycle.get("timestamp", "")),
                "ref_price": ref_price,
                "reconcile": f"{intended}->{desired}",
                "action_kind": cycle.get("action_kind"),
            }
            n_actions += 1
            if args.dry_run:
                log.info("[DRY] %s %s reconcile %s→%s: session=%s side=%s qty=%.6f @~%.6g%s",
                         track, symbol, intended, desired, live_id, side, qty, ref_price,
                         (f" (margin≈{margin_used:.2f})" if margin_used else ""))
                continue

            # REAL final exit → close DIRECTLY on the exchange (engine-independent),
            # bypassing the engine's no-op close for external-qty sessions.
            # Gated on `retired` (the Day-31 hard exit): the decay source
            # oscillates short↔flat every bar, so honoring every transient flat
            # would churn the real position (close→re-short daily = fee drag).
            # The position is held through oscillation and closed once, for good,
            # at the hold-window backstop.
            if track == "real" and desired == "flat" and link_state.get("retired"):
                acc_id = link.get("real_account_id")
                realized = _real_direct_close(int(acc_id), symbol, live_id) if acc_id is not None else None
                if realized is None:
                    log.error("[FAIL] real %s direct close failed — intended kept, retry next cycle", symbol)
                    continue
                link_state[track] = "flat"
                n_actions += 0  # already counted above
                log.info("[SENT] real %s reconcile %s→flat via direct exchange close, realized=%.2f",
                         symbol, intended, realized)
                if acc_id:
                    reason = ("hard_exit(retired)" if link_state.get("retired")
                              else cycle.get("forced_exit_reason") or cycle.get("action_kind") or "exit")
                    _telegram_notify(int(acc_id),
                        f"🟢 <b>REAL 청산</b> — 신상저격수(lifecycle)\n종목: <b>{symbol}</b>\n"
                        f"사유: {reason}\n실현손익: <b>{realized:+,.2f} USDT</b>")
                continue
            try:
                res = _submit(args.api_url, live_id, side=side, symbol=symbol,
                              quantity=qty, metadata=metadata)
                result = res.get("result", res)
                # REAL short entry: /submit-signal returns HTTP 200 even when the
                # exchange order is rejected — process_queue swallows OrderExecutionError
                # into status='failed' (e.g. -2019 insufficient margin). Confirm a short
                # actually opened on the exchange before marking done; else keep flat so
                # next cycle retries (no false "in sync" that silently skips entry).
                if track == "real" and desired == "short":
                    _, pos_after = _real_symbol_state(int(link["real_account_id"]), symbol)
                    if pos_after >= 0:
                        log.error("[FAIL] real %s short NOT opened (exchange qty=%.6f, rejected/partial?) "
                                  "— keep flat, retry next cycle. result=%s", symbol, pos_after, result)
                        continue
                # success "No position to close" is benign for close → still in sync
                link_state[track] = desired  # update ONLY on success → failures retry next cycle
                if track == "real" and margin_used and link.get("real_account_id") in real_budget:
                    real_budget[link["real_account_id"]] -= margin_used  # consume shared budget
                log.info("[SENT] %s %s reconcile %s→%s: session=%s side=%s qty=%.6f result=%s",
                         track, symbol, intended, desired, live_id, side, qty, result)
                # Telegram: REAL-track entry/exit/analysis (immediate). PAPER excluded.
                if track == "real" and link.get("real_account_id"):
                    acc_id = link["real_account_id"]
                    if desired == "short":
                        lev = int(link.get("real_leverage", 1) or 1)
                        _telegram_notify(acc_id,
                            f"🔴 <b>REAL 숏 진입</b> — lifecycle 신규상장 decay\n"
                            f"종목: <b>{symbol}</b>\n진입가(라이브 마크): ~{mark_price:g}  (신호가 {ref_price:g})\n"
                            f"투입(전체 가용 마진): ${margin_used:,.2f}  (qty {qty:,.4f}, {lev}x)\n"
                            f"전략: 상장 Day-1 종가 공매도, Day-14 vol_cliff/Day-30/SL+50% 청산\n"
                            f"BACKTEST(System-2): {s2_id}  ts={cycle.get('timestamp','')}")
                    else:  # close_position
                        res = _real_trade_result(live_id)
                        pnl = ""
                        if res:
                            last, cur, init = res
                            if last is not None:
                                pnl += f"\n실현손익(직전 청산): <b>{last:+,.2f} USDT</b>"
                            if cur is not None and init:
                                pnl += f"\n세션 누적: {cur - init:+,.2f} USDT ({(cur / init - 1) * 100:+.2f}%)"
                        reason = cycle.get("forced_exit_reason") or cycle.get("action_kind") or "exit"
                        _telegram_notify(acc_id,
                            f"🟢 <b>REAL 청산</b> — lifecycle\n종목: <b>{symbol}</b>\n사유: {reason}{pnl}")
            except requests.HTTPError as exc:
                log.error("[FAIL] %s %s → session=%s: HTTP %s %s (intended kept=%s, will retry)",
                          track, symbol, live_id,
                          getattr(exc.response, "status_code", "?"),
                          getattr(exc.response, "text", str(exc))[:200], intended)
            except requests.RequestException as exc:
                log.error("[FAIL] %s %s → session=%s: %s (intended kept=%s, will retry)",
                          track, symbol, live_id, exc, intended)

    if not args.dry_run:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))

    log.info("Planned %d reconcile action(s). mode=%s include_real=%s",
             n_actions, "DRY-RUN" if args.dry_run else "SUBMIT", args.include_real)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reconcile linked v2 live sessions to System-2 lifecycle state.")
    p.add_argument("--api-url", default="http://localhost:8001",
                   help="Backend base URL (default: http://localhost:8001)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                      help="(default) print intended actions, do not POST")
    mode.add_argument("--submit", dest="dry_run", action="store_false",
                      help="actually POST signals to live sessions")
    p.add_argument("--include-real", action="store_true", default=False,
                   help="also reconcile REAL (is_paper=false) sessions — requires --submit")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(run(args))
