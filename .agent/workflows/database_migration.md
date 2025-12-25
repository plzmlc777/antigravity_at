---
description: Safe Database Migration Protocol (PREVENT DATA LOSS)
---

# Safe Database Migration Protocol

**CRITICAL RULE**: NEVER DELETE, RESET, OR OVERWRITE AN EXISTING DATABASE FILE (`.db`, `.sqlite`, etc.) TO APPLY SCHEMA CHANGES. DATA LOSS IS UNACCEPTABLE.

## 1. Pre-Migration Safety Check
Before making ANY changes to the database structure (models):
1.  **Identify Critical Data**: Check what important data exists (User Accounts, API Keys, Order History).
    ```bash
    # Example Check
    sqlite3 backend/sql_app.db "SELECT count(*) FROM exchange_accounts;"
    ```
2.  **Create Backup**: Always create a timestamped backup.
    ```bash
    cp backend/sql_app.db backend/sql_app.db.bak_$(date +%s)
    ```

## 2. Migration Valid Paths
Choose one of the following methods. **DO NOT DELETE THE DB.**

### Option A: SQL `ALTER TABLE` (Preferred for simple additions)
If you just need to add a column:
1.  Connect to the DB.
2.  Execute the `ALTER TABLE` command.
    ```python
    # Example Script
    from sqlalchemy import create_engine, text
    engine = create_engine("sqlite:///backend/sql_app.db")
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE table_name ADD COLUMN new_column_name VARCHAR DEFAULT 'default_value'"))
    ```

### Option B: Python Migration Script
If `ALTER` is complex, write a script to:
1.  Rename old table (`ALTER TABLE x RENAME TO x_old`).
2.  Create new table with new schema (`CREATE TABLE x ...`).
3.  Copy data from old to new (`INSERT INTO x SELECT ... FROM x_old`).
4.  Drop old table (Only after verification).

## 3. Post-Migration Verification
1.  **Verify Schema**: Ensure new columns exist.
2.  **Verify Data**: Ensure OLD data (API keys, etc.) still exists.
    ```bash
    sqlite3 backend/sql_app.db "SELECT * FROM exchange_accounts LIMIT 1;"
    ```

## 4. Emergency Recovery
If data is lost:
1.  **Stop Services**: `pm2 stop all`
2.  **Restore Backup**: `cp backend/sql_app.db.bak_... backend/sql_app.db`
3.  **Report**: Inform the user immediately.
