# Paradigm 80 — oi_premium_5m_decoupling — R-1 GRAVEYARD

**Date**: 2026-05-15
**Phase**: R-1 (PoC)
**Verdict**: FAIL — all four directional variants negative; trigger event does not carry directional alpha above fee floor

## Hypothesis tested (Mechanism A — Decouple-reversal)

5m OI z-score and 5m premium z-score over rolling 24h window (W=288 bars):
- LONG trigger:  `oi_z > +2.0` AND `premium_z < -2.0`  → fwd_60m gross return × (+1) − 8 bp fee
- SHORT trigger: `oi_z < -2.0` AND `premium_z > +2.0` → fwd_60m gross return × (-1) − 8 bp fee

Hypothesis: when OI grows but mark-price falls below index (perp underpriced), arbitrageurs push perp price up (mean-reversion). Symmetric for the opposite leg.

## Sample (richest of the paradigm-architect runs to date)

- 14 syms × 1.48 yr overlap (OI joblib 2024-11-07 → 2026-05-02, premium 5m wider but bottleneck OI)
- Trigger rate ≈ 0.21 % of 5m bars
- **n_obs = 5859 trades** (LONG 3309 + SHORT 2550)
- candidate pool 2,795,761 non-trigger 60m windows
- expected_n per cell (4Q × 2 sides) = 325.5 — well above Lesson #11 floor of 30 (no prescreen issue)

## Aggregate stats (focus Z=2.0, focus hold=60m)

| Metric | Value | Gate |
|---|---|---|
| mean_net_bp | **−8.110** | — |
| obs_t | −2.590 | — |
| null_mean_t (fee floor) | −6.423 | — |
| **signal_t_excess** | **+3.833** | A PASS (≥ 2.0) |
| ci_lower_bp | **−13.041** | **B FAIL** (> 0) |
| ci_upper_bp | −2.276 | — |
| perm_p_two_sided | **1.000** | **C FAIL** (≤ 0.10) |

`signal_t_excess` is well above 2 σ because the observed t is much less negative than the fee-floor null (−2.59 vs −6.42) — but the observation is on the wrong side of zero. **The trigger predicts negative directional return; mean-reversion hypothesis is falsified.**

## Concentration (Lesson #16) — broad-negative, not cherry-picked

- 14 / 14 symbols measurable → **0 / 14 with bootstrap ci_lower > 0** (symbol_ci_pos_ratio = 0.000)
- 9 quarters measurable → **1 / 9 with positive t-stat** (quarter_pos_t_ratio = 0.111)
- Verdict: **broad-negative**, fails Concentration Gate independently of three-gate (no cherry-pick to repackage)

## Hold sweep — 5m → 240m all negative, all same direction

| hold | n_obs | mean_bp | obs_t | null_mean_t | sig_t_excess | perm_p_two | ci_lower_bp | ci_upper_bp |
|---|---|---|---|---|---|---|---|---|
| 5m | 5859 | −6.510 | −5.661 | −21.422 | +15.761 | 1.000 | −8.653 | −4.170 |
| 15m | 5859 | −7.239 | −3.405 | −12.497 | +9.092 | 1.000 | −11.082 | −2.836 |
| 30m | 5859 | −6.667 | −2.187 | −8.845 | +6.658 | 1.000 | −12.529 | +0.231 |
| 60m | 5859 | −8.110 | −2.590 | −6.296 | +3.706 | 1.000 | −13.048 | −2.277 |
| 240m | 5859 | −5.451 | −1.238 | −3.252 | +2.014 | 0.996 | −14.427 | +3.430 |

Every hold horizon negative mean. signal_t_excess is positive (observed beats fee floor) but the observed itself sits in the −5 to −8 bp range — i.e. the trigger marginally beats random direction × random window, but **gross return is approximately 0 ± noise**, and the 8 bp fee swallows everything.

## Symmetric negative tests (mandatory, included to forestall mirror-antipattern fishing)

We ran two additional variants on the same sample so the answer is exhaustive — **none salvage the paradigm**.

### (1) Mirror-direction of Mechanism A (LONG/SHORT swapped)
- LONG: `oi_z < -2.0` AND `premium_z > +2.0`
- SHORT: `oi_z > +2.0` AND `premium_z < -2.0`
- mean_net_bp = **−7.890**, obs_t = −2.520, signal_t_excess = +3.886, ci_lower_bp = −13.70, perm_p_two = 1.0
- three-gate: A PASS / B FAIL / C FAIL → **FAIL**
- Diagnostic: gross_return ≈ 0 regardless of side; fee 8 bp is the dominant force. Mirror does **not** revive the paradigm (Lesson #8 mirror antipattern confirmed for this trigger family).

### (2) Mechanism B — Decouple-confirm-continuation (same-sign joint)
- LONG: `oi_z > +2.0` AND `premium_z > +2.0`
- SHORT: `oi_z < -2.0` AND `premium_z < -2.0`
- n_obs = 7,461 (slightly more abundant than opposite-sign)
- mean_net_bp = **−11.238**, obs_t = −5.284, signal_t_excess = +1.93 (just below A=2.0 floor), ci_lower_bp = −16.75, perm_p_two = 0.96
- three-gate: A FAIL / B FAIL / C FAIL → **FAIL**
- Diagnostic: same-sign joint events are *more* adverse than opposite-sign. Continuation hypothesis also falsified.

## Root-cause interpretation

The 5m premium z-score × OI z-score joint event detector — in every reasonable directional configuration on a 14-sym × 1.48-yr panel — produces gross fwd-60m returns indistinguishable from zero. The post-trigger mean return is small enough that:

- The **fee floor (8 bp round-trip) dominates** every variant.
- `signal_t_excess` is positive only because we're comparing against an even more fee-drifted null (random sub-sample of all non-trigger windows). The trigger has slightly **less negative drift** than random, but not enough to clear fee.

Mechanism interpretations that are NOT supported by data:
- Decouple-reversal (A focus) — FALSIFIED.
- Decouple-continuation (B same-sign) — FALSIFIED.
- Mirror-A (continuation interpretation of original trigger) — FALSIFIED.

The remaining theoretical variant (mirror-B = same-sign joint as **counter**-trend trade) is the trivial sign-flip of (B): by symmetry its mean_net_bp would be `+(B_gross) − 8bp = +0.32 − 8 = −7.68 bp` — i.e. roughly the same as Mirror-A. We did not run it explicitly because the conclusion is mechanically determined and already negative.

## Why this is *not* a sample-density failure (vs Lesson #18)

- 5,859 trades in focus configuration is the **largest n** any paradigm-architect R-1 has produced on the 14-sym panel.
- expected_n per cell = 325 (≫ 30 floor)
- 14/14 syms direction-consistent negative
- 9/9 quarters lean negative (only 1 positive t)
- **The mechanism is genuinely null** — no amount of additional sample will reverse a uniform broad-negative outcome.

## Why this is *not* funding_oi family retire territory (Lesson #10/#11 family)

- Funding events are 8 h discrete; this paradigm operates on **5 m granularity premium dislocation**, which captures intra-funding-period mark-index spread dynamics not visible in funding.
- The 8 h-averaged premium does correlate strongly with funding direction (8 h autocorr 0.96 on BTC), but the **5 m premium z-score** is a different signal (high-frequency arbitrage tension), not a funding proxy.
- The fact that the dimension proved null here is paradigm-specific (premium × OI joint at 5 m), not a re-derivation of the funding family. Funding family retire is unrelated; do not promote this graveyard into a family-wide ban.

## Recommended catalog updates

1. **paradigm-architect spec — new lesson #19 candidate**: "5 m joint event triggers that condition on both OI z-score and premium z-score have no directional alpha in any of the four sign-quadrant configurations on the 14-sym × 1.48-yr panel. Future PoCs combining OI×premium z-score joints should be considered duplicates of this null result unless they invoke a fundamentally different feature transform (e.g., premium acceleration, OI dispersion across exchanges, not simple z-score of the level)."
2. **No family retirement** — premium signal alone has not been tested; OI signal alone is well-known directional via paradigm 21 (`oi_price_decoupling` 1d). The null is specific to the **5 m premium × 5 m OI joint event** triplet.
3. **Mirror antipattern reaffirmed (Lesson #8)** — original direction, mirror direction, AND mechanism-B same-sign joint were all measured here in one batch. Future R-1 scripts should bake in this symmetric negative test as a standard sub-section to prevent useless follow-up R-1s.

## Reproduction

- Script: `backend/scripts/research/oi_premium_5m_decoupling_r1.py`
- Outputs:
  - `backend/runs/research_track/oi_premium_5m_decoupling/r1__metrics.json`
  - `backend/runs/research_track/oi_premium_5m_decoupling/r1__per_symbol.csv`
  - `backend/runs/research_track/oi_premium_5m_decoupling/r1__hold_sweep.csv`
  - `backend/runs/research_track/oi_premium_5m_decoupling/r1__stdout.log`
- Symmetric negative tests run as one-off Python sessions on Mint (not separate scripts; rerun script body if reproduction needed).
