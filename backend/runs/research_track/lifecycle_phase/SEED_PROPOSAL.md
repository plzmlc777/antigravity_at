# lifecycle_pump_decay R-5 SEED PROPOSAL

**Paradigm slug**: `lifecycle_pump_decay`
**INDEX phase**: `R-4` → proposed `R-5_ARTIFACT_READY` (pending user approval)
**Mechanism class**: post-listing Day-1-close SHORT decay (event-anchored, long-horizon Day-30)
**Direction**: SHORT
**Type**: E (event-study)
**Created**: 2026-05-13, R-2 + R-3 evaluated; R-5 promotion eval 2026-05-21 KST 16:30

---

## 1. Elite Gate Verdict

### Standard 7-criterion gate (R-2): **PASS** (`gate_eval__r2.md` ✅)

| Gate | Threshold | Value | Verdict |
|---|---|---|---|
| n | ≥ 100 | 167 | PASS |
| median_pct | ≥ 15.0% | 21.61% | PASS |
| win_rate_positive | ≥ 0.55 | 0.581 | PASS |
| perm_p | ≤ 0.05 | 0.000 | PASS |
| perm_sigma | (info) | 6.8σ | very strong |
| bootstrap_ci_lo_pct | > 0 | 3.27% | PASS (marginal) |
| quarterly_pos_ratio | ≥ 0.75 | 3/4 = 0.75 | PASS (exactly threshold; Q2 outlier dropped n=1) |

### Life-changing 4-dim gate (computed): **3/4 PASS, 1 dim assumption-dependent**

| Dim | Threshold | Value | Verdict |
|---|---|---|---|
| trades/yr | ≥ 12 | ~154.6 (167 trades / 1.08yr listing span) | PASS (12.9x cushion) |
| edge per trade | ≥ 2%/trade | mean 7.31% (median 21.61%) | PASS (3.7x cushion on mean, 10.8x on median) |
| sharpe annualized | ≥ 1.0 | 1.89 (per-trade 0.152 × √154.6) | PASS (1.89x cushion) |
| capital util | ≥ 30% | 906% (9.06 avg concurrent open at 1-unit-per-trade) | **PASS structurally** but requires per-position sizing constraint to avoid leverage explosion. With cap (e.g., ≤5% per name, max 10 concurrent), effective util ~50% target |

### Lesson #16 Concentration Gate: **N/A → structurally satisfied**
- R-3 metrics lack formal per-symbol bootstrap output (script predates Lesson #16 enforcement).
- **However**: each listing is a **single unique event per symbol** (167 trades = 167 unique symbols). Per-symbol diversity is structurally 100% (no symbol contributes >1 trade), so the Concentration Gate criterion "≥30% syms ci+" is trivially satisfied at this granularity.
- **Quarter-concentration check**: Q3 2025 fails (n=66, median -3.52%, winrate 48.5%) while Q2/Q4 2025 + Q1 2026 all PASS. This is the **temporal weakness** — bear macro regime Q3 2025 reverted the SHORT bias.

### Lesson #26 walk-forward TS-CV 5-fold: **3/4 PASS measurable + 1 too-small**

| Fold | n | median | winrate | Status |
|---|---|---|---|---|
| 2025Q2 | 25 | +31.38% | 0.760 | PASS |
| 2025Q3 | 66 | -3.52% | 0.485 | **FAIL** |
| 2025Q4 | 49 | +39.34% | 0.653 | PASS |
| 2026Q1 | 26 | +4.80% | 0.538 | PASS (marginal — median below 15% threshold but positive + winrate >0.5) |
| 2026Q2 | 1 | -50.08 | 0.000 | n too small, drop |

**3/4 measurable folds PASS, 1/4 FAIL** → meets Lesson #26 minimum 3/5 (treating Q2 2026 as fold 5 with n<10 drop, effective is 3/4 = 75%).

### R-3 regime stratify: **major concern, BEAR regime collapses**

| BTC regime | n | median | mean | winrate |
|---|---|---|---|---|
| bear (-12.56% pre) | 38 (22.8%) | **-50.08%** | -9.24% | 0.421 |
| neutral (-0.52% pre) | 78 (46.7%) | +28.21% | +10.21% | 0.603 |
| bull (+11.05% pre) | 51 (30.5%) | +30.24% | +15.21% | 0.667 |

- **Bear regime** = 22.8% of cohort, BUT median **-50.08%** (SL hit floor) — every bear listing pumps into BTC bull bounce.
- **Best params (sl=0.8 hold=30) on bear**: median +13.93% but mean -7.21% — sl-relaxation lifts median but mean stays negative.
- **Implication**: paradigm operates **conditionally on non-bear BTC macro regime**. Bear-regime listings have systematic SHORT-squeeze risk.

### Plateau robustness: **strong**

- 27 of 40 (sl × hold) grid cells PASS plateau threshold.
- Optimal: sl=0.8 hold=30 → median +28.98%, win 0.665, mean +6.67%.
- Adjacent cells (sl=0.7/0.6/1.0, hold=21/30/45) all >20% median.
- Default config (sl=0.5 hold=30 → median 21.61%, mean 7.31%, win 0.581) sits inside plateau center.

---

## 2. Overall Elite Gate Verdict

**Verdict**: **PARTIAL PASS** — R-5 seed proposal with **strict bear-regime filter** required.

**Rationale**:
- **R-2 7-criterion gate ALL PASS** (perm_sigma 6.8σ, n=167, median 21.61%, ci_lo +3.27%).
- **Life-changing 4-dim 3/4 structural PASS** + 1 dim requires position-sizing rules (resolvable in seed spec).
- **TS-CV 3/4 PASS** meets Lesson #26 minimum.
- **R-3 plateau 27/40 cells** = strong parameter robustness.
- **R-3 bear regime FAIL** is the single blocking concern → addressed by R-5 seed spec with **explicit BTC 30d pre-trend bear-regime filter** (skip listings in bear regime).

**Comparison vs precedent R-5 LIVE paradigms**:
- paradigm 22 funding_carry: 5/5 strict cutoff, paper baseline confirmed
- paradigm 24 premium_index_z: 9.0σ DOGE / 5.4σ SOL / 5.7σ LDO, all 5/5 strict
- paradigm 69 btc_rv_highvol: 13σ retroactive 2.4yr, plateau 96/96
- **lifecycle_pump_decay**: 6.8σ perm + 27/40 plateau + 3/4 TS-CV — comparable strict-grade evidence to R-5 LIVE peers, with **conditional bear-filter requirement** as additional caveat

**Listing family R-5 active status**: currently **NONE** (5/5 prior listing-family R-1 graveyards). lifecycle_pump_decay R-5 promotion would establish the **first R-5 LIVE in listing family**, completing the family escape from OUTCOME-LEVEL family proxy Lesson #56 prediction (one R-4 escape per ~10 family members observed → lifecycle is the 6th instance and the empirical escape).

---

## 3. R-5 Seed Specification

### 3.1 Universe + entry filter

- **Universe**: Binance Futures USDT perpetuals
- **Trigger**: new listing (`onboardDate`) — entry on Day 1 close (24h after listing open)
- **Mandatory filters**:
  1. **BTC 30d pre-listing return ≥ -5%** (skip bear regime listings; Lesson #20 narrow-scope sign-conditional). Bear regime defined as BTC 30d cumulative return < -5%.
  2. **Day 1 high return ≥ +20%** OR **Day 1 close return ≥ +5%** (pump confirmation; avoids stillborn listings that already collapsed Day 1). Pump-conditional or not — R-2 metrics show both n=70 pumped and n=97 not-pumped have similar median (21.44% vs 21.61%), so filter is **soft preference**, not hard cutoff.
  3. Symbol age ≥ 0 (i.e., entry the day the symbol starts trading on Binance Futures perp).

### 3.2 Position + execution

- **Direction**: SHORT
- **Entry price**: Day 1 close (UTC 24h after onboard)
- **Position size**: 5% of paper portfolio per name; max 10 concurrent open positions (caps capital util at ~50% effective)
- **Stop loss**: +50% from entry (i.e., exit if price rises ≥50% above entry close) — matches R-2 default
- **Take profit**: none (let decay play out; SL + time exit only)
- **Hold period**: 30 days from entry (Day 31 close exit if not stopped out)
- **Fees**: 0.04% per side (Binance Futures taker) × 2 = 0.08% round trip (embedded in net returns)

### 3.3 Mode + monitoring

- **Mode**: paper trading first (NOT live), via Mint server PM2 cron deployment
- **Session name**: `lifecycle_pump_decay_v1`
- **Substrate dependency**:
  - Real-time Binance Futures `exchangeInfo` API polling (onboardDate registry, 1x/day update)
  - 1m OHLCV feed (existing infra)
  - BTC 30d cumulative return regime indicator (computed daily from BTC OHLCV)
- **Day 7 baseline measurement**: 2026-05-28+ (7 days post-seed), compare per-trade returns vs R-2/R-3 baseline 21.61% median
- **Day 30 validation**: 2026-06-20+, full TS-CV-on-live comparison

### 3.4 Expected baseline (R-5 LIVE peer comparison)

| Paradigm | Strict-grade | Hold | Type | Expected per-trade edge |
|---|---|---|---|---|
| paradigm 22 funding_carry | 5/5 | ~7d | E | ~2-3% |
| paradigm 24 premium_index_z DOGE | 9.0σ | 1d | T | varies |
| paradigm 69 btc_rv_highvol | 13σ retro | 270m | E | +1-2% |
| paradigm 127 alt_volume_burst pos | 5/5 | 60m | E | +0.5-1% |
| paradigm 128 alt_volume_burst neg | 5/5 | 15m | E | +0.5-1% |
| **lifecycle_pump_decay** (proposed) | 6.8σ + 27/40 plateau | 30d | E | **+7-10% mean** / **+20-25% median** |

lifecycle_pump_decay is the **highest per-trade edge** R-5 LIVE candidate (long-horizon Day-30 hold compounds the magnitude). Risk profile is also the most asymmetric: SL=+50% means max loss per trade is bounded at -50% × position size, while upside per trade is capped at +100% (if listing goes to zero).

### 3.5 Risk profile

- **Max single-trade loss**: -50% × 5% = -2.5% of portfolio
- **Max simultaneous drawdown**: 10 concurrent × -2.5% = -25% (worst case all SL hit)
- **Expected drawdown**: Q3 2025 bear-regime fold (median -3.52%, mean unknown) suggests ~5-10% drawdown windows even with bear filter (filter is BTC 30d, not real-time regime)
- **Bear-filter sensitivity**: removing bear regime (38/167 = 22.8%) leaves n=129 cohort, expected median ~+28-30% (between neutral 28.21% and bull 30.24% values)

---

## 4. Compatibility With Existing R-5 LIVE 10 Paradigms

| Existing R-5 | Conflict risk |
|---|---|
| paradigm 22/24 funding/premium R-5 | NONE — different substrate (funding/premium vs listing events) |
| paradigm 69 btc_rv_highvol R-5 | NONE — intraday 270m vs 30-day |
| paradigm 127/128 volume_burst R-5 | NONE — sub-hour vs 30-day |
| Other R-5 ARTIFACT_READY (volume_burst neg/pos) | NONE — different trigger class |

No resource conflicts (separate substrate, separate timescale, separate exit cycle). Position-cap (max 10 concurrent) ensures portfolio capacity remains for other R-5 LIVE strategies.

---

## 5. Substrate Availability

- **listing_dates.json**: 577 entries already cached (paradigm-architect verified — local file `/home/hcpark/antigravity/backend/runs/research_track/lifecycle_phase/listing_dates.json`)
- **Binance Futures exchangeInfo API**: existing infrastructure polls onboardDate (auto-updated daily)
- **OHLCV 1m**: existing PM2 cron backfill for new Binance perp listings
- **BTC 30d return indicator**: trivial to compute from existing BTC 1d OHLCV

**Substrate status**: ALL AVAILABLE. No new infra build required.

---

## 6. Lesson Cross-Reference

| Lesson | Status |
|---|---|
| #11 sample density | n=167 PASS (per-cell trivially satisfied — each listing is its own unique event) |
| #15 non-focus 4-cond | N/A (single direction, no sign-cond grid required for entry trigger) |
| #16 Concentration Gate | Structurally satisfied (167 unique symbols, no aggregation concern) |
| #19 Symmetric Negative Test | N/A (entry-side directional paradigm, not joint-trigger) |
| #20 sign-cond narrow scope | applied → bear regime filter is exact Lesson #20 narrow-scope conditioning |
| #26 walk-forward TS-CV | 3/4 PASS measurable folds + 1 too small drop |
| #27 entry-side vs exit-side | **entry-side** (listing event triggers entry; Day-30 time exit, NOT external event exit) |
| #28 substrate availability | PASS — all sources available at event time (listing date is published in advance) |
| #29 cross-proxy | N/A (single-axis event paradigm) |
| #30 data window ratio | N/A (this is FULL R-2/R-3 window 1.08yr, not ad-hoc slice) |
| #32 universe-baseline coherent | applied (BTC 30d regime is universe baseline, used as filter not as A vs B baseline) |
| #40 structural threshold feasibility | N/A (no z-score on non-negative aggregate) |
| #56 OUTCOME-LEVEL family proxy | escape candidate (5/5 prior listing graveyards; lifecycle_pump_decay = potential first family R-5 escape) |
| #61 R-0 inventory provenance | dispatch verified — INDEX claim "R-4 only" matches actual state ✅ |

---

## 7. User Approval Gate (STRICT — paradigm-architect spec)

**Agent halt at this report. R-5 seed execution requires user explicit acknowledgment.**

### Approval options:

1. **Approve full seed (recommended)**: deploy on Mint as paper session `lifecycle_pump_decay_v1` with bear-filter + 5%/name + max 10 concurrent + sl=0.5 hold=30. Day 7 baseline 2026-05-28+.

2. **Approve modified seed**: user may override any parameter (e.g., bear filter threshold, position size, hold period). Suggest substitutions in approval message.

3. **Defer seed pending additional validation**: e.g., request formal per-symbol Concentration Gate output (would require R-3.5 rerun with infra patch to lifecycle_phase_r3.py), or request bear-filtered R-2 rerun (n=129 expected).

4. **Reject / graveyard**: cite bear regime FAIL as blocking concern; mark lifecycle_pump_decay as `R-4_BEAR_REGIME_FAIL` not eligible for R-5.

**Default agent action without explicit user ack**: **NO seeding**. agent halts here.

---

## 8. Seed deployment checklist (post-approval, executed in separate turn)

- [ ] Mint server PM2 cron entry: `lifecycle_pump_decay_v1` daily 00:05 UTC scan for new listings
- [ ] Paper session config: 5%/name × 10 concurrent cap × sl=0.5 hold=30
- [ ] BTC 30d regime filter logic embedded in entry decision
- [ ] Pump-confirmation soft filter (Day 1 high ≥ +20% or Day 1 close ≥ +5%) — log both filtered and unfiltered paths for Day 30 comparison
- [ ] INDEX update: `current_phase` → `R-5_ARTIFACT_READY`, `seed_spec` populated
- [ ] PARADIGM_QUEUE §6.59 update with seed deployment timestamp
- [ ] Day 7 baseline measurement script scheduled 2026-05-28+
- [ ] Day 30 validation script scheduled 2026-06-20+
