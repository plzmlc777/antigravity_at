---
description: Standard Version Release & Reporting Protocol
---
# Version Release Protocol

**Trigger**: User requests a "Version Up" or "Deployment".

## 1. Pre-Release Checks
- [ ] **Run Tests**: Ensure all current features (especially recently modified ones) are working.
- [ ] **DB Backup**: Create a labeled DB backup (e.g., `db_backup_v0.9.3.x.sql`) per `database_migration.md`.

## 2. Generate Change Log Report
**CRITICAL**: You must generate a detailed report comparing the new version with the previous one.
**Format**:

### Version vX.Y.Z Release Report

#### 1. User Ordered Changes
*List changes explicitly requested by the user.*
*   [Feature/Fix Name]: Description of user's request and the implementation.
*   *Example*: "Added Limit Order support (Requested 2024-01-15)".

#### 2. Self-Initiated Changes (Agent)
*List changes made autonomously by the AI for stability, refactoring, or bug fixing.*
*   [Category]: Exact change and REASON.
*   *Example*: "Refactored `version.js` to avoid hardcoding (Initiated to prevent future errors)".

#### 3. Modified Files
*List of all files modified in this release.*

## 3. Apply Version Bump (Use Script Only!)

> **IMPORTANT**: 버전은 **코드 2곳**만 수정하면 됨 (DB 저장 없음)

**반드시 `bump_version.sh` 스크립트를 사용:**

### Linux 환경 (WSL 내부)
```bash
# 버전업 + 커밋 + 태그 + 푸시 + PM2 재시작 (올인원)
./scripts/bump_version.sh X.Y.Z

# 푸시 없이 (로컬 테스트용)
./scripts/bump_version.sh X.Y.Z --no-push
```

### WSL 환경 (Windows에서 실행)
```bash
# Git Bash / PowerShell에서 WSL 통해 실행
wsl -e bash -c "cd /home/hcpark/antigravity && ./scripts/bump_version.sh X.Y.Z"

# 또는 WSL 터미널에서 직접 실행
cd /home/hcpark/antigravity && ./scripts/bump_version.sh X.Y.Z
```

### PM2 바이너리가 없는 경우
`tools/node/`가 .gitignore에 포함되어 fresh clone 시 PM2가 없을 수 있음:
```bash
# 시스템 PM2 사용 (글로벌 설치된 경우)
pm2 restart at-backend at-frontend

# 또는 npm 스크립트 사용
npm run restart
```

스크립트가 자동으로 수정하는 파일:
- `frontend/package.json` — `version` 필드
- `backend/app/core/config.py` — `PROJECT_VERSION` 변수

## 4. Commit, Tag & Push

> **NOTE**: `bump_version.sh` 스크립트가 커밋, 태그, 푸시를 자동 처리합니다.
> 수동으로 할 필요 없음!

스크립트 미사용 시 (비권장):
```bash
git add .
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

## 5. Post-Release
- Restart Services (`pm2 restart all`).
- Verify UI shows correct version.
- Notify User with the **Change Log Report** generated in Step 2.

## 6. Remote Server Deployment

### 일반 배포 (코드 변경만)
```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"
```

### DB 마이그레이션 포함 배포
```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && cd backend && python3 -m migrations.run_migrations && cd .. && pm2 restart at-backend at-frontend"
```

### Git 히스토리 재작성 후 (force push 후)
`git pull`이 실패하므로 force reset 필요:
```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git fetch origin && git reset --hard origin/master && pm2 restart at-backend at-frontend"
```

### 버전 확인
```bash
# 로컬
curl -s http://localhost:8001/api/v1/system/version

# 리모트
ssh mint@121.183.229.140 "curl -s http://localhost:8001/api/v1/system/version"
```
