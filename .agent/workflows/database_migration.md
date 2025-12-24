---
description: Safe Database Migration Protocol (PREVENT DATA LOSS)
---

# Safe Database Migration Workflow

> [!CAUTION]
> **NEVER DELETE** the database file (`sql_app.db`) to apply schema changes (e.g., adding columns) if it contains critical user data like **API Keys** or **Trading History**.
> Doing so will wipe the `exchange_accounts` table and break the application (Error 1501).

Follow these steps when you modify the backend `models` and need to update the DB schema.

## 1. Check for Critical Data
Before making any changes, check if the database contains production data.
```bash
sqlite3 backend/sql_app.db "SELECT count(*) FROM exchange_accounts;"
```
If count > 0, **DO NOT DELETE THE FILE.**

## 2. Apply Schema Changes SAFELY

### Option A: Use SQL ALTER TABLE (Recommended for simple additions)
If you just added a new column (e.g., `trailing_percent`), add it manually.

1. Open DB shell:
   ```bash
   sqlite3 backend/sql_app.db
   ```
2. Check existing schema:
   ```sql
   .schema conditional_orders
   ```
3. Add the new column:
   ```sql
   ALTER TABLE conditional_orders ADD COLUMN trailing_percent FLOAT;
   ALTER TABLE conditional_orders ADD COLUMN highest_price FLOAT;
   ```
4. Verify:
   ```sql
   .schema conditional_orders
   ```
5. Exit:
   ```sql
   .quit
   ```

### Option B: Use Migration Tool (Alembic) - *If Configured*
If Alembic is set up in the project:
1. Generate migration script:
   ```bash
   alembic revision --autogenerate -m "add trailing_percent"
   ```
2. Apply migration:
   ```bash
   alembic upgrade head
   ```

## 3. Emergency Reset (Only if strictly necessary)
If you MUST reset the DB (e.g., unrecoverable schema mismatch), you **MUST BACKUP** the keys first.

1. Export Accounts:
   ```bash
   sqlite3 backend/sql_app.db ".mode csv" ".headers on" ".output accounts_backup.csv" "select * from exchange_accounts;" ".quit"
   ```
2. Reset DB:
   ```bash
   rm backend/sql_app.db
   # Restart backend to recreate tables
   ```
3. Restore Accounts:
   ```bash
   sqlite3 backend/sql_app.db ".mode csv" ".import accounts_backup.csv exchange_accounts"
   ```

## 4. Verify Application State
After any DB change, verify the status allows trading:
```bash
curl http://localhost:8001/api/v1/status
```
Ensure specific keys are present and not returning "API ID Null" errors.
