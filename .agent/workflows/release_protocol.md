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

## 3. Apply Version Bump & DB Sync
1.  Update `package.json` (Frontend)
2.  Update `backend/app/core/config.py` (Backend VERSION variable)
3.  **MANDATORY**: Update `system_metadata` table in PostgreSQL:
    ```sql
    UPDATE system_metadata SET value = 'vX.Y.Z', updated_at = NOW() WHERE key = 'version';
    ```
4.  (If applicable) Verify dynamic version injection works.

## 4. Commit, Tag & Push
**MANDATORY**: You MUST push the changes to density the remote repository immediately.
```bash
git add .
git commit -m "chore: bump version to vX.Y.Z"
# git tag vX.Y.Z (Optional but recommended)
git push
```

## 5. Post-Release
- Restart Services (`pm2 restart all`).
- Verify UI shows correct version.
- Notify User with the **Change Log Report** generated in Step 2.
