# Remote Server Deployment Guide

> 배포 요청 시 Claude가 읽는 참조 문서.

## Safety Rules

- 배포 전 반드시 라이브 세션 확인: `is_paper = f` 실거래 존재 시 사용자 승인 필수
- 배포 전 DB 백업 필수 (최근 2개만 유지)
- 리모트 배포는 사용자 명시적 요청 시에만

## Servers

### 민트 서버 (Real: 183.99.228.81)
> 실거래 운영 + SAS 파이프라인. REAL 모드.
> Claude Code CLI 설치됨 (Max 플랜 인증).

| 항목 | 값 |
|------|-----|
| Host | 183.99.228.81 |
| User | mint |
| Path | ~/auto_trading |
| Mode | REAL |
| PM2 | at-backend, at-frontend + SAS 에이전트 8개 |

```bash
# 라이브 세션 확인
ssh mint@183.99.228.81 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'

# DB 백업
ssh mint@183.99.228.81 'PGPASSWORD=antigravity_password pg_dump -U antigravity_user -h localhost antigravity_db > ~/db_backup_$(date +%Y%m%d_%H%M%S).dump && ls -t ~/db_backup*.dump | tail -n +3 | xargs -r rm -v'

# Quick Deploy
ssh mint@183.99.228.81 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"

# Full Deploy (with SAS agents)
ssh mint@183.99.228.81 "cd ~/auto_trading && git pull origin master && cd backend && python3 -m migrations.run_migrations && cd .. && ENABLE_AGENTS=1 pm2 restart ecosystem.config.cjs"

# Verify
ssh mint@183.99.228.81 "curl -s http://localhost:8001/api/v1/system/version"

# 세션 복원 확인
ssh mint@183.99.228.81 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore\|session\|RUNNING"'
```

### 우분투 서버 (Test: 172.30.1.60)
> 테스트 전용. MOCK 모드. 사설IP (공유기 내부). 실거래 세션 체크 불필요.

| 항목 | 값 |
|------|-----|
| Host | 172.30.1.60 |
| User | ubuntu |
| Path | ~/auto_trading |
| Mode | MOCK |
| PM2 | at-backend, at-frontend만 |

```bash
# Quick Deploy
ssh ubuntu@172.30.1.60 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"

# Verify
ssh ubuntu@172.30.1.60 "curl -s http://localhost:8001/api/v1/system/version"
```

## Emergency Recovery

```bash
# 세션 복원 실패 시 백엔드 재시작
ssh <server> 'pm2 restart at-backend && sleep 5 && pm2 logs at-backend --lines 50 --nostream'

# DB 복구
ssh <server> 'ls -la ~/db_backup*.dump'
ssh <server> 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db < ~/db_backup_<timestamp>.dump'
```

## Troubleshooting

```bash
# SSH host key 오류
ssh-keyscan -H <host> >> ~/.ssh/known_hosts

# WSL Git credential
git config --global credential.helper '/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe'

# 서비스 상태
ssh <server> "pm2 status && pm2 logs --lines 20"
```
