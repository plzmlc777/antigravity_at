-- Migration: Add 'environment' field to exchange_accounts table
-- Version: 0.9.9.53
-- Description: Replace is_virtual + api_url with single 'environment' field
--
-- Run this migration with:
--   psql -U <user> -d <database> -f 001_add_environment_field.sql

-- 1. Add the new 'environment' column
ALTER TABLE exchange_accounts
ADD COLUMN IF NOT EXISTS environment VARCHAR(20) DEFAULT 'real';

-- 2. Migrate existing data based on is_virtual flag
UPDATE exchange_accounts
SET environment = CASE
    WHEN is_virtual = true THEN 'virtual'
    ELSE 'real'
END
WHERE environment IS NULL OR environment = 'real';

-- 3. (Optional) Remove old columns after verifying migration
-- Uncomment these lines after confirming the migration worked correctly:
-- ALTER TABLE exchange_accounts DROP COLUMN IF EXISTS is_virtual;
-- ALTER TABLE exchange_accounts DROP COLUMN IF EXISTS api_url;

-- 4. Verify migration
SELECT id, account_name, environment,
       CASE WHEN is_virtual THEN 'virtual' ELSE 'real' END as expected_env
FROM exchange_accounts;
