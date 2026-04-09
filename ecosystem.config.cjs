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
            // SISDS Phase 3 — sandbox researcher processor.
            // CIO-20260410-001. Runs 1 hour after daily generator to process
            // any (sandbox, pending) entries. Dispatches sandbox-researcher
            // agent for parameter sweep + walk-forward + promote/retire.
            // Max 1 strategy per cycle. Skip if none pending or one already running.
            name: "sas-sandbox-processor",
            script: "./.claude/skills/at-orchestrator/scripts/sas/run_sandbox_cycle.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "0 1 * * *"  // 01:00 UTC = 10:00 KST (1h after daily generator)
        },
        {
            // SISDS Phase 4 — paper scheduler.
            // CIO-20260410-001. Every 6 hours:
            //   Job 1: promote sandbox-passed → paper trading session
            //   Job 2: evaluate paper sessions older than 14 days
            name: "sas-paper-scheduler",
            script: "./.claude/skills/at-orchestrator/scripts/sas/run_paper_scheduler.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "0 */6 * * *"  // every 6 hours
        },
        {
            // SISDS Phase 6 — live monitor.
            // CIO-20260410-001. Daily at 15:00 KST (06:00 UTC).
            // Activates user-approved entries, monitors live strategies for
            // degradation, enforces 7-day grace period on degraded entries.
            name: "sas-live-monitor",
            script: "./.claude/skills/at-orchestrator/scripts/sas/run_live_monitor.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "0 6 * * *"  // 06:00 UTC = 15:00 KST
        },
        {
            // SISDS Phase 8 — meta-observer (weekly system health audit).
            // CIO-20260410-001. Sunday 13:00 KST (04:00 UTC).
            // Reviews pipeline throughput, calibration, lessons, agent performance.
            name: "sas-meta-observer",
            script: "./.claude/skills/at-orchestrator/scripts/sas/run_meta_observer.sh",
            interpreter: "bash",
            cwd: ".",
            autorestart: false,
            cron_restart: "0 4 * * 0"  // 04:00 UTC Sunday = 13:00 KST Sunday
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
