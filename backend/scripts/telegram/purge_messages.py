"""Selectively bulk-delete Telegram messages the system sent.

Reads the sent-log (app/core/telegram_sent_log.py), filters by text substring
/ chat / age, and calls deleteMessage for each match. Telegram only lets a bot
delete its own messages within 48h, so older matches are reported as skipped.

Built 2026-07-19 (ADL-risk spam couldn't be purged — no message_ids recorded).
Only messages sent AFTER the sent-log was deployed are purgeable.

Examples:
  # 미리보기 — 오늘 ADL 메시지
  PYTHONPATH=. python3 scripts/telegram/purge_messages.py --contains "ADL" --dry-run
  # 실제 삭제 (48h 이내만)
  PYTHONPATH=. python3 scripts/telegram/purge_messages.py --contains "ADL"
  # 특정 그룹, 최근 6시간
  PYTHONPATH=. python3 scripts/telegram/purge_messages.py --contains "ADL" --chat -1003140577899 --hours 6
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.telegram_sent_log import LOG_PATH  # noqa: E402

DELETE_WINDOW_SEC = 48 * 3600


def bot_token(account_id: int) -> str:
    from app.db.session import SessionLocal
    from app.models.user import User  # noqa: F401
    from app.models.account import ExchangeAccount
    from app.core import security
    db = SessionLocal()
    try:
        acc = db.query(ExchangeAccount).get(account_id)
        return security.decrypt_key(acc.encrypted_telegram_bot_token)
    finally:
        db.close()


def load_log() -> list:
    if not os.path.exists(LOG_PATH):
        return []
    out = []
    for line in open(LOG_PATH):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def delete_message(token: str, chat_id: str, message_id: int) -> tuple[bool, str]:
    data = urllib.parse.urlencode({"chat_id": chat_id, "message_id": message_id}).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{token}/deleteMessage", data=data),
            timeout=15,
        ) as r:
            resp = json.load(r)
            return bool(resp.get("ok")), ""
    except urllib.error.HTTPError as e:
        try:
            return False, json.loads(e.read().decode()).get("description", str(e))
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contains", help="본문에 이 문자열이 포함된 메시지만 (대소문자 무시)")
    ap.add_argument("--chat", help="이 chat_id로 보낸 것만")
    ap.add_argument("--hours", type=float, help="최근 N시간 이내 발송분만")
    ap.add_argument("--source", help="발송 경로 필터 (telegram_service/lifecycle_notify/qa_bot)")
    ap.add_argument("--account-id", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    entries = load_log()
    now = time.time()
    matched, too_old = [], 0
    for e in entries:
        try:
            ts = datetime.fromisoformat(e["ts"]).timestamp()
        except Exception:
            continue
        if args.contains and args.contains.lower() not in (e.get("text", "").lower()):
            continue
        if args.chat and str(e.get("chat_id")) != str(args.chat):
            continue
        if args.source and e.get("source") != args.source:
            continue
        if args.hours and (now - ts) > args.hours * 3600:
            continue
        if (now - ts) > DELETE_WINDOW_SEC:
            too_old += 1
            continue
        matched.append(e)

    print(f"매칭 {len(matched)}건 (48h 초과로 삭제 불가 {too_old}건 제외)")
    for e in matched[:10]:
        print(f"  [{e['ts']}] {e['chat_id']} #{e['message_id']} — {e['text'][:60]}")
    if len(matched) > 10:
        print(f"  ... 외 {len(matched) - 10}건")

    if args.dry_run:
        print("(dry-run — 실제 삭제 안 함)")
        return
    if not matched:
        return

    token = bot_token(args.account_id)
    deleted, failed = 0, 0
    deleted_keys = set()
    for e in matched:
        ok, err = delete_message(token, e["chat_id"], e["message_id"])
        if ok:
            deleted += 1
            deleted_keys.add((str(e["chat_id"]), int(e["message_id"])))
        else:
            failed += 1
            print(f"  실패 #{e['message_id']}: {err}")
        time.sleep(0.05)

    # 성공적으로 삭제한 항목만 로그에서 제거 (실패분은 남겨 재시도 가능).
    kept = [ln for ln in load_log()
            if (str(ln["chat_id"]), int(ln["message_id"])) not in deleted_keys]
    try:
        with open(LOG_PATH, "w") as f:
            for ln in kept:
                f.write(json.dumps(ln, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"로그 정리 실패(무시 가능): {exc}")

    print(f"삭제 완료 {deleted}건, 실패 {failed}건")


if __name__ == "__main__":
    main()
