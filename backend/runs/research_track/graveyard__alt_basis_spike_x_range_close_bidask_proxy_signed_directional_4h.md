# Graveyard — paradigm 131 `alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h`

**Killed at**: 2026-05-21 09:56:37 KST · **Phase**: R-1 PoC · **Host**: hcp_local
**Verdict**: `BROAD_FALSIFIED_LESSON_52A_LONG_DRIFT_ARTIFACT`
**Paradigm counter**: 130 → **131** (continuous-parallel 3-streak non-PASS)

## Hypothesis

Dual-axis LIQUIDITY-STRESS conjunction at 4h frame:
- **Axis 1**: mark-index basis pct rolling-30d z-score, |basis_z| > 1.5 (perp dislocation)
- **Axis 2**: (high-low)/close 4h rolling-30d z-score, range_close_z > +1.5 (bid-ask spread proxy widening)
- **Joint trigger**: BOTH axes extreme in same 4h bar (liquidity stress confluence)
- **Direction**: MEAN-REVERSION via sign(basis_z) — paradigm 111 continuation broad-falsified, MR direction tested
- **Forward hold**: 4h directional
- **Debounce**: 8h
- **Universe**: 6 alts (SOL/HBAR/AVAX/DOGE/ETH/LINK) × 12 months 2025-05..2026-04 (paradigm 111 markPrice cache reuse)

## Why graveyard — three independent killing signals

### Signal #1 — All 4 quadrants FAIL 3-gate AND Concentration Gate

| Quadrant | n | gross_bp | net_bp | sigex | ci_lower | perm_p_above | gate3 | gate_conc |
|---|---|---|---|---|---|---|---|---|
| A_focus pos × SHORT_MR | 118 | **-15.41** | -23.41 | -0.60 | -50.77 | 0.730 | FAIL | FAIL |
| A_mirror pos × LONG | 118 | **+15.41** | +7.41 | +1.01 | -35.21 | 0.168 | FAIL | FAIL |
| B_focus neg × LONG_MR | 91 | +8.18 | +0.18 | +0.59 | -31.37 | 0.271 | FAIL | FAIL |
| B_mirror neg × SHORT | 91 | -8.18 | -16.18 | -0.30 | -59.73 | 0.641 | FAIL | FAIL |

**0/4 quadrants pass 3-gate. 0/6 syms ci_pos in ALL 4 quadrants (universal universe-wide low-power).**

### Signal #2 — Lesson #21 axis stacking trap CONFIRMED (4th dogfood)

INDIVIDUAL-vs-JOINT sigex comparison (sequential dispatch in single R-1 batch per agent skill):

| Trigger | n | gross_bp | sigex |
|---|---|---|---|
| **Joint A_focus** (basis>+1.5 AND range>+1.5) × SHORT | 118 | -15.41 | **-0.60** |
| Individual basis_only (basis>+1.5) × SHORT | 658 | +0.76 | -0.17 |
| **Joint B_focus** (basis<-1.5 AND range>+1.5) × LONG | 91 | +8.18 | **+0.59** |
| Individual basis_only (basis<-1.5) × LONG | 623 | +1.13 | +0.55 |
| Individual range_close_only (range>+1.5) × LONG | 703 | -4.42 | +0.14 |

- Joint A_focus sigex (-0.60) **WORSE** than individual basis_only (-0.17) by **delta -0.43**
- Joint B_focus sigex (+0.59) **essentially equal** to individual basis_only (+0.55) by delta +0.04
- → **axis_stacking_trap_detected = TRUE**

The range_close axis adds NOISE not signal. Conjunction reduces n 5.6x (658→118) without sigex gain.

**Lesson #21 dogfood lineage** (axis stacking does not synthesize alpha):
- paradigm 83 oi_5m_latent_regime — 1st (multi-feature k-means latent)
- paradigm 122 dual-anchor × OI velocity — 2nd
- paradigm 124 realized kurtosis confluence — 3rd
- **paradigm 131 basis × range_close conjunction — 4th**

### Signal #3 — Lesson #52a universe LONG drift artifact 2nd EXPLICIT dogfood

Detection rule fires (paradigm 99/129 precedent):
- A_mirror_LONG gross +15.41 (positive)
- B_focus_LONG gross +8.18 (positive)
- Both LONG quadrants ci_lower deeply negative (-35.21, -31.37)
- 0/6 syms ci_pos in BOTH LONG quadrants (no per-pair mechanism)

→ `is_long_drift_artifact_52a = TRUE`

The 6-alt universe over 2025-05..2026-04 exhibits unconditional bull-market drift.
Any LONG-direction trade subset on any filter gains +8-15bp gross regardless of
trigger mechanism. SHORT direction symmetrically loses. The apparent "alpha" is
NOT mechanism — it is universe-wide drift artifact.

**Lesson #52a dogfood lineage**:
- paradigm 99 funding per-sym velocity — 1st (implicit, retrospectively re-classified)
- paradigm 129 alt_parkinson_range — 1st EXPLICIT dogfood
- **paradigm 131 basis × range_close — 2nd EXPLICIT dogfood**

**Lesson #52a CONFIRMED-eligible** (promotion target at next §6 update).

## Mechanism failure analysis — 4 sub-causes

1. **paradigm 111 single-axis basis already broad-falsified** (2026-05-20): A_focus pLOW LONG gross -0.37bp essentially zero alpha. paradigm 131 attempted rescue via range_close conjunction — failed.

2. **range_close is direction-blind by construction** (non-negative aggregate, Lesson #40 acknowledged upper-tail only). Combining direction-blind volatility magnitude with signed basis-z does NOT synthesize directional alpha.

3. **Sample density loss 5.6x without sigex gain**: 658 (basis-only) → 118 (joint). Axis conjunction discards 82% of basis-only events without compensating signal density.

4. **Bull-drift universe-wide bias dominates** the conditional sample. A_mirror_LONG and A_focus_SHORT are mathematical mirrors of each other (same data, opposite sign). ci_lower<0 in BOTH directions confirms no real mechanism — only universe drift.

## R-0 prescreen analysis (Lesson #11 borderline)

- Total triggers n=209 (A_pos_basis=118, B_neg_basis=91)
- Per-quarter measurable (≥30): A 1/5 quarters, B 1/5 quarters
- R-0 verdict: `R0_HALT_INSUFFICIENT_DENSITY` (Lesson #11 strict floor failed)
- **Dispatched anyway with caveat** for decisive Lesson #21 + Lesson #52 measurement
- Quadrant aggregate n=118 + 91 sufficient for axis comparison + dual artifact detection
- Per-quarter Concentration measurement carries low-power caveat (only 3 quarters ≥10 trades per quadrant)

**Sub-amendment Lesson #46 sub-amendment 6th dogfood**: R-0 stratified n=137 estimate showed A_focus -29.79bp / B_focus +19.68bp with sign-flip=2 [A=1,-1,-1,1 / B=-1,1,1,-1] (high instability). Full R-1 broad-falsified all 4 quadrants confirmed sign-flip prediction.

## Lessons applied / dogfooded at R-1

| Lesson | Status | Note |
|---|---|---|
| #11 | R-0 halt + R-1 dispatched with caveat | 1/5 quarter measurable per quadrant |
| #16 | 0/6 sym ci_pos ALL 4 quadrants | 4-quadrant universal zero concentration |
| #19 | SNT 4-quadrant single batch | PASS |
| **#21** | **4th dogfood CONFIRMED** | joint sigex ≤ individual axis sigex (axis stacking trap) |
| #28 | substrate 6/6 paradigm 111 cache reuse | PASS |
| #30 | 12mo / 12mo full window = 1.0 | PASS |
| #34 | basis_z + range_close_z empirical percentiles measured | basis_z p99=2.69 p01=-2.37 / range_close_z p99=3.58 |
| #40 | axis 2 upper-tail-only acknowledged (range_close non-negative) | PASS |
| #44 | 13th xref dogfood (10 paradigm xrefs + RUNBOOK) | PASS |
| #45 | explicit empirical z-thresholds (no HMM) | PASS |
| #46 | REFINEMENT 6th dogfood + sub-amendment 6th | R-0 stratified weak signal → R-1 broad-falsified confirmed |
| **#52a** | **2nd EXPLICIT dogfood → CONFIRMED-eligible** | universe LONG drift artifact (A_mirror_LONG + B_focus_LONG both gross>0) |

## Liquidity-microstructure family advisory caution status

| paradigm | mechanism | status |
|---|---|---|
| 105 (~111 impl) | mark-index basis percentile single-axis | GRAVEYARD |
| 121 | HMM realized-vol state × markPrice basis filter | GRAVEYARD (Lesson #45 confirmed) |
| **131** | **basis_z × range_close_z joint conjunction MR** | **GRAVEYARD (this)** |

**3 liquidity-microstructure single-domain graveyards across 3 distinct sub-mechanisms**. Advisory caution — NOT yet Tier 4 retire. Need 1-2 more distinct sub-mechanism fails to confirm family-wide retire.

Distinguishing factor: paradigm 22 (premium_index_zscore R-5 SEEDED 3x DOGE/SOL/LDO) and paradigm 24 (funding_carry R-5 SEEDED HBAR/AXS/COMP) ARE liquidity-microstructure successful exceptions. The retire candidate is "high-frequency 4h-frame conjunction" sub-class, not the broader family.

## Continuous-parallel campaign status post-131

| Metric | Pre-131 | Post-131 |
|---|---|---|
| Cumulative graveyards | 130 | **131** |
| R-5 seeded | 10 LIVE (paradigm 127+128 Mint deploy 2026-05-21) | 10 (unchanged) |
| Family retire formal | 8 | 8 (unchanged) |
| Family retire CANDIDATE | 4 | 4 (unchanged) |
| Advisory caution | 2 + 1 escalated | 2 + 1 escalated (liquidity-microstructure family caution maintained) |
| Lessons confirmed | 31 | **31 + Lesson #52 split formalization recommended (52a CONFIRMED-eligible)** |
| Lesson candidates | 5 | 5 (#21 4th dogfood reinforced — already confirmed) |
| continuous-parallel streak | 2-streak non-PASS | **3-streak non-PASS** |
| D-Day | D-13 | D-13 |
| Day 7 baseline | D-7 (paradigm 127+128 Mint) | D-7 |

**3-streak axis pivot threshold reached** — paradigm 129 (range estimator) + 130 (correlation breakdown) + 131 (basis × range_close conjunction).

## Next-paradigm recommendation

**PIVOT AWAY** definitively from:
- Cross-asset correlation/beta/lead-lag family (paradigm 75/81/118/130 — 4 graveyards advisory escalated)
- Per-symbol range/RV/quarticity intrinsic moment family (paradigm 129)
- **Liquidity-microstructure single-domain 4h-frame conjunction** (paradigm 105/111/121/131 — 3 graveyards, advisory caution)
- Magnitude-only or magnitude+magnitude conjunction (Lesson #21 4 dogfoods)
- Conditional-overextension event detection on bull-drift universe (Lesson #52a 2 dogfoods)

**Recommended next-paradigm pivots** (axis-family distinct):

### Path 1 — Event-anchored funding boundary refinement
`funding_boundary_x_oi_direction_x_magnitude_triple_confirm` — boundary-restricted slice of paradigm 22 R-5 family. funding sign × OI direction × |funding| magnitude triple-conjunction at 8h funding boundary. Distinct via event-anchoring + 3-way confirm (NOT single-direction conjunction). Substrate: DB funding (full backfill) + microstructure OI (joblib).

### Path 2 — Cross-venue ARBITRAGE refinement
`cross_exchange_oi_divergence_x_funding_spread_alt` — paradigm 103 cross-exchange spread caution-class extension to OI divergence axis. Bybit V5 substrate already verified 7 deep-syms. Distinct via cross-venue mechanism (not single-venue conjunction). Substrate: Bybit V5 OI API + Binance OI joblib.

### Path 3 — Lifecycle-event refinement (DEFERRED)
`lifecycle_listing_day_forced_buyer_window_short_post_pump` — paradigm 87 entry-side mechanism refinement specific window (e.g., listing day +60min to +240min). Requires lifecycle live mode (2026-05-29+).

### Path 0 (META RECOMMENDED) — INVENTORY HALT
3-streak non-PASS threshold reached + Lesson #52a CONFIRMED-eligible + Lesson #21 4th dogfood reinforced + paradigm 127+128 Day 7 baseline imminent (2026-05-28).

**Recommended user decision point**: paradigm-architect halt for 1-2 days until Day 7 baseline (2026-05-28) and Day 30 D-Day (2026-06-03) to:
1. Validate paradigm 127+128 live performance (avoid wasted dispatches if R-5 paradigms underperform)
2. Conduct meta-review of axis-family closing rate (130 graveyards / 10 R-5 = 7.7% R-5 yield)
3. Formal Lesson #52 split (52a CONFIRMED + 52b candidate at 1 INVERSE dogfood)
4. Liquidity-microstructure family-distinct verification audit

## Artifacts

- `backend/scripts/research/paradigm131_r0_prescreen.py`
- `backend/scripts/research/paradigm131_r1.py`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/r0_prescreen.json`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/r1__metrics.json`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/gate_eval__r1.md`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/sym_4h_panel.joblib`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/trig_panel.joblib`

## One-liner summary

paradigm 131 (basis × range_close joint conjunction MR @ 4h, 6 alts × 12mo) BROAD_FALSIFIED via 3 independent signals: (1) 0/4 quadrants pass 3-gate + 0/6 sym ci_pos universal, (2) Lesson #21 axis stacking trap CONFIRMED 4th dogfood (joint sigex -0.60 worse than individual basis-only -0.17 in A_focus), (3) Lesson #52a universe LONG drift artifact 2nd EXPLICIT dogfood (A_mirror_LONG +15.41 + B_focus_LONG +8.18 both gross>0 + 0/6 sym ci_pos) → **Lesson #52a CONFIRMED-eligible promotion target**. Continuous-parallel 3-streak non-PASS threshold reached (129+130+131). Liquidity-microstructure single-domain advisory caution maintained (105/111/121/131 = 3 sub-mechanism graveyards).
