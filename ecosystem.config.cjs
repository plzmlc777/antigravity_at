// Environment-aware PM2 config.
// Local (default): backend + frontend only. Agents are on-demand via CLI.
// GCP/Remote: backend + frontend + all SISDS cron agents.
//
// Usage:
//   pm2 start ecosystem.config.cjs                    # local (core only)
//   ENABLE_AGENTS=1 pm2 start ecosystem.config.cjs    # remote (core + agents)

const enableAgents = process.env.ENABLE_AGENTS === '1';

const coreApps = [
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
];

const agentApps = [
    {
        // Phase D — weekly LEARN→EVOLVE→REFLECT cycle.
        name: "at-weekly-cycle",
        script: "./.claude/skills/at-orchestrator/scripts/run_weekly_cycle.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "7 9 * * 0"
    },
    {
        // SAS Phase 3 — daily strategy generator.
        name: "sas-daily-generator",
        script: "./.claude/skills/at-orchestrator/scripts/sas/run_daily_generator.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "0 9 * * *"
    },
    {
        // SISDS Phase 3 — sandbox researcher processor.
        name: "sas-sandbox-processor",
        script: "./.claude/skills/at-orchestrator/scripts/sas/run_sandbox_cycle.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "0 */2 * * *"
    },
    {
        // SISDS Phase 4 — paper scheduler.
        name: "sas-paper-scheduler",
        script: "./.claude/skills/at-orchestrator/scripts/sas/run_paper_scheduler.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "0 */6 * * *"
    },
    {
        // SISDS Phase 6 — live monitor. Daily 15:00 KST.
        name: "sas-live-monitor",
        script: "./.claude/skills/at-orchestrator/scripts/sas/run_live_monitor.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "0 6 * * *"
    },
    {
        // SISDS Phase 8 — meta-observer. Sunday 13:00 KST.
        name: "sas-meta-observer",
        script: "./.claude/skills/at-orchestrator/scripts/sas/run_meta_observer.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "0 4 * * 0"
    },
    {
        // SAS Phase 3 — weekly audition judge. Monday 10:00.
        name: "sas-weekly-judge",
        script: "./.claude/skills/at-orchestrator/scripts/sas/run_weekly_judge.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "0 10 * * 1"
    },
    {
        // SAS Phase 4 — monthly graveyard resurrect. Day 1, 11:00.
        name: "sas-monthly-resurrect",
        script: "./.claude/skills/at-orchestrator/scripts/sas/run_monthly_resurrect.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: false,
        cron_restart: "0 11 1 * *"
    }
];

module.exports = {
    apps: enableAgents ? [...coreApps, ...agentApps] : coreApps
};
