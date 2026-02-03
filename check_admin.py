import sys
import os
from sqlalchemy import text

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.db.session import engine

def check():
    with engine.connect() as conn:
        result = conn.execute(text('SELECT email, is_admin FROM users'))
        rows = result.all()
        for row in rows:
            print(f"User: {row.email}, Admin: {row.is_admin}")

if __name__ == "__main__":
    check()
