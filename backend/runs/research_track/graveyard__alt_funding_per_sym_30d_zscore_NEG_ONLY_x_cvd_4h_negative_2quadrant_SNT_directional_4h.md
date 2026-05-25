# Graveyard — paradigm 140 alt_funding_per_sym_30d_zscore_NEG_ONLY_x_cvd_4h_negative_2quadrant_SNT_directional_4h

**Phase**: R-0 prescreen HALT (R-1 never dispatched)
**Verdict**: `R0_HALT_STEP4_LESSON_11_JOINT_DENSITY`
**Sub-class**: `FAIL_SAMPLE_INSUFFICIENT_PER_QUARTER_13.8_VS_CUTOFF_30`
**Date (KST)**: 2026-05-21 12:14
**Cumulative graveyard count**: 140 (was 139 paradigm per-sym z-score Lesson #40 4th dogfood R-0 halt)
**Streak**: 12-streak non-PASS (129-140)

## Hypothesis (paradigm 139 R-0 path 1 reformulation)

paradigm 139 R-0 halted on Lesson #40 sub-class C (per-sym z-score inherits raw funding
asymmetry). User-recommended **path 1**: drop B-quadrant per substrate infeasibility,
recover paradigm 22 R-5 A-only one-sided z-score, joint with CVD 4h axis.

- Axis 1 (funding per-sym 30d z-score, A-side only): z ≤ -2.0
- Axis 2 (CVD ratio 4h, A-side only): cvd ≤ -0.1
- Joint trigger A: funding_z ≤ -2.0 AND CVD ≤ -0.1 → SHORT 4h (continuation thesis)
- 2-quadrant SNT (Lesson #19 exception, paradigm 139 inheritance):
  - A_focus = joint × SHORT (primary)
  - A_mirror = joint × LONG (MR contrary)

## R-0 5-step prescreen results

| Step | Gate | Verdict | Notes |
|---|---|---|---|
| 1 | funding_z ≤ -2.0 A-side reachable ≥1.5% in ≥3/10 syms | **PASS** | **10/10 syms** 4.05%-5.60% rate (paradigm 139 STEP 1 reconfirmed) |
| 2 | substrate availability funding DB + CVD joblib | **PASS** | 10/10 funding DB ok, 10/10 CVD joblib ok |
| 3 | CVD ≤ -0.1 A-side reachable ≥2% in ≥3/10 syms | **PASS** | **5/10 syms** reachable (HBAR 4.40 / AXS 6.97 / COMP 8.34 / LDO 3.07 / ETC 4.25) **5/10 syms sub-2%** (SOL 0.71 / ETH 0.48 / LINK 1.46 / DOGE 1.52 / AVAX 1.94) |
| 4 | Joint trigger density per-quarter n ≥ 30 (Lesson #11) | **FAIL** | **Total 55 joint A triggers / per-quarter avg 13.8 << 30 cutoff** |
| 5 | funding_z vs CVD per-sym Pearson \|r\| < 0.5 | PASS | mean_abs_r=0.035 / max_abs_r=0.074 (**near-perfect independence**) |

## STEP 4 critical detail — joint rate too sparse

Per-sym joint trigger counts (funding_z ≤ -2.0 AND CVD ≤ -0.1):

| sym | n_common_4h | n_joint | rate |
|---|---|---|---|
| HBARUSDT | 4795 | 8 | 0.17% |
| AXSUSDT | 4795 | 11 | 0.23% |
| COMPUSDT | 4795 | 9 | 0.19% |
| AVAXUSDT | 4795 | 2 | 0.04% |
| SOLUSDT | 4807 | 5 | 0.10% |
| DOGEUSDT | 4795 | 3 | 0.06% |
| ETHUSDT | 4807 | 2 | 0.04% |
| LINKUSDT | 4795 | 4 | 0.08% |
| LDOUSDT | 4795 | 5 | 0.10% |
| ETCUSDT | 4795 | 6 | 0.13% |
| **TOTAL** | **47979** | **55** | **0.115%** |

**Root-cause mechanics**:
- funding_z ≤ -2.0 marginal rate ≈ **4.83%** (10-sym avg)
- CVD ≤ -0.1 marginal rate ≈ **3.31%** (10-sym avg)
- Lesson #21 corr near-zero (max_abs_r=0.074) ⇒ **multiplicative joint rate ≈ 4.83% × 3.31% ≈ 0.16%**
  - Empirical 0.115% confirms independence
- 2.4yr × 6 bars/day × 10 syms ≈ 53k candidate bars
- Joint expected: 53k × 0.16% ≈ 85 (observed 55, lower because cohort funding DB only ~365d window not full 2.4yr CVD span)
- Per 4-quarter split: 55/4 = **13.8 per cell << 30 Lesson #11 cutoff**

**Lesson #21 sub-finding paradoxical result**:
- Two-axis independence (corr ≈ 0) is normally a **positive** indicator (no axis redundancy)
- BUT extreme independence + low marginal rates ⇒ **multiplicative density collapse**
- This is **Lesson #11 + Lesson #21 sub-finding interaction**: independence too good = joint too sparse

## Lesson #44 23rd amendment xref dogfood

- **paradigm 22 funding_carry R-5 SEEDED** (HBAR/AXS/COMP): single-axis funding_z LONG MR, A-side only. paradigm 22 succeeds because it uses **single axis** (no joint sparsity penalty). Marginal rate 4-5% × 365d × 3 syms = ~150 triggers, sufficient.
- **paradigm 72 taker_volume 5m GRAVEYARD**: family Tier 4 retire. CVD ratio 4h is DNA-distinct (ratio not magnitude, 4h not 5m). paradigm 140 dropping joint and going CVD-alone 4h would re-enter paradigm 72 family.
- **paradigm 132 R-1 GRAVEYARD Lesson #21 5th dogfood**: 3-way axis stacking trap. paradigm 140 = 2-way attempt but **multiplicative sparsity** is now the binding constraint, not stacking trap. Lesson #21 6th dogfood never reached (R-0 halt precludes R-1 V1/V2/V3 measurement).
- **paradigm 138 funding raw bp R-0 HALT**: Lesson #40 sub-class C 3rd dogfood. paradigm 140 reformulation path.
- **paradigm 139 funding per-sym z R-0 HALT**: Lesson #40 4th dogfood. paradigm 140 direct path 1 attempt — STEP 1+2+3+5 PASS but STEP 4 joint density block.
- **Funding family Tier 4 retire**: 10 graveyards now (73/79*/96/97/98/99/103/132/138/139/140). paradigm 22+79 R-5 exception unchanged. paradigm 140 is 10th funding family graveyard.

## Lesson #21 sub-finding amendment candidate — "independence-density tradeoff"

**Existing Lesson #21**: 2-axis (or N-axis) joint must improve sigex over individual axes
by ≥1.2x to justify axis stacking (5th dogfood paradigm 132 confirmed).

**NEW sub-finding (paradigm 140 dogfood)**: Even WITHOUT executing the joint test, R-0 must
verify per-axis marginal rates × axis count is compatible with Lesson #11 per-cell n ≥ 30.
Specifically:
> If `marginal_rate_axis_1 × marginal_rate_axis_2 × n_candidates_per_quarter < 30`,
> R-0 halts BEFORE Lesson #11 STEP 4. Independence between axes (Lesson #21 PASS) makes
> this multiplication tight; correlation > 0.5 actually inflates joint rate (but triggers
> Lesson #21 stacking trap warning). The "ideal independence" zone (corr ≈ 0) is the
> WORST for joint sample density.

**Implications**:
- Joint paradigms with **2 low-marginal-rate axes (each < 5%)** and **independence (corr < 0.3)**
  cannot pass Lesson #11 at typical universe sizes (10-15 syms × 1-2 yr).
- Required: either (a) loosen one axis threshold, (b) expand universe to 30+ syms,
  (c) extend window to 3+ yr, (d) drop joint pretense.

## Reformulation paths for user (R-0 output)

| Path | Approach | Risk / next-step |
|---|---|---|
| **path 1 (RECOMMENDED)** | funding_z A-side ALONE × SHORT 4h (paradigm 22 mirror direction test) | Single-axis, no joint sparsity. Per-sym ~150 trigger rate. Direction-distinct from paradigm 22 R-5 (paradigm 22 = LONG MR, paradigm 140-r1 = SHORT continuation on same trigger). 4-quadrant SNT 1-sided (A_focus SHORT + A_mirror LONG, no B-side per Lesson #40). Lesson #44 paradigm 22 direction-distinct comparison. **DIRECT path** to test paradigm 22 untested direction. |
| path 2 | Loosen CVD threshold to -0.05 (~6-8% marginal) + retain funding_z ≤ -2.0 | Joint rate ~0.3% × 53k = 159 triggers, per-cell ~40 acceptable. **RISK**: CVD weakens to noise level (\|cvd\| < 0.1 often within bid-ask noise). |
| path 3 | Loosen funding_z threshold to ≤ -1.5 (~12% marginal) + retain CVD ≤ -0.1 | Joint rate ~0.4% × 53k = 212 triggers per-cell ~53. **RISK**: paradigm 22 R-5 z-score ≤ -2.0 is the validated threshold; loosening dilutes signal. |
| path 4 | Drop funding entirely, CVD 4h alone × SHORT 4h | paradigm 72 family Tier 4 retire territory. 4h aggregation breaks 5m fee floor risk **partially** (4h × CVD ratio is DNA-distinct from 5m × taker volume z). Needs separate R-0. |
| path 5 | CVD ALONE × LONG 4h (mean-reversion on extreme selling) | Different mechanism direction. CVD < -0.15 (deeper threshold) × LONG. Universe rate ~2% × 53k = ~1060 triggers, plentiful sample. **NOVEL but family-untested**. |

**Recommended next dispatch (paradigm 141 candidate)**: **path 1** (funding_z A-side ALONE × SHORT 4h, paradigm 22 mirror direction test). Direct, distinct, sample-sufficient, leverages paradigm 22 R-5 validated trigger threshold.

## Campaign state

- Cumulative graveyards: **140** (paradigm 140 R-0 STEP 4 joint density halt)
- R-5 LIVE: 10 (paradigm 127+128 unchanged)
- 12-streak non-PASS (129-140)
- R-5 yield: 10/140 = **7.14%** (down from 7.19%)
- Lesson #40 instances: **4** (109+110+138+139) — paradigm 140 STEP 1 reconfirmed A-side feasibility (path 1 worked at axis level)
- Lesson #21 sub-finding amendment **candidate** (independence-density tradeoff)
- Funding family Tier 4 graveyards: **10** (73/79*/96/97/98/99/103/132/138/139/140)
- D-Day 2026-06-03: D-13
- paradigm 127+128 Day 7 baseline: D-7 (2026-05-28)

## Decision (paradigm-architect spec compliance)

R-1 NOT DISPATCHED. R-0 STEP 4 halt at Lesson #11 sample density.

**Per spec failure protocol**:
> `R-1 expected_n_per_cell < 30 (Lesson #11) | do NOT dispatch R-1, halt and request sample-density expansion`

paradigm 140 specifically expanded the joint-axis paradigm to confirm:
1. paradigm 139 path 1 is structurally viable at axis level (STEP 1+3 both PASS)
2. BUT 2-axis joint sparsity is binding constraint at typical universe scale (STEP 4 FAIL)
3. Sub-finding: independence too good = joint too sparse (Lesson #21 sub-amendment candidate)

**Lesson #21 6th dogfood (V1/V2/V3 individual-vs-joint sigex) DEFERRED** to R-1 of a path
that survives R-0 sample density (path 1 candidate paradigm 141).
