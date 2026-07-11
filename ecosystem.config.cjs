// Environment-aware PM2 config.
// Local (default): backend + frontend only. Agents are on-demand via CLI.
// GCP/Remote: backend + frontend + all SISDS cron agents.
//
// Usage:
//   pm2 start ecosystem.config.cjs                    # local (core only)
//   ENABLE_AGENTS=1 pm2 start ecosystem.config.cjs    # remote (core + agents)

const enableAgents = process.env.ENABLE_AGENTS === '1';
// Crypto Meta-Strategy paper cycles — held back until 30-day acceptance gate result.
// Enable explicitly when crypto pool reaches profitability (post pool redesign).
const enableCryptoMeta = process.env.ENABLE_CRYPTO_META === '1';

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
    // ─── SAS / SISDS autonomous pipeline DECOMMISSIONED 2026-05-11 ───
    // After 33 days of operation: W18 winner KPI 0.0331%/mo (vs 12% gate),
    // paper sessions PnL ≈ 0%, judge ignored sandbox best_config (obv_trend_follow
    // 18.29% candidate eliminated), .py files vanished mid-pipeline. 9 agent
    // entries removed: at-weekly-cycle, sas-daily-generator, sas-sandbox-processor,
    // sas-paper-scheduler, sas-live-monitor, sas-meta-observer, sas-weekly-judge,
    // sas-monthly-resurrect, sas-watchdog. account-keepalive kept (different track).
    {
        // Account keepalive — daily 18:00 UTC (= 03:00 KST).
        // Pings real Kiwoom/Binance accounts via balance-query so Kiwoom OAuth
        // tokens don't expire from inactivity. Worker writes account_keepalive_logs
        // and sends Telegram alert on hard failure; agent layers anomaly detection.
        name: "account-keepalive",
        script: SAS_WRAPPER,
        args: `'0 18 * * *' ${SAS_SCRIPTS}/run_account_keepalive.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Daily safety restart of at-backend + at-frontend at 03:30 KST (18:30 UTC).
        // Defends against SQLAlchemy connection pool drift over multi-day uptime
        // (incident 2026-05-08: pool exhaustion → /system/version /auth/token timeouts).
        // Live sessions (paper) auto-resume on backend startup.
        name: "daily-backend-restart",
        script: SAS_WRAPPER,
        args: `'30 18 * * *' ./scripts/maintenance/daily_backend_restart.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // KR — daily dynamic strategy selector (Mon-Fri 18:00 KST = 09:00 UTC).
        // Evaluates 7-strategy pool over last 30 days, applies hard filters (maxDD<-25%
        // reject, min_trades=5), persists selection JSON for downstream paper/live use.
        name: "kr-selector",
        script: SAS_WRAPPER,
        args: `'0 9 * * 1-5' ./scripts/kr/run_kr_selector.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    // ─── per-symbol dedicated strategies (v1.1 철학: 종목별 1:1) ───
    // S60 (005930): daily 외인+기관 consensus (ka10059 → investor_flow_daily).
    // Walk-forward IS sharpe 4.32 / OOS 4.10 / win 78%.
    // 1m candles 위에서 09:00 entry / 15:20 exit 운용. Requires investor_flow_daily.
    {
        name: "kr-paper-cycle-s60-005930",
        script: SAS_WRAPPER,
        args: `'35 8 * * 1-5' ./scripts/kr/run_kr_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_PAPER_SESSION: "005930_s60_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    // S61 (122630, 레버리지 ETF): daily 외국인 5일 누적 trend.
    // Walk-forward IS sharpe 10.36 / OOS 7.83 / win 80%.
    {
        name: "kr-paper-cycle-s61-122630",
        script: SAS_WRAPPER,
        args: `'40 8 * * 1-5' ./scripts/kr/run_kr_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_PAPER_SESSION: "122630_s61_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    // ─── Composer framework (Phase 6, 2026-05-02) ───
    // Pattern + KR investor flow + LightGBM combination, validated OOS:
    //   122630 sharpe 2.20 PF 2.21 +30pts vs BH
    //   007210 sign 62.9% p=0.005 +23pts (downside protection)
    //   055550 sign 65.0% p=0.001
    // Sessions live under runs/paper_sessions/{session_id}/.
    // Add new sessions via `paper_session_cli create --spec <json>` — this entry
    // automatically picks them up via `run --all`.
    {
        // Daily KR 1m OHLCV backfill (ka10080). 16:00 KST (07:00 UTC) Mon-Fri.
        // Runs 30 min after market close, BEFORE composer-flow-backfill and
        // the KR paper cycles so candle data is fresh. Idempotent: only
        // inserts rows newer than the table's current max per symbol.
        // Without this, ohlcv stalls and S60/S61/meta sessions fail with
        // "No data for X from <start_date>".
        name: "kr-ohlcv-backfill",
        script: SAS_WRAPPER,
        args: `'0 7 * * 1-5' ./scripts/kr/run_kr_ohlcv_backfill.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_OHLCV_SYMBOLS: "005930,061090,122630,000660,007210,055550,196170" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Daily KR investor flow backfill (ka10059). 16:30 KST (07:30 UTC) Mon-Fri.
        // Runs ~1 hour after market close, before composer-paper-cycle and the
        // KR per-symbol paper cycles read the data. Symbols cover BOTH the
        // composer pool (122630/007210/055550) AND the dedicated KR sessions
        // (005930/061090/122630) — S60 needs 005930 flow, S61 needs 122630 flow,
        // and meta sessions ingest flow as a feature for 061090/122630.
        name: "composer-flow-backfill",
        script: SAS_WRAPPER,
        args: `'30 7 * * 1-5' ./scripts/kr/run_composer_flow_backfill.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { COMPOSER_FLOW_SYMBOLS: "005930,061090,122630,000660,007210,055550,196170" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Composer paper cycle — runs paper_session_cli run --all.
        // 16:50 KST (07:50 UTC) Mon-Fri, 20 minutes after flow-backfill.
        name: "composer-paper-cycle",
        script: SAS_WRAPPER,
        args: `'50 7 * * 1-5' ./scripts/kr/run_composer_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Binance 1m OHLCV daily incremental backfill — 02:00 UTC (11:00 KST).
        // Pulls last 3 days from data.binance.vision archive (idempotent ON
        // CONFLICT). Without this, ohlcv stalls at initial-backfill cutoff and
        // paper paradigm sessions iterate the same bar forever (incident
        // 2026-05-13: 14 paradigm sessions cycles=18 vs uniq_ts=1). Runs 30
        // minutes before binance-paper-cycle so the cycle sees fresh candles.
        name: "binance-ohlcv-backfill",
        script: SAS_WRAPPER,
        args: `'0 2 * * *' ./scripts/binance/run_binance_ohlcv_backfill.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Binance paradigm-source joblib refresh — 02:15 UTC (11:15 KST).
        // Incremental refresh of premium_index/*.joblib (premium_index_zscore,
        // premium_velocity_zscore) and microstructure/*_full_metrics.joblib
        // (oi_price_decoupling). Sources read these joblibs at session
        // evaluation; without daily refresh, z-scores are computed from stale
        // history → pred=0 indefinitely even with fresh ohlcv (incident
        // 2026-05-13: 6 paradigm sessions stuck at pred=0 because joblibs
        // were last updated 2026-05-03/04).
        name: "binance-joblib-refresh",
        script: SAS_WRAPPER,
        args: `'15 2 * * *' ./scripts/binance/run_binance_joblib_refresh.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Binance Phase 1 paper cycle — daily 02:30 UTC (11:30 KST).
        // Moved from 00:30 UTC on 2026-05-13 so binance-ohlcv-backfill (02:00
        // UTC) and binance-joblib-refresh (02:15 UTC) can land fresh data
        // first. 24/7 perpetual futures, UTC-day boundary. Runs all active
        // paper sessions; KR sessions skip if data not fresh, Binance sessions
        // advance.
        // Initial seeds: SOL S+T+B, HBAR S+P, AXS V (all 5/5 PERFECT robustness).
        name: "binance-paper-cycle",
        script: SAS_WRAPPER,
        args: `'30 2 * * *' ./scripts/binance/run_binance_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Lifecycle paper session auto-spawner — daily 03:00 UTC (12:00 KST).
        // Detects new Binance Futures USDT perpetual listings (age 1-14d, not
        // tokenized stocks/commodities) and auto-creates per-listing PaperSession
        // for the lifecycle_pump_decay paradigm (paradigm-architect R-4 PASS:
        // median +21.6%/trade, σ=6.8). Runs AFTER binance-paper-cycle so newly
        // spawned sessions appear on next day's cycle. Idempotent — re-runs same
        // day produce 0 spawns when sessions already exist.
        // Backfills 35d of 1m ohlcv per new symbol via backfill_ohlcv_archive,
        // writes spec JSON to backend/configs/paper_sessions/lifecycle/, then
        // creates session via paper_session_cli.
        name: "lifecycle-spawner-daily",
        script: SAS_WRAPPER,
        args: `'0 3 * * *' ./scripts/research/run_lifecycle_spawner.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    // ─── Sena Technology (061090) daily Telegram brief ───
    // Aggregates Naver quote/news/discussion + OpenDART disclosures into a
    // single Markdown message. Mode (pre|post) passed via env (sas_loop_wrapper
    // parses cron + script only — see wrapper note).
    {
        // Sole daily brief — KST 08:30 (= UTC 23:30 Sun-Thu = KST Mon-Fri).
        // Consolidated to a single pre-market run (post-market brief removed 2026-06-14).
        name: "sena-brief-premarket",
        script: SAS_WRAPPER,
        args: `'30 23 * * 0-4' ./.claude/skills/at-orchestrator/scripts/sena_brief/run_sena_brief.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { SENA_BRIEF_MODE: "pre" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Monthly REAL trading report → Telegram — 1st 22:00 UTC (= 2nd 07:00 KST).
        // Deterministic worker: last complete calendar month's realized-PnL stats
        // for acct8 (Binance Futures REAL) from live_trade_executions, vs prior
        // month, + live total equity, telegrammed to the REAL alert chats.
        // Read-only. No trading. 07:00 KST delivery (07:00 KST on the 1st = 22:00
        // UTC on the last day of prev month, not cron-expressible → lands 2nd 07:00).
        name: "monthly-real-report",
        script: SAS_WRAPPER,
        args: `'0 22 1 * *' ./scripts/binance/run_monthly_real_trading_report.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Weekly REAL trading report → Telegram — Sun 22:00 UTC (= Mon 07:00 KST).
        // Same worker as monthly (scripts.real_trading_report --period week): last
        // 7 days' realized-PnL stats for acct8 vs the prior 7 days, + live equity.
        // Read-only. No trading. Established 2026-07-04.
        name: "weekly-real-report",
        script: SAS_WRAPPER,
        args: `'0 22 * * 0' ./scripts/binance/run_weekly_real_trading_report.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Weekly competition-pool ranking snapshot — Mon 07:10 KST (22:10 UTC Sun).
        // Phase 1 of the strategy tournament: ranks Category B (non-lifecycle)
        // paper strategies by per-trade Sharpe (min-5-trade gate) and writes a
        // dated snapshot to record the accumulation trajectory. Read-only, no
        // elimination (Phase 2's tournament_controller will act on these).
        name: "competition-snapshot",
        script: SAS_WRAPPER,
        args: `'10 22 * * 0' ./scripts/binance/run_competition_snapshot.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Weekly paper-mode report (Category A lifecycle / B competition split)
        // → Telegram — Mon 07:20 KST (22:20 UTC Sun). Read-only. No trading.
        name: "paper-weekly-report",
        script: SAS_WRAPPER,
        args: `'20 22 * * 0' ./scripts/binance/run_paper_weekly_report.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Monthly paper-mode report (Category A/B split) → Telegram —
        // 1st 22:20 UTC (= 2nd 07:20 KST). Read-only. No trading.
        name: "paper-monthly-report",
        script: SAS_WRAPPER,
        args: `'20 22 1 * *' ./scripts/binance/run_paper_monthly_report.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
];

// Crypto Meta-Strategy MoE (held back: enable via ENABLE_CRYPTO_META=1).
// Walk-forward eval (post leak fix 2026-05-01) shows BTC -5.3%/mo, ETH -6.3%/mo,
// SOL -9.3%/mo. Pool not yet profitable for these symbols — held until pool
// redesign or per-symbol strategy discovery completes.
const cryptoApps = [
    {
        // Crypto Meta paper cycle for BTCUSDT — daily 00:30 UTC (post UTC-day boundary).
        name: "crypto-paper-cycle-meta-btcusdt",
        script: SAS_WRAPPER,
        args: `'30 0 * * *' ./scripts/crypto/run_crypto_meta_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { CRYPTO_META_SESSION: "BTCUSDT_meta_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Crypto Meta paper cycle for ETHUSDT — 00:35 UTC (5min after BTC).
        name: "crypto-paper-cycle-meta-ethusdt",
        script: SAS_WRAPPER,
        args: `'35 0 * * *' ./scripts/crypto/run_crypto_meta_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { CRYPTO_META_SESSION: "ETHUSDT_meta_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Crypto Meta paper cycle for SOLUSDT — 00:40 UTC.
        name: "crypto-paper-cycle-meta-solusdt",
        script: SAS_WRAPPER,
        args: `'40 0 * * *' ./scripts/crypto/run_crypto_meta_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { CRYPTO_META_SESSION: "SOLUSDT_meta_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Weekly retrain — BTCUSDT (Sundays 02:00 UTC).
        name: "crypto-meta-retrain-btcusdt",
        script: SAS_WRAPPER,
        args: `'0 2 * * 0' ./scripts/crypto/run_crypto_meta_retrain.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { CRYPTO_META_RETRAIN_SYMBOL: "BTCUSDT" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Weekly retrain — ETHUSDT (Sundays 02:30 UTC).
        name: "crypto-meta-retrain-ethusdt",
        script: SAS_WRAPPER,
        args: `'30 2 * * 0' ./scripts/crypto/run_crypto_meta_retrain.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { CRYPTO_META_RETRAIN_SYMBOL: "ETHUSDT" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Weekly retrain — SOLUSDT (Sundays 03:00 UTC).
        name: "crypto-meta-retrain-solusdt",
        script: SAS_WRAPPER,
        args: `'0 3 * * 0' ./scripts/crypto/run_crypto_meta_retrain.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { CRYPTO_META_RETRAIN_SYMBOL: "SOLUSDT" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    }
];

let allApps = enableAgents ? [...coreApps, ...agentApps] : coreApps;
if (enableCryptoMeta) allApps = [...allApps, ...cryptoApps];
module.exports = { apps: allApps };
