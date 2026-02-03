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
```bash
# 버전업 + 커밋 + 태그 + 푸시 + PM2 재시작 (올인원)
./scripts/bump_version.sh X.Y.Z

# 푸시 없이 (로컬 테스트용)
./scripts/bump_version.sh X.Y.Z --no-push
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
