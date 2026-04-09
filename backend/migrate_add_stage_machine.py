"""
Migration: Add state machine columns to strategy_audition + create strategy_transitions table.

SISDS Phase 1 — CIO-20260410-001.

Adds:
  strategy_audition.stage           VARCHAR  (birth|sandbox|paper|live|retired|legacy)
  strategy_audition.stage_status    VARCHAR  (pending|running|passed|failed|degraded|waiting_human)
  strategy_audition.stage_entered_at  TIMESTAMP
  strategy_audition.stage_expected_exit_at  TIMESTAMP
  strategy_audition.last_transition_by  VARCHAR(64)
  strategy_audition.last_transition_reason  TEXT
  strategy_audition.live_session_id  VARCHAR  (foreign key to live_bot_sessions)

Creates:
  strategy_transitions  — audit log of every stage transition

Also maps existing rows from legacy `status` to new `(stage, stage_status)`:
  graduated (pre-SAS)  → (legacy, passed)
  audition             → (sandbox, running)
  eliminated           → (retired, failed)
  resurrected          → (sandbox, pending)
  error                → (retired, failed)

Idempotent: safe to re-run.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text

from app.db.session import engine


def migrate():
    with engine.connect() as conn:
        # ─── 1. strategy_audition 컬럼 추가 ───────────────────────────────
        existing = conn.execute(text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'strategy_audition'
            """
        )).fetchall()
        existing_cols = {row[0] for row in existing}

        additions = [
            ("stage", "VARCHAR"),
            ("stage_status", "VARCHAR"),
            ("stage_entered_at", "TIMESTAMP"),
            ("stage_expected_exit_at", "TIMESTAMP"),
            ("last_transition_by", "VARCHAR(64)"),
            ("last_transition_reason", "TEXT"),
            ("live_session_id", "VARCHAR"),
        ]

        for col_name, col_type in additions:
            if col_name not in existing_cols:
                conn.execute(text(
                    f"ALTER TABLE strategy_audition ADD COLUMN {col_name} {col_type}"
                ))
                print(f"Added: strategy_audition.{col_name}")
            else:
                print(f"Already exists: strategy_audition.{col_name}")

        # ─── 2. 기존 데이터 매핑 (legacy → new stage machine) ────────────
        # Legacy graduated (pre-SAS) → (legacy, passed)
        conn.execute(text(
            """
            UPDATE strategy_audition
            SET stage = 'legacy',
                stage_status = 'passed',
                stage_entered_at = COALESCE(stage_entered_at, created_at),
                last_transition_by = COALESCE(last_transition_by, 'migration_script'),
                last_transition_reason = COALESCE(last_transition_reason, 'Pre-SISDS legacy graduated')
            WHERE status = 'graduated' AND audition_week = 'pre-SAS' AND stage IS NULL
            """
        ))

        # Current audition → (sandbox, running)
        conn.execute(text(
            """
            UPDATE strategy_audition
            SET stage = 'sandbox',
                stage_status = 'running',
                stage_entered_at = COALESCE(stage_entered_at, created_at),
                last_transition_by = COALESCE(last_transition_by, 'migration_script'),
                last_transition_reason = COALESCE(last_transition_reason, 'Pre-SISDS audition mapped to sandbox running')
            WHERE status = 'audition' AND stage IS NULL
            """
        ))

        # Eliminated → (retired, failed)
        conn.execute(text(
            """
            UPDATE strategy_audition
            SET stage = 'retired',
                stage_status = 'failed',
                stage_entered_at = COALESCE(stage_entered_at, judged_at, created_at),
                last_transition_by = COALESCE(last_transition_by, 'migration_script'),
                last_transition_reason = COALESCE(last_transition_reason, 'Pre-SISDS eliminated')
            WHERE status = 'eliminated' AND stage IS NULL
            """
        ))

        # Error → (retired, failed)
        conn.execute(text(
            """
            UPDATE strategy_audition
            SET stage = 'retired',
                stage_status = 'failed',
                stage_entered_at = COALESCE(stage_entered_at, judged_at, created_at),
                last_transition_by = COALESCE(last_transition_by, 'migration_script'),
                last_transition_reason = COALESCE(last_transition_reason, 'Pre-SISDS error')
            WHERE status = 'error' AND stage IS NULL
            """
        ))

        # Resurrected → (sandbox, pending)
        conn.execute(text(
            """
            UPDATE strategy_audition
            SET stage = 'sandbox',
                stage_status = 'pending',
                stage_entered_at = COALESCE(stage_entered_at, last_resurrected_at, created_at),
                last_transition_by = COALESCE(last_transition_by, 'migration_script'),
                last_transition_reason = COALESCE(last_transition_reason, 'Pre-SISDS resurrected mapped to sandbox pending')
            WHERE status = 'resurrected' AND stage IS NULL
            """
        ))

        # Any remaining with NULL stage → default to (sandbox, running)
        conn.execute(text(
            """
            UPDATE strategy_audition
            SET stage = 'sandbox',
                stage_status = 'running',
                stage_entered_at = COALESCE(stage_entered_at, created_at),
                last_transition_by = COALESCE(last_transition_by, 'migration_script'),
                last_transition_reason = COALESCE(last_transition_reason, 'Pre-SISDS default mapping')
            WHERE stage IS NULL
            """
        ))

        # ─── 3. NOT NULL constraints (after data is populated) ──────────
        conn.execute(text(
            "ALTER TABLE strategy_audition ALTER COLUMN stage SET NOT NULL"
        ))
        conn.execute(text(
            "ALTER TABLE strategy_audition ALTER COLUMN stage_status SET NOT NULL"
        ))
        print("Set NOT NULL on stage and stage_status")

        # ─── 4. Indexes ──────────────────────────────────────────────────
        for idx_name, idx_sql in [
            ("idx_sa_stage", "CREATE INDEX IF NOT EXISTS idx_sa_stage ON strategy_audition(stage)"),
            ("idx_sa_stage_status", "CREATE INDEX IF NOT EXISTS idx_sa_stage_status ON strategy_audition(stage, stage_status)"),
            ("idx_sa_expected_exit", "CREATE INDEX IF NOT EXISTS idx_sa_expected_exit ON strategy_audition(stage_expected_exit_at) WHERE stage_expected_exit_at IS NOT NULL"),
        ]:
            conn.execute(text(idx_sql))
            print(f"Index ensured: {idx_name}")

        # ─── 5. strategy_transitions 테이블 ─────────────────────────────
        exists = conn.execute(text(
            "SELECT to_regclass('public.strategy_transitions')"
        )).scalar()

        if exists is None:
            conn.execute(text(
                """
                CREATE TABLE strategy_transitions (
                    id SERIAL PRIMARY KEY,
                    strategy_id VARCHAR NOT NULL,

                    from_stage VARCHAR NOT NULL,
                    from_status VARCHAR NOT NULL,
                    to_stage VARCHAR NOT NULL,
                    to_status VARCHAR NOT NULL,

                    transitioned_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    transitioned_by VARCHAR(64) NOT NULL,
                    reason TEXT NOT NULL,

                    evidence JSON
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX idx_transitions_strategy ON strategy_transitions(strategy_id)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_transitions_time ON strategy_transitions(transitioned_at DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_transitions_by ON strategy_transitions(transitioned_by)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_transitions_from ON strategy_transitions(from_stage, from_status)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_transitions_to ON strategy_transitions(to_stage, to_status)"
            ))
            print("Created: strategy_transitions table + 5 indexes")
        else:
            print("Already exists: strategy_transitions")

        conn.commit()

        # ─── 6. Verification ─────────────────────────────────────────────
        print("\n--- Verification ---")
        rows = conn.execute(text(
            """
            SELECT stage, stage_status, COUNT(*)
            FROM strategy_audition
            GROUP BY stage, stage_status
            ORDER BY stage, stage_status
            """
        )).fetchall()
        for row in rows:
            print(f"  ({row[0]}, {row[1]}): {row[2]}")


if __name__ == "__main__":
    migrate()
