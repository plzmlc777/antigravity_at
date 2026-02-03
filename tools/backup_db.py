import os
import sys
import subprocess
from backend.app.core.config import settings

def backup_db():
    user = settings.POSTGRES_USER
    password = settings.POSTGRES_PASSWORD
    host = settings.POSTGRES_SERVER
    db_name = settings.POSTGRES_DB
    
    # Set PGPASSWORD env var
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    
    cmd = [
        "pg_dump",
        "-h", host,
        "-U", user,
        "-d", db_name,
        "-f", "backup_full_20260108.sql"
    ]
    
    print(f"Running backup for {db_name} on {host}...")
    try:
        subprocess.run(cmd, env=env, check=True)
        print("Backup successful: backup_full_20260108.sql")
    except subprocess.CalledProcessError as e:
        print(f"Backup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    backup_db()
