"""
Migration: Create gap_signals table.

Queue for gap signals emitted by meta-learner / self-critic / cio and consumed
by skill-architect. See decision_log CIO-20260408-008 (P1 infrastructure).

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
            "SELECT to_regclass('public.gap_signals')"
        )).scalar()

        if exists is None:
            conn.execute(text(
                """
                CREATE TABLE gap_signals (
                    id SERIAL PRIMARY KEY,
                    signal_id VARCHAR NOT NULL UNIQUE,
                    source VARCHAR NOT NULL,
                    issued_at TIMESTAMP NOT NULL,
                    gap_type VARCHAR NOT NULL,
                    evidence JSON,
                    proposed_intent JSON,
                    activation_policy JSON,
                    status VARCHAR NOT NULL DEFAULT 'pending',
                    consumed_at TIMESTAMP,
                    consumed_by VARCHAR,
                    result JSON,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX ix_gap_signals_signal_id ON gap_signals (signal_id)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_gap_signals_source ON gap_signals (source)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_gap_signals_gap_type ON gap_signals (gap_type)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_gap_signals_status ON gap_signals (status)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_gap_signals_status_created "
                "ON gap_signals (status, created_at)"
            ))
            print("Created: gap_signals table + indexes")
        else:
            print("Already exists: gap_signals")

        conn.commit()


if __name__ == "__main__":
    migrate()
