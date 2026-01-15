---
description: Full System Rollback Protocol (Code + Database)
---
# Full System Rollback Protocol

**Trigger**: When the user requests a "Rollback" to a previous version.
**Goal**: Revert both Code and Database to the state of the target version.

## Prerequisite
- Version tags should be associated with DB Backups (e.g., `db_backup_v0.9.3.3.sql`).

## Procedure

### 1. Identify Target Version
Confirm the version or commit hash to rollback to (e.g., `v0.9.3.3`).

### 2. Stop Services
Prevent data corruption during restore.
```bash
npx pm2 stop all
```

### 3. Revert Code
Use Git to checkout the previous state.
```bash
# If tag exists
git checkout v0.9.3.3

# OR if using commit hash
git checkout <commit_hash>
```

### 4. Restore Database (CRITICAL)
**User Requirement**: DB must match the code version.
Find the matching backup file (e.g., `db_backup_v0.9.3.3.sql`).

**PostgreSQL Restore Command:**
```bash
# Drop existing connections/db (Dangerous, use with caution or drop tables)
# Re-create DB usually required or clean restore.

# 1. Drop & Create (Clean Slate)
PGPASSWORD=antigravity_password dropdb -U antigravity_user -h localhost antigravity_db
PGPASSWORD=antigravity_password createdb -U antigravity_user -h localhost antigravity_db

# 2. Restore Dump
PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost -d antigravity_db < db_backup_v0.9.3.3.sql
```

### 5. Restart Services
```bash
npx pm2 restart all
```

### 6. Verify
- Check Frontend Version Display.
- Check DB Data Integrity (e.g., Recent orders removed if they didn't exist in old version).
