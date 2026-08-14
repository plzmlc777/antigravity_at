# Graveyard — paradigm 229 alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h

**Date (KST)**: 2026-07-17
**Phase halted**: R-1 (Lesson #37 full sweep)
**Verdict**: `BROAD_FALSIFIED_LESSON_39_SUB_CLASS_A_MIRROR_SYMMETRIC_MID_CAP_UNIVERSE_FIX_INSUFFICIENT`
**Predecessor comparison**: paradigm 228 (cap-mixed universe, 30d z-score) → CONCENTRATED_R1_PASS but NARROW_SCOPE_LIFE_CHANGING_FAIL

---

## Hypothesis under test

Per-symbol OI-value share of universe total (fraction = sym_OI / sum_all_OI), 7-day rolling change in that fraction, 90d rolling percentile rank of that 7d change. Bilateral 4-quadrant SNT:

- A_focus: pct_rank > p95 & bar_up → LONG (concentration surge continuation)
- A_mirror: pct_rank > p95 & bar_up → SHORT
- B_focus: pct_rank < p05 & bar_dn → SHORT (concentration exit continuation)
- B_mirror: pct_rank < p05 & bar_dn → LONG

**Design fix intent vs paradigm 228**:
1. pct_rank (bounded [0,1]) replaces z-score — solves Lesson #40 structural threshold concern
2. Mid-cap only universe (HBAR/LINK/AVAX/DOGE/NEAR) — no ETH/SOL/BTC mega-cap normalization noise
3. 7d change captures faster capital rotation than 30d z

---

## R-0 prescreen — PASS

| Item | Lesson | Result |
|---|---|---|
| 1 | #61 slug grep | PASS — no `oi_share_rank_pct` in INDEX or graveyard |
| 2 | #28 substrate audit | PASS — 5 mid-cap syms with ≥799 days OI + kline coverage |
| 3 | #11 sample density | PASS — 27-52 hits/sym/side at p95/p05 (>30) |
| 4 | #62 DNA 5-dim strict | PASS — pct_rank statistic ≠ z-score (228), decoupling (127/128), velocity (196) |
| 5 | #56 family proxy | PASS — cross_sym_fraction_pct_rank_class NEW |
| 6 | Alpha decay P1 | Era-stratify planned |
| 7 | #40 structural threshold | PASS — pct_rank bounded [0,1] |
| 8 | Concentration pre | 5-sym universe → need 2 CI-pos (30% of 5) |
| 9 | Life-changing pre | Flagged — 27-52 hits/yr/sym × 5 syms × 24h hold |

---

## R-1 execution — Lesson #37 full hold × threshold sweep

**Cells tested**: 7 configurations
- p95_h1 (baseline)
- p90_h1, p90_h2
- p97_h1
- p95_h2, p95_h3
- p98_h1

**Trigger density (baseline p95/p05)**:
- HBAR n_days=776, hi_hits=52 (6.7%), lo_hits=35 (4.5%)
- LINK n_days=777, hi=36 (4.6%), lo=44 (5.7%)
- AVAX n_days=777, hi=48 (6.2%), lo=45 (5.8%)
- DOGE n_days=777, hi=51 (6.6%), lo=27 (3.5%)
- NEAR n_days=704, hi=43 (6.1%), lo=39 (5.5%)

Empirical density = 4.5–6.7%, matching the design target (5%). No Lesson #11 sparsity issue.

**Aggregate result across all 7 cells × 5 syms × 4 quadrants = 140 sym×quadrant×cell tests**:

- **three_gate PASS count: 0 / 140**
- **concentration_gate PASS count: 1 / 28 quadrant-cell** (p95_h3 B_focus only)

### Best cell: p95_h3 B_focus (short-side, hold=3d)

| sym | n | mean_bp | signal_t_excess | ci_lower_bp | perm_p_below | 3gate |
|---|---|---|---|---|---|---|
| HBAR | 17 | -190.5 | -0.84 | -640.6 | 0.242 | FAIL |
| LINK | 21 | 29.0 | 0.21 | -231.4 | 0.588 | FAIL |
| AVAX | 15 | 341.4 | **1.87** | **26.4** | 0.950 | FAIL (perm_p) |
| DOGE | 14 | 242.3 | 1.01 | -231.0 | 0.840 | FAIL |
| NEAR | 15 | 229.6 | **1.77** | **2.4** | 0.946 | FAIL (perm_p) |

Concentration: n_ci_pos=2/5 (40%), quarter_pos_t_ratio_avg=0.67 → concentration_gate PASS.

BUT: AVAX and NEAR both have signal_t_excess < 2.0 (fail Gate #1) AND perm_p ≈ 0.95 (fail Gate #3, meaning the null distribution is dominated by fee-drift shorts of similar magnitude — cannot distinguish observation from generic bearish drift).

### Best cell: p95_h1 A_focus (long-side, hold=1d)

HBAR n=24 mean=567.6bp obs_t=2.06 signal_t_excess=1.74 ci_lower=-26.9bp perm_p=0.036. Fails ci_lower (marginally) and signal_t_excess (marginally). Concentration n_ci_pos=0/5 → concentration_gate FAIL.

---

## Lesson #39 sub-class analysis — CONFIRMED SUB-CLASS A

The bilateral quadrant results across every cell show near-perfect fee-symmetric mirroring:

| Cell | Quadrant | HBAR mean_bp | LINK mean_bp | AVAX mean_bp | DOGE mean_bp | NEAR mean_bp |
|---|---|---|---|---|---|---|
| p95_h1 | A_focus | +567.6 | -178.9 | +47.2 | +86.8 | +33.0 |
| p95_h1 | A_mirror | -583.6 | +162.9 | -63.2 | -102.8 | -49.0 |
| **Sum** | | -16.0 | -16.0 | -16.0 | -16.0 | -16.0 |

Sum = -16bp = -2 × fee (8bp round-trip × 2 sides). This is the Lesson #39 signature: **A_focus and A_mirror are exact-symmetric within fee, meaning the bar-direction filter carries ZERO directional information beyond a coin-flip on the trigger day**. The pct_rank trigger identifies "unusual OI-share change day" but does not predict same-direction price continuation.

Same pattern applies to B_focus / B_mirror pairs. Bilateral pct_rank triggering on mid-cap OI-share fails to synthesize a directional axis.

---

## Root-cause verdict

The paradigm 228 failure (cap-normalization noise) fix by mid-cap restriction was successful — **all 5 syms had adequate individual trigger density and OI signal quality**. However, the deeper issue revealed:

**The 7d change in per-sym OI-share fraction of a mid-cap universe does not carry directional predictive information about next-day-to-3-day price movement**. Bar-direction filter fails to select a subset of triggers with directional bias. The pct_rank statistic on OI-share change is a symmetric noise variable at the mid-cap layer.

This differs from paradigm 228 where the z-score triggered on 3 syms (HBAR/AVAX/NEAR B_focus) with real (fee-limited) short-side edge — the paradigm 229 pct_rank version LOSES that fragment of edge because the rolling percentile normalization discards the raw magnitude of composition shift.

**Interpretation**: paradigm 228 sub-class B (partial info mixed direction on 3/7 syms) is present in raw z-space but destroyed by percentile-rank normalization. Percentile normalization is a strictly weaker feature transform for share-composition signals.

---

## Lessons dogfooded / candidates

- **Lesson #37** (full hold × threshold sweep) — 7 cells × 4 quadrants × 5 syms verdict scan MANDATORY, primary-only inspection insufficient. **7th confirmed dogfood.**
- **Lesson #39 sub-class A** (broad-uniform-negative fee-symmetric mirror) — **8th confirmed dogfood** — pct_rank of cross-sym OI-share does not synthesize directional axis
- **Lesson #40** (structural threshold feasibility) — pct_rank correctly PASSES this gate (bounded), which was the intended fix from 228. Confirms Lesson #40 is a NECESSARY but not SUFFICIENT check
- **Lesson candidate (NEW)**: `pct_rank_normalization_destroys_partial_info_signals` — when a raw-magnitude z-score version shows partial-info concentration (228's HBAR/AVAX/NEAR B_focus), replacing z with rolling percentile rank destroys that edge because rank compression discards magnitude of the underlying shift. Reformulation prescription for future paradigms: **do NOT substitute pct_rank for z-score if the raw z version shows Lesson #74 partial-info; instead try log-ratio, or shift-magnitude-conditional filter.**
- **Lesson #74** (paradigm 228 NARROW_SCOPE_LIFE_CHANGING_FAIL) — NOT applicable here since paradigm 229 does not even reach concentration gate PASS on any life-changing-eligible cell

---

## Artifacts

- R-1 script: `backend/scripts/research/paradigm_229_oi_share_rank_pct_mid_cap_r1.py`
- R-1 metrics (7 cells):
  - `r1_baseline_p95_h1__metrics.json` (primary)
  - `r1_p90_h1__metrics.json`
  - `r1_p90_h2__metrics.json`
  - `r1_p95_h2__metrics.json`
  - `r1_p95_h3__metrics.json` (best concentration cell)
  - `r1_p97_h1__metrics.json`
  - `r1_p98_h1__metrics.json`
- All under: `backend/runs/research_track/paradigm_229_alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h/`

## Next paradigm recommendation

Do NOT revive OI-share-fraction family with mid-cap universe. Two potential paths forward if this family is revisited:

1. **Magnitude-conditioning fix**: raw share-change magnitude filter (e.g., only trigger if |share_change_7d| > 0.5% absolute), not percentile-normalized
2. **Cross-family combination**: pair OI-share z-score (228 style) with a second independent signal (funding rate direction, or premium spread) to add axis synthesis missing in single-signal bar-direction filter

Alternatively — abandon OI-share family entirely for one full paradigm cycle to allow lesson library to mature. Recommend routing to non-substrate alternatives for paradigm 230+.
