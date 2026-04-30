"""Migrate live_trade_executions.requested_quantity Integer → Float.

Original schema was designed for Korean stocks (whole-share quantities). Crypto
needs fractional quantities (e.g. 0.131 BTC). With Integer column, every
fractional BUY signal got truncated to 0 → BUY 0 fills, no completed cycles.

Safe cast: Integer → DOUBLE PRECISION preserves all existing values.

Usage: cd backend && PYTHONPATH=. ./venv/bin/python3 migrate_qty_to_float.py
"""
from sqlalchemy import text
from app.db.session import engine

def column_type(conn, table, col):
    row = conn.execute(text(f"""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = '{table}' AND column_name = '{col}'
    """)).first()
    return row[0] if row else None

def migrate():
    with engine.connect() as conn:
        before = column_type(conn, "live_trade_executions", "requested_quantity")
        print(f"current type: {before}")
        if before is None:
            print("ERROR: column not found")
            return
        if before in ("double precision", "real", "numeric"):
            print(f"already a float type ({before}) — nothing to do")
            return
        conn.execute(text(
            "ALTER TABLE live_trade_executions "
            "ALTER COLUMN requested_quantity TYPE DOUBLE PRECISION "
            "USING requested_quantity::DOUBLE PRECISION"
        ))
        conn.commit()
        after = column_type(conn, "live_trade_executions", "requested_quantity")
        print(f"new type: {after}")

if __name__ == "__main__":
    migrate()
