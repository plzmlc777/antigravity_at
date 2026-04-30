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

// Loop wrapper keeps processes alive between scheduled runs.
// Each agent sleeps until its cron schedule, executes, then sleeps again.
const SAS_WRAPPER = "./.claude/skills/at-orchestrator/scripts/sas/sas_loop_wrapper.sh";
const SAS_SCRIPTS = "./.claude/skills/at-orchestrator/scripts/sas";

const agentApps = [
    {
        // Phase D — weekly LEARN→EVOLVE→REFLECT cycle.
        name: "at-weekly-cycle",
        script: SAS_WRAPPER,
        args: "'7 9 * * 0' ./.claude/skills/at-orchestrator/scripts/run_weekly_cycle.sh",
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // SAS Phase 3 — daily strategy generator. 23:00 UTC (08:00 KST next day) daily.
        name: "sas-daily-generator",
        script: SAS_WRAPPER,
        args: `'0 23 * * *' ${SAS_SCRIPTS}/run_daily_generator.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // SISDS Phase 3 — sandbox researcher processor. Every 2 hours.
        name: "sas-sandbox-processor",
        script: SAS_WRAPPER,
        args: `'0 */2 * * *' ${SAS_SCRIPTS}/run_sandbox_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // SISDS Phase 4 — paper scheduler. Every 6 hours.
        name: "sas-paper-scheduler",
        script: SAS_WRAPPER,
        args: `'0 */6 * * *' ${SAS_SCRIPTS}/run_paper_scheduler.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // SISDS Phase 6 — live monitor. Daily 06:00 UTC (15:00 KST).
        name: "sas-live-monitor",
        script: SAS_WRAPPER,
        args: `'0 6 * * *' ${SAS_SCRIPTS}/run_live_monitor.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // SISDS Phase 8 — meta-observer. Sunday 04:00 UTC (13:00 KST).
        name: "sas-meta-observer",
        script: SAS_WRAPPER,
        args: `'0 4 * * 0' ${SAS_SCRIPTS}/run_meta_observer.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // SAS Phase 3 — weekly audition judge. Monday 10:00 UTC.
        name: "sas-weekly-judge",
        script: SAS_WRAPPER,
        args: `'0 10 * * 1' ${SAS_SCRIPTS}/run_weekly_judge.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // SAS Phase 4 — monthly graveyard resurrect. Day 1, 11:00 UTC.
        name: "sas-monthly-resurrect",
        script: SAS_WRAPPER,
        args: `'0 11 1 * *' ${SAS_SCRIPTS}/run_monthly_resurrect.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Health watchdog — checks audition freshness + per-agent exit codes.
        // Sends Telegram alerts (TELEGRAM_BOT_TOKEN/CHAT_ID via .env). Every 6h.
        name: "sas-watchdog",
        script: SAS_WRAPPER,
        args: `'0 */6 * * *' ${SAS_SCRIPTS}/run_watchdog.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    }
];

module.exports = {
    apps: enableAgents ? [...coreApps, ...agentApps] : coreApps
};
