# Graveyard — Paradigm 235 `alt_realized_semivariance_updown_asymmetry_ratio_30d_rolling_z_bilateral_4h`

- **Verdict**: `R0_HALT_DNA_DUPLICATE_PRIOR_GRAVEYARD`
- **Phase halted**: R-0 (before R-1 dispatch)
- **Date**: 2026-07-24 04:04 KST
- **Dispatch mode**: SELF-RECOMMEND (paradigm-dispatch-daily cron)
- **Paradigm counter**: 235
- **Wall clock**: ~4 seconds (Lesson #61 grep hit + Lesson #62 DNA table)

## Hypothesis

Per-symbol 4h realized semivariance asymmetry:
`log_sdr(t) = log(downside_semidev(t) / upside_semidev(t))` over 30d rolling window; 90d rolling z-score; 4-quadrant SNT bilateral (A: z>=+T × DOWN, B: z<=-T × UP + mirrors); T ∈ {1.5, 2.0}; hold 4h primary + 8h/24h sweep; 14-alt cohort.

## R-0 Prescreen Results (9-item checklist)

| Item | Lesson | Status | Note |
|---|---|---|---|
| 1 | #61 slug grep | **HIT** | 2 prior paradigms in semivariance family (134 R-1 graveyard, 199 R-0 halt) |
| 2 | #28 substrate audit | PARTIAL_MISMATCH | Claimed `ohlcv_cache_12col/*_4h.joblib` does not exist; actual is `ohlcv_cache/*_1m.joblib` (resample required). Informational — not the halt reason. HBAR not in cache. |
| 3 | #11 sample density | SKIPPED | halt upstream |
| 4 | #62 DNA strict table | **FAIL** | 5/6 dim overlap with paradigm 134 |
| 5 | #56 family proxy | SAME_FAMILY | realized semivariance asymmetry (Patton-Sheppard 2015 signed decomposition family) — Lesson #54 candidate blocker |
| 6 | #74 alpha decay P1 | SKIPPED | halt upstream |
| 7 | #40 structural threshold | SKIPPED | halt upstream |
| 8 | #16 concentration pre-estimate | HISTORICAL_FAIL | paradigm 134 = 0/12 syms ci_pos UNIVERSAL across ALL 4 quadrants |
| 9 | #79 predictive content pretest | SKIPPED | halt upstream |

## DNA Overlap Strict Table (Lesson #62)

Predecessor: **paradigm 134** `alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h` (graveyard 2026-05-21, `BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE`).

| Dim | Predecessor (paradigm 134) | Proposed (paradigm 235) | Match |
|---|---|---|---|
| statistic_class | `log(RV_up/RV_down)` realized semivariance asymmetry ratio z | `log(downside_semidev/upside_semidev)` semivariance asymmetry ratio z | **IDENTICAL** (log(A/B) = −log(B/A); sign flip absorbed by 4-quadrant SNT) |
| decomposition | positive/negative return variance decomposition | positive/negative return variance decomposition | **IDENTICAL** |
| direction | 4-quadrant SNT bilateral, sign-conditional | 4-quadrant SNT bilateral, sign × bar_direction | **IDENTICAL** |
| trigger | `|z|>=2` spike, 30d rolling z | `|z|>=1.5 or 2.0` spike, 30d rolling z over 90d baseline | **IDENTICAL** (threshold sweep is intra-cell variation, not structural) |
| hold | 4h primary | 4h primary + 8h/24h sweep | **IDENTICAL** (4h primary matches) |
| universe | 12 alts (BTC/ETH/SOL/XRP/DOGE/AVAX/BNB/LINK/LTC/BCH/FIL/NEAR) | 14 alts (12 shared + WIF + HBAR) | PARTIAL (12/14 = 86% overlap) |

**DNA overlap score**: **5/6** → paradigm-architect halt rule triggered ("Halt on DNA duplicate (5/6 dim overlap)").

## Verdict Rationale

### 1. Statistic sign-invariance under 4-quadrant SNT

The user's Item 4 in the R-0 spec claims "statistic_class: NO — different transform" because paradigm 235 uses `log(D/U)` while paradigm 134 used `log(U/D)`. This is mathematically wrong:

- `log(D/U) = −log(U/D)`
- The 4-quadrant SNT design (Lesson #19) tests both `z >= +T` AND `z <= −T` triggers
- A sign flip of the underlying statistic swaps A↔B quadrants but does not change the total test surface
- Therefore paradigm 235 tests the **exact same 4 quadrants** as paradigm 134

### 2. Universal absence of mechanism precludes universe expansion recovery

Paradigm 134's failure signature was `0/12 syms ci_pos UNIVERSAL across ALL 4 quadrants` — this is the **absence of mechanism** pattern (NEW Lesson #54 candidate 1st dogfood at paradigm 134 graveyard), not concentration failure. When 0/12 syms exhibit any directional edge across all 4 quadrants, adding 2 syms (WIF/HBAR) cannot flip the null result. Expected outcome: ~0-2/14 syms ci_pos at best, far below the 0.30 (~4/14) concentration gate.

This is exactly the same rebuttal that halted paradigm 199 (proposed 20-sym universe expansion) on 2026-05-22.

### 3. "Slower-moving window" rescue attempt is orthogonal to failure mode

The user's rationale ("30d window may be more stable across eras than 1st-order return z-scores") assumes paradigm 134 failed due to **era instability** (Pattern P1 alpha decay). It did not. Paradigm 134 failed due to **cross-sectional universal absence** — no sym in any era exhibited a positive edge. A slower window smooths a null signal into another null signal.

### 4. Family-level Lesson #54 blocker

Lesson #54 (candidate emerging from paradigm 134, now with 2 dogfoods incl. paradigm 135 VRP): "Signed decomposition of a magnitude statistic does NOT synthesize directional alpha without an independent mechanism story." Paradigm 235's hypothesis provides no new mechanism story — the "mean-revert after sustained downside/upside vol" framing is the same reversal narrative paradigm 134 attempted.

## Lessons Dogfooded

- **Lesson #61 (slug grep first)**: HIT at Item 1. Family predecessor identified in <1s.
- **Lesson #62 (DNA 5/6 strict table)**: 5/6 overlap confirmed. Halt rule triggered as designed.
- **Lesson #44 (family-proxy cross-reference)**: 19th xref dogfood SUCCESS — collision detected pre-dispatch (following paradigm 135 = 18th).
- **Lesson #54 (candidate — signed decomposition without mechanism story)**: 3rd dogfood (after paradigm 134 = 1st, paradigm 199 = 2nd via reflection). Elevated to formal CONFIRMED eligibility (3 dogfoods accumulated).
- **Lesson #19 (4-quadrant SNT sign absorption)**: user's Item 4 "different transform" claim rebutted via sign-flip absorption in 4-quadrant design.
- **Lesson #28 (substrate availability)**: PARTIAL_MISMATCH flagged (informational) — hypothesis specified non-existent `ohlcv_cache_12col/` path; actual cache is `ohlcv_cache/*_1m.joblib`. HBAR not available in cache. Would have required R-0 substrate remap even absent DNA issue.
- **Lesson #16 (concentration gate as absence-of-mechanism detector)**: precedent from paradigm 134 (0/12 universal) applied to reject paradigm 235 pre-dispatch.

## Lesson Candidate Emitted (new)

**Candidate Lesson**: *Sign inversion of a symmetric ratio statistic under 4-quadrant SNT is NOT a novel statistic class.*

When a hypothesis proposes `log(A/B)` where the predecessor used `log(B/A)`, and the direction test is 4-quadrant SNT (bilateral sign), the two hypotheses test the identical surface. The DNA overlap table must count this as `statistic_class: IDENTICAL`, not "different transform". First dogfood: paradigm 235.

## Recommendation

Proceed to next hypothesis in queue. Do NOT retry any semivariance-asymmetry ratio variant with:
- Different log base (log2 vs ln — trivial rescale)
- Difference form (`sdev_dn − sdev_up` — same information content under z-score normalization)
- Threshold tweaks (|z|>=1.0, 2.5, 3.0 — intra-cell variation)
- Window tweaks (7d, 14d, 60d — smoothing degree, not mechanism)
- Universe expansions (20-sym, 30-sym — universal absence is scale-invariant)

Any of these will DNA-collide with paradigm 134/199/235.

**Genuinely fresh substrate suggestions for the family** (independent mechanism story required):
- **Options-market IV skew** (25d put IV − 25d call IV) as a cross-substrate proxy — different data source, different mechanism story
- **Realized higher moments beyond 2nd-order** — skewness/kurtosis rolling z (paradigm 124 partial precedent but different statistic)
- **Cross-symbol semivariance dispersion** (variance of per-sym semivariance ratios across universe) — 2nd-order cross-sectional, not per-sym directional

## Files

- Prescreen JSON: `backend/runs/research_track/paradigm_235_alt_realized_semivariance_updown_asymmetry_ratio_30d_rolling_z_bilateral_4h/r0_prescreen.json`
- Graveyard MD: `backend/runs/research_track/graveyard__paradigm_235_alt_realized_semivariance_updown_asymmetry_ratio_30d_rolling_z_bilateral_4h.md`
- INDEX.json entry: key `paradigm_235_alt_realized_semivariance_updown_asymmetry_ratio_30d_rolling_z_bilateral_4h` (added via jq)
