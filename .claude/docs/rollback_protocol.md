---
description: Git-focused Rollback Protocol (Code Only by Default)
---
# Rollback Protocol

**Trigger**: When the user requests a "Rollback" to a previous version.
**Goal**: Revert the Code state to the target version. 

> [!IMPORTANT]
> **Default Policy**: Unless explicitly requested by the user, **DO NOT rollback the database**. Only perform a Git rollback.

## Procedure

### 1. Identify Target Version
Confirm the version or commit hash to rollback to (e.g., `v0.9.3.3`).

### 2. Stop Services
```bash
export PATH="$(pwd)/tools/node/bin:$PATH"
pm2 stop all
```

### 3. Revert Code
Use Git to checkout the previous state.
```bash
# Stash any local changes first
git stash

# Checkout target
git checkout <version_tag_or_hash>
```

### 4. Restore Database (OPTIONAL - ONLY IF REQUESTED)
**Only proceed if the user specifically asked to rollback the database.**
Find the matching backup file in `backups/`.

```bash
# Restore Dump
PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost -d antigravity_db < backups/db_backup_XXXX.sql
```

### 5. Restart Services
```bash
export PATH="$(pwd)/tools/node/bin:$PATH"
pm2 restart all
```

### 6. Verify
- Check Frontend Version Display in the UI.
- Check Logs: `pm2 logs`
