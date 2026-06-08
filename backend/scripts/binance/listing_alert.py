#!/usr/bin/env python3
"""Alert on new/upcoming Binance crypto perp listings (lifecycle REAL trigger).

Polls fapi exchangeInfo and sends a Telegram alert (account 8 → 7899) when a NEW
crypto (underlyingType=COIN & contractType=PERPETUAL) listing appears that hasn't
been alerted before:
  - PENDING_TRADING with a future onboardDate (forward-announced, hours ahead), or
  - TRADING with onboardDate within the last FRESH_WINDOW (freshly listed, in case
    the PENDING_TRADING window was never observed).

Idempotent via a seen-state JSON. Read-only — performs NO trading. Designed to run
on a cron (every few hours). Reuses the spawner's exchangeInfo fetch and the
driver's Telegram helper so it shares the crypto-only gate + REAL chat fan-out.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# backend/ on sys.path so `scripts.*` modules import (run via -m or directly)
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from scripts.research.lifecycle_session_spawner import fetch_exchange_info  # noqa: E402
from scripts.binance.lifecycle_live_signal_driver import ROOT, _telegram_notify  # noqa: E402

STATE = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_alert_seen.json"
FRESH_WINDOW_MS = 48 * 3600 * 1000
REAL_ACCOUNT_ID = 8  # → telegram 7899


def _load_seen() -> set:
    try:
        return set(json.loads(STATE.read_text())) if STATE.exists() else set()
    except Exception:
        return set()


def main() -> int:
    info = fetch_exchange_info()
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    candidates = {}  # symbol -> (onboard_ms, status)
    for s in info.get("symbols", []):
        if s.get("underlyingType") != "COIN" or s.get("contractType") != "PERPETUAL":
            continue
        ob = s.get("onboardDate") or 0
        st = s.get("status")
        if st == "PENDING_TRADING" and ob > now_ms:
            candidates[s["symbol"]] = (ob, st)
        elif st == "TRADING" and 0 < (now_ms - ob) <= FRESH_WINDOW_MS:
            candidates[s["symbol"]] = (ob, st)

    seen = _load_seen()
    new = {sym: v for sym, v in candidates.items() if sym not in seen}

    if new:
        lines = ["\U0001F195 <b>신규 crypto 상장 감지</b> (lifecycle REAL 트리거)"]
        for sym, (ob, st) in sorted(new.items(), key=lambda x: x[1][0]):
            dt = datetime.fromtimestamp(ob / 1000, tz=timezone.utc).strftime("%m-%d %H:%M UTC")
            tag = "예정(PENDING)" if st == "PENDING_TRADING" else "상장됨(TRADING)"
            lines.append(f"• {sym}  onboard={dt}  [{tag}]")
        lines.append("→ 다음 11:30 KST 사이클이 spawn→REAL 풀-복리 진입 예정")
        _telegram_notify(REAL_ACCOUNT_ID, "\n".join(lines))
        print(f"[listing-alert] {len(new)} new crypto listing(s): {sorted(new)}")
    else:
        print("[listing-alert] no new crypto listings")

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(sorted(seen | set(candidates))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
