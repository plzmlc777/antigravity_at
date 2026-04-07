#!/bin/bash
# Track D — 신서버 자동 배포 스크립트
#
# 목적: 민트 서버 또는 새 리모트 서버 도착 시 1~2시간 이내 풀 셋업.
#       Binance Futures + 한국 주식 양쪽을 모두 운영할 수 있는 환경 구축.
#
# 사용:
#   ./deploy_to_new_server.sh <user@host>          # 풀 배포
#   ./deploy_to_new_server.sh <user@host> --dry-run # 명령만 출력
#
# 전제:
#   1. 신서버에 SSH 키 인증 가능
#   2. 신서버에 sudo 권한 있는 사용자
#   3. 로컬에 GitHub deploy key 있음
#   4. .env 파일은 별도로 안전하게 전달 (이 스크립트는 암호 자체를 옮기지 않음)
#
# 단계:
#   1. 시스템 패키지 (python3, postgres, nginx 등)
#   2. Node + PM2
#   3. Claude Code CLI
#   4. PostgreSQL DB 생성 + OHLCV 마이그레이션
#   5. Git clone + venv + npm install + frontend build
#   6. .env 파일 사용자에게 안내 (수동 단계)
#   7. SSH 키 + GitHub deploy key
#   8. cron 등록 (ops-monitor / daily-review / monthly-evaluator)
#   9. .claude memory + agents + skills sync
#  10. PM2 시작 + 헬스체크

set -e

# ── 인자 ────────────────────────────────────────────────────────────────
TARGET="${1:-}"
DRY_RUN=false
[ "${2:-}" = "--dry-run" ] && DRY_RUN=true

if [ -z "$TARGET" ]; then
    echo "Usage: $0 <user@host> [--dry-run]"
    echo "Example: $0 mint@121.183.229.140"
    exit 1
fi

LOCAL_REPO=/home/hcpark/antigravity
REMOTE_REPO='~/auto_trading'

# ── 헬퍼 ────────────────────────────────────────────────────────────────
run() {
    if $DRY_RUN; then
        echo "[DRY] $*"
    else
        echo "[RUN] $*"
        eval "$@"
    fi
}

remote() {
    run "ssh $TARGET '$1'"
}

step() {
    echo
    echo "════════════════════════════════════════════════════════════════"
    echo "STEP $1: $2"
    echo "════════════════════════════════════════════════════════════════"
}

# ── 0. 사전 점검 ────────────────────────────────────────────────────────
step 0 "사전 점검"
run "ssh -o ConnectTimeout=5 $TARGET 'echo Connected as \$(whoami) on \$(hostname)'"

# ── 1. 시스템 패키지 ────────────────────────────────────────────────────
step 1 "시스템 패키지 설치"
remote "sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv postgresql postgresql-contrib git curl build-essential libpq-dev"

# ── 2. Node + PM2 ───────────────────────────────────────────────────────
step 2 "Node.js + PM2"
remote "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
remote "sudo apt-get install -y nodejs"
remote "sudo npm install -g pm2"

# ── 3. Claude Code CLI ──────────────────────────────────────────────────
step 3 "Claude Code CLI"
remote "sudo npm install -g @anthropic-ai/claude-code"
echo "[NOTE] Claude Code OAuth 로그인은 신서버에서 수동으로:"
echo "        ssh $TARGET"
echo "        claude  # 그 다음 /login → Max plan 계정 사용"

# ── 4. PostgreSQL ───────────────────────────────────────────────────────
step 4 "PostgreSQL DB 생성"
remote "sudo -u postgres psql -c \"CREATE USER antigravity_user WITH PASSWORD 'antigravity_password';\" || true"
remote "sudo -u postgres psql -c \"CREATE DATABASE antigravity_db OWNER antigravity_user;\" || true"
remote "sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE antigravity_db TO antigravity_user;\""

# ── 5. Git clone + 의존성 ───────────────────────────────────────────────
step 5 "Git clone + 의존성"
remote "test -d $REMOTE_REPO || git clone https://github.com/plzmlc777/antigravity_at.git $REMOTE_REPO"
remote "cd $REMOTE_REPO && git checkout master && git pull origin master"
remote "cd $REMOTE_REPO/backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
remote "cd $REMOTE_REPO/frontend && npm install && npm run build"

# ── 6. .env 안내 (수동 단계) ────────────────────────────────────────────
step 6 ".env 파일 (수동)"
echo "[ACTION REQUIRED] 다음을 직접 신서버로 안전하게 복사:"
echo "  scp $LOCAL_REPO/.env $TARGET:$REMOTE_REPO/.env"
echo "  필수 변수: POSTGRES_*, KIWOOM_*, BINANCE_* (있다면), SECRET_KEY"

# ── 7. SSH + GitHub Deploy Key ──────────────────────────────────────────
step 7 "GitHub deploy key (자동 commit/push 용)"
remote "test -f ~/.ssh/github_deploy || ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N '' -C 'new-server-deploy'"
remote "cat ~/.ssh/github_deploy.pub"
echo "[ACTION REQUIRED] 위 공개키를 GitHub repo Settings → Deploy keys 에 등록 (Allow write access)"
remote "cat > ~/.ssh/config << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF"
remote "cd $REMOTE_REPO && git remote set-url origin git@github.com:plzmlc777/antigravity_at.git"

# ── 8. DB 마이그레이션 ──────────────────────────────────────────────────
step 8 "DB 마이그레이션"
remote "cd $REMOTE_REPO/backend && source venv/bin/activate && python3 -m migrations.run_migrations"
echo "[ACTION] OHLCV 시계열 데이터(약 2,700만 건) 별도 dump → restore 권장:"
echo "  pg_dump -t ohlcv antigravity_db > ohlcv.sql"
echo "  scp ohlcv.sql $TARGET:~ && ssh $TARGET 'psql antigravity_db < ohlcv.sql'"

# ── 9. .claude sync (memory + agents + skills) ─────────────────────────
step 9 ".claude memory/agents/skills sync"
run "rsync -avz --delete $LOCAL_REPO/.claude/agents/ $TARGET:$REMOTE_REPO/.claude/agents/"
run "rsync -avz --delete $LOCAL_REPO/.claude/skills/ $TARGET:$REMOTE_REPO/.claude/skills/"
run "rsync -avz $LOCAL_REPO/.claude/strategy_candidates/ $TARGET:$REMOTE_REPO/.claude/strategy_candidates/ || true"
echo "[NOTE] Claude memory(~/.claude/projects/...)는 신서버 hostname 디렉터리로 별도 복사 필요"

# ── 10. cron 등록 ───────────────────────────────────────────────────────
step 10 "cron 등록"
remote "(crontab -l 2>/dev/null | grep -v auto_trading/scripts/cron_; echo '*/30 * * * * $REMOTE_REPO/scripts/cron_ops_monitor.sh'; echo '0 7 * * 1-5 $REMOTE_REPO/scripts/cron_daily_review.sh'; echo '0 0 1 * * $REMOTE_REPO/scripts/cron_monthly_evaluator.sh') | crontab -"
remote "crontab -l"

# ── 11. PM2 시작 ────────────────────────────────────────────────────────
step 11 "PM2 시작"
remote "cd $REMOTE_REPO && pm2 start ecosystem.config.cjs && pm2 save && pm2 startup | tail -1 | sudo bash || true"
remote "pm2 status"

# ── 12. 헬스 체크 ───────────────────────────────────────────────────────
step 12 "헬스 체크"
remote "curl -sS http://localhost:8001/api/v1/status | head"
remote "curl -sS http://localhost:8001/api/v1/system/version || true"

# ── 13. Kill switch (선택, 검증 후 활성화) ──────────────────────────────
step 13 "Kill switch 활성화 (검증 후 수동)"
echo "[ACTION] 신서버에서 1주일 페이퍼 검증 후 다음 줄을 .env 에 추가:"
echo "  KILL_SWITCH_ENABLED=true"
echo "  그 후 pm2 restart at-backend"

echo
echo "✅ 신서버 배포 스크립트 완료. 수동 단계 (ACTION REQUIRED) 모두 처리되었는지 확인."
