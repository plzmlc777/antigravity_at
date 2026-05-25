# Graveyard: paradigm 134 alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h

**Date**: 2026-05-21 11:08 KST
**Verdict**: BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE (Lesson #39 sub-class A)
**Phase**: R-1
**Host**: hcp_local (paradigm-architect agent dispatch)
**Predecessor**: paradigm 133 (CONCENTRATED_R1_PASS narrow-scope FAIL) Path 4 PRIMARY RECOMMENDATION

## Hypothesis

NEW asymmetric statistic class — Patton & Sheppard (2015) realized semivariance asymmetry.

- **Step 1**: per-symbol 5m log returns r_t
- **Step 2**: 1h RV_up = Σ r_t² for r_t > 0 (positive semivariance, upside vol)
- **Step 3**: 1h RV_down = Σ r_t² for r_t < 0 (negative semivariance, downside vol)
- **Step 4**: 24h rolling RV_up_24h, RV_down_24h sums
- **Step 5**: log_ratio = log((RV_up_24h+ε)/(RV_down_24h+ε)) — symmetric around 0
- **Step 6**: per-symbol 30d rolling z-score of log_ratio
- **Trigger**: |log_ratio_z| > 2 (asymmetric vol regime)
- **Direction**: sign(log_ratio_z) carries DIRECTIONAL info (Patton-Sheppard signed decomp)
  - z > +2 → LONG (up-vol dominant → upside continuation)
  - z < -2 → SHORT (down-vol dominant → downside continuation)
- **Forward hold**: 4h
- **Debounce**: 8h
- **Universe**: 12 alts (ADA excluded Lesson #30)

**Critical theoretical claim** (rejected empirically): signed semivariance ratio naturally
encodes direction (unlike paradigm 133 vol-of-vol where magnitude/direction separated).

## R-0 prescreen results

- **Verdict**: R0_READY_FOR_R1 (PASS all gates)
- **n_triggers_total**: 1981 (z>+2 pos=973 / z<-2 neg=1008)
- **n_quarters**: 10 (2024Q1 - 2026Q2)
- **measurable_quarters pos/neg**: 9/10 and 8/10 (Lesson #11 PASS)
- **Lesson #34 z empirical**: z_min=-8.42 / z_max=6.79 / pct above +2: 2.67% / pct below -2: 3.45%
- **Lesson #40 log transform**: PASS (log of positive ratio symmetric, |z|>2 both sides reachable)
- **Lesson #46 sub-amendment sign-flip (10th dogfood — STRONG WARNING SIGNAL fired)**:
  - A_focus signs [-1, -1, +1, -1] (2 flips, mostly negative)
  - B_focus signs [-1, -1, -1, -1] (**0 flips, UNIFORMLY NEGATIVE**)
  - B_mirror n=69 gross=+66.48bp t=+2.59 — R-0 ALREADY signaled hypothesis direction inverted

## R-1 4-quadrant SNT results

| quadrant | n | gross_bp | net_bp | obs_t | null_t | sigex | ci_lower_bp | perm_p | 3gate |
|---|---|---|---|---|---|---|---|---|---|
| A_focus_z_pos_LONG_4h | 973 | **+10.25** | -5.75 | -0.83 | -2.61 | +1.78 | -19.14 | 0.043 | FALSE (excess fail) |
| A_mirror_z_pos_SHORT_4h | 973 | -10.25 | -26.25 | -3.81 | -2.37 | -1.44 | -39.50 | 0.918 | FALSE |
| B_focus_z_neg_SHORT_4h | 1008 | **+1.87** | -14.13 | -1.90 | -2.44 | +0.54 | -28.42 | 0.306 | FALSE |
| B_mirror_z_neg_LONG_4h | 1008 | -1.87 | -17.87 | -2.41 | -2.63 | +0.22 | -32.52 | 0.434 | FALSE |

**Zero passing quadrants** — broad-falsified.

## Concentration Gate (Lesson #16 STRICT 30%)

| quadrant | q_pos_t | quarter_ratio | sym_ci_pos | sym_ratio | gate_pass |
|---|---|---|---|---|---|
| A_focus_LONG | 4/9 | 0.44 (FAIL) | **0/12** | 0.00 (FAIL) | FALSE |
| A_mirror_SHORT | 1/9 | 0.11 (FAIL) | 0/12 | 0.00 (FAIL) | FALSE |
| B_focus_SHORT | 3/9 | 0.33 (FAIL) | 0/12 | 0.00 (FAIL) | FALSE |
| B_mirror_LONG | 2/9 | 0.22 (FAIL) | 0/12 | 0.00 (FAIL) | FALSE |

**0/12 syms ci_pos across ALL 4 quadrants** — universal absence of mechanism, not concentration.

### A_focus_LONG per-quarter t breakdown

| quarter | t | comment |
|---|---|---|
| 2024Q1 | -0.48 | neg |
| 2024Q2 | -0.73 | neg |
| 2024Q3 | +0.52 | weak pos |
| 2024Q4 | **-3.18** | strong neg |
| 2025Q1 | +0.35 | weak pos |
| 2025Q2 | -0.31 | neg |
| 2025Q3 | +0.31 | weak pos |
| 2025Q4 | -0.59 | neg |
| 2026Q1 | +1.90 | pos (insufficient for gate) |

5/9 quarters negative; no consistent regime where mechanism holds.

### B_focus_SHORT per-quarter t breakdown

| quarter | t | comment |
|---|---|---|
| 2024Q2 | -0.42 | neg |
| 2024Q3 | **-4.31** | very strong neg (would have been SHORT against rally) |
| 2024Q4 | -2.51 | strong neg |
| 2025Q1 | +0.34 | weak pos |
| 2025Q2 | **+2.70** | strong pos |
| 2025Q3 | -0.45 | neg |
| 2025Q4 | +1.35 | pos |
| 2026Q1 | -2.55 | strong neg |
| 2026Q2 | -0.97 | neg |

6/9 quarters negative; alternating mechanism flips.

## Verdict reasoning

**BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE** (Lesson #39 sub-class A — broad uniform negative):

1. **All 4 quadrants net negative** (no positive net per-trade edge).
2. **Both gross focus +10.25 / +1.87 bp are well under fee floor 16bp.**
   A_focus gross +10.25 vs A_mirror gross -10.25: exact-symmetric mirror (gap=20.5bp marginal,
   threshold for Lesson #53 = 20bp boundary). Mathematically the mirror MUST be -focus when
   gross fee-floor noise — no mechanism asymmetry detected.
3. **0/12 syms ci_pos universal** across all 4 quadrants = "trigger has zero directional info".
   This is NOT concentration failure (where some syms work); it is **absence of mechanism**.
4. **Patton-Sheppard signed semivariance does NOT translate** to crypto perp 4h forward
   directional alpha. Original Patton-Sheppard equity index regime cannot be ported to
   12-alt crypto perp universe.
5. **R-0 sign-flip 10th dogfood TRUE POSITIVE**: B_focus uniform negative [-1,-1,-1,-1]
   foretold R-1 B_focus 6/9 negative quarters confirmation.

## Lesson #53 candidate detection (REFINED — boundary case)

- A: focus gross +10.25 / mirror gross -10.25 → gap 20.5bp (boundary of 20bp threshold)
- B: focus gross +1.87 / mirror gross -1.87 → gap 3.7bp (clear NOT inverted)

Per Lesson #53 candidate detection logic: focus<0 AND mirror>0 AND gap>20bp = inverted.
Here focus +10.25 (NOT <0) and gap exactly at boundary 20.5bp. **NOT inverted** —
this is a fee-floor symmetric mirror, not a mechanism direction inversion.

R-0 advisory mis-fired due to small-sample stratified n=69 vs full R-1 n=1008.
R-0 B_mirror gross +66.48 was a small-n artifact; R-1 full B_mirror gross is -1.87.

## Lessons applied (32 confirmed + 5 candidates inventory)

- **Lesson #11**: PASS at R-0 (n=1981, measurable 9/10 + 8/10 quarters)
- **Lesson #16 STRICT 30% (paradigm 133 strengthening)**: **FAIL at R-1**
  (0/12 syms ci_pos universal across ALL quadrants — absence of mechanism, not concentration)
- **Lesson #19**: PASS (4-quadrant SNT in single R-1 batch)
- **Lesson #20 narrow-scope**: NOT QUALIFIED (no quadrant 4-cond PASS)
- **Lesson #21**: PASS (single trigger axis = log_ratio z, no stacking)
- **Lesson #22**: PASS (1h base + 24h rolling RV_up/RV_down + 30d z, stateless, 4h hold)
- **Lesson #23**: PASS (continuous rolling, no event anchor)
- **Lesson #28**: PASS (1m OHLCV substrate, 755-799 days)
- **Lesson #30**: PASS (data window 100%, no short-window syms)
- **Lesson #34**: PASS (empirical z + log_ratio percentiles measured pre-execution)
- **Lesson #39 sub-class A**: **CONFIRMED at R-1** — broad uniform negative (3rd confirmed
  dogfood for sub-class A after paradigm 108 + paradigm 131-class)
- **Lesson #40 log transform**: PASS (log of positive ratio → symmetric z feasible)
- **Lesson #41 narrow-scope pre-empt**: N/A (no PASS quadrants to pre-empt)
- **Lesson #44**: **17th dogfood** — full graveyard xref
  (paradigm 65/66/67/68/69/81/84/118/121/123/124/125/129/130/131/132/133 + 126/127/128 R-5)
- **Lesson #45**: PASS (explicit z-threshold on log_ratio, NOT HMM unsupervised)
- **Lesson #46 sub-amendment**: **10th dogfood — TRUE POSITIVE WARNING confirmed**.
  B_focus uniform [-1,-1,-1,-1] sign-flip 0 at R-0 stratified n=50×4q correctly
  foretold B_focus 6/9 negative quarters at R-1 full sample. A_focus 2 flips also
  correctly indicated unstable mechanism (5/9 negative quarters).
- **Lesson #52a/b**: detection negative (A_focus_LONG net-negative, NOT both LONG pos)
- **Lesson #53 candidate**: detection negative (gap A=20.5bp boundary not strictly >20bp;
  gap B=3.7bp clear NOT inverted) — REFINED understanding: 20bp threshold needs to be
  >20bp STRICT not >=20bp; fee-floor symmetric mirror is NOT direction inversion

## Family-distinct verification (Lesson #45 confirmed)

- NEW asymmetric statistic class **realized semivariance up/down ratio** novelty CONFIRMED.
- Distinct from 18 cross-referenced paradigms (65/66/67/68/69/81/84/118/121/123/124/125/129/130/131/132/133 + 126/127/128 R-5).
- HMM/unsupervised avoided. Frame-grade dense (1h base, 24h rolling, 30d z, 4h hold).
- Single trigger axis (Lesson #21). Log transform applied per Lesson #40.

## Side discovery: SIGNED SEMIVARIANCE CARRIES NO DIRECTIONAL ALPHA IN CRYPTO PERP

The Patton-Sheppard (2015) signed semivariance decomposition was developed for equity
index regimes where down-side risk is asymmetric in price (downward jumps more severe).
In crypto perp 12-alt 4h forward window:
- Up-vol dominant regimes do NOT systematically continue upward (+10.25bp gross < 16bp fee)
- Down-vol dominant regimes do NOT systematically continue downward (+1.87bp gross < 16bp fee)
- The asymmetric vol structure is INFORMATIONLESS for forward 4h direction

This empirically falsifies the Patton-Sheppard porting hypothesis for crypto perp markets.
**Mechanism explanation**: crypto perp price dynamics are dominated by funding-rate
incentives, liquidation cascades, and BTC contagion (paradigm 69 R-5 SEEDED dominant pattern)
— NOT by RV directional decomposition.

## NEW Lesson #54 candidate (1st dogfood)

**"Signed decomposition of a magnitude statistic does not synthesize directional alpha
without an independent mechanism story"** — first dogfood:

- paradigm 133 (vol-of-vol): magnitude statistic + trigger-bar sign proxy = CONCENTRATED narrow
- paradigm 134 (signed semivariance ratio): magnitude statistic with sign INSIDE the statistic
  = BROAD_FALSIFIED uniform absence

Both attempts to extract direction from 2nd-order RV failed. The Patton-Sheppard signed
decomposition adds direction to the statistic but does NOT add mechanism — the mechanism
must be supplied externally (e.g., funding regime, liquidation cascade, BTC contagion).

Candidate Lesson #54 elevates this from incidental observation to formal antipattern.
Promote to confirmed after 2nd independent dogfood (cf. Lesson #11/#16/#19/#41 promotion path).

## Continuous-parallel policy compliance

Per [feedback_paradigm_campaign_continuous_parallel] (2026-05-19) +
[Persistence over efficiency] (2026-05-21 amendment):
- dispatch continues regardless of closing rate
- "실패하고 실패하고 또 실패하더라고 계속 찾아야 해"
- Counter increment: 133 → **134** (formal paradigm 134 R-1 graveyard)
- 6-streak non-PASS (129/130/131/132/133/134)

## Counter status

- Cumulative graveyards: **133 → 134**
- R-5 seeded LIVE: 10 (unchanged)
- R-5 yield: 7.46% (10/134)
- Non-PASS streak: **6** (129/130/131/132/133/**134**)
- Lessons: **32 confirmed + 6 candidates** (Lesson #46 sub-amendment 10th dogfood TRUE POSITIVE +
  Lesson #44 17th dogfood + NEW Lesson #54 candidate 1st dogfood)

## Next-candidate recommendations

Based on paradigm 134 findings (BROAD_FALSIFIED — signed semivariance ratio
carries no directional info in crypto perp 4h):

### Path 1 (HIGHEST priority): Volatility risk premium (VRP) family
- VRP = implied vol (perp funding-implied) − realized vol
- Mechanism: divergence between expected and realized vol carries direction
  (perp funding-rate reflects market positioning; realized vol reflects actual)
- Substrate: funding_rate (DB available) + 1m OHLCV (realized vol)
- Distinct from paradigm 96/97/98/99 funding family (funding-implied vol NOT raw funding)
- Distinct from paradigm 133/134 (mixing funding-IMPLIED + realized = NOT pure RV)
- **CAUTION**: borders on Lesson #21 axis stacking (2 axes — funding + RV)
  Mitigation: VRP is a SINGLE derived statistic (subtraction), not joint conjunction
- Expected outcome: NOVEL family-distinct, no priors

### Path 2 (HIGH priority): Cross-symbol RV dispersion
- universe-aggregate RV dispersion (std of 12-alt RV at each time)
- Mechanism: when alt RVs converge (low dispersion), market in synchronized regime
  → directional info from BTC; when diverge (high dispersion), idiosyncratic
- DISTINCT from paradigm 118 (realized correlation matrix) via DISPERSION not CORRELATION
- DISTINCT from paradigm 133 (per-sym vol-of-vol) via UNIVERSE-AGGREGATE
- **CAUTION**: universe-aggregate per [universe-aggregate advisory caution]
- **NOT RECOMMENDED** — universe-aggregate scalar family has 3 broad-falsified

### Path 3 (MEDIUM priority): Multi-day RV persistence (long-horizon vol regime)
- 7d rolling RV z-score > +2 (long-horizon vol expansion)
- 4h forward hold under BTC up-trend filter
- DISTINCT from paradigm 69 R-5 (BTC RV close-to-close vs per-sym 7d expansion)
- CAUTION: Lesson #21 axis stacking (vol regime + BTC trend) — paradigm 132 trap fresh
- **NOT RECOMMENDED** — Lesson #21 trap

### Path 4 (HIGH priority): Funding-rate-implied directional bias (NOT raw funding)
- funding_rate × OI joint persistent regime (3d window) → directional info
- DISTINCT from paradigm 73/79/96/97/98/99 funding family (joint with OI persistence)
- CAUTION: Funding family Tier 4 retired — funding × OI joint already paradigm 132 (axis stack FAIL)
- **NOT RECOMMENDED** — family retired + axis stacking

### Path 5 (MEDIUM priority): Trade flow microstructure (Lesson #45-compliant)
- 5m taker buy ratio z-score > +2 (extreme buyer aggression)
- 4h forward hold
- DISTINCT from paradigm 72 (60m taker buy vol — different frame, different metric)
- CAUTION: Taker-side aggressive volume family Tier 4 retired (paradigm 23/60/72)
- **NOT RECOMMENDED** — family retired

**PRIMARY RECOMMENDATION**: **Path 1 (Volatility Risk Premium / VRP family)** —
NOVEL family entry, distinct from RV family and funding family individually, single
derived statistic (subtraction = SINGLE axis NOT stacking conjunction), mechanism story
robust (funding-implied vol carries market expectation, realized vol carries actual; divergence
is information signal). Cost ~45min implementation (need funding-IMPLIED vol calculation).

## Artifacts

- R-0 script: `/home/hcpark/antigravity/backend/scripts/research/paradigm134_r0_prescreen.py`
- R-1 script: `/home/hcpark/antigravity/backend/scripts/research/paradigm134_r1.py`
- R-0 metrics: `/home/hcpark/antigravity/backend/runs/research_track/alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h/r0_prescreen.json`
- R-1 metrics: `/home/hcpark/antigravity/backend/runs/research_track/alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h/r1__metrics.json`
- Graveyard report: this file
