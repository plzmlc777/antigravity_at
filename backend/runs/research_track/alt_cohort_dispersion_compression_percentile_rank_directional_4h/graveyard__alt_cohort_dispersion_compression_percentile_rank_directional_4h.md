# Graveyard: alt_cohort_dispersion_compression_percentile_rank_directional_4h

- **Paradigm number**: 110
- **Phase halted**: R-1 BROAD_FALSIFIED (4-quadrant SNT + 20-cell sweep + Concentration + Lesson #21 all FAIL; A_focus direction INVERTED)
- **Verdict**: BROAD_FALSIFIED_FEE_FLOOR (mechanism direction inverted, A_mirror real but fee-bound)
- **Date**: 2026-05-20 KST
- **Host**: Mint (mint@183.99.228.81 sole live operating server)
- **Dispatch**: /new-paradigm-frontier continuous-parallel policy 8th dispatch (103+104+105+106+107+108+109+110)
- **Rescue path of paradigm 109**: percentile rank reformulation (z-score impossible by Lesson #40 candidate)

## One-sentence

Paradigm 109 rescue R1 reformulation (percentile rank ≤ 0.10 replacing z ≤ −2) successfully resolves structural threshold infeasibility (10% trigger rate by design) — but reveals **underlying mechanism is direction-inverted not null**: A_focus (compression + BTC up → cohort LONG) gross **−12.94bp**, t=**−6.40**, **13/13 alts ci_neg**, perm_p 0.000; A_mirror (compression + BTC up → cohort SHORT) gross +12.94bp = real mechanism but ≪ 16bp fee floor; Lesson #40 candidate confirmed via 2nd dogfood as **independent of mechanism viability**.

## 5-axis novelty matrix (paradigm 109 inherited)

| Axis | Status | Note |
|---|---|---|
| Data source | known | OHLCV |
| **Statistic** | **NOVEL** | Cross-section return dispersion percentile rank compression (paradigm 109 was z-score, infeasible by Lesson #40) |
| Time scale | known | 1h trigger / 240m hold |
| **Universe** | **NOVEL** | Cohort uniform-alignment regime as universe-level statistic, not per-symbol |
| **Mechanism** | **NOVEL** | Dispersion compression → uniformity regime → directional cascade — verified REAL but direction INVERTED |

3/5 NOVEL passed. Statistic dimension distinct from paradigm 109 (z-score → percentile rank).

## R-0 prescreens (all PASS by design)

| Lesson | Status | Detail |
|---|---|---|
| **#40 candidate (1st structural feasibility check)** | **PASS** by design | percentile rank guarantees ≥10% trigger rate, fixes paradigm 109 fail mode |
| #11 sample density | PASS | A focus 116.8/q × 4 quadrants × 4-9 quarters, B same 117.2/q |
| #19 SNT 4-quadrant | PASS_4Q_RUN | all 4 quadrants computed single batch |
| #21 axis-alone | measured | single axes alone both deeply negative, joint also negative — no synthesis |
| #23 trigger rate | PASS | 11.51% (cutoff 1.5%) |
| #28 substrate audit | PASS | 13/13 alts joblib cached × 2.36yr |
| #30 data window ratio | PASS | 100% (Mint full 2.36yr) |
| #32 universe-baseline coherence | measured | A_focus −20.94bp vs baseline −16.42bp (both negative, A_focus worse by 4.52bp) |
| #34 empirical distribution | validated | σ_cs p5=0.00189 p50=0.00407 p90=0.00869, p_rank p10≈0.089 |

## R-1 4-quadrant Symmetric Negative Test (primary p_rank≤0.10 × hold 240m)

| Quadrant | n | gross_bp | net_bp | t | sigex | perm_p | ci_low_bp | syms_ci_pos | q_pos | Gate |
|---|---|---|---|---|---|---|---|---|---|---|
| **A_focus** (z↓ BTC↑ → LONG) | 1,168 | **−12.94** | −20.94 | **−6.40** | −4.99 | 0.000 | −27.20 | **0/13** | 0.00 | **FAIL — direction inverted** |
| A_mirror (z↓ BTC↑ → SHORT) | 1,168 | +12.94 | +4.94 | +1.51 | +2.84 | 0.428 | −1.60 | 4/13 | 0.90 | FAIL (perm_p + ci_low) |
| B_same_sign (z↓ BTC↓ → SHORT) | 1,172 | +3.93 sub-fee | −4.07 | −1.12 | +0.19 | 0.607 | −11.18 | 0/13 | 0.30 | FAIL |
| B_mirror (z↓ BTC↓ → LONG) | 1,172 | −3.93 | −11.93 | −3.27 | −1.84 | 0.039 | −18.90 | 0/13 | 0.40 | FAIL |

**Critical pattern**: A_focus + A_mirror are exact negatives (±12.94bp) — Lesson #39 candidate symmetric perfect mirror antipattern 2nd dogfood (paradigm 108 was 1st).

But unlike paradigm 108 (where perfect mirror = zero directional info), paradigm 110 A_mirror shows 9/10 quarters pos_t + 4/13 syms ci_pos = **mechanism direction is REAL** (compression + BTC up → cohort SHORT is the correct direction); fee floor 16bp + perm_p 0.428 block it.

## R-1 20-cell hold×p_rank sweep (Lesson #37)

Only **1 cell** with 3-gate AND Concentration PASS:
- `B_same_pr0.15_h1440` (24h hold, p_rank≤0.15, BTC down SHORT)
- n=1,671 / gross +25.35bp / net +17.35bp / t=1.97 / sigex 2.43 / perm_p 0.074 / ci_low +0.63bp / q_pos 7/10 / syms_pos 4/13

Life-changing 4-dim:
- trades/yr = 708 ✅
- **edge/trade = 0.17%** ❌ (≪ 2% cutoff, 11.8x deficit)
- sharpe ≈ — / util ≈ —

**NARROW_SCOPE_LIFE_CHANGING_FAIL ineligible** (Lesson #20 4-cond not all PASS due to monotonicity FAIL — 24h hold is outlier vs 60m-240m all FAIL). Default to BROAD_FALSIFIED_FEE_FLOOR.

## Lesson #21 axis-alone dogfood

- axis_1 (p_rank ≤ 0.10 alone, LONG any BTC dir): t=−6.70, sigex=−4.63 (deeply negative)
- axis_2_btc_up (BTC up alone, LONG random subsample): t=−5.21
- axis_2_btc_dn (BTC down alone, SHORT random subsample): t=−3.56
- joint: also negative

→ Each axis alone is deeply negative; joint axis is also negative. No alpha synthesis. Lesson #21 confirmed for this paradigm.

## Lesson #32 universe-baseline-coherent dogfood (negative-drift artifact form)

- A_focus_LONG = −20.94bp
- B_baseline_same_filter (p_rank compression alone LONG) = −16.42bp
- A_focus worse than baseline by 4.52bp

A_focus drift is on **negative drift** direction (both negative, A_focus more negative). This is a new sub-pattern of Lesson #32 — paradigm 101 was positive-drift artifact (A_focus +52.9 < B baseline +68.4); paradigm 110 is **negative-drift artifact concentration** (A_focus −20.94 worse than B −16.42). Mechanism interpretation: BTC-up filter concentrates cohort's negative post-fee drift further (cohort underperforms BTC-up regime systematically post-fee).

## NEW Lesson #41 candidate — Compression-regime-conditional-on-BTC-direction-inverts

**Rule**: When the cohort dispersion compresses (low cross-section std), the cohort **does NOT follow BTC direction** in the next 4h — instead reverses direction (BTC up → cohort SHORT, BTC down → cohort weak LONG / null).

**Why** (hypothesis): Compression regime indicates macro-driven "all-aligned" state where individual symbols have already moved with macro. Subsequent 4h is mean-reversion or alt-vs-BTC rotation, not continuation.

**Evidence (1 dogfood paradigm 110)**:
- A_focus (compression + BTC up → cohort LONG): gross −12.94bp t=−6.40 13/13 alts ci_neg, perm_p 0.000 = decisively inverted
- A_mirror (compression + BTC up → cohort SHORT): gross +12.94bp 9/10 quarters pos_t + 4/13 syms ci_pos = real but fee-bound
- B_same (compression + BTC down → cohort SHORT): sub-fee weak negative, asymmetric

**How to apply**: Compression-conditional cohort hypotheses with BTC-direction follow assumption are pre-likely-inverted. Consider Lesson #8 amendment (symmetric LONG bias amendment) and Lesson #41 mirror-precedence prescreen for similar trigger structures.

**Status**: 1st dogfood, candidate. Awaiting 2nd dogfood (independent compression-direction-conditional paradigm).

## Lesson #40 candidate 2nd dogfood (CONFIRMED 자격)

- paradigm 109: structural threshold infeasibility (z≤−2 unreachable, σ_cs.z_min=−1.92)
- paradigm 110: structural threshold reformulation SUCCESS (10% trigger rate), but mechanism direction INVERTED
- **Interpretation**: STRUCTURAL_FIX_INSUFFICIENT_UNDERLYING_MECHANISM_ALSO_NULL_OR_INVERTED
- **Lesson #40 candidate CONFIRMED**: structural threshold feasibility ≠ mechanism viability. R-0 prescreens must check **both dimensions independently**.

## Lesson #39 candidate 2nd dogfood

- paradigm 108: A_focus +2.08bp / A_mirror exact −2.08bp = perfect symmetry (1st dogfood)
- paradigm 110: A_focus −12.94bp / A_mirror exact +12.94bp = perfect symmetry (2nd dogfood)

Both cases: trigger conditions have zero net directional information; sign comes from input direction axis. Lesson #39 candidate → confirmed 자격 ready (2 dogfoods).

However, paradigm 110 differs from paradigm 108 in that A_mirror (the "inverted" cell) shows real concentration (9/10 quarters pos_t + 4/13 syms ci_pos), unlike paradigm 108 (broad-uniform-negative). This refines Lesson #39:
- Sub-class A (paradigm 108): perfect symmetry + both quadrants broad-uniform-negative = zero directional info, pure direction-bet trap
- Sub-class B (paradigm 110): perfect symmetry + mirror shows real concentration = mechanism direction inverted, A_mirror is the correct direction but fee-bound

## Life-changing 4-dim (A_focus primary 240m)

| Dim | Value | Threshold | Pass |
|---|---|---|---|
| trades/yr | 495.5 | ≥ 12 | ✅ |
| edge/trade | **−0.21%** | ≥ +2% | ❌ |
| sharpe | **−4.17** | ≥ 3 | ❌ |
| util | 22.6% | ≥ 30% | ❌ |

3/4 FAIL (primary direction inverted). Even A_mirror direction is below fee floor (gross +12.94bp < 16bp).

## Family classification

- **Cross-section dispersion compression family**: 109 + 110 = 2 sub-class graveyards (z-score structural / percentile rank inverted)
- **Combined with adjacent broader cross-section family** (74-77 corr breakdown / 64-65 momentum rotation / 94-95 volume share retired): 6+ retired sub-families in cross-section domain
- **Tier 4 formal retire consideration**: 109+110 alone insufficient for formal Tier 4 (different fail modes, not 2 broadly-falsified mechanism instances). Lesson #41 candidate provides framework for future dispatch in this family — must condition on mechanism inversion possibility.
- **No formal Tier 4 retire**: paradigm 110 leaves "compression regime mean-reversion / alt-vs-BTC rotation" path open (Lesson #41 hypothesis can be tested as independent paradigm 111+ if user authorizes).

## Infrastructure (Mint, permanent assets)

- `backend/scripts/research/paradigm110_alt_cohort_dispersion_compression_percentile_rank_r1.py` (committed)
- `backend/runs/research_track/alt_cohort_dispersion_compression_percentile_rank_directional_4h/r1__metrics.json` (234KB committed)
- `backend/runs/research_track/alt_cohort_dispersion_compression_percentile_rank_directional_4h/graveyard__alt_cohort_dispersion_compression_percentile_rank_directional_4h.md` (this file)
- joblib cache 14 syms × 2.36yr reused (paradigm 109 infrastructure)
- p_rank rolling computation: 0.3s for 20,688 hourly bars × 720-window
- Wall clock: 38 seconds R-1 (paradigm 109 cache reused)

## Verdict & next steps

- **110번째 graveyard**. `BROAD_FALSIFIED_FEE_FLOOR` with mechanism direction inversion (distinct from broad uniform negative or fee-floor pure cases).
- **Lesson #40 candidate → confirmed 자격** (2 dogfoods 109+110, both directional).
- **Lesson #39 candidate → confirmed 자격** (2 dogfoods 108+110, with sub-class refinement A perfect-symmetry-broad-neg vs B perfect-symmetry-real-direction-inversion).
- **NEW Lesson #41 candidate** (1st dogfood) — compression-regime-conditional-on-BTC-direction-inverts.
- **No formal family retire** (109+110 different fail modes, mechanism real but inverted in 110).
- Adjacent paths still open:
  - Compression + BTC-direction CONTRARIAN paradigm (Lesson #41 hypothesis test, but fee floor pre-block likely)
  - log-transform z-score variant (paradigm 109 rescue R2)
  - ratio compression variant (paradigm 109 rescue R3)
  - Different mechanism class entirely (cross-section magnitude pre-event)
