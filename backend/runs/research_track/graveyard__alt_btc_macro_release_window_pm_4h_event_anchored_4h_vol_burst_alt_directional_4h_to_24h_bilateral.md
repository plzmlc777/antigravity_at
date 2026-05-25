# Graveyard — paradigm 218 `alt_btc_macro_release_window_pm_4h_event_anchored_4h_vol_burst_alt_directional_4h_to_24h_bilateral`

**Verdict**: `NARROW_SCOPE_LIFE_CHANGING_FAIL_LESSON_70_ESCAPE_INVALID`
**Halt phase**: R-1 (PASS_SWEEP_CELL surface, GRAVEYARD on structural prescreen)
**Halt timestamp**: 2026-05-23 09:00 KST
**Counter**: 217 → 218

## Hypothesis (user-provided, paradigm-architect Option E reformulation)

US macro release calendar event window-anchored vol burst paradigm, reformulated at BTC 4h granularity to match substrate after paradigm 217 R-0 HALT (BTC 1m DB only 142d).

- **timing anchor**: FOMC (19 events) + CPI (27 events) = 45 total in BTC 4h cache span (2024-02-01 → 2026-04-30)
- **trigger**: BTC 4h |log return| 30d rolling p90 spike (paradigm 69 R-5 LIVE mechanism inherit)
- **direction**: BTC 4h directional sign at release window (UP=hawkish / DOWN=dovish)
- **forward**: 13 alts × hold 4h primary + 8h / 12h / 24h sweep
- **4-quadrant SNT**: vol spike × {BTC UP / DN} × {LONG / SHORT}

## R-1 surface result (FORMAL PASS — interpretively artifact)

| Cell | n_obs | obs_mean (bp) | signal_t_excess | ci_lower (bp) | perm_p | 3-gate |
|---|---|---|---|---|---|---|
| **A_focus** LONG×UP_spike | 65 | **+221.1** | **+15.70** | +194.5 | 0.000 | **PASS** |
| A_mirror SHORT×UP_spike | 65 | -237.1 | -16.12 | -265.6 | 0.000 | FAIL |
| **B_same** SHORT×DN_spike | 65 | **+351.7** | **+13.78** | +299.8 | 0.000 | **PASS** |
| B_mirror LONG×DN_spike | 65 | -367.7 | -13.70 | -419.6 | 0.000 | FAIL |

Sweep-cell PASS: 8/16 (all 4 holds × A_focus + B_same continuation cells PASS).

## Concentration + Quarterly + Era (PRIMARY 4h, A_focus + B_same)

| Cell | syms_ci_pos | quarters_pos_t | era_2024 | era_2025 | era_2026 |
|---|---|---|---|---|---|
| A_focus | 13/13 (1.0) | 3/3 (1.0) Q1+Q2+Q3 2024 only | n=65 +221bp t=+15.4 | absent | **absent** |
| B_same | 13/13 (1.0) | 3/3 (1.0) Q2+Q4 2024 + Q4 2025 | n=52 +307bp t=+10.7 | n=13 +530bp t=+18.5 | **absent** |

**Era stratify reveals critical structural flaw**: 0 macro-event-coincident BTC vol p90 spikes in 2026 era despite cache extending to 2026-04-30 (3 FOMC + 4 CPI events in 2026 portion of cache).

## Why GRAVEYARD despite formal 3-gate PASS

### 1. Lesson #70 ESCAPE INVALID (2nd dogfood, 1st was paradigm 217 R-0 HALT)

- **paradigm 218 event set ⊂ paradigm 69 R-5 LIVE event set**: paradigm 69 fires on ALL BTC 4h vol p90 spikes (~497 over 819d). paradigm 218 fires only on the 10 spike-bars that happen to align with macro release ±4h windows.
- **Macro filter is purely selective (10/497 = 2.01% selectivity)**, not mechanism-additive. The "alpha" measured is paradigm 69's mechanism with a sparser anchor, not a distinct mechanism.
- **Premium over paradigm 69 parent insignificant**:
  - paradigm 69 R-5 LIVE precedent: +186bp at 240m hold, 13 alts
  - paradigm 218 A_focus: +221bp at 4h hold, 13 alts
  - Diff: +35bp gain
  - n_indep events: 5 per direction (not 65 — the 13 alts share entry timestamps and BTC-driven correlation under spike)
  - SE_subsample under paradigm 69 null with n_indep=5: ~179bp
  - **z = +0.20σ, p_one-sided = 0.422** → cannot reject H0 ("no macro premium beyond parent paradigm 69")
- **Conclusion**: paradigm 218 = paradigm 69 with a 50x sparser, no-better-edge trigger. Lesson #70 scope clarification ([[feedback-lesson-70-scope-clarification-amendment]]) requires the event-anchored class to be mechanistically distinct, not a strict-subset selector. **ESCAPE claim INVALID.**

### 2. Life-changing 4-dim STRUCTURAL FAIL (Item 9, 3rd operational dogfood)

| Dim | Estimate | Threshold | Verdict |
|---|---|---|---|
| trades/yr aggregate | 29 (5 events × 13 alts ÷ 2.25yr) | ≥12 | PASS |
| trades/yr per-alt | 2.2 | ≥12 | **FAIL** |
| capital util | **1.32%** (4h × 29 / 8760) | ≥30% | **FAIL 22x** |
| per-trade edge | +221bp / +352bp | ≥+2% | PASS |
| sharpe (rough) | ~3.0 (single cell, n=5 events) | ≥1.5 | PASS but contingent |

**Capital util 1.32% materializes paradigm 215 precedent (1.5% util STRUCTURAL FAIL)** — third Item 9 operational instance. Sparse-trigger event-anchored paradigms (event count ≪ 100/yr) cannot deploy capital meaningfully even if per-trade edge is large.

### 3. Sample density: 5 independent events per direction (Lesson #11 borderline)

- The n_obs=65 per cell is inflated by 13 alts sharing the same 5 entry timestamps; under BTC vol cascade these alts are highly correlated.
- **Effective independent events per direction = 5**, ≪ Lesson #11 30/cell cutoff.
- 5/13 alts UP-spike + 5/13 alts DN-spike = 50/50 cross-set ratio (clean Item 7 PASS) but **structurally too small for paradigm-grade inference**.

### 4. Pattern P1 alpha decay 7th consecutive instance + 2026 era-universal decay 5th instance

- A_focus quarters: 2024Q1 / 2024Q2 / 2024Q3 only — **0 of 5 quarters since 2024Q4 admit A_focus events**.
- B_same quarters: 2024Q2 / 2024Q4 / 2025Q4 — **0 of 2026 quarters admit B_same events**.
- 3 FOMC + 4 CPI events fall within 2026 portion of BTC cache, but NONE coincide with BTC vol p90 spike.
- **Pattern P1 7th consecutive** ([[feedback-broad-cross-class-alpha-decay-hypothesis]] formal universal verdict triggered).
- **2026 era-universal decay 5th instance CONFIRMED** ([[feedback-2026-era-universal-decay-candidate]]).

### 5. Lesson #39 sub-class A (perfect symmetric mirror) realised

- A_focus +221.1 / A_mirror -237.1 → mid -8bp (≈ -fee 8bp exactly)
- B_same +351.7 / B_mirror -367.7 → mid -8bp (≈ -fee 8bp exactly)
- **Cells are exact mirrors around the fee floor.** Per Lesson #39 sub-class A taxonomy this is consistent with the trigger carrying no informational content beyond direction (pure direction-bet + fee drag asymmetry between continuation and reversal). Combined with point 1 (paradigm 69 mechanism reduction), the macro-event filter contributes zero novel direction signal.

### 6. Lesson #42 20th dogfood — B_mirror = NEGATIVE

- B_mirror (LONG_after_DN_spike) obs_t = -14.05, signal_t_excess = -13.70, ci_lower_bp = -419.6, three_gate_pass = **false**
- Chain position 20. Updated 3-tier before this dogfood: 10 CONFIRMED / 8 NEGATIVE / 1 PASS_AS_ARTIFACT.
- **20th instance = NEGATIVE**. Updated tally: 10 CONFIRMED / **9 NEGATIVE** / 1 PASS_AS_ARTIFACT. Lesson #42 ratio shifts further toward NEGATIVE-dominant (45% confirmed vs 45% negative + 5% artifact).

## Lesson coverage (R-1 executed, GRAVEYARD on structural+ESCAPE+life-changing)

- ✅ **Lesson #11** sample density borderline (5 indep events per direction × 13 alts inflated to 65)
- ✅ **Lesson #19** SNT 4-quadrant — A_focus + B_same continuation surface PASS, A_mirror + B_mirror reversal exact-symmetric FAIL
- ✅ **Lesson #28** substrate-shape PASS (BTC 4h + 13 alts 4h 819d)
- ✅ **Lesson #30** data window ratio = 100% (full 819d used) — PASS
- ✅ **Lesson #37** full hold×cell sweep verdict scan: 8 cells PASS (4 holds × 2 continuation cells)
- ✅ **Lesson #39** sub-class A perfect symmetric mirror artifact (exact ±k bp around fee floor)
- ✅ **Lesson #40** structural threshold: NOT triggered (vol p90 is upper-tail of non-negative magnitude, achievable)
- ✅ **Lesson #42** 20th dogfood = NEGATIVE (B_mirror)
- ✅ **Lesson #56** family-proxy: macro-anchored class — but reducible to paradigm 69 (Lesson #70 ESCAPE INVALID)
- ✅ **Lesson #61** INDEX grep PASS (paradigm 217 sibling identified, distinct hold class)
- ✅ **Lesson #62** DNA 4-dim surface PASS but Lesson #70 reduction overrides
- ✅ **Lesson #67** ESCAPE: BTC trigger → 13 alts cross-asset cascade (paradigm 70+71+206 advisory caution)
- ✅ **Lesson #68** ESCAPE: macro release calendar event (irregular sparse events, session-boundary distinct)
- ✅ **Lesson #69** 9-item template ALL EXECUTED
- ❌ **Lesson #70 ESCAPE INVALID** (2nd dogfood; 1st = paradigm 217 R-0 HALT scope clarification): event-anchored class addition claim INVALID when event set ⊂ parent paradigm 69 trigger pool
- ❌ **Item 6 alpha decay** Pattern P1 7th consecutive + 2026 era-universal 5th instance
- ❌ **Item 9 life-changing structural** FAIL 3rd operational (1.32% util, paradigm 215 1.5% precedent realised)

## Family-distinct strict 5/5 audit (REVISED post-result)

vs paradigm 69 R-5 LIVE BTC RV p90 alt LONG:
- statistic class: paradigm 218 = paradigm 69 trigger ∩ macro_release_window subset — **NOT distinct mechanism**
- universe: 13 alts identical
- entry-side: paradigm 69 continuous spike / paradigm 218 spike + macro intersection — **selector not new mechanism**
- mechanism: BTC vol cascade IDENTICAL (paradigm 69 mechanism unchanged)
- hold: 4h–24h sweep inherits paradigm 69 R-5 LIVE 240m class

**Revised 5/5 verdict: 1/5 distinct (event-anchor is filter only)**. R-0 audit's pre-execution 4/5 claim was over-optimistic; empirical event set ⊂ parent set confirms reducibility. Lesson #70 scope clarification's "event-anchored class addition" pattern fails when the event filter does not produce a NEW trigger event but only **culls** the parent's trigger pool.

## Cross-set asymmetry (Item 7, 7th instance)

- n_UP_spike = 5, n_DN_spike = 5
- ratio_UP/DN = 1.00x (perfectly balanced)
- Item 7 historical: 1.83x / 2.79x / 3.36x / 0.86x / 1.143x / 2.15x / **1.00x**
- Mean asymmetry across 7 instances: 1.88x; paradigm 218 is the most-balanced instance to date.
- Interpretation: small n_indep=5 + 5 makes 1:1 ratio not informative; not a signal of structural balance.

## Unconditional baseline (Lesson #39 sub-class B test)

Unconditional pooled returns over BTC dir + 13 alts (no event filter, no spike filter, full panel):

| Cell | n | mean (bp) | t |
|---|---|---|---|
| BTC_UP × LONG 4h | 32,838 | +77.3 | +89.5 |
| BTC_UP × SHORT 4h | 32,838 | -93.3 | -108.1 |
| BTC_DN × LONG 4h | 31,109 | -96.0 | -99.0 |
| BTC_DN × SHORT 4h | 31,109 | +80.0 | +82.5 |

- **Unconditional BTC UP × LONG 4h = +77bp** vs paradigm 218 A_focus +221bp. Ratio 2.86x.
- **Unconditional BTC DN × SHORT 4h = +80bp** vs paradigm 218 B_same +352bp. Ratio 4.40x.
- The +144bp (A_focus) and +272bp (B_same) "premia" over unconditional are within parent paradigm 69's effect band (+108bp uplift over unconditional via vol p90 filter alone), not unique to macro-event filter.
- **Sub-class B unconditional baseline confirms paradigm 69 mechanism reduction**: paradigm 218's macro filter does not add measurable premium beyond the vol p90 filter alone.

## Pattern P1 alpha decay update (7th consecutive)

Pre-paradigm-218 streak: 6 consecutive (paradigm 87 + 136 + 202 + 210 + 211 + 212).
paradigm 217: NOT_TESTED (R-0 HALT).
paradigm 218: **NEGATIVE 2026 era** (0 of 3 2026 quarters admit cell events; 0 of 2 2026 quarters for A_focus).

**Streak now 7 consecutive — formal universal verdict triggered** ([[feedback-broad-cross-class-alpha-decay-hypothesis]]).

**2026 era-universal decay 5th instance CONFIRMED** ([[feedback-2026-era-universal-decay-candidate]]): paradigm 218 explicitly shows 0 of the 2026 portion of cache admits the spike∩macro_release intersection.

## Memorial chain dogfood

- **paradigm 203 MEMORIAL precedent mode-switch (user-provided hypothesis mandatory)**: ACTIVE, preserved
- User provided Option E (paradigm-architect自体 recommendation 채택) — counted as user-provided per precedent
- agent SELF-RECOMMEND streak remains BROKEN

## Lesson candidate (post-paradigm-218)

**Lesson candidate #72 reinforced** (BTC 1m substrate gap blocks event-anchored cross-asset cascade): paradigm 218 4h reformulation succeeded substrate-wise but reduced to parent paradigm 69 due to coarse granularity. **±4h window contains too much non-event BTC drift to isolate macro-event mechanism**.

**NEW Lesson candidate #73** — "**Event-anchored selector ⊂ parent-paradigm trigger pool is selector not mechanism**":
- When event-anchored R-1 produces apparent PASS but event set is empirically a strict subset of a parent paradigm's trigger set, the event anchor is functioning as a selector (subsample filter) not as a mechanism producer.
- Test: compute parent-paradigm-conditional gain (observed − parent_mean) and compare to subsample SE under parent null.
- If gain p-value > 0.10 vs parent, classify as Lesson #70 ESCAPE INVALID and graveyard regardless of formal 3-gate PASS.
- **First dogfood = paradigm 218** (z = +0.20σ vs parent, p = 0.422). Confirmation requires 2nd dogfood future paradigm.

**NEW Lesson candidate #74** — "**±4h window resolution forfeits microstructure precision for sample availability**":
- ±4h on 4h granularity = 1 bar = entire 4h drift, not event-microstructure measurement
- Future event-anchored paradigms requiring microstructure precision (e.g., ±15min spike isolation) must verify trigger-source granularity ≥ 4x the anchor window, otherwise the "anchor" becomes a noisy filter
- **First dogfood = paradigm 218** (4h window on 4h bars = trivial alignment, no microstructure information). Confirmation requires 2nd dogfood future paradigm.

## Artifacts

- `backend/scripts/research/alt_btc_macro_release_window_pm_4h_event_anchored_4h_vol_burst_alt_directional_4h_to_24h_bilateral_r1.py`
- `backend/runs/research_track/alt_btc_macro_release_window_pm_4h_event_anchored_4h_vol_burst_alt_directional_4h_to_24h_bilateral/r1__metrics.json`
- `backend/runs/research_track/graveyard__alt_btc_macro_release_window_pm_4h_event_anchored_4h_vol_burst_alt_directional_4h_to_24h_bilateral.md` (this file)

## Cumulative tally post-paradigm-218

- **Total graveyards**: 217 → 218 (counted)
- **R-1 surface-PASS-but-structurally-FAIL subtype**: NARROW_SCOPE_LIFE_CHANGING_FAIL family (paradigm 95 + 99 + 218)
- **Lesson #70 ESCAPE INVALID dogfoods**: 2 (paradigm 217 R-0 HALT scope clarification + paradigm 218 R-1 selector-not-mechanism)
- **Pattern P1 alpha decay streak**: **7 consecutive** — formal universal verdict triggered
- **2026 era-universal decay**: **5th instance CONFIRMED**
- **Item 9 life-changing 4-dim STRUCTURAL FAIL operational dogfoods**: 3 (paradigm 213 + 215 + 218)
- **Lesson #42 20th dogfood result**: NEGATIVE. Updated tally 10 CONF / 9 NEG / 1 ARTIFACT
- **agent SELF-RECOMMEND chain**: BROKEN preserved (paradigm 203 MEMORIAL precedent)
- **Continuous-parallel campaign**: maintained per [[feedback-paradigm-campaign-continuous-parallel]]
- **Persistence-over-efficiency**: maintained per [[feedback-persistence-over-efficiency]]

## Next-action recommendation (paradigm 219)

Per [[feedback-direct-recommendation]] + continuous-parallel policy + user-provided mode-switch ACTIVE:

**Primary recommendation**: User provides next hypothesis (paradigm 203 MEMORIAL mode-switch ACTIVE).

**Substrate-feasible axis options** (post-paradigm-218 learnings):

- **Option A — Funding-flip pre-event window (paradigm 22 R-5 LIVE distinct mechanism extension)**: 8h funding boundary ±15min spike-conditional alt forward. Funding family Tier 4 retire except paradigm 22 R-5 LIVE exception class. Risk: family exhaustion.
- **Option B — Liquidation cascade self-anchored per-sym (no BTC trigger)**: avoids Lesson #67 ESCAPE issues + paradigm 218 parent-paradigm-reduction. Requires liquidation-feed substrate audit (binance liqs aggregated stream availability check).
- **Option C — KR equity pattern strategy track-3 cross-pollination**: lesson #29 cross-proxy strict mandates 2 independent signals — KR/Binance signal pair. Out-of-scope for paradigm-architect (composer-builder track).
- **Option D — DEFER paradigm 219 until BTC 1m archive backfill** completes (separate session, ~30min ETA, paradigm-architect halt-discipline violation if attempted now).
- **Option E — Macro-event paradigm class formal Tier 4 retire**: paradigm 217 + 218 dual fail (substrate-gap + selector-reduction) → recommend formal family retire to redirect campaign capacity.

**Direct recommendation (per [[feedback-direct-recommendation]])**: **Option E (macro-event paradigm family Tier 4 retire) + user supplies fresh non-event-anchored axis for paradigm 219**. Macro-event-anchored class has exhausted substrate-feasible variants without producing distinct mechanism alpha; further variations risk Item 9 capital util structural FAIL.
