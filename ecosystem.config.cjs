module.exports = {
    apps: [
        {
            name: "at-backend",
            script: "./venv/bin/python3",
            args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8001",
            cwd: "./backend",
            env: {
                PYTHONPATH: ".",
                PYTHONDONTWRITEBYTECODE: "1"
            }
        },
        {
            name: "at-frontend",
            script: "npm",
            args: "run dev -- --host 0.0.0.0",
            cwd: "./frontend",
            env: {
                NODE_ENV: "development"
            }
        },
        {
            // Phase D — weekly LEARN→EVOLVE→REFLECT cycle.
            // PM2 cron_restart fires the script every Sunday at 09:07 local time.
            // The script runs to completion then exits; PM2 reschedules for next week.
            // Logs land in .claude/skills/at-orchestrator/runs/cycle_<UTC>.log
            name: "at-weekly-cycle",
            script: "./.claude/skills/at-orchestrator/scripts/run_weekly_cycle.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "7 9 * * 0"
        },
        {
            // SAS Phase 3 — daily strategy generator.
            // CIO-20260408-015. Every day at 09:00 local, meta-learner rotates
            // through 8 categories to emit 1 strategy gap_signal; main-turn
            // dispatches strategy-builder autonomous which auto-registers
            // to the audition pool (Step 7.5). Idempotent: skips if today's
            // slot is already filled.
            name: "sas-daily-generator",
            script: "./.claude/skills/at-orchestrator/scripts/sas/run_daily_generator.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "0 9 * * *"
        },
        {
            // SAS Phase 3 — weekly audition judge.
            // CIO-20260408-015. Every Monday at 10:00 local, audition-judge
            // agent runs a standardized backtest competition on this week's
            // audition candidates and selects exactly ONE winner (or none).
            // Includes graveyard soft-move for eliminated strategies.
            name: "sas-weekly-judge",
            script: "./.claude/skills/at-orchestrator/scripts/sas/run_weekly_judge.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "0 10 * * 1"
        },
        {
            // SAS Phase 4 — monthly graveyard resurrect.
            // CIO-20260408-015. Day 1 of each month at 11:00 local.
            // Reviews eliminated pool (judged >=30 days ago), classifies
            // elimination reasons, and resurrects up to 3 strategies that
            // meet the threshold score. File-level restore from _graveyard/.
            name: "sas-monthly-resurrect",
            script: "./.claude/skills/at-orchestrator/scripts/sas/run_monthly_resurrect.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "0 11 1 * *"
        }
    ]
};
