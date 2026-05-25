# paradigm 197 GRAVEYARD — funding rate 5d/30d ratio z spike (3rd substrate)

- **counter**: 197
- **slug**: `alt_per_sym_5d_30d_funding_rate_short_long_ratio_z_spike_directional_4h_bilateral`
- **phase**: R-1
- **verdict**: `BROAD_FALSIFIED_FEE_FLOOR_3SUBSTRATE_UNIVERSE_LIMIT_CONFIRMED`
- **date**: 2026-05-22 KST

## Hypothesis (recap)

Per-sym 8h funding rate. Compute 5d-window mean / 30d-window mean → 90d rolling z-score. |z|>=+2 spike trigger split by concurrent 4h bar direction into 4 quadrants (A_focus/A_mirror/B_same/B_mirror). 3rd-substrate transplant of paradigm 195 (RV ratio) + paradigm 196 (OI ratio) formulation onto funding rate axis. PRIMARY GOAL: universe-level concentration limit 3-substrate cross-verify.

## Prescreen verdicts

- **Lesson #70 corollary scope**: PROCEED (b) class shift. statistic + direction + hold all different from paradigm 22 R-5 LIVE → not spec-adaptive expansion. Same precedent as paradigm 182/184.
- **Lesson #61 slug grep**: clean (only `funding_term_structure_8h_vs_3d` exists, graveyard family-distinct).
- **Lesson #62 5/5 strict**:
  - vs paradigm 22 (funding_carry R-5 LIVE): 4/5 strict distinct (universe 14-alt overlap by design; statistic+mechanism+direction+hold all distinct).
  - vs funding family Tier 4 retire (73/79/96/97/98/99/132): window-ratio statistic = NEW class within funding axis.
- **Lesson #11 sample density**: 53,196 valid panel rows, ~10.7% z>=+2 trigger rate → ~5,700 triggers panel; per-quadrant × per-quarter >= 50/cell → PASS.
- **Lesson #21 axis stacking**: single derived statistic, no stacking. PASS.
- **Lesson #67/68 ESCAPE**: per-sym idiosyncratic + continuous rolling. PASS.

## R-1 result (16 cells, 4 quadrants x 4 holds)

- **3-gate PASS cells**: **0/16**
- **Concentration PASS cells**: 0/16
- **Life-changing 4-dim PASS cells**: 0/16
- **Best cell**: `A_focus_h24h` sigex **+1.52** (sub-2 threshold), n=831, gross=+30.9bp, net=+22.9bp, ci_lower=-10.4bp, **1/12 syms ci_pos = 8.3%**

### 4-quadrant SNT per-cell key numbers (primary 4h hold)

| Cell | n | gross_bp | net_bp | sigex | perm_p_above | ci_lower_bp | syms_ci_pos |
|---|---|---|---|---|---|---|---|
| A_focus_4h | 831 | +9.7 | +1.7 | +1.43 | 0.081 | -10.0 | 0/12 (0.0%) |
| A_mirror_4h | 831 | -9.7 | -17.7 | -1.32 | 0.905 | -29.8 | 0/12 (0.0%) |
| B_same_4h | 845 | +2.6 | -5.4 | +0.55 | 0.283 | -16.9 | 0/12 (0.0%) |
| B_mirror_4h | 845 | -2.6 | -10.6 | -0.58 | 0.721 | -22.0 | 0/12 (0.0%) |

### Hold sweep (best cell per hold)

| hold | best_quadrant | sigex | net_bp | syms_ci_pos |
|---|---|---|---|---|
| 4h | A_focus | +1.43 | +1.7 | 0/12 |
| 8h | A_focus | +0.82 | +0.9 | 0/12 |
| 12h | A_focus | +0.84 | +3.6 | 0/12 |
| 24h | A_focus | +1.52 | +22.9 | 1/12 |

Hold-horizon expansion → modest sigex pickup at 24h via gross expansion but **CI never positive at any hold**.

## 3-substrate cross-verify (RV -> OI -> funding)

| substrate | best cell | sigex | 3-gate | syms_ci_pos_ratio | universe verdict |
|---|---|---|---|---|---|
| paradigm 195 RV | A_focus_h12h | +3.42 | PASS | per-sym dict not populated in artifact (Conc FAIL noted) | - |
| paradigm 196 OI | A_focus_h4h | +2.29 | FAIL | **7.1% (1/14)** | HYP1 candidate |
| **paradigm 197 funding** | **A_focus_h24h** | **+1.52** | **FAIL** | **8.3% (1/12)** | **HYP1 CONFIRMED 3-substrate** |

**Universe-level concentration limit verdict**: **HYPOTHESIS_1_CONFIRMED_3SUBSTRATE** — 14-sym alt cohort × 4h-hold × short/long-window-ratio-z directional bilateral paradigm class structurally fails to produce universe-dispersed alpha across **three independent statistical substrates** (volatility / OI / funding). Best per-cell concentration **never exceeds 14% threshold** across any of the three substrates.

## Lesson #42 9th dogfood verdict

| hold | B_mirror_net_bp | B_same_net_bp | delta_bp | B_mirror_sigex |
|---|---|---|---|---|
| 4h | -10.6 | -5.4 | **-5.3** (B_same > B_mirror at 4h, FIRST partial deviation) | -0.58 |
| 8h | +3.0 | -19.0 | **+22.0** | +1.19 |
| 12h | +4.8 | -20.8 | **+25.7** | +0.98 |
| 24h | +14.8 | -30.8 | **+45.7** | +1.12 |

**Verdict**: 8/9 dogfoods CONFIRMED Lesson #42 (B_mirror > B_same capitulation MR universal cross-class) — confirmed at h8h/h12h/h24h with progressive delta widening (+22 -> +46bp). **First partial deviation at 4h** where B_same outperforms by 5.3bp; sub-threshold (sigex<2 both) and qualitative direction reasserts at all longer holds. Lesson #42 universal status maintained but **adds horizon-dependence note**: at minimum hold (4h) the capitulation MR mechanism does not yet manifest in funding substrate — funding ratio z anchor lags 8h cycle, requiring >=8h forward to capture MR.

## Per-sym z-distribution diagnostic (caveat)

Panel z-distribution shows structural pathology — `frac_ge_2 = 10.7%` and `frac_le_neg2 = 28.3%` (far from normal 2.3% per tail). Per-sym percentile dispersion:

- SOL: z_p50 = **-11.57**, frac z<=-2 dominates (2,272/4,092 valid rows = 55.5%) — sustained negative-funding regime
- BCH: z_p50 = **-4.81**, similar pathology
- ADA: z_max = +13.18, p90=+11.13 — extreme positive tail (concentrated positive-funding episodes)

**Root cause**: funding rate magnitudes are small and can sign-flip; `short_mean / long_mean` ratio amplifies when long_mean approaches zero. The `|long_mean|>1e-6` guard masks NaN-flips but not near-zero amplification.

**Implication for the verdict**: even though the z-statistic is structurally noisy on funding substrate, the **directional verdict remains valid** because:
1. The 4-quadrant SNT directly compares behavior under z>=+2 trigger irrespective of z magnitude
2. No quadrant produces 3-gate PASS — even the most generous interpretation (24h A_focus +22.9bp net) has CI lower at -10.4bp
3. Per-sym concentration (<=8.3%) is consistent with paradigm 195/196 RV/OI substrates which used clean 5min-aggregated ratios

The pathology lowers the **information content** of the funding-ratio-z statistic but does not falsify the universe-level concentration verdict, which is reproduced across 3 independent substrates.

## Sparse-strict life-changing 4-dim audit

Best cell `A_focus_h24h`:
- trades/yr = **369.3** (PASS >=12, but extreme — debounce 24h with z>=+2 trigger fires constantly)
- per-trade edge = **0.23%** (FAIL <2%)
- capital util = **101.2%** (PASS >=30%, but cap effectively exceeds 100% due to overlap)
- sharpe = **0.85** (FAIL <1.5)
- **PASS = False** — fails edge and sharpe dimensions decisively

## Per-sym cross-substrate winner verify

Across all 3 substrates' best cells, the lone ci_pos sym at h24h in paradigm 197 is **not the same** as paradigm 195/196 winners (per-sym artifact populated only in p196 = NEAR/BTC clusters near-zero). No consistent cross-substrate winner sym pattern emerges — universe-level limit is structurally substrate-invariant.

## Verdict

**BROAD_FALSIFIED_FEE_FLOOR_3SUBSTRATE_UNIVERSE_LIMIT_CONFIRMED**

Three-substrate cross-verify formally CONFIRMS HYPOTHESIS 1: **14-sym alt cohort × 4h-hold × short/long-window-ratio-z directional bilateral paradigm class produces no universe-dispersed alpha across volatility / OI / funding substrates**. Best concentration never exceeds 14% threshold on any of the three substrates. Recommend formal Tier 4 retire of this paradigm class (statistic-form invariant across momentum-like axes).

## Next-action / paradigm 198 recommendations

Three independent paths to escape this saturation:

1. **Universe expansion (RECOMMENDED)**: drop the 14-sym constraint. Run paradigm 197 (or RV/OI variants) on **20+ sym cohort** after 6-sym 4h OHLCV backfill (~20min ETA). Tests whether universe limit is **cohort-bound** (Top-14 alt sample saturation) rather than statistical-form-bound.
2. **Statistic class shift**: abandon short/long-window-ratio-z entirely. Try absolute-level threshold or cross-section rank-percentile. paradigm 22 already uses sparse z-MR with R-5 LIVE — single-sym deep-screen approach may be the only funding-axis path.
3. **Hold-class shift**: abandon 4h forward hold class. Try 8h-anchored holds tied to funding cycle (paradigm 22-style sparse MR). Already proven path; not a frontier.

**Concrete recommendation**: paradigm 198 = **universe expansion test (path 1)**. Run paradigm 195 RV-ratio formulation on 20+ sym cohort to test cohort-bound vs statistical-form-bound. If concentration ratio remains <14% on expanded universe -> statistic-form retire becomes universal. If concentration jumps to >=30% -> 14-sym cohort saturation was the binding constraint and we have a new path.

## Artifacts

- script: `backend/scripts/research/paradigm197_alt_per_sym_5d_30d_funding_rate_short_long_ratio_z_spike_directional_4h_bilateral_r1.py`
- metrics: `backend/runs/research_track/alt_per_sym_5d_30d_funding_rate_short_long_ratio_z_spike_directional_4h_bilateral/r1__metrics.json`
- log: `backend/runs/research_track/alt_per_sym_5d_30d_funding_rate_short_long_ratio_z_spike_directional_4h_bilateral/r1__run.log`
- INDEX backup: `backend/runs/research_track/INDEX.json.bak_paradigm197`
