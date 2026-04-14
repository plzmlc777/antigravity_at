# Remote Server Deployment Guide

> 배포 요청 시 Claude가 읽는 참조 문서.

## Safety Rules

- 배포 전 반드시 라이브 세션 확인: `is_paper = f` 실거래 존재 시 사용자 승인 필수
- 배포 전 DB 백업 필수 (최근 2개만 유지)
- 리모트 배포는 사용자 명시적 요청 시에만

## Servers

### 민트 서버 (Real: 121.183.229.140)
| 항목 | 값 |
|------|-----|
| Host | 121.183.229.140 |
| User | mint |
| Path | ~/auto_trading |

```bash
# 라이브 세션 확인
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'

# DB 백업
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password pg_dump -U antigravity_user -h localhost antigravity_db > ~/db_backup_$(date +%Y%m%d_%H%M%S).dump && ls -t ~/db_backup*.dump | tail -n +3 | xargs -r rm -v'

# Quick Deploy
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"

# Full Deploy (with migration)
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && cd backend && python3 -m migrations.run_migrations && cd .. && pm2 restart at-backend at-frontend"

# Verify
ssh mint@121.183.229.140 "curl -s http://localhost:8001/api/v1/system/version"

# 세션 복원 확인
ssh mint@121.183.229.140 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore\|session\|RUNNING"'
```

### GCP 서버 (Temp: 34.64.87.89)
> 민트 서버 이사 기간(~2026-04-24) 임시 운영. REAL 모드.
> 키움 API 지정단말기 + Binance IP 화이트리스트 등록 완료.

| 항목 | 값 |
|------|-----|
| Host | 34.64.87.89 |
| User | hcpark |
| Path | ~/auto_trading |
| Branch | master (기본 브랜치 아님, 반드시 master) |
| Mode | REAL |
| Spec | 2 vCPU, 4GB RAM (asia-northeast3-a) |

```bash
# 라이브 세션 확인
ssh hcpark@34.64.87.89 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'

# Quick Deploy
ssh hcpark@34.64.87.89 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"

# Full Deploy (with frontend rebuild)
ssh hcpark@34.64.87.89 "cd ~/auto_trading && git pull origin master && cd frontend && npm run build && cd .. && pm2 restart at-backend at-frontend"

# Verify
ssh hcpark@34.64.87.89 "curl -s http://localhost:8001/api/v1/status"
```

### 우분투 서버 (Test: 121.183.229.170)
> 테스트 전용. MOCK 모드. 실거래 세션 체크 불필요.

| 항목 | 값 |
|------|-----|
| Host | 121.183.229.170 |
| User | ubuntu |
| Path | ~/auto_trading |
| Mode | MOCK |

```bash
# Quick Deploy
ssh ubuntu@121.183.229.170 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"

# Verify
ssh ubuntu@121.183.229.170 "curl -s http://localhost:8001/api/v1/system/version"
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
