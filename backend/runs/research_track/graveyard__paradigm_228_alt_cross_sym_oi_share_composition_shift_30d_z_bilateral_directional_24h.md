# Paradigm 228 Graveyard — cross-sym OI share composition shift 30d z bilateral directional

**Slug**: `paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h`
**Family**: `cross_sym_oi_composition_concentration` (first paradigm in family)
**Phase halted at**: R-1 (Lesson #37 full sweep completed)
**Verdict**: `CONCENTRATED_R1_PASS_NARROW_SCOPE_LIFE_CHANGING_STRUCTURAL_FAIL_LESSON_74_CANDIDATE_4TH_DOGFOOD`
**Date**: 2026-07-16

## Hypothesis

Per-sym daily OI value (USDT) as a fraction of universe-total OI, 30d rolling z-score, |z|>=T bilateral trigger × bar direction. 4-quadrant SNT × directional hold sweep. Universe: 7 syms (HBAR/LINK/AVAX/SOL/DOGE/ETH/NEAR — substrate-limited from planned 14; ADA excluded per Lesson #30).

Mechanism claim: rapid OI-share gain (z>=+1.5) → concentration continuation (LONG); rapid OI-share loss (z<=-1.5) → capital exit continuation (SHORT).

## R-0 Prescreen (9 items, ALL PASS)

| Item | Verdict | Notes |
|---|---|---|
| 1 slug grep | PASS_NONE | Only forward-looking NEXT_PARADIGM_RUNBOOK matches (executing that rec) |
| 2 substrate audit | PASS_7of14 | Universe reduced from 14 to 7 syms with OI + OHLCV coverage |
| 3 sample density | PASS | z=1.5 gives 88-127 events/sym/side; well above 30/cell |
| 4 DNA family-distinct | PASS_5of5 | vs oi_price_decoupling (paradigm 127/128), oi_velocity (196) — distinct normalization + mechanism |
| 5 family-proxy outcome | PASS | Cross-sym FRACTION is genuinely new dimension (127/128 is per-sym level; 196 is per-sym velocity) |
| 6 alpha decay P1 | ERA_STRATIFICATION_INCLUDED | Included in R-1 output |
| 7 structural threshold feasibility | PASS_EMPIRICAL | z range [-5.13, +5.28]; z>=1.5 12.7% pos, z<=-1.5 13.2% neg |
| 8 concentration gate pre-estimate | RISK_NARROW_7_SYMS | 30% target = 2.1 syms → 3 needed, tight margin |
| 9 life-changing pre-estimate | RISK_FLAGGED_UTIL | At z=1.5 h=1 util ~11%; at z=2.0 h=2 util projected ~3% |

## R-1 Full Sweep (Lesson #37 mandatory)

Sweep: z ∈ {1.0, 1.5, 2.0} × hold ∈ {1, 2, 3} × 4 quadrants = 36 cells

| z | h | quadrant | ci_pos ratio | quarter_pos_t | concentration_gate |
|---|---|---|---|---|---|
| 1.0 | 1 | A_focus | 1/7 (14%) | 0.59 | FAIL |
| 1.0 | 2 | A_focus | 1/7 (14%) | 0.59 | FAIL |
| 1.0 | 3 | A_focus | 1/7 (14%) | 0.46 | FAIL |
| 1.5 | 1 | A_focus | 1/7 (14%) | 0.66 | FAIL |
| 1.5 | 1 | B_focus | 2/7 (29%) | 0.67 | FAIL (just below 30%) |
| 1.5 | 2 | B_focus | 2/7 (29%) | 0.77 | FAIL |
| 1.5 | 3 | B_focus | 1/7 (14%) | 0.77 | FAIL |
| 2.0 | 1 | B_focus | 1/7 (14%) | 0.70 | FAIL |
| **2.0** | **2** | **B_focus** | **3/7 (43%)** | **0.90** | **PASS** |
| 2.0 | 3 | B_focus | 2/7 (29%) | 0.90 | FAIL |

**Only 1/36 cells clears Concentration Gate**: z=2.0 h=2 B_focus (SHORT on share-exit + bar-DOWN).

## Cell z=2.0 h=2 B_focus detail

| Sym | n | mean_bp | obs_t | ci_lower_bp | 3-gate |
|---|---|---|---|---|---|
| HBARUSDT | 12 | 329.4 | 2.06 | +16.4 | fail (perm_p) |
| LINKUSDT | 9 | — | — | — | n<10 |
| AVAXUSDT | 12 | 301.8 | 2.20 | +45.3 | fail (perm_p) |
| SOLUSDT | 12 | 133.2 | 0.79 | -162.5 | fail |
| DOGEUSDT | 16 | -81.4 | -0.46 | -411.8 | fail |
| ETHUSDT | 25 | -34.0 | -0.37 | -207.8 | fail |
| NEARUSDT | 26 | 232.4 | 2.14 | +28.8 | fail (perm_p) |

3 syms with ci_lower>0 (HBAR/AVAX/NEAR), all obs_t between 2.06-2.20 individually. quarter_pos_t=0.90 across time — highly consistent.

## Lesson #39 mirror antipattern check (z=2.0 h=2)

| Sym | B_focus mean_bp | B_mirror mean_bp | sum | expected (-2×fee) |
|---|---|---|---|---|
| HBAR | +329.4 | -345.4 | -16.0 | -16.0 ✓ |
| AVAX | +301.8 | -317.8 | -16.0 | -16.0 ✓ |
| SOL | +133.2 | -149.2 | -16.0 | -16.0 ✓ |
| DOGE | -81.4 | +65.4 | -16.0 | -16.0 ✓ |
| ETH | -34.0 | +18.0 | -16.0 | -16.0 ✓ |
| NEAR | +232.4 | -248.4 | -16.0 | -16.0 ✓ |

Perfect fee-symmetric mirror. Sub-class B mechanism DIRECTION IS B_focus for 3/7 syms (HBAR/AVAX/NEAR/SOL positive), inverted for 2/7 (DOGE/ETH negative). Mixed cross-sym direction — trigger has partial information content, not zero (unlike Lesson #39 sub-class A broad-uniform-negative).

## Lesson #74 STRUCTURAL narrow-scope life-changing 4-dim FAIL

Best cell (z=2.0 h=2 B_focus, 3 syms HBAR/AVAX/NEAR):

| Dim | Value | Target | Verdict |
|---|---|---|---|
| edge/trade | ~2.5% (mean 288bp of 3 pos syms) | ≥ 2% | PASS |
| trades/yr/sym | ~5 (12-26 total / 2.4yr) | ≥ 50 | FAIL 10x |
| capital util | ~2.7% (5 × 2d / 365) | ≥ 30% | **FAIL 11x** |
| sharpe (annual) | ~1.5-2.0 (obs_t noisy at n=12-26) | ≥ 1.5 | marginal |

**2/4 life-changing dims STRUCTURAL FAIL.** Sparse trigger DNA (z=2.0 × 2d hold) creates util ceiling ~3%. Cannot recover within DNA — narrowing to top-3 makes util worse, not better; broadening (z=1.5) drops concentration gate (2/7).

## Era stratification (Lesson #46 P1 check)

Sample too sparse for definitive P1 verdict per cell (n<5 in most eras). Directional hints:
- NEAR: 2024H2 n=7 t=0.60 mean=126bp → 2025H1 n=11 t=1.43 mean=264bp → 2025H2 n=4 mean N/A → 2026H1 n=2 mean N/A (declining density)
- HBAR: only 2025H2 has n=5 (mean=394 t=1.36); others n<5
- AVAX: all eras n<5

Declining n in 2026H1 across all 3 PASS syms suggests trigger frequency decay (mechanism becoming rarer as universe matures), but under-powered to declare formal P1.

## Root cause

Cross-symbol OI-share z-score is dominated by 2 mega-caps (ETH 71% mean share, SOL 22% mean share) with 5 minor syms totaling ~6%. z-score of ETH's share change is structurally noisy (denominator dominated by itself). Minor syms have volatile share fractions but small absolute OI moves. Real edge exists in 3 mid-cap alts (HBAR/AVAX/NEAR) via z=2.0 h=2 B_focus SHORT — but sparse-trigger sparse-hold DNA cannot support capital utilization targets.

## Decision

**GRAVEYARD.** R-2 NOT dispatched.

- Concentration Gate PASS on 1/36 cells is real edge signal (not noise) — 3/7 syms with obs_t>2.0 individually + quarter_pos_t=0.90
- BUT Item 9 life-changing structural infeasibility per Lesson #74 antipattern (paradigm 213 precedent) — 4th `NARROW_SCOPE_LIFE_CHANGING_FAIL` dogfood (paradigm 95, 212, 213, 228)
- Perfect Lesson #39 fee-symmetric mirror across all syms with mixed direction across syms confirms trigger information is partial
- R-2 dispatch into sparse-trigger DNA has 0 known path to util>=30% recovery (validated in paradigm 213 exhaustive scoping)

## Lesson candidates

- **Lesson #74 candidate 4th dogfood**: NARROW_SCOPE_LIFE_CHANGING_FAIL_STRUCTURAL pattern when broad-scope edge < 2% AND sparse-trigger DNA (hold ≥ 2d × |z| ≥ 2.0) — confirmed 4th precedent. Consider promoting to CONFIRMED at 5th dogfood.
- **NEW Lesson candidate**: cross-symbol FRACTION statistics on cap-weighted OI universe suffer from mega-cap-dominance normalization noise. When any single sym holds >60% of universe fraction, z-score of its own share change is structurally weak. **Prescription**: use equal-weighted rank / demean by cap-tier / restrict universe to same-tier syms.

## Artifacts

- Script: `backend/scripts/research/paradigm_228_oi_share_composition_r1.py`
- Metrics (7 sweep files): `backend/runs/research_track/paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h/r1_*.json`
- Best cell (only PASS conc gate): `r1_z2_0_h2__metrics.json`
