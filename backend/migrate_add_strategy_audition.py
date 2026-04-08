"""
Migration: Create strategy_audition table.

SAS (Strategy Audition System) — CIO-20260408-015.
Tracks every AI-generated strategy's lifecycle through audition → graduated/eliminated.

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
            "SELECT to_regclass('public.strategy_audition')"
        )).scalar()

        if exists is None:
            conn.execute(text(
                """
                CREATE TABLE strategy_audition (
                    id SERIAL PRIMARY KEY,
                    strategy_id VARCHAR NOT NULL UNIQUE,
                    gap_signal_id VARCHAR,
                    category VARCHAR NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'audition',
                    audition_week VARCHAR NOT NULL,
                    rank_in_week INTEGER,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    judged_at TIMESTAMP,
                    backtest_result JSON,
                    judge_notes TEXT,
                    graveyard_path VARCHAR,
                    resurrect_count INTEGER NOT NULL DEFAULT 0,
                    last_resurrected_at TIMESTAMP,
                    metadata JSON
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX ix_strategy_audition_strategy_id ON strategy_audition (strategy_id)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_strategy_audition_gap_signal_id ON strategy_audition (gap_signal_id)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_strategy_audition_category ON strategy_audition (category)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_strategy_audition_status ON strategy_audition (status)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_strategy_audition_week ON strategy_audition (audition_week)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_strategy_audition_status_week "
                "ON strategy_audition (status, audition_week)"
            ))
            print("Created: strategy_audition table + 6 indexes")
        else:
            print("Already exists: strategy_audition")

        conn.commit()


if __name__ == "__main__":
    migrate()
