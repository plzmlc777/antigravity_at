---
description: Safe Database Migration Protocol (PREVENT DATA LOSS)
---

# Safe Database Migration Protocol

**CRITICAL RULE**: NEVER DROP OR RESET THE DATABASE TO APPLY SCHEMA CHANGES. DATA LOSS IS UNACCEPTABLE.

> **NOTE**: 이 프로젝트는 **PostgreSQL**을 사용합니다 (SQLite 아님)

## 1. Pre-Migration Safety Check
Before making ANY changes to the database structure (models):
1.  **Identify Critical Data**: Check what important data exists (User Accounts, API Keys, Order History).
    ```bash
    # PostgreSQL 접속 (credentials from .env)
    psql -h localhost -U antigravity_user -d antigravity_db -c "SELECT count(*) FROM exchange_accounts;"
    ```
2.  **Create Backup**: Always create a timestamped backup.
    ```bash
    pg_dump -h localhost -U antigravity_user antigravity_db > backups/db_backup_$(date +%Y%m%d_%H%M%S).sql
    ```

## 2. Migration Valid Paths
Choose one of the following methods. **DO NOT DROP THE DB.**

### Option A: Python Migration Script (Preferred)
프로젝트 표준: `backend/migrate_*.py` 스크립트 작성

```python
# Example: backend/migrate_add_new_column.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Check existing columns
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'your_table'
        """))
        existing = {row[0] for row in result}

        if 'new_column' not in existing:
            conn.execute(text("""
                ALTER TABLE your_table
                ADD COLUMN new_column VARCHAR(255) DEFAULT NULL
            """))
            print("Added: new_column")
        else:
            print("Skipped: new_column (already exists)")

        conn.commit()

if __name__ == "__main__":
    migrate()
```

실행:
```bash
cd backend && python3 migrate_add_new_column.py
```

### Option B: Direct SQL (Simple cases)
psql로 직접 실행:
```bash
psql -h localhost -U antigravity_user -d antigravity_db -c \
  "ALTER TABLE table_name ADD COLUMN new_col VARCHAR DEFAULT 'value';"
```

## 3. Post-Migration Verification
1.  **Verify Schema**: Ensure new columns exist.
    ```bash
    psql -h localhost -U antigravity_user -d antigravity_db -c "\d your_table"
    ```
2.  **Verify Data**: Ensure OLD data (API keys, etc.) still exists.
    ```bash
    psql -h localhost -U antigravity_user -d antigravity_db -c "SELECT * FROM exchange_accounts LIMIT 1;"
    ```

## 4. Emergency Recovery
If data is lost:
1.  **Stop Services**: `pm2 stop all`
2.  **Restore Backup**:
    ```bash
    psql -h localhost -U antigravity_user -d antigravity_db < backups/db_backup_YYYYMMDD_HHMMSS.sql
    ```
3.  **Report**: Inform the user immediately.
