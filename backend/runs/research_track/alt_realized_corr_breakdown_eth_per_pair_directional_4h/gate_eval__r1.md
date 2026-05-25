# R-1 Gate Eval — paradigm 130 alt_realized_corr_breakdown_eth_per_pair_directional_4h

**Date**: 2026-05-21 09:42 KST
**Verdict**: `BROAD_FALSIFIED_A_FOCUS_NEGATIVE`
**Sub-class**: A pair both negative + Lesson #52 amendment candidate (SHORT-side gross-positive inversion)

## Three-gate per quadrant

| Quadrant | sigex ≥ 2.0 | ci_lower > 0 | perm_p ≤ 0.10 | 3-gate |
|---|---|---|---|---|
| A_focus pos×LONG | ✗ (-0.84) | ✗ (-37.51bp) | ✗ (0.808) | FAIL |
| A_mirror pos×SHORT | ✗ (+1.54) | ✗ (-20.45bp) | ✓ (0.059) | FAIL |
| B_focus neg×SHORT | ✓ (+3.08) | ✗ (-12.84bp) | ✓ (0.000) | FAIL |
| B_mirror neg×LONG | ✗ (-1.46) | ✗ (-50.61bp) | ✗ (0.939) | FAIL |

**B_focus and A_mirror both SHORT — gross positive but ci negative + 0/11 syms ci_pos = artifact.**

## Concentration Gate (Lesson #16)

| Quadrant | q_pos_t_ratio ≥ 0.5 | sym_ci_pos_ratio ≥ 0.30 | n_syms_ci_pos ≥ 3 | gate |
|---|---|---|---|---|
| A_focus_LONG | ✗ (0.11) | ✗ (0.00) | ✗ (0) | FAIL |
| A_mirror_SHORT | ✓ (0.56) | ✗ (0.00) | ✗ (0) | FAIL |
| B_focus_SHORT | ✓ (0.56) | ✗ (0.00) | ✗ (0) | FAIL |
| B_mirror_LONG | ✗ (0.00) | ✗ (0.00) | ✗ (0) | FAIL |

## Lesson #52 detection (3rd dogfood with INVERSE pattern)

- `is_long_drift_artifact = False` (original definition: both LONG gross > 0)
- Inverse: **both LONG gross < 0 AND both SHORT gross > 0**
- 0/11 sym ci_pos in EVERY quadrant
- → NEW sub-class E candidate: trigger-conditional SHORT-bias artifact (conditional-overextension trigger)
- → Lesson #52 should likely split: 52a (unconditional bull-drift) + 52b (conditional-overextension SHORT-bias)

## Lesson #46 REFINEMENT 5th dogfood

- R-0 stratified A_focus +31.73bp t=1.06 (sign flips=1)
- Full R-1 A_focus -8.77bp gross — stratified estimate misleading positive
- 2024Q1 +113bp bull market regime artifact dominated stratified weighting
- Sub-amendment: stratified estimate alone insufficient prescreen

## Lesson #44 amendment 12th dogfood

7 graveyard cross-references all DISTINCT:
- paradigm 62 cross_sec_weekly_mr / 75 lead_lag / 81 rolling_beta / 118 universe_corr / 99 funding velocity / 129 parkinson / RUNBOOK antipattern

## Verdict reasoning

```
0/4 quadrants three-gate PASS
0/4 Concentration Gate PASS
Both A quadrants net < 0 (focus -24.77 / mirror -7.23)
Both LONG quadrants gross negative (-8.77 / -18.59)
Both SHORT quadrants gross positive (+8.77 / +18.59)
0/11 syms ci_pos in any quadrant (pure systemic artifact)
→ BROAD_FALSIFIED_A_FOCUS_NEGATIVE
→ Lesson #52 amendment candidate (inverse SHORT-bias artifact)
```
