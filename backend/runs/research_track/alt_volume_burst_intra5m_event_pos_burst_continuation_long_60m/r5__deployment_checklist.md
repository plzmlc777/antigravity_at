# paradigm 127 — R-5 Deployment Checklist (Mint deploy)

**Paradigm**: `alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m`
**Number**: 127 (paradigm 126 A-arm split)
**Direction**: LONG, hold 75min (R-3 caveat 1 sweet-spot)
**Capacity Class**: C (small-capital optimal, $10k per session)
**R-4 verdict**: PASS_R4_HIGH_FREQ_DIFFUSE_SMALL_CAPITAL (7/7 gates)
**Artifact preparation completed**: 2026-05-21 KST (paradigm-architect dispatch)
**HALT status**: Mint deploy is **USER-DRIVEN** — agent does NOT execute deploy commands.

---

## Artifacts already generated (verify before deploy)

| Artifact | Path | Status |
|---|---|---|
| Source class | `backend/app/composer_framework/sources/binance_alt_volume_burst_pos_continuation_long_source.py` | created + py_compile PASS |
| Sources package init | `backend/app/composer_framework/sources/__init__.py` | updated (import + __all__) |
| Pipeline factory registration | `backend/app/composer_framework/pipeline_spec.py` | `@register_source("bn_alt_volume_burst_pos_continuation_long")` added |
| Paper session configs (13) | `backend/configs/paper_sessions/<SYM>_alt_volume_burst_pos_continuation_long.json` | 13 files (one per ALT) |
| R-5 seed spec | `backend/runs/research_track/alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m/r5__seed_spec.json` | FINALIZED |
| INDEX.json paradigm 127 phase | `backend/runs/research_track/INDEX.json` | updated R-4 -> R-5 in this dispatch |

ecosystem.config.cjs modification: **NOT REQUIRED**. The existing `binance-paper-cycle` PM2 entry (cron `'30 2 * * *'` = 02:30 UTC = 11:30 KST daily) calls `paper_session_cli run --all --exchange binance`, which auto-picks up newly-seeded sessions. This avoids the merge-conflict risk the dispatch spec was trying to dodge.

---

## Mint deploy steps (USER EXECUTES)

### Step 1 — Pull repo on Mint

```bash
ssh mint
cd /home/mint/auto_trading
git pull origin master
```

Verify the 4 new/modified source-code files are present (see "Artifacts" table above).

### Step 2 — py_compile sanity check on Mint

```bash
cd /home/mint/auto_trading/backend
source venv/bin/activate
python3 -m py_compile app/composer_framework/sources/binance_alt_volume_burst_pos_continuation_long_source.py
python3 -m py_compile app/composer_framework/sources/__init__.py
python3 -m py_compile app/composer_framework/pipeline_spec.py
python3 -c "from app.composer_framework.pipeline_spec import SOURCE_FACTORIES; assert 'bn_alt_volume_burst_pos_continuation_long' in SOURCE_FACTORIES; print('REGISTERED OK')"
```

### Step 3 — Seed 13 per-symbol paper sessions via paper_session_cli

```bash
cd /home/mint/auto_trading/backend
source venv/bin/activate

# Seed all 13 paradigm 127 sessions in one loop
for SYM in ADAUSDT AVAXUSDT BCHUSDT BNBUSDT DOGEUSDT ETHUSDT FILUSDT LINKUSDT LTCUSDT NEARUSDT SOLUSDT WIFUSDT XRPUSDT; do
  python3 -m scripts.paper_session_cli create \
    --spec configs/paper_sessions/${SYM}_alt_volume_burst_pos_continuation_long.json
done

# Verify
python3 -m scripts.paper_session_cli list | grep alt_volume_burst_pos_continuation_long
```

Expected: 13 new active sessions, one per alt.

### Step 4 — Backend restart (so source registry picks up new factories)

```bash
pm2 restart at-backend
# Wait ~5 sec for FastAPI to warm
pm2 logs at-backend --lines 30 --nostream
```

Verify no import errors in the startup logs.

### Step 5 — Wait for next binance-paper-cycle fire

The existing PM2 cron `binance-paper-cycle` runs at 02:30 UTC = 11:30 KST daily. New sessions advance automatically on the next cycle. To force-test sooner:

```bash
# Manual cycle (skip cron, run once now)
cd /home/mint/auto_trading
bash scripts/binance/run_binance_paper_cycle.sh

# Check log
tail -100 backend/runs/binance_paper/logs/$(ls -t backend/runs/binance_paper/logs/ | head -1)
```

Look for log lines containing `bn_alt_volume_burst_pos_continuation_long` and the 13 alt symbols, with non-zero `bnvbpl_signal` events on bars where 1m volume burst conditions are met.

### Step 6 — Mint ps verify (sanity)

```bash
pm2 status
# Confirm at-backend + binance-paper-cycle running, no error states
ps aux | grep paper_session | head
```

---

## Day 7 baseline (2026-05-28)

Run on Mint:

```bash
cd /home/mint/auto_trading/backend
source venv/bin/activate
python3 scripts/backtest_paper_specs.py \
  --paradigm-prefix alt_volume_burst_pos_continuation_long \
  --window-days 7 \
  --output backend/runs/research_track/alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m/day7_baseline.json
```

Day 7 PASS criteria (per r5__seed_spec.json `day_7_baseline_check_criteria`):
- ≥80 trades in 7d across 13 syms (extrapolated 16.5/day × 7 × 0.7 confidence)
- min net_bp_per_trade (16bp fee) ≥ 24
- max drawdown not below -15%
- per-sym ci_neg ratio ≤ 5/13 (drift alarm)
- burst signal count per sym ≥ 4

Day 7 FAIL triggers Day 14 investigation, not termination.

---

## Day 30 baseline (2026-06-20)

```bash
python3 scripts/backtest_paper_specs.py \
  --paradigm-prefix alt_volume_burst_pos_continuation_long \
  --window-days 30 \
  --output backend/runs/research_track/alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m/day30_baseline.json
```

Day 30 demote criterion: measured ann_gross < 1,533% (50% of R-3 expected 3,066% post-20bp slippage).
Day 30 terminate criterion: measured ann_gross < 920% OR any 3/5 OOS folds ci_lower negative.

---

## Rollback (if anything goes wrong)

Per-session graceful demote:

```bash
cd /home/mint/auto_trading/backend
for SYM in ADAUSDT AVAXUSDT BCHUSDT BNBUSDT DOGEUSDT ETHUSDT FILUSDT LINKUSDT LTCUSDT NEARUSDT SOLUSDT WIFUSDT XRPUSDT; do
  python3 -m scripts.paper_session_cli pause \
    --session ${SYM}_alt_volume_burst_pos_continuation_long_paper_seed
done
```

If source code itself is bad, `git revert <commit>` + backend restart restores prior state (sessions remain in DB but emit nothing since source registry doesn't have the type).

---

## Lessons applied at seed (Lesson Q3 §6.24 update required)

- Lesson #41 amendment dual-mode high-freq diffuse — **3rd dogfood (CONFIRMED-formal promotion)**
- Lesson #49 unconditional fwd_ret pool — **4th dogfood**
- Lesson #50 first-burst-sign 5m bin aggregation MANDATORY — **CONFIRMED (2 dogfoods)**
- NEW Capacity Class C dimension formalized — paradigm 127 is reference implementation

---

**End of deployment checklist.** User runs steps 1–6, then waits for Day 7 baseline 2026-05-28.
