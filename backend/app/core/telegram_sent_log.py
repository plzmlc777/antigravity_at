"""Append-only log of Telegram messages the system sends, so they can be
selectively bulk-deleted later (Telegram Bot API offers no sent-message
enumeration, and deleteMessage needs the message_id).

Built 2026-07-19 after ADL-risk spam could not be purged (no message_ids
recorded). Every send path records here; scripts/telegram/purge_messages.py
consumes it.

Design constraints:
- best-effort: recording must NEVER raise into a send path or block trading.
- no DB schema change (JSONL append, zero migration).
- Telegram lets a bot delete its own messages only within 48h, so entries
  past PRUNE_AGE_HOURS are useless and get pruned opportunistically.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "runs", "telegram_sent", "sent_log.jsonl",
)
PRUNE_AGE_HOURS = 72  # keep a little past the 48h delete window
_lock = threading.Lock()
_last_prune = 0.0


def record_sent(chat_id, message_id, text: str, source: str = "") -> None:
    """Append one sent message. Best-effort: swallows all errors."""
    if not message_id or chat_id in (None, ""):
        return
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chat_id": str(chat_id),
            "message_id": int(message_id),
            "text": (text or "")[:280],
            "source": source,
        }
        with _lock:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            with open(LOG_PATH, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _maybe_prune()
    except Exception as exc:  # never propagate into a send path
        log.debug("sent-log record failed: %s", exc)


def _maybe_prune() -> None:
    global _last_prune
    now = time.time()
    if now - _last_prune < 3600:  # at most hourly
        return
    _last_prune = now
    try:
        if not os.path.exists(LOG_PATH):
            return
        cutoff = now - PRUNE_AGE_HOURS * 3600
        kept = []
        with open(LOG_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = datetime.fromisoformat(e["ts"]).timestamp()
                    if ts >= cutoff:
                        kept.append(line)
                except Exception:
                    continue
        with _lock:
            with open(LOG_PATH, "w") as f:
                f.write("\n".join(kept) + ("\n" if kept else ""))
    except Exception as exc:
        log.debug("sent-log prune failed: %s", exc)


def extract_message_id(response_json) -> int | None:
    """Pull message_id out of a Telegram sendMessage response dict."""
    try:
        if response_json and response_json.get("ok"):
            return response_json["result"]["message_id"]
    except Exception:
        pass
    return None
