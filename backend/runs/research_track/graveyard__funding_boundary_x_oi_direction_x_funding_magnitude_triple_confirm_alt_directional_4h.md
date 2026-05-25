# Graveyard: paradigm 132 — funding_boundary_x_oi_direction_x_funding_magnitude_triple_confirm_alt_directional_4h

**Date**: 2026-05-21 10:20 KST
**Counter**: 131 → 132 (continuous-parallel policy, 4-streak non-PASS reached)
**Phase killed**: R-1 PoC 4-quadrant SNT + Lesson #21 INDIVIDUAL-vs-JOINT decisive + Lesson #44 funding family Tier 4 retire reconciliation
**Verdict**: `BROAD_FALSIFIED_LESSON_21_5TH_DOGFOOD_AXIS_STACKING_TRAP`
**Host**: hcp_local
**Substrate**: funding_rate DB (365d, 13 alts intersection) + microstructure OI 5m joblib (2.2yr) + ohlcv 1m (DB resampled 4h)

## Hypothesis recap

3-way axis stacking + paradigm 22 family-slice EXEMPTION CLAIM:
- Axis 1 (event anchor): 8h funding boundary (00/08/16 UTC)
- Axis 2 (OI direction binary): prior 8h cumulative OI declining (long unwind in progress)
- Axis 3 (funding magnitude): |funding_rate| > rolling-30d p70 percentile
- Trigger fire: all 3 conditions
- Direction (user-stated "squeeze LONG bias" hypothesis): funding>0+OI_decline → LONG / funding<0+OI_decline → SHORT
- Forward hold: 4h directional, 8h debounce, 16bp round-trip fee
- Universe: 13 alts (8h-cycle funding canonical + OI 5m substrate intersection)

## R-0 prescreen results

- Per-symbol n_funding intersection: 1005-1090 events × 13 alts = 13914 total funding boundaries
- Triggers post-debounce: **n=1176** (A_long=370, B_short=806)
- Lesson #11 per-quarter measurable: A 4/4 + B 4/4 (n≥30 ALL cells PASS — full sample density)
- Lesson #46 stratified 4-quarter sign-flip:
  - A_long_MR: per-q gross_bp [+7.9, -14.5, -34.1, -20.4] flips=1 (Q3 positive only, then 3 quarters negative — direction inverted in 2025Q4+)
  - B_short_MR: per-q gross_bp [-20.8, -19.2, -18.8, +14.0] flips=1 (3 quarters short-direction failing, Q2 inverted)
- Lesson #30 funding window ratio: 365d / 730d hypothesized = 0.50 PASS
- Lesson #34 empirical funding |rate| p70 per-sym verified
- Lesson #40 percentile rank PASS (signed funding sign + |rate| p70)

## R-1 4-quadrant SNT (Lesson #19)

| Quadrant | n | gross_bp | net_bp | obs_t | sigex | ci_lower_bp | perm_p_above | gate3 | gate_conc |
|---|---|---|---|---|---|---|---|---|---|
| **A_focus pos × LONG (hypothesis)** | 370 | **-19.56** | -27.56 | -3.38 | -2.55 | -40.84 | 0.995 | FAIL | FAIL |
| A_mirror pos × SHORT | 370 | **+19.56** | +11.56 | +1.42 | **+2.09** | -2.05 | 0.016 | FAIL (ci) | FAIL |
| **B_focus neg × SHORT (hypothesis)** | 806 | **-15.69** | -23.69 | -3.02 | -2.05 | -36.91 | 0.979 | FAIL | FAIL |
| B_mirror neg × LONG | 806 | **+15.69** | +7.69 | +0.98 | **+2.20** | -5.31 | 0.012 | FAIL (ci) | FAIL |

**0/4 quadrants pass 3-gate. Mirror quadrants nearly pass (sigex 2.09+2.20 perm_p 0.016+0.012) but ci_lower<0 due to high variance.**

### Critical mirror finding: paradigm 22 MR direction CONFIRMED

The mirror quadrants (A_mirror_pos_short / B_mirror_neg_long) succeed gross (+19.56 / +15.69) while the focus quadrants (paradigm 132's hypothesized direction) fail symmetrically. This means:
- **funding>0 + OI decline + magnitude extreme → market goes DOWN (SHORT wins)**
- **funding<0 + OI decline + magnitude extreme → market goes UP (LONG wins)**

This is the **OPPOSITE** of paradigm 132's "squeeze LONG bias" hypothesis but EXACTLY the **paradigm 22 family MR direction** (z>+ENTRY_Z → SHORT, z<-ENTRY_Z → LONG). The squeeze logic ("long unwind in progress → snap-back UP") is empirically INVERTED at the 4h horizon. The actual mechanism is **continuation of MR direction** (funding-positive coincides with continued price decline in the next 4h, not snap-back).

## Lesson #21 5th DOGFOOD — INDIVIDUAL-vs-JOINT decisive measurement

| Variant | n | gross_bp | sigex | perm_p | ci_lower_bp |
|---|---|---|---|---|---|
| V1 anchor_only (every 8h boundary) | 13913 | -6.54 | nan* | nan* | -17.43 |
| V2 magnitude_only (|funding|>p70) | 2541 | -10.64 | -1.81 | 0.977 | -26.08 |
| V3 oi_direction_only (OI decline) | 7331 | -4.92 | nan* | nan* | -16.76 |
| V4 anchor+magnitude | 2541 | -10.64 | -1.81 | 0.977 | -26.08 |
| V5 anchor+oi_direction | 7331 | -4.92 | nan* | nan* | -16.76 |
| **V6 TRIPLE_JOINT (hypothesis)** | **1176** | **-16.91** | **-2.64** | **0.998** | **-34.23** |

*NaN sigex for V1/V3/V5 because `n_obs > n_pool * 2 cap` (fee_aware_perm_test early-return when pool insufficient). Pool size = 13914 boundary 4h fwd returns; V1 n=13913 ≈ pool, V3/V5 n=7331 ratio ~1.9x < 2x.

**axis_stacking_trap DETECTED = TRUE**:
- V6 sigex (-2.64) **WORSE** than MAX measurable individual (V2/V4 = -1.81) by delta -0.83
- V6 gross_bp (-16.91) **WORSE** than V4 (-10.64), V5 (-4.92), V3 (-4.92), V1 (-6.54)
- The 3-way conjunction REDUCES sample 11.8x (13913 → 1176) AND degrades gross by -10.4bp vs anchor-only
- **3-way axis stacking adds NOISE not signal** — paradigm 132 user hypothesis falsified
- All variants directionally negative under the hypothesis direction (LONG on positive funding) — direction is INVERTED at 4h horizon

**Lesson #21 5th dogfood CONFIRMED CONFIRMED CONFIRMED** lineage:
- 1st: paradigm 83 oi_5m_latent_regime k-means k=4 (2026-05-15)
- 2nd: paradigm 122 dual-anchor × OI velocity (2026-05-20)
- 3rd: paradigm 124 realized kurtosis confluence (2026-05-20)
- 4th: paradigm 131 basis × range_close (2026-05-21)
- **5th: paradigm 132 funding × OI × magnitude triple (this)** — 4th explicit consecutive Q3 dogfood

## Lesson #44 amendment 14th xref — funding family Tier 4 retire reconciliation

Pre-dispatch concern (R-0 explicitly flagged): paradigm 132 claimed "paradigm 22 R-5 family-slice exemption" from funding family Tier 4 retire (paradigm 73+79+96+97+98+99 = 6 sub-class graveyards). The exemption was contingent on `V6 sigex > paradigm 22 R-1 baseline (proxy=1.5) × 1.2 = 1.8 AND 3-gate PASS`.

**Result**: V6 sigex = -2.64 << 1.8 threshold. **Exemption NOT EARNED.** paradigm 132 is correctly classified as a NEW funding-family sub-variant for which Tier 4 retire fully applies. The mechanism (event-anchored 4h directional triple-confirm) is structurally distinct from paradigm 22 (continuous 15-day funding-z MR), and the joint-trigger directional hypothesis fails BOTH directions decisively.

**Funding family Tier 4 retire strengthening**: paradigm 73+79+96+97+98+99 + **132** = **7 sub-class graveyards**. The "squeeze logic at funding boundary" sub-mechanism is now formally tested and broad-falsified. paradigm 22 R-5 SEEDED continuous-MR remains the unique exception within the funding family.

## Lesson #52 a/b dual detection

- **52a universe LONG drift artifact**: FALSE — A_focus_LONG and B_mirror_LONG both NEGATIVE (-19.56 / +15.69 — note B_mirror positive due to direction-inversion not drift). Cannot trigger 52a because A_focus_LONG is decisively negative.
- **52b SHORT-bias INVERSE**: FALSE — but the SHORT mirror gross +19.56bp does show direction-inversion. The actual pattern is **DIRECTION-INVERTED FROM HYPOTHESIS + paradigm 22 MR direction confirmed** — closer to a NEW Lesson #53 candidate: "joint-trigger hypothesis direction-inverted vs single-axis family direction".

**New finding documented for potential Lesson #53 candidate**:
**Joint-trigger hypothesis falsified mirror-confirms family direction.** When a multi-axis paradigm hypothesizes a NEW directional mechanism (e.g. "squeeze LONG bias") but the SNT mirror reveals the ESTABLISHED family direction (paradigm 22 MR) wins, the new mechanism is not a useful refinement — it's a direction-inverted formulation of an already-known signal. This is distinct from Lesson #21 (joint vs individual) and Lesson #52a/b (universe drift). Need 1-2 more dogfoods before candidate promotion.

## Mechanism failure analysis — 4 sub-causes

1. **Direction inversion** (primary): paradigm 132's "squeeze LONG on positive funding" hypothesis is empirically opposite of paradigm 22 family MR direction at 4h horizon. The "long unwind" framing predicts snap-back, but the data shows continuation of price weakness when funding+OI+magnitude all extreme together.
2. **Axis stacking trap** (secondary): V6 joint sigex strictly worse than V2/V4 anchor+magnitude individual. Adding OI direction axis to the funding+magnitude pair degrades signal by -0.83 sigex.
3. **Funding family Tier 4 retire applies**: paradigm 132's joint sub-variant joins the 7th funding family graveyard. Exemption attempt via paradigm 22 family-slice claim fails on baseline-improvement criterion.
4. **365d data window limit (Lesson #30)**: funding DB caps R-1 window at 365d, limiting per-quarter sample to 4 quarters (2025Q3-2026Q2). Despite n=1176 total triggers (sufficient by Lesson #11), no quarter-to-quarter consistency in direction (per-q sign flips reveal regime instability).

## Funding family Tier 4 retire status update

| paradigm | mechanism | status |
|---|---|---|
| 22 (funding_carry) | rolling z-score MR 15-day hold | R-5 SEEDED (unique exception) |
| 73 (funding_oi_bipolar) | funding × OI joint detection | GRAVEYARD |
| 79 (funding_dispersion broad) | cross-sym dispersion broad | GRAVEYARD |
| 96 (funding sign flip) | sign-flip event | GRAVEYARD |
| 97 (funding term cs dispersion) | cross-sym velocity dispersion | GRAVEYARD |
| 98 (funding regime stratify) | regime stratification | GRAVEYARD |
| 99 (funding velocity per-sym) | per-sym velocity | GRAVEYARD |
| **132 (funding boundary × OI dir × mag triple)** | **3-way confirmation joint** | **GRAVEYARD (this)** |

**8 sub-class graveyards + 1 R-5 exception** — funding axis variation space sub-mechanism saturation increasingly definitive. paradigm 22 continuous-MR remains unique successful path.

## Lessons applied / dogfooded at R-1

| Lesson | Status |
|---|---|
| #11 | R-0 PASS (4/4 + 4/4 measurable) |
| #16 | 0/13 sym ci_pos ALL 4 quadrants (universal zero concentration) |
| #19 | SNT 4-quadrant single batch |
| #21 | **5th dogfood CONFIRMED-eligible** (joint << individual sigex, axis stacking trap) |
| #28 | substrate 13/13 funding + 13/13 OI 5m intersection PASS |
| #30 | funding 365d/730d = 0.50 PASS (capped) |
| #34 | funding |rate| p70 per-sym empirical PASS |
| #39 | SNT 4-quadrant manual sub-class detection |
| #40 | percentile rank + binary OI direction PASS |
| #41 | edge-first measurement (all variants fee-floor failed) |
| #44 | **14th xref dogfood + funding family Tier 4 retire reconciliation EXPLICIT** |
| #45 | explicit empirical thresholds (no HMM) |
| #46 | REFINEMENT 7th + sub-amendment 7th (R-0 stratified n=50x4q + sign-flip) |
| #52a | FALSE (direction-inverted mirror, not universe drift) |
| #52b | FALSE (no SHORT-side asymmetry, mirror exact ±19.56/±15.69) |

## Continuous-parallel campaign status post-132

- Cumulative graveyards: 131 → **132**
- R-5 seeded: 10 LIVE (paradigm 127+128 Mint deploy unchanged)
- Family retire formal: 8 + funding family **strengthened to 7 sub-class graveyards (was 6)**
- Family retire CANDIDATE: 4 (unchanged)
- Advisory caution: 2 + 1 (liquidity-microstructure unchanged)
- Lessons: 31 confirmed + 5 candidates + **Lesson #21 5th dogfood reinforced (already confirmed)** + Lesson #44 14th xref + Lesson #53 candidate "joint hypothesis direction-inverted mirror-confirms family" 1st implicit dogfood
- continuous-parallel **4-streak non-PASS** (129+130+131+132) — axis pivot threshold strengthened
- D-Day 2026-06-03 D-13 / paradigm 127+128 Day 7 baseline 2026-05-28 D-7
- R-5 yield: 7.6% (10/132) — closing rate continued decline

## Next-paradigm recommendation

**FUNDING AXIS DEFINITIVELY EXHAUSTED for joint variants.** paradigm 22 continuous-MR is the unique surviving funding-family mechanism after 8 sub-class graveyards (73/79/96/97/98/99/132 + paradigm 80 oi_premium also joint-funding-adjacent). Any future funding-related candidate must be:
1. Cross-domain (e.g. funding × NON-funding-derived axis like volume burst, listing event) — even then Lesson #21 axis stacking trap risk applies
2. Continuous (NOT event-anchored) — paradigm 22 lineage only
3. Mean-reversion direction (paradigm 22 family direction) — squeeze-inversion hypotheses falsified

**Lesson #44 amendment evolution candidate**: 14 dogfoods now include explicit family-Tier-4-retire reconciliation pre-dispatch. Recommend formal amendment: "paradigm claiming family-slice exemption from Tier 4 retire MUST pass R-1 with sigex >= 1.5x baseline + 3-gate ALL PASS + Concentration Gate PASS. Mirror-direction wins do NOT count as exemption-earning."

**Recommended next path**: **PIVOT to user decision** — 4-streak non-PASS warrants user re-evaluation:
- Path 0: inventory halt until D-Day 2026-06-03 (paper pool comprehensive review, 13 days)
- Path 1: pivot to **volume burst family** mid-cap untouched sub-variants (paradigm 127/128 lineage)
- Path 2: pivot to **listing event family** Tier 4 retired but with NEW substrate (e.g. delisting first-2h)
- Path 3: dispatch substrate-unblocked candidate (DART KR equity new sub-mechanism, paradigm 92/93 family retire requires new direction)
- Path 4: substrate-extension dispatch (paid feed gates / forward WS recorder accrual)

**META observation**: 4 consecutive Q3 candidates (129/130/131/132) all triggered Lesson #21 axis stacking trap or Lesson #52a long-drift artifact. The 4h directional joint-trigger paradigm space is **structurally saturated**. Single-axis high-frequency burst paradigms (127/128) remain the only paradigm class producing R-4 PASS in Q3 to date.

## Artifacts

- R-0 prescreen: `backend/runs/research_track/funding_boundary_x_oi_direction_x_funding_magnitude_triple_confirm_alt_directional_4h/r0_prescreen.json`
- R-1 metrics: `backend/runs/research_track/funding_boundary_x_oi_direction_x_funding_magnitude_triple_confirm_alt_directional_4h/r1__metrics.json`
- Scripts: `backend/scripts/research/paradigm132_r0_prescreen.py` + `paradigm132_r1.py`
- Cached panels: `sym_panel.joblib` (reusable for funding family follow-ups) + `trig_panel.joblib`
- Graveyard report: this file
