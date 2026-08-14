# Graveyard — paradigm 236 alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d

**Slug**: `alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d`
**Paradigm number**: 236
**Dispatch mode**: SELF-RECOMMEND (autonomous)
**Date**: 2026-07-25
**Final phase**: R-3 GRAVEYARD
**Type**: E (event-anchored, per-trade edge)

## Hypothesis

Per-symbol Binance Futures perp daily book-depth `imbalance_mean` (from `runs/book_depth/{SYM}USDT_bookdepth.joblib`) rolling 30d z-score as bilateral swing predictor.
  - z > +threshold => LONG next 1..3d (bid dominance → price appreciation)
  - z < -threshold => SHORT next 1..3d (ask dominance → price decline)

Fee 8bp round-trip. Universe = 14 perp symbols (ADA/AVAX/BCH/BNB/BTC/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP). Window 2025-05-03 to 2026-05-02 (364 daily rows per sym, 333 after 30d warmup + 3d fwd).

## DNA vs prior book_depth paradigm (`book_depth_fragility_short`)

| Dim | prior | this |
|---|---|---|
| Substrate | book_depth joblib | book_depth joblib (OVERLAP) |
| Statistic | `top1_concentration` p80 + `near_imbalance`<-0.1 conjunction | `imbalance_mean` rolling 30d z-score |
| Universe | SHORT-only ~6 syms | bilateral 14 syms |
| Entry type | AND-threshold conjunction | continuous z-score |
| Mechanism | concentration fragility → SHORT | depth asymmetry → same-direction |

3/5 dimensions DISTINCT → DNA check passed.

## R-0 Prescreen (all pass)

- Lesson #40 structural feasibility: `imbalance_mean ∈ [-1, +1]`, rolling z bounded → z=±1.0/1.5/2.0 achievable
- Lesson #79 OOS correlation pretest: 14/14 symbols |corr|≥0.02 on at least one horizon (SOLUSDT: +0.180 at 3d, BTC +0.236, LTC +0.194). Correlations predominantly positive at 2d/3d → supports hypothesis direction.
- Lesson #56 family proxy: prior book_depth paradigm used different signal axis (top1_concentration + near_imbalance conjunction), not `imbalance_mean` rolling z
- Lesson #11 sample density: at z=1.0 threshold, ~55–65 events per symbol per direction over 333 days → PASS

## R-1 Result — PASS (marginal)

Full sweep: 3 thresholds × 3 holds × 4 quadrants × 14 syms = 504 cells scanned.

Only 1 cell out of 108 aggregate cells cleared the "n_symbols_pass_three_gate >= 3" bar:

| Cell | thr | hold | quadrant | total_events | n_pass_3gate | mean_of_sym_means_bp |
|---|---|---|---|---|---|---|
| WINNER | 1.0 | 3d | B_focus (SHORT on z<=-1.0) | 800 | 3/14 | +67.91 |

Passing symbols: BTC (t=2.028, mean=+96bp), FIL (t=2.035, mean=+173bp), LTC (t=2.741, mean=+199bp).

**Directional asymmetry warning**: A_focus (LONG on z>=+thr) fails universally with mean **NEGATIVE** across all 9 (thr × hold) cells (-16 to -27bp). B_mirror (SHORT on z>=+thr, i.e., inverted direction) shows slightly positive at 1d/3d holds with 1-2 syms passing — this is a mild Lesson #39 sub-class B mechanism-inverted risk indicator, though not universal.

Lesson #39 sub-class A pathology check: 2/126 (sym,thr,hold) pairs flagged (1.6%). Safe from broad-uniform-negative pathology.

## R-2 Result — PASS (marginal)

Best cell (thr=1.0, hold=3d, B_focus) re-run + 4-fold time-series CV walk-forward with 7d embargo.

- **Full window 3-gate pass**: 3/14 (BTC, FIL, LTC) — same as R-1
- **WF-stable (>=3/4 positive folds)**: 8/14 (ADA, BCH, BTC, DOGE, ETH, FIL, LTC, SOL)
- **WF fold-level 3-gate pass**: 0/32 folds — each fold has only n=5-14 trades, insufficient for individual 3-gate PASS

BTC fold detail: 4/4 positive (+31 / +100 / +449 / +153 bp). LTC: 4/4 positive. FIL: 3/4 positive (fold4=-3bp).

R-2 verdict: PASS_TO_R3 on WF-stable count criterion.

## R-3 Result — GRAVEYARD

Permutation test (n=200, shuffle imb_z within symbol) on top 8 symbols:

| sym | n | real_bp | perm_mean | perm_std | perm_sigma | perm_p_gt |
|---|---|---|---|---|---|---|
| LTC | 55 | +199.46 | +29.59 | 70.28 | **2.417** | 0.010 |
| BTC | 65 | +95.91 | +11.91 | 39.67 | **2.117** | 0.010 |
| ETH | 57 | +97.60 | -18.35 | 75.55 | 1.535 | 0.065 |
| BCH | 50 | +57.69 | -34.51 | 69.83 | 1.320 | 0.085 |
| FIL | 65 | +172.86 | +16.91 | 143.90 | 1.084 | 0.135 |
| DOGE | 54 | +110.25 | +16.76 | 92.33 | 1.013 | 0.170 |
| ADA | 58 | +130.54 | +62.40 | 76.28 | 0.893 | 0.180 |
| SOL | 57 | +87.45 | +24.18 | 74.90 | 0.845 | 0.235 |

**Elite gate requires `perm_sigma ≥ 4.0` for ≥2 symbols. RESULT: 0/8 pass, 2/8 marginal.**

The gap between perm_mean and real_alpha is small relative to perm_std for most symbols. BTC/LTC show real ~2.1-2.4σ above shuffle noise, meaningful but not elite. FIL passed the 3-gate on raw data but perm_std is very high (144bp) because the underlying signal density is thin — FIL's real alpha is not distinguishable from a lucky reshuffle.

### Temporal window analysis — signal is regime-dependent (emerged Q4 2025)

Split window into thirds:

| sym | early (2025-06~09) | mid (2025-09~2026-01) | late (2026-01~04) |
|---|---|---|---|
| BTC | -86bp | +158bp | +301bp |
| FIL | -72bp | +491bp | +135bp |
| LTC | -35bp | +375bp | +271bp |

The signal did NOT exist in the first third of the sample. It emerged in Q4 2025 and persisted into Q1-Q2 2026. This is not decay but late-emergence — either a real regime shift or a fitting artifact of the limited 12-month window. Either way, the effective sample is ~8 months not 12, further eroding statistical power.

### Fee sensitivity — signal fee-robust but low absolute magnitude

LTC (best): fee=4→203bp, fee=8→199bp, fee=12→195bp, fee=16→191bp. Not fee-driven; signal is real ~200bp per trade on LTC alone. However with only n=55 trades over 333 days = ~60 trades/yr, and only 1-3 syms tradeable, the annualized capital-utilization is very low.

### BTC regime stratify — no strong dependence

Signal survives in both bull and bear regimes (LTC bull=+223bp, bear=+185bp; BTC bull=+59bp, bear=+114bp). Slightly stronger in bear (higher ask-side pressure realization). Not regime-fragile.

## Failure classification

**Primary failure**: `GRAVEYARD_R3_PERM_TEST_INSUFFICIENT` — 0/8 symbols meet elite gate `perm_sigma ≥ 4.0`; only 2/8 reach marginal `perm_sigma ≥ 2.0`.

**Secondary concerns**:
1. Directional asymmetry: only SHORT side works; LONG side (A_focus) is universally negative. Hypothesis validity is halved.
2. Regime-emergence: signal did not exist in first 4 months of sample. True out-of-sample validation impossible until 2026 H2 data accumulates.
3. Sample density: daily-frequency signal → 50-70 events per symbol; insufficient for elite gate discrimination even before considering multiple testing correction across 9 cells × 4 quadrants = 36 tests.

## Lessons candidates (novel patterns not yet in Q3 catalog)

**Lesson candidate #80**: Book-depth `imbalance_mean` daily z-score as bilateral swing predictor is directionally asymmetric — SHORT side (z<=-thr → downside) shows real ~2σ perm-test signal on select syms, LONG side (z>=+thr → upside) is uniformly negative. Bilateral hypothesis reduces to unilateral SHORT-only survivor, halving effective breadth. Future book-depth paradigms should R-0 halt bilateral hypotheses and pre-declare unilateral scope.

**Lesson candidate #81**: Rolling z-score signals on 12-month sample yield ~50-70 events per (sym, direction). Elite gate `perm_sigma ≥ 4.0` requires ~200+ events. Daily-frequency substrates need multi-year data OR sub-daily aggregation OR broader universe expansion (30+ syms) BEFORE R-1 dispatch to have any chance of clearing elite gate. R-0 should compute `expected_n_events_per_sym_per_direction × n_universe_syms` and halt if the product is < 1500 (which would empirically give per-sym `perm_sigma` distribution median < 2.0).

**Lesson candidate #82**: When temporal-thirds split shows sign flip (early negative, mid/late positive), the effective sample size is materially less than reported. R-3 should down-weight `n_trades` by the fraction of the sample that exhibits sign-consistent behavior. This paradigm effectively had ~8 months of real signal not 12, further eroding perm-test power.

## Artifacts

- `backend/scripts/research/paradigm_236_book_depth_imbalance_z_r1.py`
- `backend/scripts/research/paradigm_236_book_depth_imbalance_z_r2.py`
- `backend/scripts/research/paradigm_236_book_depth_imbalance_z_r3.py`
- `backend/runs/research_track/alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d/r1__metrics.json`
- `backend/runs/research_track/alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d/r2__metrics.json`
- `backend/runs/research_track/alt_book_depth_imbalance_mean_rolling_z_bilateral_swing_1d_to_3d/r3__metrics.json`

## No promotion action

No paper spec written. No `tier_promotion_queue.json` mutation. No live session touched.
