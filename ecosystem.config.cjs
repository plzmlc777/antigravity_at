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
        // KR — daily EOD paper cycle for 061090 (Mon-Fri 17:00 KST = 08:00 UTC).
        // Legacy session: S2 BB Reversion baseline (kept for comparison).
        name: "kr-paper-cycle",
        script: SAS_WRAPPER,
        args: `'0 8 * * 1-5' ./scripts/kr/run_kr_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: {
            KR_PAPER_SESSION: "061090_s2_seed"
        },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // KR — paper cycle for S31 1m_period_x3 (mb=4, ms=1).
        // OOS-validated winner: +19.15% / Sharpe 5.42 / WinR 87% / maxDD -2.26%.
        // Runs 5 minutes after the legacy cycle to avoid DB contention.
        name: "kr-paper-cycle-s31",
        script: SAS_WRAPPER,
        args: `'5 8 * * 1-5' ./scripts/kr/run_kr_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: {
            KR_PAPER_SESSION: "061090_s31_1m_x3_seed"
        },
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
    {
        // KR — Meta-Strategy MoE paper cycle (Mon-Fri 17:10 KST = 08:10 UTC).
        // Phase 5 wire-in: env_encoder + meta_lgbm picks 1 of 12 strategies + safety gates.
        // Runs 10 minutes after kr-paper-cycle-s31 to avoid DB contention.
        name: "kr-paper-cycle-meta",
        script: SAS_WRAPPER,
        args: `'10 8 * * 1-5' ./scripts/kr/run_kr_meta_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: {
            KR_META_SESSION: "061090_meta_seed"
        },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // KR — Weekly meta-learner retrain for 061090 (Sundays 09:00 KST = 00:00 UTC).
        // Rebuilds perf_matrix on latest data, retrains LightGBM, atomic-swaps the
        // canonical model path consumed by kr-paper-cycle-meta.
        name: "kr-meta-retrain",
        script: SAS_WRAPPER,
        args: `'0 0 * * 0' ./scripts/kr/run_kr_meta_retrain.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    // ─── Multi-symbol expansion (2026-05-01): 005930 (Samsung) + 122630 (KODEX leverage) ───
    // Per-symbol meta_lgbm models; daily paper cycles + weekly retrain.
    {
        // 005930 baseline only — meta-strategy held back; pool/symbol mismatch
        // (top-1 acc 0% on walk-forward CV; oracle +602 shows potential but
        // current 12-strategy pool doesn't fit blue-chip Samsung).
        name: "kr-paper-cycle-s31-005930",
        script: SAS_WRAPPER,
        args: `'15 8 * * 1-5' ./scripts/kr/run_kr_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_PAPER_SESSION: "005930_s31_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        name: "kr-paper-cycle-s31-122630",
        script: SAS_WRAPPER,
        args: `'25 8 * * 1-5' ./scripts/kr/run_kr_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_PAPER_SESSION: "122630_s31_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        name: "kr-paper-cycle-meta-122630",
        script: SAS_WRAPPER,
        args: `'30 8 * * 1-5' ./scripts/kr/run_kr_meta_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_META_SESSION: "122630_meta_seed" },
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        name: "kr-meta-retrain-122630",
        script: SAS_WRAPPER,
        args: `'0 1 * * 0' ./scripts/kr/run_kr_meta_retrain.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_META_RETRAIN_SYMBOL: "122630" },
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
    // S67 (061090, S/R dual-trigger): S1 pivot bounce + PDH breakout-retest, EOD-flat, 15m.
    // Backtest (thru 2026-04): 2026 71 trades +19.35% sharpe 2.28, WF 5/6. PAPER forward
    // test — first cycle (May) -6.89% vs BH +11.78%: regime flipped up, strategy is a
    // down/choppy specialist. Kept on paper to accumulate regime-transition evidence.
    {
        name: "kr-paper-cycle-s67-061090",
        script: SAS_WRAPPER,
        args: `'45 8 * * 1-5' ./scripts/kr/run_kr_paper_cycle.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_PAPER_SESSION: "061090_s67_seed" },
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
        // Pre-market brief — KST 08:30 (= UTC 23:30 Sun-Thu = KST Mon-Fri).
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
        // Post-market brief — KST 16:30 (= UTC 07:30 Mon-Fri).
        name: "sena-brief-postmarket",
        script: SAS_WRAPPER,
        args: `'30 7 * * 1-5' ./.claude/skills/at-orchestrator/scripts/sena_brief/run_sena_brief.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { SENA_BRIEF_MODE: "post" },
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
