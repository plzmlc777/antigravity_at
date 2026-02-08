# Remote Server Deployment Guide

## CRITICAL SAFETY RULES

### 1. LIVE SESSION CHECK (MANDATORY)

**Before ANY deployment to the remote server, you MUST check for running live sessions:**

```bash
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'
```

#### If RUNNING sessions exist with `is_paper = f` (REAL TRADING):

> **STOP! DO NOT DEPLOY!**
>
> Real money is at risk. The user must explicitly approve the deployment.
>
> Ask: "라이브 실거래 세션이 실행 중입니다. 정말 배포를 진행하시겠습니까?"

#### If only `is_paper = t` (Paper Trading) sessions exist:
- Proceed with caution
- Warn the user that paper trading sessions will be interrupted

#### If no RUNNING sessions:
- Safe to deploy

---

## Deployment Procedure

### Step 1: Pre-Deployment Checks

```bash
# 1. Check live sessions (CRITICAL)
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'

# 2. Check current version
ssh mint@121.183.229.140 'cd /home/mint/auto_trading && cat backend/app/core/config.py | grep PROJECT_VERSION'

# 3. Check pending updates
ssh mint@121.183.229.140 'cd /home/mint/auto_trading && git fetch && git log HEAD..origin/master --oneline'
```

### Step 2: Database Backup (MANDATORY)

**Always backup before any deployment:**

```bash
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password pg_dump -U antigravity_user -h localhost antigravity_db > ~/db_backup_$(date +%Y%m%d_%H%M%S).dump'
```

### Step 3: Check for DB Schema Changes

```bash
# Check if any model files changed
ssh mint@121.183.229.140 'cd /home/mint/auto_trading && git diff HEAD..origin/master --name-only | grep -E "(models|migrations)"'
```

If models changed, identify and run the appropriate migration script after pulling.

### Step 4: Pull Code

```bash
ssh mint@121.183.229.140 'cd /home/mint/auto_trading && git pull origin master'
```

### Step 5: Run Migrations (if needed)

```bash
ssh mint@121.183.229.140 'cd /home/mint/auto_trading/backend && source venv/bin/activate && python migrate_<script_name>.py'
```

### Step 6: Restart Services

```bash
ssh mint@121.183.229.140 'cd /home/mint/auto_trading && pm2 restart all'
```

### Step 7: Verify Deployment

```bash
# Check services are online
ssh mint@121.183.229.140 'pm2 status'

# Check backend health
ssh mint@121.183.229.140 'curl -s http://localhost:8001/health'

# Check live sessions restored (if any were running)
ssh mint@121.183.229.140 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore\|session\|RUNNING"'
```

### Step 8: Post-Deployment Backup

```bash
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password pg_dump -U antigravity_user -h localhost antigravity_db > ~/db_backup_post_deploy_$(date +%Y%m%d_%H%M%S).dump'
```

---

## Server Information

| Item | Value |
|------|-------|
| Host | 121.183.229.140 |
| User | mint |
| Project Path | /home/mint/auto_trading |
| Backend Port | 8001 |
| Frontend Port | 5173 |
| DB Name | antigravity_db |
| DB User | antigravity_user |

---

## Emergency Recovery

### If Live Session Lost After Restart:

1. Check if session is in DB:
```bash
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'
```

2. Restart backend to trigger session restore:
```bash
ssh mint@121.183.229.140 'pm2 restart at-backend && sleep 5 && pm2 logs at-backend --lines 50 --nostream'
```

3. Verify session restored:
```bash
ssh mint@121.183.229.140 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore"'
```

### If Config Data Lost:

1. Check backup files:
```bash
ssh mint@121.183.229.140 'ls -la ~/db_backup*.dump'
```

2. Restore from backup:
```bash
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db < ~/db_backup_<timestamp>.dump'
```

---

## Incident Log

| Date | Incident | Cause | Resolution |
|------|----------|-------|------------|
| 2026-02-08 | Live session 298380 interrupted during v1.0.0.2 deploy | PM2 restart killed running session | Session auto-restored after backend restart; Config restored from live_bot_sessions |

---

## Reminders for Claude

1. **ALWAYS check for live sessions before deployment**
2. **ALWAYS backup DB before any changes**
3. **If real trading session exists, ask user for explicit approval**
4. **After PM2 restart, verify live sessions are restored**
5. **Keep backup files for at least 7 days**
