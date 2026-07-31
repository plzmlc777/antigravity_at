#!/usr/bin/env bash
# Core-tables DB backup to Cloudflare R2 (off-site copy).
#
# Invocation: sas_loop_wrapper.sh "20 18 * * *" scripts/maintenance/backup_core_to_r2.sh
#   18:20 UTC = 03:20 KST — 20 min after the USB full backup so the two never
#   contend for pg_dump CPU.
#
# Scope: everything EXCEPT the market-data tables. Measured 2026-07-31:
#   full DB          14.95 GB   (42 tables)
#   market data      14.94 GB   (4 tables — refetchable from Binance/Kiwoom APIs)
#   core operational  9.81 MB   (38 tables — irreplaceable)
# The compressed core dump is ~2.1 MB, which keeps us permanently inside R2's
# 10 GB free tier even with unbounded retention.
#
# Credentials live in ~/.r2_backup.env (chmod 600), NOT in this file and NOT in
# the repo. See memory/feedback_credentials_in_db.md for the project convention.
#
# rclone notes (learned 2026-07-31):
#   - Credentials are passed as RCLONE_S3_* env vars, never as CLI flags.
#     Flags land in /proc/<pid>/cmdline and are readable by any local user via ps.
#   - Requires rclone >= 1.74 (/usr/local/bin). The distro package (1.60, 2022)
#     throws "NotImplemented 501" on the first PUT to R2 and only succeeds on
#     retry; 1.74.4 uploads cleanly with zero errors.

set -uo pipefail

RCLONE_BIN="/usr/local/bin/rclone"
MOUNT_POINT="/mnt/backup"
STAGING_DIR="/mnt/backup/r2_staging"
LOG="/mnt/backup/db_backups/r2_backup.log"
CRED_FILE="${HOME}/.r2_backup.env"

DB_NAME="antigravity_db"
DB_USER="antigravity_user"
DB_HOST="localhost"
export PGPASSWORD="antigravity_password"

# Market-data tables excluded from the off-site copy (refetchable).
EXCLUDES=(
  --exclude-table-data=ohlcv
  --exclude-table-data=binance_positioning_metric
  --exclude-table-data=binance_open_interest_hist
  --exclude-table-data=binance_funding_rate
)

TS=$(TZ=Asia/Seoul date +%Y%m%d_%H%M%S)

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
  echo "[$(TZ=Asia/Seoul date)] FAIL: ${reason}" | tee -a "$LOG" 2>/dev/null >&2
  notify "🔴 [민트] R2 원격 백업 실패
사유: ${reason}
시각: $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')"
  exit 1
}

# ── Gate 1: tooling ───────────────────────────────────────────────────────
[ -x "$RCLONE_BIN" ] || fail "rclone not found at ${RCLONE_BIN}"

# ── Gate 2: credentials present ───────────────────────────────────────────
[ -f "$CRED_FILE" ] || fail "credential file missing: ${CRED_FILE}"
# shellcheck disable=SC1090
set -a; source "$CRED_FILE"; set +a
for v in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT R2_BUCKET; do
  [ -n "${!v:-}" ] || fail "credential var ${v} is empty"
done

# Hand credentials to rclone via the environment so they never appear in ps.
export RCLONE_S3_PROVIDER="Cloudflare"
export RCLONE_S3_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_S3_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_S3_ENDPOINT="$R2_ENDPOINT"
export RCLONE_S3_NO_CHECK_BUCKET="true"
rc() { "$RCLONE_BIN" --config /dev/null --retries 3 --low-level-retries 5 --timeout 120s "$@"; }

# ── Gate 3: staging area available ────────────────────────────────────────
mountpoint -q "$MOUNT_POINT" || fail "${MOUNT_POINT} not mounted (staging unavailable)"
mkdir -p "$STAGING_DIR" "$(dirname "$LOG")" || fail "cannot create staging dir"
echo "[$(TZ=Asia/Seoul date)] start ${TS}" >> "$LOG"

DUMP_PATH="${STAGING_DIR}/${DB_NAME}_core_${TS}.dump"
cleanup() { rm -f "$DUMP_PATH"; }
trap cleanup EXIT

# ── Dump core tables only ─────────────────────────────────────────────────
pg_dump -U "$DB_USER" -h "$DB_HOST" -F c "${EXCLUDES[@]}" "$DB_NAME" \
  > "$DUMP_PATH" 2>>"$LOG"
DUMP_EXIT=$?
[ "$DUMP_EXIT" -eq 0 ] && [ -s "$DUMP_PATH" ] || fail "pg_dump exit=${DUMP_EXIT}"

head -c 5 "$DUMP_PATH" | grep -q "PGDMP" || fail "header check — not a pg_dump custom file"

TOC_COUNT=$(pg_restore --list "$DUMP_PATH" 2>/dev/null | grep -c '^[0-9]')
[ "${TOC_COUNT:-0}" -ge 1 ] || fail "pg_restore --list returned no entries"

SIZE_BYTES=$(stat -c%s "$DUMP_PATH")
SIZE_H=$(du -h "$DUMP_PATH" | cut -f1)

# Sanity: a core dump far larger than expected means an exclude stopped working
# and we are about to push 1.2GB into a 10GB free tier.
MAX_MB=200
if [ "$SIZE_BYTES" -gt $((MAX_MB * 1024 * 1024)) ]; then
  fail "core dump unexpectedly large (${SIZE_H} > ${MAX_MB}MB) — exclude-table-data may have failed"
fi

# ── Upload ────────────────────────────────────────────────────────────────
REMOTE_PATH="daily/${DB_NAME}_core_${TS}.dump"
rc copyto "$DUMP_PATH" ":s3:${R2_BUCKET}/${REMOTE_PATH}" 2>>"$LOG" || fail "rclone upload failed"

# ── Verify: remote object exists with byte-exact size ─────────────────────
# lsjson gives an exact integer; `rclone size` prints a human string that is
# trivially mis-parsed (an earlier version of this script read "2.02 MiB" as 2).
REMOTE_SIZE=$(rc lsjson ":s3:${R2_BUCKET}/${REMOTE_PATH}" 2>/dev/null \
  | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(d[0]["Size"] if d else "")
except Exception:
    print("")')

if [ "${REMOTE_SIZE:-}" != "$SIZE_BYTES" ]; then
  fail "remote size mismatch: local=${SIZE_BYTES} remote=${REMOTE_SIZE:-none}"
fi

echo "[$(TZ=Asia/Seoul date)] OK ${SIZE_H} (${SIZE_BYTES}B) toc=${TOC_COUNT} -> ${REMOTE_PATH}" >> "$LOG"
echo "[backup-r2] OK ${SIZE_H} toc=${TOC_COUNT} remote=${REMOTE_PATH}"
exit 0
