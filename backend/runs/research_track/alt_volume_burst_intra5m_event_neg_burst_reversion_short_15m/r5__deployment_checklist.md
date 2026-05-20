# paradigm 128 — R-5 Deployment Checklist (Mint deploy)

**Paradigm**: `alt_volume_burst_intra5m_event_neg_burst_reversion_short_15m`
**Effective hold post-R-3 caveat 1**: 10min (NOT 15min as in directory name; name retained for historical traceability)
**Number**: 128 (paradigm 126 B-arm split — FIRST SHORT-only seed in campaign)
**Direction**: SHORT, hold 10min, **SL=0.5% MANDATORY**
**Capacity Class**: B (medium-capital; $100k feasible, $1M plausible)
**R-4 verdict**: PASS_R4_DUAL_MODE_HIGH_FREQ_DIFFUSE_SHORT_WITH_MANDATORY_SL (8/8 gates)
**Artifact preparation completed**: 2026-05-21 KST (paradigm-architect dispatch)
**HALT status**: Mint deploy is **USER-DRIVEN**.

---

## Artifacts already generated

| Artifact | Path | Status |
|---|---|---|
| Source class | `backend/app/composer_framework/sources/binance_alt_volume_burst_neg_reversion_short_source.py` | created + py_compile PASS |
| Sources package init | `backend/app/composer_framework/sources/__init__.py` | updated (import + __all__) |
| Pipeline factory registration | `backend/app/composer_framework/pipeline_spec.py` | `@register_source("bn_alt_volume_burst_neg_reversion_short")` added |
| Paper session configs (13) | `backend/configs/paper_sessions/<SYM>_alt_volume_burst_neg_reversion_short.json` | 13 files (one per ALT) |
| R-5 seed spec | `backend/runs/research_track/alt_volume_burst_intra5m_event_neg_burst_reversion_short_15m/r5__seed_spec.json` | FINALIZED |
| INDEX.json paradigm 128 phase | `backend/runs/research_track/INDEX.json` | updated R-4 -> R-5 in this dispatch |

ecosystem.config.cjs: **NO modification required** (binance-paper-cycle picks up sessions automatically).

---

## CRITICAL SHORT-specific deploy notes

1. **SL=0.5% MANDATORY** is enforced in `pipeline_spec.policy.kwargs.sl_pct = 0.005`. LongShortThresholdPolicy emits `sl_price = open_price * (1 + 0.005)` on enter_short, and the backtester evaluates the SL on each subsequent bar. Verify the SL is firing in Day 7 logs.

2. **Funding-rate skip (>+3bp/8h) is NOT enforced in code**. The current LongShortThresholdPolicy has no funding-aware hook. This must be enforced via OPERATIONAL MONITOR at deploy time:
   - Log per-symbol 8h funding rate at every trigger time.
   - If funding > +3bp at trigger, the entry should be skipped/cancelled BEFORE order submission.
   - Concrete implementation options (defer to operator):
     - Add a pre-entry guard in `paper_session_cli` runner for this paradigm
     - Build a separate `FundingAwareLongShortPolicy` subclass and re-deploy
     - Manual review of trade log + post-hoc filtering on Day 7 baseline
   - Day 7 monitoring requirement: count of trades where funding >+3bp must be tracked, and edge net of those trades computed.

3. **First SHORT-only seed in campaign** — operational telemetry for SHORT-side slippage and stop-rate has no precedent in the 8 existing R-5 seeds (all LONG or hybrid). Day 7 baseline must include:
   - `stop_rate_empirical_pct` (target 25.7%, alarm if >50%)
   - per-trade slippage measurement at entry (alarm if >5bp/side)
   - per-symbol funding-skip count

---

## Mint deploy steps (USER EXECUTES)

### Step 1 — Pull repo on Mint
```bash
ssh mint
cd /home/mint/auto_trading
git pull origin master
```

### Step 2 — py_compile sanity check
```bash
cd /home/mint/auto_trading/backend
source venv/bin/activate
python3 -m py_compile app/composer_framework/sources/binance_alt_volume_burst_neg_reversion_short_source.py
python3 -m py_compile app/composer_framework/sources/__init__.py
python3 -m py_compile app/composer_framework/pipeline_spec.py
python3 -c "from app.composer_framework.pipeline_spec import SOURCE_FACTORIES; assert 'bn_alt_volume_burst_neg_reversion_short' in SOURCE_FACTORIES; print('REGISTERED OK')"
```

### Step 3 — Seed 13 paper sessions
```bash
cd /home/mint/auto_trading/backend
source venv/bin/activate

for SYM in ADAUSDT AVAXUSDT BCHUSDT BNBUSDT DOGEUSDT ETHUSDT FILUSDT LINKUSDT LTCUSDT NEARUSDT SOLUSDT WIFUSDT XRPUSDT; do
  python3 -m scripts.paper_session_cli create \
    --spec configs/paper_sessions/${SYM}_alt_volume_burst_neg_reversion_short.json
done

python3 -m scripts.paper_session_cli list | grep alt_volume_burst_neg_reversion_short
```

### Step 4 — Backend restart
```bash
pm2 restart at-backend
pm2 logs at-backend --lines 30 --nostream
```

### Step 5 — Wait for binance-paper-cycle (or manual fire)
```bash
cd /home/mint/auto_trading
bash scripts/binance/run_binance_paper_cycle.sh
tail -100 backend/runs/binance_paper/logs/$(ls -t backend/runs/binance_paper/logs/ | head -1)
```

Look for `bn_alt_volume_burst_neg_reversion_short` and SHORT enter_short events with sl_price set.

### Step 6 — SHORT-specific verification (CRITICAL FIRST CYCLE)

After first cycle, inspect a sample trade log to verify SL is active:

```bash
python3 -m scripts.paper_session_cli logs --session ETHUSDT_alt_volume_burst_neg_reversion_short_paper_seed --tail 50
```

Confirm at least one trade shows `enter_short` with `sl_price` ≈ entry × 1.005 (0.5% above entry).

If no trades fired in first cycle: likely waiting for first 1m burst event meeting criteria. Re-check after 24h.

---

## Day 7 baseline (2026-05-28) — SHORT-specific

```bash
python3 scripts/backtest_paper_specs.py \
  --paradigm-prefix alt_volume_burst_neg_reversion_short \
  --window-days 7 \
  --output backend/runs/research_track/alt_volume_burst_intra5m_event_neg_burst_reversion_short_15m/day7_baseline.json
```

Day 7 SHORT-specific PASS criteria:
- empirical stop_rate ≤ 35% (target 25.7%; alarm >50%)
- per-trade slippage measured ≤ 5bp/side
- funding-skip count tracked (manual analysis)
- per-sym ci_neg ratio ≤ 5/13

---

## Day 30 baseline (2026-06-20)

```bash
python3 scripts/backtest_paper_specs.py \
  --paradigm-prefix alt_volume_burst_neg_reversion_short \
  --window-days 30 \
  --output backend/runs/research_track/alt_volume_burst_intra5m_event_neg_burst_reversion_short_15m/day30_baseline.json
```

Day 30 demote criterion: measured ann_gross < 995% (50% of R-3 expected 1,990% post-SL).
Day 30 terminate criteria (ANY of):
- measured ann_gross < 597% (30% of expected)
- any 3 of 5 OOS folds ci_lower negative
- empirical stop_rate > 70% sustained 7 days

---

## Rollback

```bash
cd /home/mint/auto_trading/backend
for SYM in ADAUSDT AVAXUSDT BCHUSDT BNBUSDT DOGEUSDT ETHUSDT FILUSDT LINKUSDT LTCUSDT NEARUSDT SOLUSDT WIFUSDT XRPUSDT; do
  python3 -m scripts.paper_session_cli pause \
    --session ${SYM}_alt_volume_burst_neg_reversion_short_paper_seed
done
```

If catastrophic SL trigger storm: pause all 13 sessions, investigate per-symbol funding/squeeze regime, optionally widen SL to 0.7% or 1.0% via config update + redeploy.

---

## Lessons applied (Lesson Q3 §6.24 update required)

- Lesson #41 amendment dual-mode high-freq diffuse SHORT — **4th dogfood (CONFIRMED-formal)**
- Lesson #49 unconditional fwd_ret pool — **5th dogfood**
- Lesson #50 first-burst-sign 5m bin aggregation MANDATORY — **CONFIRMED (2 dogfoods, paradigm 128 INVERSION evidence is the 2nd)**
- First SHORT-only seed operational telemetry (stop_rate / funding skip / SHORT slip) — NEW operational dimensions catalogued

---

**End of deployment checklist.** User runs steps 1–6, then validates Day 7 baseline 2026-05-28 with SHORT-specific metrics.
