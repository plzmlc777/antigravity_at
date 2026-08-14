# Graveyard — paradigm 241 (alt_new_perp_listing_attention_effect_existing_alts_bilateral_5d)

- Paradigm number: **241**
- Phase reached: **R-1**
- Verdict: **CONCENTRATED_R1_PASS → HALT (Lesson #16)**
- Trigger family: listing_event (external, non-OHLCV)
- R-1 metrics: `backend/runs/research_track/paradigm_241_listing_attention_effect/r1__metrics.json`
- R-1 script: `backend/scripts/research/paradigm_241_listing_attention_effect_r1.py`
- Date (KST): 2026-07-30

## Hypothesis (recap)

Each USDT-M perp new-listing event on Binance creates a measurable 5-day directional return
effect on the 14 pre-existing alt universe:
- A_focus: LONG existing alts post-listing (halo/attention rotation)
- A_mirror: SHORT existing alts post-listing (attention drain)
- B_focus: LONG existing alts during bear-BTC-regime listings
- B_mirror: SHORT existing alts during bear-BTC-regime listings

Entry: onboard_date + 24h → exit: +5d close. Universe: BTC/ETH/BNB/SOL/XRP/DOGE/ADA/AVAX/LINK/LTC/BCH/FIL/NEAR/WIF (pre-existing at event time only). Fee: 8bp round-trip.

## R-0 Prescreen

| Check | Result |
|---|---|
| Slug grep prior art | none in code/docs |
| DNA vs lifecycle_pump_decay | 3/6 overlap (data + trigger + hold-approx) → PASS |
| Substrate audit | listing_dates.json + 14 caches (2024-01→2026-05) confirmed |
| Sample density (Lesson #11) | 148 debounced events × ~14 syms = ~2064 obs (target ≥ 30/cell) PASS |
| Lesson #77 non-OHLCV trigger | PASS (event-anchored) |
| Lesson #79 predictive-content pretest | EXEMPT (external event, not microstructure) |
| Lesson #40 structural threshold | N/A (no threshold, all events used) |
| Lesson #56 family proxy | lifecycle_pump_decay trades LISTED TOKEN, this trades EXISTING alts — different mechanism, different universe, not outcome-equivalent |

## R-1 Results — 4-Quadrant SNT + 2 extra regime cells

Fee = 8bp round-trip, hold = 5d, entry = onboard + 24h, debounce = 3d.

| Quadrant | n | mean_bp | obs_t | sig_ex | perm_p | ci_lower_bp | ci_upper_bp | 3-gate |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| A_focus LONG all | 2064 | -108.7 | -4.79 | -4.00 | 0.000 | -189.8 | -28.8 | FAIL |
| **A_mirror SHORT all** | **2064** | **+92.7** | **+4.08** | **+4.87** | **0.001** | **+12.8** | **+173.8** | **PASS** |
| B_focus LONG bear-BTC | 866 | -199.5 | -6.23 | -5.73 | 0.000 | -320.6 | -81.8 | FAIL |
| **B_mirror SHORT bear-BTC** | **866** | **+183.5** | **+5.73** | **+6.23** | **0.000** | **+65.8** | **+304.6** | **PASS** |
| C LONG bull-BTC | 1159 | -46.0 | -1.43 | -0.86 | 0.214 | -163.7 | +65.6 | FAIL |
| C SHORT bull-BTC | 1159 | +30.0 | +0.93 | +1.50 | 0.415 | -81.6 | +147.7 | FAIL |

Interpretation: two SHORT cells cleanly clear 3-gate; the LONG twins symmetrically fail (perm_p 0 negative sign). Not a Lesson #39 sub-class A "broad-uniform-negative both sides"; the SHORT side has real statistical excess above the fee floor.

## Concentration diagnostic (Lesson #16) — MANDATORY block

### SHORT direction, all 2064 obs, direction=-1
- **Per-sym bootstrap ci_pos: 2/14 = 14 %** (need ≥ 30 %, min 3)
  - Only FILUSDT (mean +234 bp, ci_lo +30.8) and WIFUSDT (mean +316 bp, ci_lo +69.9) individually ci-positive
  - Median alt sym has non-significant edge: BTC -0.2, BNB -1.0, XRP +21.7, ETH +23.4, BCH +14.3
- **Per-quarter t_pos ratio: 4/10 = 40 %** (need ≥ 50 %)
  - Positive: 2024Q2, 2025Q1, 2025Q4, 2026Q1
  - Strongly negative: 2024Q1 (t=-3.48), 2025Q3 (t=-2.31), 2026Q2 (t=-2.86)
- **Concentration gate: FAIL**

### LONG direction, direction=+1
- syms_ci_pos: 0/14 = 0 %
- q_pos_t: 5/10 = 50 % (marginal, tied to signal direction flip)
- Concentration gate: FAIL

## Alpha-decay Pattern P1 (era stratify)

| era | n | LONG mean_bp | LONG t | SHORT mean_bp | SHORT t |
|---|---:|---:|---:|---:|---:|
| 2024H1 | 272 | -35 | -0.5 | +19 | +0.3 |
| 2024H2 | 378 | **+101** | **+1.66** | -117 | -1.9 |
| 2025H1 | 532 | -191 | -4.7 | **+175** | **+4.3** |
| 2025H2 | 546 | -156 | -3.5 | +140 | +3.1 |
| 2026H1 | 336 | -198 | -5.1 | +182 | +4.7 |

Regime flip between 2024H2 (weakly LONG) and 2025H1+ (consistent SHORT). Not monotonic decay but a **sign flip** — the "halo" hypothesis held very weakly in 2024H2 then inverted to "attention drain" starting 2025. Consistent with 2024→2025 explosion of listing frequency (Q1 21 → Q4 46 → Q3 66) diluting the halo per event.

## Verdict rationale

Both SHORT quadrants clear the 3-gate (signal_t_excess ≥ 2, ci_lower > 0, perm_p ≤ 0.10), but:

1. **Concentration gate FAIL** — the paradigm-level SHORT edge is a fee-covered edge on 2 tail-vol alts (WIF, FIL), not a universe-wide attention-drain effect. Trading the full 14-alt cohort would deliver near-zero for the middle 12 syms and drag the aggregate down after fees.
2. **Non-persistent regime**: 2024H1/H2 opposite sign vs 2025+. Only 60% of the 30-month period supports SHORT. Live deployment would be exposed to unpredictable regime flips.
3. **Interpretability**: FIL and WIF have distinctive risk profiles (post-halving weakness, memecoin), so the "signal" is more plausibly a per-sym tail-vol reversion coincident with listing cadence than a genuine cross-sectional attention effect.

Per agent handbook (Lesson #16): CONCENTRATED_R1_PASS ⇒ halt at R-1, do NOT auto-promote. Graveyard.

## Novel-lesson candidate

**Candidate Lesson (2 dogfoods eligible if repeated)**: `cross_sectional_event_broadcast_concentration_dominates` —
When a single external event fan-outs to N heterogeneous syms and the aggregate 3-gate passes but per-sym ci-pos ratio is < 30%, the "aggregate effect" is a portfolio artifact: the aggregate integrates over-fee edge from the 2-3 highest-vol tail syms and near-zero+fee-drag from the middle syms. For paradigms where trading requires simultaneously entering the whole cohort (e.g., "all alts post-listing"), aggregate-level PASS is NOT actionable. Prescription: at R-0, require the hypothesis to specify a symbol-selection rule (top-vol only? filter by recent momentum?), not just "the universe." Rejects paradigms that lean on universe-wide signals without a per-sym gating mechanism.

This candidate should be re-examined vs prior graveyards — if a second dogfood confirms the same failure mode with 2 tail-sym drivers, promote to CONFIRMED Lesson.

## Files

- Script: `backend/scripts/research/paradigm_241_listing_attention_effect_r1.py`
- Metrics: `backend/runs/research_track/paradigm_241_listing_attention_effect/r1__metrics.json`
- Observations: `backend/runs/research_track/paradigm_241_listing_attention_effect/observations.csv`
- This graveyard doc: `backend/runs/research_track/graveyard__paradigm_241_alt_new_perp_listing_attention_effect_existing_alts_bilateral_5d.md`

## Next-step recommendation

Two derivative hypotheses worth registering as separate paradigms (NOT continuations of 241):

1. **paradigm_2xx_tail_vol_alt_short_5d_post_listing_focused**: restrict cohort to WIF+FIL-like tail-vol alts (per-sym 30d vol > universe median × 1.5) and re-run R-1. Concentration would be reframed at the tail-vol sub-cohort level.
2. **paradigm_2xx_listing_cadence_regime_short_alt_cohort_5d**: gate by rolling 30d listing count (Q1-2024 low-cadence period supports opposite direction). Regime-conditioned edge may be cleaner.

Both would need fresh R-0 registration and independent DNA novelty checks.
