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
        }
    ]
};
