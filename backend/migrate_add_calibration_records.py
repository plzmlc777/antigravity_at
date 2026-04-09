"""
Migration: Create calibration_records table.

SISDS Phase 7 (CIO-20260410-001). Tracks prediction accuracy across stage transitions.
Idempotent: safe to re-run.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text

from app.db.session import engine


def migrate():
    with engine.connect() as conn:
        exists = conn.execute(text(
            "SELECT to_regclass('public.calibration_records')"
        )).scalar()

        if exists is None:
            conn.execute(text(
                """
                CREATE TABLE calibration_records (
                    id SERIAL PRIMARY KEY,
                    strategy_id VARCHAR NOT NULL,
                    transition VARCHAR NOT NULL,
                    measured_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    predicted JSON NOT NULL,
                    actual JSON NOT NULL,
                    gap JSON NOT NULL,
                    calibration_error FLOAT NOT NULL,
                    stage_duration_days INTEGER,
                    detected_causes JSON,
                    resolution VARCHAR
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX ix_cal_strategy_time ON calibration_records(strategy_id, measured_at DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_cal_transition ON calibration_records(transition, measured_at DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_cal_error ON calibration_records(calibration_error)"
            ))
            print("Created: calibration_records table + 3 indexes")
        else:
            print("Already exists: calibration_records")

        conn.commit()


if __name__ == "__main__":
    migrate()
