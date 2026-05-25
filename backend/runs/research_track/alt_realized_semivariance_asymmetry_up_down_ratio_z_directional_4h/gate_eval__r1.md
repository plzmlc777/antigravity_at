# R-1 Gate Evaluation — paradigm 134 alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h

**Date**: 2026-05-21 11:08 KST
**Phase**: R-1 (PoC only — R-2 NOT dispatched per user directive)
**Verdict**: BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE (Lesson #39 sub-class A)

## Three-Gate per quadrant (R-1 PoC criteria)

| quadrant | signal_t_excess >= 2.0 | ci_lower > 0 | perm_p <= 0.10 | 3-gate PASS |
|---|---|---|---|---|
| A_focus_z_pos_LONG_4h | +1.78 FAIL | -19.14 FAIL | 0.043 PASS | FALSE |
| A_mirror_z_pos_SHORT_4h | -1.44 FAIL | -39.50 FAIL | 0.918 FAIL | FALSE |
| B_focus_z_neg_SHORT_4h | +0.54 FAIL | -28.42 FAIL | 0.306 FAIL | FALSE |
| B_mirror_z_neg_LONG_4h | +0.22 FAIL | -32.52 FAIL | 0.434 FAIL | FALSE |

**Passing quadrants: 0/4** → BROAD_FALSIFIED branch.

## Concentration Gate (Lesson #16 STRICT — paradigm 133 lesson)

Concentration not applicable since no quadrant passed three-gate. Diagnostic only:

| quadrant | q_pos_t_ratio >= 0.50 | sym_ci_pos_ratio >= 0.30 | n_ci_pos >= 3 | gate PASS |
|---|---|---|---|---|
| A_focus_LONG | 0.44 FAIL | 0.00 FAIL | 0 FAIL | FALSE |
| A_mirror_SHORT | 0.11 FAIL | 0.00 FAIL | 0 FAIL | FALSE |
| B_focus_SHORT | 0.33 FAIL | 0.00 FAIL | 0 FAIL | FALSE |
| B_mirror_LONG | 0.22 FAIL | 0.00 FAIL | 0 FAIL | FALSE |

**0/12 syms ci_pos universal across ALL 4 quadrants** = absence of mechanism, not concentration.

## R-1 Verdict Decision Tree

```
4-quadrant SNT evaluated → 0 PASS
  └─ both focus A_focus_LONG net=-5.75 AND B_focus_SHORT net=-14.13 negative
     └─ both A_mirror net=-26.25 AND B_mirror net=-17.87 also negative
        └─ ALL 4 quadrants net-negative
           └─ verdict: BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE
           └─ sub-class: A_broad_uniform_negative_no_axis_synthesis (Lesson #39 sub-class A)
```

Lesson #53 candidate check:
- gap A focus(+10.25) vs mirror(-10.25) = 20.5bp (boundary, NOT strictly >20bp)
- gap B focus(+1.87) vs mirror(-1.87) = 3.7bp (clear NOT inverted)
- → Lesson #53 NOT triggered. Mirror is mathematical fee-floor symmetric, NOT direction inversion.

## Promotion decision

**HALT at R-1 PoC** (per user directive "R-1 only halt 의무").

DO NOT promote to R-2. Reasons:
1. BROAD_FALSIFIED verdict — all quadrants fail
2. Concentration universal absence (0/12 syms ci_pos × 4 quadrants)
3. R-0 sub-amendment 10th dogfood TRUE POSITIVE warning predicted this outcome
4. Per-trade edge at fee floor (gross +10/+1.87 bp << 16bp fee)

## Graveyard

- `/home/hcpark/antigravity/backend/runs/research_track/graveyard__alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h.md`
