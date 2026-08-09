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
        // Account keepalive — daily 01:00 UTC (= 10:00 KST, 장중).
        // 03:00 KST였으나 키움 계좌조회 API가 장외 시간대에 HTTP 200 + 빈 페이로드를
        // 반환해 잔고 검증이 무의미했음(2026-07-31 규명: 스케줄 실행분 전량 cash={}).
        // 장중으로 옮겨 토큰 보온 + 실제 잔고 검증을 동시에 달성.
        // Pings real Kiwoom/Binance accounts via balance-query so Kiwoom OAuth
        // tokens don't expire from inactivity. Worker writes account_keepalive_logs
        // and sends Telegram alert on hard failure; agent layers anomaly detection.
        name: "account-keepalive",
        script: SAS_WRAPPER,
        args: `'0 1 * * *' ${SAS_SCRIPTS}/run_account_keepalive.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Local DB backup to the USB-attached external disk, 18:00 UTC (= 03:00 KST).
        // Replaces the ubuntu-side pull backup (sync_from_mint.sh); same time slot.
        // Script aborts + alerts if /mnt/backup is not mounted, so a detached USB
        // disk can never silently dump 1.2GB into the root filesystem.
        name: "db-backup-usb",
        script: SAS_WRAPPER,
        args: `'0 18 * * *' ./scripts/maintenance/backup_to_usb.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // Off-site core-tables backup to Cloudflare R2, 18:20 UTC (= 03:20 KST).
        // Runs 20 min after db-backup-usb so the two never contend for pg_dump CPU.
        // Excludes the 4 market-data tables (14.94 GB, refetchable from exchange
        // APIs); the resulting core dump is ~2.1 MB, permanently inside R2's 10 GB
        // free tier. This is the only copy that survives loss of the mint machine.
        name: "db-backup-r2",
        script: SAS_WRAPPER,
        args: `'20 18 * * *' ./scripts/maintenance/backup_core_to_r2.sh`,
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
        // Runs 30 min after market close, BEFORE kr-flow-backfill and
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
        // Runs ~1 hour after market close, before the KR per-symbol paper cycles
        // read the data — S60 needs 005930 flow, S61 needs 122630 flow.
        // Renamed from composer-flow-backfill 2026-07-31: the composer/pattern KR
        // track was retired 2026-07-11 and this job was repurposed for S60/S61,
        // but the stale name made it read as dead-track leftovers.
        name: "kr-flow-backfill",
        script: SAS_WRAPPER,
        args: `'30 7 * * 1-5' ./scripts/kr/run_kr_flow_backfill.sh`,
        interpreter: "bash",
        cwd: ".",
        env: { KR_FLOW_SYMBOLS: "005930,122630" },
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
    {
        // 텔레그램 Q&A 봇 — 리포트 그룹에서 @coinAtsProject_bot 멘션/답장 질문에
        // 즉답 (참가자 전원, 조회 전용, 도구 전면 차단 + 사전수집 컨텍스트).
        // 상주 long-polling 데몬 (cron 아님). 2026-07-11 구축.
        name: "telegram-qa-bot",
        script: "./venv/bin/python3",
        args: "scripts/telegram/qa_bot.py",
        cwd: "./backend",
        env: { PYTHONPATH: ".", PYTHONUNBUFFERED: "1" },
        autorestart: true,
        max_restarts: 20,
        restart_delay: 10000
    },
    {
        // 3군 paradigm dispatch — 매일 03:45 KST 가설 1건 자율 발굴 (Phase B).
        // queue.json pending 소비, 비면 SELF-RECOMMEND. headless claude로
        // paradigm-architect 투입 (R-0→R-4), R-4 PASS는 승격 큐 등록. 2026-07-11 배선.
        name: "paradigm-dispatch-daily",
        script: SAS_WRAPPER,
        args: `'45 18 * * *' ./scripts/research/run_paradigm_dispatch.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // ── 초단기 트랙 (2026-08-09 신설) ────────────────────────────────
        // WS 실시간 수집기 — 상주 프로세스(크론 아님).
        //   bookTicker 후보 24종목 → runs/ws_quotes/*.jsonl (분 스프레드·큐잔량)
        // kline_1m 은 뺐다 — 2026-08-09 실측으로 **데이터가 오지 않는다**(구독은
        // 수락되므로 조용히 아무것도 안 하는 상태가 된다). 상세는 스크립트 docstring.
        // 호가 아카이브가 2026-03-30 에 중단돼 최근 스프레드는 과거로 소급할 방법이
        // 없다. 오늘부터 쌓지 않으면 그 하루치는 영영 못 얻는다.
        // 연결은 24시간마다 강제 종료되므로 재연결이 정상 경로다(자체 처리).
        name: "ultra-ws-collector",
        script: "./venv/bin/python3",
        args: "-u scripts/binance/ultra_ws_collector.py",
        cwd: "./backend",
        interpreter: "none",
        env: { PYTHONPATH: ".", PYTHONDONTWRITEBYTECODE: "1" },
        autorestart: true,
        max_restarts: 50,
        restart_delay: 15000
    },
    {
        // 2군 페이퍼 마켓메이킹 — 상주 프로세스. 주문은 거래소로 나가지 않는다.
        // bookTicker(큐 앞 물량) + trade(소진량)로 가격-시간 우선을 모사해
        // "내 앞 물량이 실제로 빠지는가"를 잰다. 백테스트로 답이 안 나오는 질문이다.
        // 대상 10종목은 대조군 포함 설계 (configs/ultra_mm_paper_symbols.txt).
        name: "ultra-mm-paper",
        script: "./venv/bin/python3",
        args: "-u scripts/binance/ultra_mm_paper.py --quote-usd 200 --inv-cap-usd 1000",
        cwd: "./backend",
        interpreter: "none",
        env: { PYTHONPATH: ".", PYTHONDONTWRITEBYTECODE: "1" },
        autorestart: true,
        max_restarts: 50,
        restart_delay: 15000
    },
    {
        // 2군 페이퍼 MM **가설 2** — 흐름 회피형 편향 호가.
        // 가설 1(양방향 최우선 고정)의 실패 지점이 "스프레드 획득이 음수"였다.
        // 최우선에 대고도 체결 순간엔 중간가가 이미 내 가격을 지나쳐 있다 =
        // 매번 당하는 쪽에 서 있다. 최근 60초 주문흐름이 한쪽으로 쏠리면 그 쪽
        // 호가를 걷어 노출을 피한다. 방향 예측이 아니라 노출 회피다.
        // **가설 1 과 같은 10종목**을 쓴다 — 규칙만 바꿔야 A/B 대조가 성립한다.
        name: "ultra-mm-paper-flowskew",
        script: "./venv/bin/python3",
        args: "-u scripts/binance/ultra_mm_paper.py --strategy flow_skew " +
              "--quote-usd 200 --inv-cap-usd 1000 --out-dir runs/ultra_mm_paper_flowskew",
        cwd: "./backend",
        interpreter: "none",
        env: { PYTHONPATH: ".", PYTHONDONTWRITEBYTECODE: "1" },
        autorestart: true,
        max_restarts: 50,
        restart_delay: 15000
    },
    {
        // 2군 페이퍼 MM **가설 3** — 큐 급소진 회피.
        // 역선택의 실체는 큐다. 내 앞 물량이 다 소진돼야 차례가 오는데, 그건 한
        // 방향으로 체결이 몰렸다는 뜻이고 곧 가격이 그 방향으로 가는 중이라는 뜻이다.
        // **나를 체결시켜 주는 조건이 곧 나를 당하게 하는 조건이다.**
        // 가설 2 는 60초 평균 흐름(느린 신호)이라 개선이 0.6~2.6bp 였다. 가설 3 은
        // 그 순간의 소진 **속도**로 도달시각을 추정해 임박하면 뺀다. 절대 잔량이
        // 아니라 속도로 판단해야 "늘 도망가서 체결 0" 이 되지 않는다.
        // 로컬 시험: 스프레드 획득 적자가 약 60% 감소, 체결은 약 90% 감소.
        name: "ultra-mm-paper-queueflee",
        script: "./venv/bin/python3",
        args: "-u scripts/binance/ultra_mm_paper.py --strategy queue_flee " +
              "--quote-usd 200 --inv-cap-usd 1000 --out-dir runs/ultra_mm_paper_queueflee",
        cwd: "./backend",
        interpreter: "none",
        env: { PYTHONPATH: ".", PYTHONDONTWRITEBYTECODE: "1" },
        autorestart: true,
        max_restarts: 50,
        restart_delay: 15000
    },
    {
        // 2군 페이퍼 MM **가설 4** — 가설 2 + 가설 3 결합.
        // 둘은 직교한다. 2는 **어느 쪽**에 설지(방향, 60초 흐름), 3은 **언제 뺄지**
        // (타이밍, 그 순간 큐 소진 속도). 실측에서도 효과 종목이 갈렸다 —
        // 가설2 는 SOL(좁은 스프레드 대형), 가설3 은 BANK/TST.
        // 로컬 시험: 스프레드 획득이 AKE +0.05 / SOL +0.39 / MELANIA +1.96 로
        // **양수 전환**. 오늘 내내 음수였던 지표다.
        // 위험은 체결 소멸 — 가설3 단독으로도 90~95% 줄었고 결합은 더 줄인다.
        // "남은 체결로 사업이 되는가" 가 주 검증 지점이다.
        name: "ultra-mm-paper-combo",
        script: "./venv/bin/python3",
        args: "-u scripts/binance/ultra_mm_paper.py --strategy combo " +
              "--quote-usd 200 --inv-cap-usd 1000 --out-dir runs/ultra_mm_paper_combo",
        cwd: "./backend",
        interpreter: "none",
        env: { PYTHONPATH: ".", PYTHONDONTWRITEBYTECODE: "1" },
        autorestart: true,
        max_restarts: 50,
        restart_delay: 15000
    },
    {
        // 2군 tier governor — day30_decision_protocol 결정 트리 매일 자동 집행.
        // TERMINATE 자동 / PROMOTE·RESEED는 Telegram 통보 (1군 진입은 수동 승인).
        // Daily 03:40 UTC (12:40 KST) — paper-cycle(02:30) + spawner(03:00) 이후
        // 당일 최신 equity/trades 반영 상태에서 판정. 2026-07-11 신설.
        name: "tier-governor",
        script: SAS_WRAPPER,
        args: `'40 3 * * *' ./scripts/binance/run_tier_governor.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // 미국 ETF 순위 스냅샷(마감 후) — 매일 21:10 UTC (서머타임 06:10 KST).
        // 키움 순위 API 는 과거 시계열이 없어 오늘 안 받으면 영영 못 쓴다.
        // 마감 후에 유효한 지표(키움 거래상위 / 연속 상승하락 / 거래대금 / 시총 /
        // 회전율)를 적재하고 이어서 코어 60종 일봉을 갱신한다. 2026-07-31 신설.
        // 평일(UTC 1-5)만 실행 — 미국장이 열린 날에만 새 순위·일봉이 생기므로
        // 주말 실행은 전날과 동일한 값의 재수집이다.
        //
        // 참고: 키움은 정기 시스템 점검 중 API 도 함께 중단된다(예: 2026-08-01(토)
        // 13:00 ~ 08-02(일) 01:00, /oauth2/token 이 302 → start.html 안내페이지).
        // 점검은 부정기 일회성이며 "주말 상시 중단"이 아니다 — 장 마감과도 무관하다.
        //
        // 주의: 주간거래 괴리율(usa24291)은 이 시각에 항상 0건이다 —
        // us-daytime-snapshot 으로 분리했다 (2026-08-01 실측).
        name: "us-rank-snapshot",
        script: SAS_WRAPPER,
        args: `'10 21 * * 1-5' ./scripts/us/run_us_rank_snapshot.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // 한국 주간거래(Blue Ocean) 세션 중에만 얻는 순위 지표 — 평일 07:30 UTC
        // (16:30 KST), 주간거래 종료(16:45 KST) 직전.
        // 실측 2026-08-01: usa24291(주간거래 괴리율)을 16:07 KST 수집 시 100건,
        // 06:10 KST 수집 시 0건. 오버나이트 세션의 실시간 괴리라 세션이 닫히면
        // 값이 없다. 미국 현지 데이터로 복제 불가능한 고유 substrate 라 창을 분리.
        name: "us-daytime-snapshot",
        script: SAS_WRAPPER,
        args: `'30 7 * * 1-5' ./scripts/us/run_us_daytime_snapshot.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // [임시] 미국 가설 큐 시더 — 매시 17분. 2026-08-01 대표님 지시로 신설.
        // 초기 큐를 빠르게 채우기 위한 일회성 조치이며 상시 운영용이 아니다.
        // 스크립트 안에 자동 만료(2026-08-02 23:59 KST)가 들어 있어 그 뒤로는
        // 호출돼도 no-op 이다. 만료 후 정리:
        //   pm2 delete us-hypothesis-seeder && pm2 save
        name: "us-hypothesis-seeder",
        script: SAS_WRAPPER,
        args: `'17 * * * *' ./scripts/us/run_us_hypothesis_seeder.sh`,
        interpreter: "bash",
        cwd: ".",
        autorestart: true,
        max_restarts: 10,
        restart_delay: 5000
    },
    {
        // 미국 ETF 페이퍼 사이클 + US 리그 거버너 — 매일 21:40 UTC.
        // us-rank-snapshot(21:10)이 일봉·순위를 갱신한 뒤 실행. 미국은 일봉
        // 기준이라 하루 1사이클이면 충분하다. 리그는 바이낸스와 분리(12석,
        // --market us) — 일봉 스윙과 분봉 intraday 를 같은 순위표에 둘 수 없다.
        name: "us-paper-cycle",
        script: SAS_WRAPPER,
        args: `'40 21 * * 1-5' ./scripts/us/run_us_paper_cycle.sh`,
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
