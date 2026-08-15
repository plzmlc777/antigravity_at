# paradigm 179 — intraday_count_concentration_max_4h_share_within_24h_z_directional_4h — R-2 walk-forward verdict

**Status**: `NARROW_SCOPE_LIFE_CHANGING_FAIL` (graveyard)
**Date**: 2026-05-22 KST
**Host**: local paradigm-architect agent
**Substrate**: `backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib` × 7 deep syms × 2.0 yrs (zero backfill)

## R-2 Spec

- universe: 7 deep-sym narrow (BTC/ETH/SOL/XRP/DOGE/BNB/LINK)
- cell: B_same_sign (max_share spike + max bar DOWN × SHORT continuation)
- trigger: max_share rolling-90d |z| >= 2
- primary hold: 8h (2 × 4h bars)
- 5-fold chronological time-series walk-forward, gap = hold_bars
- fee 8 bp/trade

## 5-Fold Walk-Forward Results

| Fold | Time range | n | mean_bp | obs_t | ci_lo_bp | sigex | perm_p | 3-gate | conc |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2024-05-06 -> 2024-11-02 | 159 | +53.49 | +2.44 | +11.21 | +3.06 | 0.001 | **PASS** | FAIL |
| 1 | 2024-11-02 -> 2025-02-28 | 159 | +44.68 | +1.15 | -35.83 | +1.77 | 0.036 | FAIL | FAIL |
| 2 | 2025-02-28 -> 2025-08-16 | 159 | +56.44 | +3.18 | +23.04 | +3.80 | 0.000 | **PASS** | **PASS** |
| 3 | 2025-08-16 -> 2025-12-06 | 159 | +66.19 | +3.38 | +31.08 | +4.00 | 0.000 | **PASS** | **PASS** |
| 4 | **2025-12-06 -> 2026-04-28** | 160 | -25.73 | -2.03 | -50.96 | -1.45 | 0.923 | FAIL | FAIL |

**n_folds_pass = 3/5** (Lesson #26 cutoff exactly met, zero margin).
**n_folds_conc_pass = 2/5** (folds 2+3 only).

## 2026Q1 OOS Fold (Fold 4) — Regime Stress Test

Fold 4 covers 2025-12-06 → 2026-04-28, fully containing 2026Q1 OOS period predicted as risk in R-1 supplement CASE_A verdict.

- **Mean -25.73bp, obs_t -2.03, sigex -1.45, perm_p 0.923 — FULLY FAIL**
- **0/7 syms ci_pos**:
  - BNB n=24 mean -31.0bp, BTC n=16 mean -25.2bp, DOGE n=22 mean -34.3bp, ETH n=21 mean -37.8bp
  - LINK n=25 mean +9.9bp (only marginally positive), SOL n=28 mean -12.8bp, XRP n=24 mean -54.7bp

**Verdict**: 2026Q1 regime reversal CONFIRMED at fold-level — universal (7/7 syms) failure, not idiosyncratic. CASE_A from R-1 supplement validated.

## Full-Cohort Aggregate (information-only)

- n=796 mean +38.93bp, obs_t +3.64, sigex +4.93, ci_lo +18.52bp — three-gate PASS
- symbol_ci_pos_ratio = 3/7 = 42.9% — Concentration Gate PASS
- Aggregate masks fold 4 collapse via time aggregation.

## Lesson #20 4-Cond Audit

| Cond | Description | Result |
|---|---|---|
| 1 | three-gate full-cohort | **PASS** (sigex +4.93, ci_lo +18.5bp, perm_p 0.000) |
| 2 | Concentration full-cohort | **PASS** (3/7 syms = 42.9% ≥ 30%) |
| 3 | Temporal WF n_folds_pass ≥ 3/5 | **PASS** (3/5, zero margin) |
| 4 | Life-changing 4-dim any-mode PASS | **FAIL** (both modes FAIL) |

**all_4_cond_pass = FALSE** — cond4 sole blocker.

## Life-Changing 4-Dim Dual-Mode

**Sparse-strict mode**:
- trades_per_yr = 402.87 (PASS ≥ 12, 33x cushion)
- per_trade_edge_pct = **0.389%** (FAIL, target ≥ 2%, 5x shortfall)
- capital_util_pct = **5.25%** (FAIL, target ≥ 30%, 5.7x shortfall)
- sharpe_annualized = 2.59 (PASS ≥ 2.0)
- **2/4 PASS, all_4_pass = FALSE**

**High-freq diffuse portfolio mode**:
- portfolio_annualized_alpha_pct = **23.77%** (PASS ≥ 20%)
- sharpe_annualized = 2.59 (PASS ≥ 2.5)
- capital_util_pct = **5.25%** (FAIL ≥ 30%)
- **2/3 PASS, all_3_pass = FALSE**

**Per-sym annualized alpha (7 deep)**:
- DOGE 42.6%, SOL 38.7%, ETH 35.8%, XRP 17.6%, BTC 13.2%, LINK 12.0%, BNB 6.5%
- 7/7 net positive but underwhelming median for life-changing target

## Failure Root Cause

`capital_util_pct = 5.25%` is the structural blocker. Per-trade hold 8h × 7 syms × ~114 trades/sym = ~5.3% time-occupied across the 2-year window. High-freq sparse-trigger paradigm inherently low capital utilization — a single symbol's position runs only 8h × ~114 = ~912 hours out of 17,544 hours / 2 years.

To break 30% util threshold would require **6x more trade frequency** (i.e., trigger rate ~25%+) or **6x longer holds** (~48h), but extending holds destroys the mean-reverting edge (R-1 hold sweep showed 4h→8h→12h saturation).

## NARROW_SCOPE_LIFE_CHANGING_FAIL 3rd Dogfood

This is the **3rd confirmed dogfood** of this verdict category:

1. **paradigm 95** (HIGH volume share + LONG continuation): util 6.39%, edge 0.47%/trade
2. **paradigm 99** (funding per-sym velocity narrow): util similar
3. **paradigm 179** (intraday max_share + SHORT continuation): util 5.25%, edge 0.39%/trade

**Common pattern**: statistical edge is real (sigex +5 typical, perm_p 0.000), Lesson #20 4-cond conds 1-3 all PASS, but per-trade magnitude × capital utilization product structurally incompatible with life-changing 4-dim. High-freq diffuse mode portfolio_alpha clears 20%/yr but util gate fails.

**Potential Lesson #71 candidate**: "High-freq sparse-trigger paradigms structurally cap capital utilization at ~5-7%, blocking life-changing 4-dim even with portfolio alpha > 20%/yr." Requires 4th dogfood for CONFIRMED status per dogfood promotion convention.

## R-3 Entry Recommendation

**HOLD — graveyard at R-2**. Reasons:
1. Life-changing 4-dim FAIL is decisive per [[feedback-life-changing-strategy-criterion]] — not a partial-merit candidate.
2. Lesson #26 cutoff met with zero margin (3/5 folds), implying any minor robustness perturbation in R-3 (regime stratify, threshold sweep) likely breaks 3/5.
3. Fold 4 (2026Q1+ regime) failure is **universal 7/7 syms** — recent regime hostile to mechanism, not noise.
4. R-3 robustness would consume agent compute on a paradigm already disqualified at the life-changing layer.

## Artifacts

- R-2 script: `backend/scripts/research/paradigm179_intraday_count_concentration_max_4h_share_within_24h_z_directional_4h_r2.py`
- R-2 metrics: `backend/runs/research_track/paradigm179_intraday_count_concentration_max_4h_share_within_24h_z_directional_4h/r2__metrics.json`
- R-2 verdict (this file): `backend/runs/research_track/paradigm179_intraday_count_concentration_max_4h_share_within_24h_z_directional_4h/r2_verdict.md`
- INDEX.json entry renamed to `paradigm_179_..._narrow_scope_life_changing_fail`

## Family/Cross-paradigm Status

- intraday_count_concentration statistic class: 1 paradigm tested (179), 1 graveyard. Not yet family-retire eligible (requires ≥3 graveyards per convention).
- B_same_sign continuation cell + 8h hold combination: substantively real signal but mechanism-bound to high-freq diffuse mode where util fails. Mechanism inversion (Option β — max_share LOW z<=-2 dispersion) blocked by Lesson #40 risk on non-negative bounded statistic (max_share ∈ [0.167, 1.0]); LOW-z threshold may be structurally infeasible without reformulation (e.g., percentile rank or log-ratio).
