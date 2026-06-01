#!/usr/bin/env python3
"""Lifecycle decay short — live signal driver (Phase 0, 3-track parallel).

설계 (`.claude/plans/lifecycle_short_real_deploy.md` §3.5):
  하나의 결정 소스(System-2 lifecycle paper 세션 = BACKTEST 트랙)가 매일 산출하는
  포지션 전이를, 페어링된 v2 noop 라이브 세션(PAPER + REAL)에 `/submit-signal`로
  그대로 미러링한다. 시그널 계산은 검증된 `BinanceLifecycleDecayEarlyExitSource` +
  `LifecycleDecayEarlyExitPolicy`가 이미 daily 사이클에서 수행하므로 재구현이 없다
  (트랙 B 사망원인인 backtest→live divergence를 구조적으로 제거).

실행 순서 (PM2 binance-paper-cycle 직후):
  1. `paper_session_cli run --all` 이 System-2 lifecycle 세션 사이클을 돌려
     `runs/paper_sessions/<id>/predictions.jsonl` 에 최신 CycleResult를 append.
  2. 본 드라이버가 그 최신 CycleResult의 side_before→side_after 전이를 읽어
     SHORT(진입) / CLOSE(청산) 시그널로 매핑, 링크된 라이브 세션에 POST.

전이 → 시그널 매핑:
  flat  → short  : side="short"           (Day-1 종가 숏 진입)
  short → flat   : side="close_position"  (Day14 vol_cliff early-exit / Day30 / SL)
  그 외          : 시그널 없음 (hold)

안전장치:
  - 기본 --dry-run: POST하지 않고 의도만 출력.
  - --submit 있어야 실제 POST. 그래도 REAL 세션은 --include-real 추가 필요.
  - 상태파일(last_submitted.json)로 동일 cycle 중복 제출 방지.

링크 레지스트리 (runs/research_track/lifecycle_phase/live_links.json):
  {
    "<system2_session_id>": {
      "symbol": "STARUSDT",
      "paper": "<live_bot_session_id|null>",
      "real":  "<live_bot_session_id|null>",
      "notional_usdt": 200.0
    }, ...
  }
  paper/real이 null이면 해당 트랙으로는 제출하지 않는다 (단계적 활성화).
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


def _transition_to_signal(cycle: dict[str, Any]) -> Optional[str]:
    """Map a CycleResult position transition to an external-signal side.

    Returns "short", "close_position", or None (hold / no actionable transition).
    """
    before = (cycle.get("side_before") or "flat").lower()
    after = (cycle.get("side_after") or "flat").lower()
    if before == "flat" and after == "short":
        return "short"
    if before == "short" and after == "flat":
        return "close_position"
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
    state: dict[str, str] = _load_json(STATE_PATH, {})

    n_planned = 0
    for s2_id, link in links.items():
        cycle = _read_last_cycle(s2_id)
        if cycle is None:
            continue
        side = _transition_to_signal(cycle)
        if side is None:
            log.info("%s (%s): hold — no transition (%s→%s)", s2_id, link.get("symbol"),
                     cycle.get("side_before"), cycle.get("side_after"))
            continue

        ts = str(cycle.get("timestamp", ""))
        # Dedup key includes the side: predictions.jsonl can hold several rows
        # at the same daily timestamp (multiple intraday cron fires). Keying on
        # ts alone would let a same-day entry mask a later forced exit; ts|side
        # dedups identical repeats while still allowing a distinct transition.
        dedup_key = f"{ts}|{side}"
        if state.get(s2_id) == dedup_key:
            log.info("%s: transition %s already submitted — skip", s2_id, dedup_key)
            continue

        symbol = link.get("symbol") or cycle.get("symbol") or ""
        ref_price = float(cycle.get("bar_close") or 0.0)
        notional = float(link.get("notional_usdt", 0.0))

        targets: list[tuple[str, str]] = []  # (track, live_session_id)
        if link.get("paper"):
            targets.append(("PAPER", link["paper"]))
        if link.get("real"):
            if args.include_real:
                targets.append(("REAL", link["real"]))
            else:
                log.info("%s: REAL target present but --include-real not set — skipping REAL", s2_id)

        for track, live_id in targets:
            if side == "short":
                qty = (notional / ref_price) if ref_price > 0 else 0.0
            else:  # close_position
                qty = 0.0  # engine closes full position
            metadata = {
                "driver": "lifecycle_decay_d14",
                "track": track,
                "system2_session": s2_id,
                "cycle_ts": ts,
                "ref_price": ref_price,
                "forced_exit_reason": cycle.get("forced_exit_reason"),
                "action_kind": cycle.get("action_kind"),
            }
            n_planned += 1
            if args.dry_run:
                log.info("[DRY] %s %s → session=%s side=%s qty=%.6f @~%.6g notional=%.2f",
                         track, symbol, live_id, side, qty, ref_price, notional)
                continue
            try:
                res = _submit(args.api_url, live_id, side=side, symbol=symbol,
                              quantity=qty, metadata=metadata)
                log.info("[SENT] %s %s → session=%s side=%s qty=%.6f result=%s",
                         track, symbol, live_id, side, qty, res.get("result", res))
            except requests.HTTPError as exc:
                log.error("[FAIL] %s %s → session=%s: HTTP %s %s", track, symbol, live_id,
                          getattr(exc.response, "status_code", "?"),
                          getattr(exc.response, "text", str(exc))[:200])
            except requests.RequestException as exc:
                log.error("[FAIL] %s %s → session=%s: %s", track, symbol, live_id, exc)

        # Mark submitted only when we actually POSTed (not dry-run) for at least the paper track.
        if not args.dry_run and targets:
            state[s2_id] = dedup_key

    if not args.dry_run:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))

    log.info("Planned %d signal(s). mode=%s include_real=%s",
             n_planned, "DRY-RUN" if args.dry_run else "SUBMIT", args.include_real)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mirror System-2 lifecycle decisions to live v2 sessions.")
    p.add_argument("--api-url", default="http://localhost:8001",
                   help="Backend base URL (default: http://localhost:8001)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                      help="(default) print intended signals, do not POST")
    mode.add_argument("--submit", dest="dry_run", action="store_false",
                      help="actually POST signals to live sessions")
    p.add_argument("--include-real", action="store_true", default=False,
                   help="also submit to REAL (is_paper=false) sessions — requires --submit")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(run(args))
