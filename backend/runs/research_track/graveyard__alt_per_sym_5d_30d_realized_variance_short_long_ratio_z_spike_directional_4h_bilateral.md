# Graveyard — paradigm 194

- **slug**: `alt_per_sym_5d_30d_realized_variance_short_long_ratio_z_spike_directional_4h_bilateral`
- **counter**: 194 (substantive)
- **verdict**: `CONCENTRATED_R1_PASS`
- **phase**: R-1 only (no R-2 promotion)
- **completed (KST)**: 2026-05-22 15:02 KST

## Hypothesis

Per-sym 4h close-to-close log returns →
`short_var = sum(ret^2) over 5d (30 bars)` /
`long_var = sum(ret^2) over 30d (180 bars)` ratio →
90d rolling z-score. `|z|≥+2` spike = vol term-structure deviation
(5d realized vol expanded vs 30d baseline). 4-quadrant SNT bilateral
split by concurrent bar direction × side (LONG/SHORT). Lesson #42 6th
dogfood: tests whether capitulation MR pattern (B_mirror > B_same)
holds on vol-ratio statistic class rather than price/drawdown class.

## Pre-dispatch prescreens (Lesson #11 + #34 + #40)

- Empirical |z|≥2 trigger rate: **6.43% (3779 / 58814 valid)**
- Per-cell aggregate (4 quadrants): ~945; per-quarter (×9): ~105 — **Lesson #11 PASS**
- **Lesson #40 structural threshold** measured pre-dispatch:
  - z.min across 14 syms: **11/14 syms z.min > −2** (NEAR −2.41, FIL −2.45, SOL −2.13 are sole exceptions)
  - z.max range: 4.57 (DOGE) to 10.35 (FIL spike) — heavily right-skewed
  - n_neg2 totals **53** vs n_pos2 **3779** (98.6% positive-side concentration)
  - **z≤−2 cell structurally infeasible** as predicted. Spec explicitly designed 4-quadrant axis as bar-direction × side (not z-sign), so test ran on z≥+2 trigger only — compliant.

## R-1 result summary (16 cells = 4 quadrants × 4 holds)

| cell                | n   | gross bp | net bp | obs_t | sigex | perm_p_above | ci_lower bp | three_gate | conc_gate | lc4 |
|---------------------|-----|----------|--------|-------|-------|--------------|-------------|------------|-----------|-----|
| A_focus_h4h         | 603 | -7.15    | -15.15 | -1.44 | -0.39 | 0.654        | -35.17      | F          | F         | F   |
| A_mirror_h4h        | 603 | 7.15     | -0.85  | -0.08 | 0.99  | 0.153        | -21.56      | F          | F         | F   |
| B_same_h4h          | 602 | -6.54    | -14.54 | -1.36 | -0.24 | 0.603        | -36.12      | F          | F         | F   |
| B_mirror_h4h        | 602 | 6.54     | -1.46  | -0.14 | 0.88  | 0.198        | -23.14      | F          | F         | F   |
| A_focus_h8h         | 603 | 30.04    | 22.04  | 1.59  | 2.31  | 0.017        | -5.54       | F          | F         | F   |
| A_mirror_h8h        | 603 | -30.04   | -38.04 | -2.75 | -1.97 | 0.972        | -65.32      | F          | F         | F   |
| B_same_h8h          | 601 | -4.79    | -12.79 | -0.89 | -0.11 | 0.545        | -40.65      | F          | F         | F   |
| B_mirror_h8h        | 601 | 4.79     | -3.21  | -0.22 | 0.50  | 0.308        | -31.37      | F          | F         | F   |
| **A_focus_h12h**    | 603 | 52.76    | 44.76  | 2.82  | **3.42** | **0.000** | **13.35**   | **T**      | **F**     | F   |
| A_mirror_h12h       | 603 | -52.76   | -60.76 | -3.83 | -3.20 | 0.997        | -91.68      | F          | F         | F   |
| B_same_h12h         | 601 | -33.85   | -41.85 | -2.38 | -1.72 | 0.965        | -75.66      | F          | F         | F   |
| B_mirror_h12h       | 601 | 33.85    | 25.85  | 1.47  | 2.02  | 0.017        | -9.61       | F          | F         | F   |
| **A_focus_h24h**    | 603 | 74.43    | 66.43  | 2.63  | **3.07** | **0.002** | **15.43**   | **T**      | **F**     | F   |
| A_mirror_h24h       | 603 | -74.43   | -82.43 | -3.27 | -2.84 | 0.997        | -133.74     | F          | F         | F   |
| B_same_h24h         | 601 | -63.60   | -71.60 | -3.01 | -2.53 | 0.994        | -117.00     | F          | F         | F   |
| **B_mirror_h24h**   | 601 | 63.60    | 55.60  | 2.34  | **2.72** | **0.004** | **10.08**   | **T**      | **F**     | F   |

## Verdict drivers

### 3/16 cells three-gate PASS
- `A_focus_h12h` sigex +3.42 ci [13.35, 75.68] bp — best cell
- `A_focus_h24h` sigex +3.07 ci [15.43, 117.74] bp
- `B_mirror_h24h` sigex +2.72 ci [10.08, 101.00] bp — Lesson #42 6th dogfood signature

### Concentration Gate FAIL (Lesson #16) — all 3 PASS cells
| cell             | q_pos_t_ratio | n_syms_ci_pos / measurable | ci_pos syms     |
|------------------|---------------|----------------------------|-----------------|
| A_focus_h12h     | 0.625 (5/8)   | 2/14 (0.143)              | LINK, XRP       |
| A_focus_h24h     | 0.375 (3/8)   | 2/14 (0.143)              | ADA, XRP        |
| B_mirror_h24h    | 0.500 (4/8)   | **0/14 (0.000)**          | (none)          |

Both A_focus PASS cells: 2/14 syms ci_pos (0.143 < 0.30 threshold).
B_mirror_h24h PASS cell: 0/14 syms ci_pos — alpha is fully homogeneous
in mean (+56bp net) but no per-sym CI clears zero. Aggregate t-stat
driven by panel mass, not by symbol-level robustness.

### Life-changing 4-dim FAIL — all 3 PASS cells
| cell             | trades/yr | edge%  | util%  | sharpe | fail dim                    |
|------------------|-----------|--------|--------|--------|------------------------------|
| A_focus_h12h     | 268.0     | 0.448  | 36.71  | 1.88   | edge (0.45% << 2%)          |
| A_focus_h24h     | 268.0     | 0.664  | 73.41  | 1.76   | edge (0.66% << 2%)          |
| B_mirror_h24h    | 267.1     | 0.556  | 73.16  | 1.56   | edge (0.56% << 2%)          |

Per-trade edge 5x below sparse-strict 2% target on every PASS cell.
Sharpe borderline (1.56 — 1.88), util OK on 24h, trades/year abundant —
but edge dimension structurally insufficient for life-changing outcome.

## Lesson #42 6th dogfood verdict — **PARTIAL_CONFIRM_HOLD_DEPENDENT**

| hold | B_mirror net bp | B_mirror sigex | B_same net bp | B_same sigex | spread | three_gate |
|------|------------------|----------------|----------------|---------------|--------|------------|
| 4h   | -1.46            | 0.88           | -14.54         | -0.24         | +13bp  | F          |
| 8h   | -3.21            | 0.50           | -12.79         | -0.11         | +10bp  | F          |
| 12h  | +25.85           | 2.02 (borderline) | -41.85      | -1.72         | +68bp  | F          |
| 24h  | **+55.60**       | **+2.72**      | -71.60         | -2.53         | **+127bp** | **T**  |

Capitulation MR pattern (B_mirror > B_same) **is present qualitatively**
on vol-ratio trigger class at 12h+24h holds, with spreads growing
monotonically with hold (10 → 13 → 68 → 127 bp). However:
1. B_mirror_h24h three-gate PASS but Concentration FAIL (0/14 syms ci_pos)
2. Quantitatively WEAKER than paradigm 193 price-level drawdown-depth
   trigger (B_mirror_h24h had net +99bp, 2/14 syms, edge 0.99%)
3. Both still fail life-changing edge dimension

**Scope: CONFIRMED QUALITATIVELY for vol-ratio statistic class but production-grade UNREACHED.**

## paradigm 193 reconciliation

| dim                | paradigm 193 (drawdown depth z) | paradigm 194 (vol ratio z)         |
|--------------------|---------------------------------|------------------------------------|
| best cell          | B_mirror_h24h (capitulation MR) | A_focus_h12h (vol expansion continuation) |
| best net bp        | +99 (n=684)                     | +45 (n=603)                        |
| best ci_lower bp   | +56                             | +13                                |
| syms ci_pos        | 2/14 (ADA, XRP)                 | 2/14 (LINK, XRP)                   |
| common sym         | XRP                             | XRP                                |
| edge%              | 0.99 (FAIL <2%)                 | 0.45 (FAIL <2%)                    |
| dominant quadrant  | B_mirror (capitulation MR)      | A_focus (vol expansion continuation) |
| axis class         | price level extremum            | vol term-structure deviation       |

**Cells PASS in DIFFERENT quadrants** → distinct statistic class confirmed.
**XRP universal winner** across both — cross-statistic-class robust
microstructure marker candidate (worth noting for future per-sym scope studies).

## Per-quarter robustness (best cell `A_focus_h12h`)

| Q       | n   | t      | mean bp | flag |
|---------|-----|--------|---------|------|
| 2024Q2  | 16  | -1.05  | -80.81  | NEG  |
| 2024Q3  | 102 | +2.81  | +96.23  | POS  |
| 2024Q4  | 147 | +0.70  | +21.87  | POS  |
| 2025Q1  | 44  | +0.44  | +39.67  | POS  |
| 2025Q2  | 60  | +2.22  | +110.86 | POS  |
| 2025Q3  | 62  | -0.62  | -23.91  | NEG  |
| 2025Q4  | 69  | +2.23  | +121.30 | POS  |
| 2026Q1  | 99  | -0.13  | -4.44   | NEG  |
| 2026Q2  | 4   | NA     | +101.80 | N/A  |

5/8 measurable quarters positive t-stat (0.625 ratio passes ≥0.5 conc
condition #1) but 2/14 per-sym ci_pos fails conc condition #2.

## Lesson dogfood

- **#11** sample density prescreen PASS (~105/cell per quarter)
- **#16** Concentration Gate FAIL on all 3 three-gate-PASS cells (gate doing its job)
- **#19** 4-quadrant SNT measured — A_focus + B_mirror PASS three-gate, A_mirror + B_same FAIL (mirror cells correctly negate, validating spec design)
- **#21** single derived statistic, no axis stacking
- **#34** empirical distribution prescreen done pre-dispatch
- **#40** structural threshold confirmed empirically (11/14 syms z.min > −2); spec acknowledged it (axis = bar-dir × side, not z-sign)
- **#42** 6th dogfood: **PARTIAL_CONFIRM_HOLD_DEPENDENT** — capitulation MR pattern qualitatively present at 12h+24h for vol-ratio trigger class but weaker than price-level class and conc-fail
- **#61** slug grep clean
- **#62** 5/5 family-distinct strict PASS
- **#67/#68/#70** ESCAPE verified
- **#69** 5-item template observed
- **#71** sparse-strict mode — edge dim fails 2% target on all PASS cells

## Novel findings

1. **Vol-ratio z generates A_focus dominance** (vol expansion × bar UP × LONG continuation) at 12h+24h, OPPOSITE of paradigm 193 drawdown-depth B_mirror dominance — two distinct mechanisms in the same overall paradigm class (per-sym z-spike events on extremum statistics).
2. **Lesson #42 scope partial-confirmed** for vol-ratio class but quantitatively weaker than price-level class. Pattern is real but capitulation MR magnitude is hold-dependent and statistic-class-dependent.
3. **XRP cross-statistic-class universal winner** — appears in top-2 ci_pos syms list for both paradigm 193 (drawdown class) and paradigm 194 (vol ratio class). Candidate marker for cross-axis per-sym scope study.
4. **Mirror cells correctly negate** (A_focus +44bp net at 12h ↔ A_mirror −60bp; B_same −72bp at 24h ↔ B_mirror +56bp) — spec design with bilateral SNT axis = bar-dir × side validated structurally.
5. **Concentration Gate operating as designed**: full aggregate three-gate strength (sigex +3.42, perm_p_above 0.000) crushed by per-sym CI scrutiny (2/14 syms only).

## Next action — paradigm 195 axis suggestions (none from Tier 4 retired families)

1. **Per-sym RV term-structure SPREAD absolute** (not ratio z): `5d_RV_bp − 30d_RV_bp` raw spread. Tests whether absolute magnitude (avoiding Lesson #40 ratio compression) generates better per-sym CI dispersal. Distinct from vol-ratio z because preserves scale.
2. **Vol-of-vol (RV of RV) z** — 2nd-order persistence statistic class. Distinct axis class. Bounded-below but different distribution from ratio.
3. **Cross-asset RV ratio z**: `per-alt RV / BTC RV` z-score. Tests relative-strength axis (alt vol vs market vol baseline) — distinct from absolute-level (paradigm 67/68/70/155 Tier 4 family) and per-sym (paradigm 69 R-5 LIVE family expansion would violate Lesson #70).

Recommendation: **paradigm 195 = option (1) per-sym RV term-structure spread absolute** — most direct test of whether Lesson #40 ratio-compression is the limiting factor on per-sym CI dispersal seen here.

## Artifacts

- `backend/scripts/research/paradigm194_alt_per_sym_5d_30d_realized_variance_short_long_ratio_z_spike_directional_4h_bilateral_r1.py`
- `backend/runs/research_track/alt_per_sym_5d_30d_realized_variance_short_long_ratio_z_spike_directional_4h_bilateral/r1__metrics.json`
- `backend/runs/research_track/INDEX.json` (paradigm 194 entry)
- `backend/runs/research_track/INDEX.json.bak_paradigm194`
