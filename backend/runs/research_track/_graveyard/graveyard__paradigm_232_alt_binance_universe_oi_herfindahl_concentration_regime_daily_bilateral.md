# Graveyard: Paradigm 232 — Universe OI Herfindahl Concentration Regime Daily Bilateral

**Verdict**: `CONCENTRATED_R1_PARTIAL_PASS_LESSON_39_SUB_CLASS_A_MIRROR_ASYMMETRIC_INFO_LOW_REGIME_LONG_ONLY_CI_LOWER_FAIL`

**Phase**: R-1
**Date**: 2026-07-21 KST
**DNA**: universe-scalar HHI = Σ(OI_share_i²) over 55 Binance USDT-M perps → 90d rolling percentile-rank → HIGH (pct_rank≥0.70) vs LOW (pct_rank≤0.30) bilateral regime × 14-alt equal-weight cohort forward return
**Novelty claim**: both trigger axes non-OHLCV (HHI level + regime membership), escapes Lesson #77 corollary that graveyarded paradigm 231

## R-0 Prescreen (All PASS)

- Slug grep: NONE (no prior HHI/Herfindahl paradigm)
- DNA 5-dim distinct: 5/5 vs paradigms 228 (per-sym OI-share z), 229 (per-sym pct-rank), 127/128 (per-sym OI-price decoupling), 196 (per-sym OI velocity)
- Substrate: 55 syms with full OI cache coverage 2024-11-07 to 2026-05-01 (541 days) + 14 alt OHLCV joblib 2024-01-02 to 2026-05-12
- Sample density: HIGH regime = 314 days × 14 syms = 4396 obs, LOW regime = 213 days × 14 syms = 2982 obs (far above 30-per-cell threshold)
- Both trigger axes non-OHLCV: HHI level (non-OHLCV) + regime membership (non-OHLCV) — Lesson #77 corollary compliance PASS

## R-1 Full Sweep (Lesson #37) — 4 pct × 3 hold × 4 quadrants = 48 cells

**HHI universe**: 55 syms, hhi_raw range [0.1283, 0.3287] mean=0.2673

| Cell | Quadrant | n | mean_bp | sigex | ci_lo | perm_p | 3gate | conc |
|------|----------|---|---------|-------|-------|--------|-------|------|
| pct=0.65 h=1 | B_focus_LOW_LONG | 3374 | +17.54 | +2.25 | -18.37 | 0.000 | F | F (0/14) |
| pct=0.65 h=5 | A_focus_HIGH_SHORT | 4858 | -17.01 | +2.36 | -111.95 | 0.998 | F | F |
| pct=0.65 h=5 | B_focus_LOW_LONG | 3374 | +53.08 | +1.77 | -23.22 | 0.010 | F | F (4/14) |
| **pct=0.70 h=5** | **B_focus_LOW_LONG** | 2982 | **+68.81** | **+2.81** | **-14.75** | **0.000** | **F** | **T (5/14, q_pos_t=0.83)** |
| **pct=0.75 h=5** | **B_focus_LOW_LONG** | 2744 | **+71.09** | **+2.81** | **-12.57** | **0.000** | **F** | **T (5/14, q_pos_t=0.83)** |
| (44 other cells) | ... | ... | ... | <2 or CI fail | | | F | F |

**Aggregate**:
- 0/48 cells achieve full three-gate PASS (all fail on ci_lower_bp<0)
- 2/48 cells achieve concentration-gate PASS (both B_focus_LOW_LONG at h=5d)
- 4 cells with sigex≥2.0

## Lesson #39 Perfect Fee-Symmetric Mirror Signature (12/12 sweep cells)

**Every single cell shows exact perfect mirror**:
- A_focus + A_mirror = -16.00 bp = -2 × 8bp fee = -2 × FEE_BPS
- B_focus + B_mirror = -16.00 bp = -2 × 8bp fee = -2 × FEE_BPS

**This is textbook Lesson #39 sub-class A**: the trigger has zero directional information; the joint signal is pure fee drag + direction bet on baseline cohort drift.

However, this paradigm is a special sub-case of sub-class A: **asymmetric across regime**.
- HIGH regime: A_focus (-70bp) + A_mirror (+54bp) — SHORT loses, LONG gains, but weak signal (sigex 0.7)
- LOW regime: B_focus (+68bp) + B_mirror (-84bp) — LONG gains, SHORT loses, strong signal (sigex 2.81)

## Baseline Drift Diagnosis

- **All-days baseline 14-alt cohort 5d gross**: -8.39 bp (mildly bearish 2024-11 to 2026-05)
- **All-days LONG net (after fee)**: -16.39 bp per 5d
- **LOW regime B_focus_LOW_LONG net**: +68.81 bp per 5d
- **DELTA (LOW - baseline)**: **+85.20 bp**

The LOW-HHI regime DOES have real predictive information for LONG on 14-alt cohort (+85bp above baseline). But:

## Fatal Structural Issues

1. **Lesson #39 sub-class A signature** on all 4 quadrants across all 12 sweep cells (12/12 = 100%). The trigger encodes no independent direction; only regime-membership matters, not the up/down axis.
2. **ci_lower_bp<0** in best cell (-14.75bp at pct=0.70 h=5d): block-bootstrap confidence interval on per-sym-day observations includes zero → the +68bp mean is not statistically distinguishable from zero at 95% CI given per-sym variance.
3. **Only 5/14 syms ci_pos** in the concentration-passing cells: 9/14 syms don't show statistically robust positive edge → the signal is concentrated in a subset (likely SOL/AVAX/LINK/DOGE/NEAR class).
4. **Asymmetric regime**: HIGH regime shows no reliable signal (all 4 HIGH cells sigex<2 or ci_lower_bp very negative). So the paradigm is really a LOW-regime LONG filter, not the bilateral crowding hypothesis originally proposed.

## Lesson #77 Corollary Compliance — VERIFIED but INSUFFICIENT

The paradigm successfully escaped paradigm 231's launchpool trap (bar-direction axis → sub-class A). BOTH trigger axes are non-OHLCV as hypothesized. Yet Lesson #39 sub-class A signature STILL appeared, because the second axis (regime membership HIGH vs LOW) doesn't actually mask the underlying fact that "regime" and "direction" are conceptually orthogonal — the perfect mirror = -2×fee proves the direction axis is uninformative independent of regime axis.

**Lesson #77 corollary compliance is NECESSARY but NOT SUFFICIENT**: non-OHLCV direction axes can still be uninformative if the signal is purely regime-based (LOW-HHI period alt bull continuation) rather than crowding-driven asymmetric.

## New Lesson Candidate (paradigm 232 dogfood)

**Lesson candidate #78 (self-nomination, 1st dogfood)**: **REGIME-MEMBERSHIP TRIGGER × DIRECTION MIRROR CHECK IS INSUFFICIENT FALSIFIER FOR REGIME-ONLY SIGNALS**. When a bilateral 4-quadrant SNT reveals asymmetric mirror pattern (one regime shows sub-class A perfect fee-symmetric mirror, the other regime shows real DELTA-vs-baseline in one direction only), the paradigm should be reformulated as **unilateral regime-conditional LONG-only continuation strategy** (drop the SHORT hypothesis, drop the HIGH regime hypothesis) rather than treated as bilateral trigger.

**Reformulation attempt (deferred to future paradigm)**: strict "LOW-HHI regime × LONG alt cohort × 5d hold" trigger. Would require:
- R-1 unilateral: verify B_focus_LOW_LONG replicates with narrower ci_lower_bp target
- Independent falsification: is LOW-HHI = "post-crash reset period" surrogate? If yes, this is a hidden regression on macro cycle, not a novel structural feature.
- Cross-quarter stability: q_pos_t=0.83 (5/6 quarters positive) is good — but 2024-11 to 2026-05 window is short (18 months = 6 quarters).

## Metrics Files

- `backend/runs/research_track/paradigm_232_alt_binance_universe_oi_herfindahl_concentration_regime_daily_bilateral/r1_pct*.json` (12 sweep cell metrics)
- `backend/scripts/research/paradigm_232_universe_oi_hhi_r1.py` (R-1 PoC code)

## Decision

**R-1 GRAVEYARD**: paradigm 232 fails three-gate on all 48 sweep cells despite achieving concentration-gate PASS in 2 cells. Lesson #39 sub-class A signature confirms trigger has no bilateral information. Reformulation as unilateral LOW-regime LONG-only continuation strategy is candidate for future paradigm (233+) but requires independent hypothesis substrate check to rule out hidden macro-cycle regression before dispatch.

**Path forward** (informational for lesson_prescreen_checklist.md):
- Lesson candidate #78 promoted to 1st-dogfood observation
- Composite ban: "universe-scalar OI HHI regime × bilateral direction" — do not re-attempt bilateral formulation; must be unilateral LONG-only if re-attempted (would still risk hidden macro-cycle regression via LOW-HHI = post-crash reset window)
