---
description: Standard protocol for deploying changes to local and remote servers using PM2
---

# Deployment Protocol

This workflow defines the standard operating procedure for developing, testing, and deploying the Auto Trading application.

## 1. Local Development & Testing

모든 명령은 `auto_trading/` 디렉토리에서 실행:

1.  **Start Services (Unified Script)**:

    **Linux 환경**:
    ```bash
    ./deploy_with_pm2.sh
    ```

    **WSL 환경 (Git Bash 등)**:
    ```bash
    wsl -e bash -c "cd /home/hcpark/antigravity && ./deploy_with_pm2.sh"
    ```

2.  **Verify Status**:

    **Linux 환경**:
    ```bash
    npm run status
    # 또는: pm2 status
    ```

    **WSL 환경**:
    ```bash
    wsl -e bash -c "cd /home/hcpark/antigravity && pm2 status"
    ```

    Ensure `at-backend` and `at-frontend` are 'online'.

3.  **Apply Changes / Restart**:

    **Linux 환경 (직접 실행)**:
    ```bash
    npm run restart
    # 또는: pm2 restart all

    # 개별 재시작
    ./tools/node/bin/pm2 restart at-backend
    ./tools/node/bin/pm2 restart at-frontend
    ```

    **WSL 환경 (Git Bash 등 Windows에서)**:
    ```bash
    # 전체 재시작
    wsl -e bash -c "cd /home/hcpark/antigravity && pm2 restart all"

    # 전체 재배포 (의존성 재설치 포함)
    wsl -e bash -c "cd /home/hcpark/antigravity && ./deploy_with_pm2.sh"

    # 개별 재시작
    wsl -e bash -c "cd /home/hcpark/antigravity && pm2 restart at-backend"
    wsl -e bash -c "cd /home/hcpark/antigravity && pm2 restart at-frontend"
    ```

4.  **Check Logs**:

    **Linux 환경**:
    ```bash
    npm run logs
    # 또는: pm2 logs
    ```

    **WSL 환경**:
    ```bash
    wsl -e bash -c "cd /home/hcpark/antigravity && pm2 logs --lines 20"
    ```

## 2. Checkpoints & Pushing Changes

**CRITICAL RULE**: Before starting *any* new major task or after completing a significant feature/fix, YOU MUST CREATE A GIT TAG.

1.  **Commit Changes**:
    ```bash
    git add .
    git commit -m "Description of changes"
    ```

2.  **Create Tag (Rollback Point)**:
    ```bash
    # Format: v[Major].[Minor].[Patch]-[feature]-[status]
    git tag -a v1.x.x-feature-name -m "Validated checkpoint"
    ```

3.  **Push Code & Tags**:
    ```bash
    git push origin master
    git push --tags
    ```

## 3. Remote Server Deployment (SSH Direct)

> [!IMPORTANT]
> 로컬에서 SSH로 직접 리모트 서버에 접속하여 배포합니다.

### Remote Server Info

| 항목 | 값 |
|------|-----|
| Host | 121.183.229.140 |
| User | mint |
| Path | ~/auto_trading |
| PM2 | /usr/local/bin/pm2 (global) |

### Quick Deploy (코드만 변경된 경우)

```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend && pm2 status"
```

### Full Deploy with DB Migration (스키마 변경 포함)

```bash
# 1. Pull + Migration + Restart (올인원)
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && cd backend && python3 -m migrations.run_migrations && cd .. && pm2 restart at-backend at-frontend && pm2 status"
```

### Step-by-Step Deploy

1. **Pull Latest Code**:
    ```bash
    ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master"
    ```

2. **Run DB Migration (스키마 변경 시)**:
    ```bash
    ssh mint@121.183.229.140 "cd ~/auto_trading/backend && python3 -m migrations.run_migrations"
    ```
    > 마이그레이션 스크립트는 멱등성(idempotent)이 있어 이미 적용된 경우 자동 skip

3. **Restart Services**:
    ```bash
    ssh mint@121.183.229.140 "pm2 restart at-backend at-frontend"
    ```

4. **Verify Deployment**:
    ```bash
    # 서비스 상태 확인
    ssh mint@121.183.229.140 "pm2 status"

    # 버전 확인
    ssh mint@121.183.229.140 "curl -s http://localhost:8001/api/v1/system/version"
    ```

5. **Check Logs (if needed)**:
    ```bash
    ssh mint@121.183.229.140 "pm2 logs --lines 50"
    ```

### Full Deploy (with dependencies)

Dependencies가 변경된 경우:

```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pip3 install -r backend/requirements.txt && cd frontend && npm install && cd .. && pm2 restart at-backend at-frontend"
```

## 4. Configuration Standards

- **Backend**: Uses `/usr/bin/python3` (System Python)
- **Frontend**: Runs via `npm run dev` (Vite) managed by PM2
- **Ports**:
    - Frontend: 5173
    - Backend: 8001
- **PM2 Config**: `ecosystem.config.cjs`

## 5. Auto-Start Configuration

| 이벤트 | 자동 시작 | 방식 |
|--------|----------|------|
| 시스템 재부팅 | ✅ | systemd (pm2-admin-ubuntu.service) |
| 로그아웃/로그인 | ✅ | ~/.bashrc (pm2 resurrect) |

```bash
# 현재 프로세스 목록 저장 (설정 변경 후 필수)
pm2 save

# 저장된 프로세스 파일: ~/.pm2/dump.pm2
```

## 6. Database Backup & Migration

### Pre-Deployment Backup (권장)

DB 스키마 변경 전 백업:

```bash
# 로컬 서버
PGPASSWORD=antigravity_password pg_dump -h localhost -U antigravity_user -d antigravity_db > backup_v$(date +%Y%m%d).sql

# 리모트 서버 (SSH 경유)
ssh mint@121.183.229.140 "cd ~/auto_trading && PGPASSWORD=<password> pg_dump -h localhost -U <user> -d <db> > backup_$(date +%Y%m%d).sql"
```

### Migration Scripts

마이그레이션 파일 위치: `backend/migrations/`

| 파일 | 설명 |
|------|------|
| `run_migrations.py` | 마이그레이션 실행 스크립트 |
| `001_add_environment_field.sql` | environment 컬럼 추가 |

```bash
# 마이그레이션 실행 (멱등성 보장)
cd backend && python3 -m migrations.run_migrations
```

### Migration 작성 규칙

1. 파일명: `NNN_description.sql` (예: `002_add_new_column.sql`)
2. `run_migrations.py`에 함수 추가
3. `IF NOT EXISTS` / `IF EXISTS` 사용하여 멱등성 보장

## 7. Troubleshooting

### SSH 접속 실패

SSH 키가 등록되어 있어야 합니다:
```bash
# 로컬 공개키 확인
cat ~/.ssh/id_ed25519.pub

# 리모트에 등록 (최초 1회)
ssh mint@121.183.229.140 "mkdir -p ~/.ssh && echo 'YOUR_PUBLIC_KEY' >> ~/.ssh/authorized_keys"
```

### 서비스 상태 확인

```bash
ssh mint@121.183.229.140 "pm2 status && pm2 logs --lines 20"
```

### 브랜치 불일치

리모트 서버는 항상 `master` 브랜치를 사용합니다:
```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git branch && git status"
```

### 배포 롤백

문제 발생 시 이전 버전으로 롤백:
```bash
# 특정 커밋으로 롤백
ssh mint@121.183.229.140 "cd ~/auto_trading && git reset --hard <commit_hash> && pm2 restart at-backend at-frontend"

# 또는 특정 태그로 롤백
ssh mint@121.183.229.140 "cd ~/auto_trading && git checkout v0.9.9.53 && pm2 restart at-backend at-frontend"
```

> ⚠️ DB 스키마 변경이 포함된 경우 백업에서 복구 필요
