# Graveyard — paradigm 217 `alt_btc_macro_release_window_pm_15min_event_anchored_vol_burst_alt_directional_5min_to_2h_bilateral`

**Verdict**: `R0_HALT_BY_SUBSTRATE_GAP_BTC_1M_INSUFFICIENT_LESSON_11_PLUS_LESSON_28`
**Halt phase**: R-0 (pre-R-1 dispatch)
**Halt timestamp**: 2026-05-23 08:49 KST
**Counter**: 216 → 217 (R-0 HALT, no R-1 executed)

## Hypothesis (user-provided, paradigm-architect Option 3 채택)

US macro release calendar event window-anchored vol burst paradigm. Major releases (CPI/FOMC/NFP/PCE/GDP) timestamp ±15min window 내 BTC realized vol (5min RV from 1m bars) spike trigger × 13 alt forward (paradigm 69 universe).

- **trigger**: BTC 5min RV at release ±15min × 30d rolling p90 spike
- **direction**: BTC release ±15min 5min directional movement sign (UP=hawkish / DOWN=dovish)
- **forward**: 13 alts × hold sweep 5min / 15min / 30min / 1h / 2h
- **SNT 4-quadrant**: BTC RV spike ±15min × {BTC dir UP / DOWN} × {LONG / SHORT}

## Why R-0 HALT (not R-1)

**Compound substrate gap at BTC 1m source**:

| Dimension | Required | Available | Verdict |
|---|---|---|---|
| BTC 1m window | ≥2.25yr (paradigm 69 R-5 reference) | **142d** (2025-12-22 → 2026-05-13) | FAIL 6x short |
| BTC 1m granularity | 1m (for 5min RV) | 1m PASS | OK |
| BTC 5m / 15m alt cache | event window ±15min match | NOT_AVAILABLE in DB | FAIL |
| BTC 4h cache | event window ±15min match | 819d but 4h granularity | FAIL granularity 16x too coarse |
| FRED API freemium classification | government public free | PASS per [[feedback-no-freemium-trial-dart-exception]] | OK (but moot) |
| Macro events 48/yr × usable yr | ≥30/cell/Q | **2.5/cell/Q** | FAIL 12x below cutoff |

### Lesson #11 sample density (FAIL_STRUCTURAL)

- BTC 1m window: 142d = 0.389 yr
- After 30d rolling p90 warmup: 112d usable = 0.307 yr
- Expected macro events in usable BTC 1m window: **14.7 events** (48/yr × 0.307)
- Distributed across 4 cells × 4 quarters: **2.5/cell/Q** vs cutoff **30** → **12x below**
- Even pooling 13 alts: 14.7 × 13 = 191 trigger×alt → 47.7/cell aggregate, BUT per-quarter ≤8 cells/Q
- BTC UP/DOWN split further halves: ~7.4 events × 13 alts / cell / direction / window

### Lesson #28 substrate-shape availability (FAIL)

- BTC trigger source = bottleneck. 12/13 alts have 750+ d of 1m data, BUT BTC = trigger anchor and only 142d available.
- Backfill ETA estimate: BTC 2.25yr × 1440 bars/day = ~1.2M rows from archive. Likely 30+ min ETA → **halt per paradigm-architect spec backfill discipline**.

### Lesson #30 data window ratio (FAIL advisory)

- BTC 1m window / BTC 4h full window = 142d / 819d = **17.3%**
- Threshold: ≥30% advisory. 17.3% structurally insufficient.
- Note: paradigm halts at R-0 (no R-1 advisory verdict downstream needed).

## Family-distinct audit (NOT REACHED)

Item 4 family-distinct 5/5 strict audit deferred because Item 2 substrate fail is fatal at R-0. Family-distinct verification is **moot** when substrate doesn't admit the experiment.

## Lesson coverage (R-0 HALT triggered by Items 2+3)

- ✅ **Lesson #11** sample density prescreen — 2.5/cell/Q ≪ 30
- ✅ **Lesson #28** substrate-shape availability — BTC 1m 142d ≪ 2.25yr required
- ✅ **Lesson #30** data window ratio advisory — 17.3% ≪ 30%
- ✅ **Lesson #61** INDEX.json grep STRICT — no prior macro/calendar paradigm collision
- ⏸ Lesson #19 SNT 4-quadrant — DEFERRED (R-0 HALT precedes execution)
- ⏸ Lesson #39 sub-class A/B avoidance — DEFERRED
- ⏸ Lesson #40 structural threshold (RV non-negative, z≤−3 infeasible) — DEFERRED but would have applied
- ⏸ Lesson #42 B mirror 20th dogfood — DEFERRED to paradigm 218
- ⏸ Lesson #69 9-item Items 4-9 — DEFERRED (substrate fail precedes)
- ⏸ Lesson #70 ESCAPE verification (paradigm 69 R-5 LIVE event-anchored class addition) — DEFERRED but would have been ESCAPE-PASS (event-anchored timing class distinct)

## Side discovery — substrate audit findings

1. **BTC 1m DB substrate window is 4.7 months**. 12/13 alts have 750+ d but BTC bottlenecks any cross-asset cascade paradigm requiring 1m-anchored BTC trigger.
2. **No 5m / 15m / 1h BTC cache in DB** — only 1m timeframe stored. Paradigms requiring intraday BTC trigger at sub-4h granularity face structural ceiling.
3. **FRED API confirmed government freemium exception class** ([[feedback-no-freemium-trial-dart-exception]]) — eligible substrate for future macro-event paradigms once BTC 1m backfill completes.

## Memorial chain dogfood

- **paradigm 203 MEMORIAL precedent mode-switch (user-provided hypothesis mandatory)**: ACTIVE
- User provided Option 3 (calendar event-anchored, paradigm-architect自体 recommendation) — chain-break confirmed
- agent SELF-RECOMMEND streak reset, memorial precedent preserved

## Pattern P1 alpha decay streak (10th operational Item 6 dogfood)

- Pre-paradigm-217 P1 streak: **6 consecutive** (paradigm 87+136+202+210+211+212)
- paradigm 217 outcome: **NOT_TESTED** (R-0 HALT pre-R-1)
- Streak status: **6 consecutive UNCHANGED** — paradigm 218 remains the 7th-consecutive Pattern P1 test slot
- 2026 era-universal decay 5th-instance test: **DEFERRED to paradigm 218**

## Lesson candidate (post-paradigm-217)

**Lesson candidate #72 — "BTC trigger source 1m substrate gap blocks event-anchored cross-asset cascade paradigms"**:

- 12/13 alts having 750+ d of 1m ≠ paradigm viability when BTC is trigger anchor
- BTC 4h (819d) does NOT substitute for BTC 1m at ±15min event-window paradigms
- Pre-paradigm-217: paradigm 69 R-5 LIVE uses BTC 4h cache (event-anchor-free unconditional p90 spike). Event-anchored paradigms require finer BTC granularity.
- Implication: future event-anchored (calendar / session boundary / macro release / spot ETF / hash-rate) paradigms must verify BTC trigger-source granularity ≥ event-window-anchor granularity FIRST.

**Dogfood 1 (paradigm 217)** → eligible for Lesson #72 candidate. Confirmation requires 2nd dogfood future paradigm.

## Next action recommendation

**paradigm 218 next-action** (continuous-parallel policy per [[feedback-paradigm-campaign-continuous-parallel]] + persistence-over-efficiency [[feedback-persistence-over-efficiency]]):

1. **Primary**: User provides next hypothesis (paradigm 203 MEMORIAL mode-switch ACTIVE, user-provided mandatory)
2. **Candidate axis options** (substrate-feasible):
   - **Option A — KR equity event-anchored (DART/KIND)**: post-DART supply contract / block trade / earnings family (Tier 4 retired 2026-11-18 까지 boundary, but exit-side narrow variants 가능)
   - **Option B — Binance non-BTC-anchored intraday**: per-sym alt 4h vol / liquidation cascade self-anchored (BTC trigger source 회피)
   - **Option C — funding family Tier 4 exception (illiquid venue / lead-lag / cross-ex OI divergence — paradigm 103 family exhaustion verified)**: very low yield
   - **Option D — BTC 1m archive backfill infrastructure task** (deferred separate session, ~30min+ ETA, paradigm-architect halt-discipline 위반 위험)
   - **Option E — macro-event reformulated with BTC 4h granularity** (FOMC + CPI 20/yr × 819d 2.25yr = ~45 events × 13 alts at ±4h event window — sample density viable, granularity matches 4h cache, BUT event window ±4h instead of ±15min loses microstructure precision)
3. **Recommendation (direct, per [[feedback-direct-recommendation]])**: **Option E (BTC 4h reformulated macro-event paradigm)** is the only structurally-feasible immediate successor preserving user's macro-event-anchor intent. paradigm 218 hypothesis: "FOMC + CPI release timestamp ± 4h window (next BTC 4h close after release) × BTC 4h directional move sign × 13 alt 4h-to-12h forward" — 45 events/yr × 2.25yr × 13 alts × 4 cells = 263/cell aggregate, sample density Lesson #11 PASS, BTC 4h substrate 819d PASS, FRED API government-exception substrate PASS.

## Artifacts

- `backend/runs/research_track/alt_btc_macro_release_window_pm_15min_event_anchored_vol_burst_alt_directional_5min_to_2h_bilateral/r0_prescreen.json`
- `backend/runs/research_track/graveyard__alt_btc_macro_release_window_pm_15min_event_anchored_vol_burst_alt_directional_5min_to_2h_bilateral.md` (this file)

## Cumulative tally post-paradigm-217

- **Total graveyards**: 216 → 217 (217th graveyard, R-0 HALT counted)
- **R-0 HALT subtype**: substrate-gap (Lesson #28 + #11 compound) — adds to Lesson #28 graveyard family
- **Pattern P1 alpha decay streak**: 6 consecutive (paradigm 217 not counted, R-0 HALT)
- **agent SELF-RECOMMEND chain**: BROKEN (paradigm 203 MEMORIAL precedent), user-provided mode ACTIVE
- **Continuous-parallel campaign**: maintained per [[feedback-paradigm-campaign-continuous-parallel]]
- **Persistence-over-efficiency**: maintained per [[feedback-persistence-over-efficiency]]
