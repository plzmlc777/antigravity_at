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

SIGNAL_SOURCE = "skill:lifecycle_decay_d14"
MIN_REAL_NOTIONAL = 5.0  # Binance Futures min notional (~$5); skip below this


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
        bal = asyncio.run(adapter.get_balance())
        return float((bal or {}).get("cash", {}).get("USDT", 0.0))
    except Exception as exc:
        log.error("REAL balance query failed for account %s: %s", account_id, exc)
        return 0.0
    finally:
        db.close()


def _telegram_notify(account_id: int, text: str) -> None:
    """Send a Telegram message via the account's configured bot/chat. No-op if
    unconfigured. REAL-track only (entry/exit/analysis). Mint-only path."""
    import asyncio
    try:
        from app.db.session import SessionLocal
        from app.models.user import User  # noqa: F401 — resolves ExchangeAccount.user mapper
        from app.models.account import ExchangeAccount
        from app.core.telegram_service import TelegramNotificationService
    except Exception as exc:
        log.error("telegram import failed (%s)", exc)
        return
    db = SessionLocal()
    try:
        acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == int(account_id)).first()
        if not acc:
            return
        svc = TelegramNotificationService(db, user_id=acc.user_id, account_id=int(account_id))
        if not svc.is_configured():
            log.info("telegram not configured for account %s — skip notify", account_id)
            return
        asyncio.run(svc.send_message(text))
        log.info("telegram notify sent (account %s)", account_id)
    except Exception as exc:
        log.error("telegram notify failed: %s", exc)
    finally:
        db.close()


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
                    # full-compound: deploy the shared account's available margin.
                    acc_id = link.get("real_account_id")
                    lev = int(link.get("real_leverage", 1) or 1)
                    if acc_id is None:
                        log.error("%s real: missing real_account_id in link — skip", s2_id)
                        continue
                    if acc_id not in real_budget:
                        real_budget[acc_id] = _real_available_usdt(int(acc_id))
                        log.info("REAL account %s available margin: %.2f USDT", acc_id, real_budget[acc_id])
                    avail = real_budget[acc_id]
                    if avail < MIN_REAL_NOTIONAL or ref_price <= 0:
                        log.info("%s real (%s): available %.2f < min %.2f (or no price) — skip, retry next cycle",
                                 s2_id, symbol, avail, MIN_REAL_NOTIONAL)
                        continue
                    margin_used = avail               # deploy full available margin
                    qty = (avail * lev) / ref_price   # notional = margin × leverage
                else:  # paper: fixed notional from link
                    qty = (notional / ref_price) if ref_price > 0 else 0.0
            else:  # flat
                side = "close_position"
                qty = 0.0

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
            try:
                res = _submit(args.api_url, live_id, side=side, symbol=symbol,
                              quantity=qty, metadata=metadata)
                result = res.get("result", res)
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
                            f"종목: <b>{symbol}</b>\n진입가: ~{ref_price:g}\n"
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
