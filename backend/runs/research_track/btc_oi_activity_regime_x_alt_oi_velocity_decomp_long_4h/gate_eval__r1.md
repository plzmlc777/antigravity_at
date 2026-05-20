# R-1 Gate Eval — paradigm 120 `btc_oi_activity_regime_x_alt_oi_velocity_decomp_long_4h`

## Three-gate (per quadrant)

| Quadrant | sigex ≥ 2.0 | ci_lower > 0 | perm_p ≤ 0.10 | 3-gate PASS |
|---|---|---|---|---|
| A_focus (z>+1 × HIGH × LONG)  | +4.07 ✓ | -1.94 ✗ | 0.000 ✓ | ✗ |
| A_mirror (z>+1 × HIGH × SHORT)| -3.86 ✗ | -22.57 ✗ | 0.000 ✓ | ✗ |
| B_focus (z<-1 × HIGH × SHORT) | -4.87 ✗ | -24.24 ✗ | 0.000 ✓ | ✗ |
| B_mirror (z<-1 × HIGH × LONG) | +4.82 ✓ | -0.49 ✗ | 0.000 ✓ | ✗ |

Result: 0/4 quadrants PASS three-gate.

## Concentration gate (per Lesson #16)

| Quadrant | q_pos_t_ratio ≥ 0.50 | sym_ci_pos_ratio ≥ 0.30 | n_syms_ci_pos ≥ 3 | Conc PASS |
|---|---|---|---|---|
| A_focus  | 4/7 = 0.57 ✓ | 0/13 = 0.00 ✗ | 0 ✗ | ✗ |
| B_mirror | 4/7 = 0.57 ✓ | 0/13 = 0.00 ✗ | 0 ✗ | ✗ |

Universal sym ci_pos = 0 / 13 — homogeneous diffuse (no concentration synthesis).

## Life-changing 4-dim (per Lesson #41 amendment)

| Quadrant | per-trade edge | ≥ 2% gate |
|---|---|---|
| A_focus | 0.022% | ✗ |
| B_mirror | 0.039% | ✗ |

Both positive quadrants ≪ 200 bp threshold (achieved 2~4 bp net).

## Lesson #19 4-quadrant Symmetric Negative Test

Mandatory single-batch execution: ✓ satisfied (single R-1 script, all 4 quadrants in one run).

## Lesson #39 symmetry check

| Pair | focus + mirror sum | abs(focus) − abs(mirror) |
|---|---|---|
| A (z>+1) | -16.00 bp = exactly -2×fee | 16.00 bp = exactly 2×fee |
| B (z<-1) | -16.00 bp = exactly -2×fee | 16.00 bp = exactly 2×fee |

**NOT sub-class A** (gross drift +10~+12 bp exists in focus direction).
**NOT sub-class B** (mechanism direction correct, mirror is inverted as expected).
**NEW sub-class C candidate** (weak positive drift × strict fee floor binding × mechanism correct).

## Final R-1 verdict

`BROAD_FALSIFIED_FEE_FLOOR_SUB_THRESHOLD`

Promotion to R-2: **NO** — graveyard at R-1.

R-5 seed proposal: **NO**.
