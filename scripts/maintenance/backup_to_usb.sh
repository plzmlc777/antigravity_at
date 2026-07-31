#!/usr/bin/env bash
# Local DB backup to the USB-attached external disk.
#
# Replaces the ubuntu-side pull backup (sync_from_mint.sh) with a local dump.
# Invocation: sas_loop_wrapper.sh "0 18 * * *" scripts/maintenance/backup_to_usb.sh
#   18:00 UTC = 03:00 KST, matching the schedule the ubuntu host used.
#
# Design notes:
#   - The mount check is the first gate. A missing/unmounted disk must abort
#     LOUDLY rather than silently writing 1.2GB into the root filesystem —
#     that is exactly how the ubuntu backup could have failed unnoticed.
#   - pg_dump custom format (-F c) is compressed and restore-friendly
#     (pg_restore --list works, selective table restore possible).
#   - PGDMP header check catches truncated/garbage output that still exits 0.

set -uo pipefail

BACKUP_DIR="/mnt/backup/db_backups"
MOUNT_POINT="/mnt/backup"
LOG="${BACKUP_DIR}/backup.log"
STATUS_FILE="${BACKUP_DIR}/last_backup.status"
RETAIN_DAYS=7
MIN_FREE_GB=5

DB_NAME="antigravity_db"
DB_USER="antigravity_user"
DB_HOST="localhost"
export PGPASSWORD="antigravity_password"

TS=$(TZ=Asia/Seoul date +%Y%m%d_%H%M%S)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Telegram creds are exported by sas_loop_wrapper.sh (decrypted from DB).
notify() {
  local msg="$1"
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -s -m 15 -X POST \
      "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d "chat_id=${TELEGRAM_CHAT_ID}" \
      -d "text=${msg}" >/dev/null 2>&1 || true
  fi
}

fail() {
  local reason="$1"
  echo "[$(TZ=Asia/Seoul date)] FAIL: ${reason}" | tee -a "$LOG" 2>/dev/null
  echo "FAIL|${START_ISO}|${reason}" > "$STATUS_FILE" 2>/dev/null
  notify "🔴 [민트] DB 백업 실패
사유: ${reason}
시각: $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')"
  exit 1
}

# ── Gate 1: external disk actually mounted ────────────────────────────────
if ! mountpoint -q "$MOUNT_POINT"; then
  echo "[$(TZ=Asia/Seoul date)] FAIL: ${MOUNT_POINT} is not mounted — aborting" >&2
  notify "🔴 [민트] DB 백업 중단
외장하드가 마운트되지 않았습니다 (${MOUNT_POINT}).
USB 연결 상태를 확인해 주십시오.
시각: $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')"
  exit 1
fi

mkdir -p "$BACKUP_DIR" || fail "cannot create ${BACKUP_DIR}"
echo "[$(TZ=Asia/Seoul date)] start ${TS}" >> "$LOG"

# ── Gate 2: free space ────────────────────────────────────────────────────
FREE_GB=$(df -BG --output=avail "$MOUNT_POINT" | tail -1 | tr -dc '0-9')
if [ "${FREE_GB:-0}" -lt "$MIN_FREE_GB" ]; then
  fail "insufficient free space: ${FREE_GB}GB < ${MIN_FREE_GB}GB"
fi

# ── Dump ──────────────────────────────────────────────────────────────────
DUMP_PATH="${BACKUP_DIR}/${DB_NAME}_${TS}.dump"
pg_dump -U "$DB_USER" -h "$DB_HOST" -F c "$DB_NAME" > "$DUMP_PATH" 2>>"$LOG"
DUMP_EXIT=$?

if [ "$DUMP_EXIT" -ne 0 ] || [ ! -s "$DUMP_PATH" ]; then
  SZ=$(stat -c%s "$DUMP_PATH" 2>/dev/null || echo 0)
  rm -f "$DUMP_PATH"
  fail "pg_dump exit=${DUMP_EXIT} size=${SZ}"
fi

# ── Verify: custom-format dumps begin with the magic string PGDMP ─────────
if ! head -c 5 "$DUMP_PATH" | grep -q "PGDMP"; then
  rm -f "$DUMP_PATH"
  fail "header check — not a valid pg_dump custom file"
fi

# ── Verify: table of contents is readable ────────────────────────────────
TOC_COUNT=$(pg_restore --list "$DUMP_PATH" 2>/dev/null | grep -c '^[0-9]')
if [ "${TOC_COUNT:-0}" -lt 1 ]; then
  rm -f "$DUMP_PATH"
  fail "pg_restore --list returned no entries (corrupt dump)"
fi

SIZE_BYTES=$(stat -c%s "$DUMP_PATH")
SIZE_H=$(du -h "$DUMP_PATH" | cut -f1)
END_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[$(TZ=Asia/Seoul date)] OK ${SIZE_H} (${SIZE_BYTES}B) toc=${TOC_COUNT}" >> "$LOG"

# ── Retention ─────────────────────────────────────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+${RETAIN_DAYS}" -delete -print | wc -l)
KEPT=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" | wc -l)
echo "[$(TZ=Asia/Seoul date)] retention: pruned ${DELETED}, kept ${KEPT}" >> "$LOG"

echo "OK|${END_ISO}|${SIZE_BYTES}|${DUMP_PATH}" > "$STATUS_FILE"
echo "[backup-usb] OK ${SIZE_H} toc=${TOC_COUNT} kept=${KEPT}"
exit 0
