# partial_autocorr_regime — Graveyard Note (2026-05-05)

## Hypothesis
Rolling 288-bar lag-2 PARTIAL autocorrelation of 5m returns isolates the
direct lag-2 dependence after controlling for lag-1 effects. AR(1) effects
(captured by autocorr_regime, R-3 perm 0.000 PASS, seeded LINK/UNI) are
subtracted. Closed-form: PACF[2] = (ρ_2 - ρ_1²) / (1 - ρ_1²).

## Distinct from prior paradigms
- autocorr_regime (seeded LINK/UNI): lag-1 PACF = ρ_1 directly
- partial_autocorr_regime: lag-2 PACF — direct lag-2 dependence beyond lag-1
- skewness/kurtosis_regime (graveyard): single-time-point distribution shape
  vs PACF time-axis dependence

## Phase R-1 (SOLUSDT) — Hurst-trap signal observed
SOL pacf2 distribution: q[10,50,90] = [-0.11, -0.01, +0.08] (narrow band).

27 sweeps (regime_filter × {0.05, 0.10, 0.15} threshold × {12, 24, 72} hold):

Best: rev_only t=0.15 h=72 — alpha 41.65 / sharpe 0.39 / 100 trades / PF 1.17

Hurst-trap pattern: threshold 0.05 → sharpe -0.59~-2.05 (bad), 0.10 → sharpe
-0.04~-2.03 (mixed), 0.15 → sharpe 0.20~0.39 (sparse positive).

## Phase R-2 (10 paper-pool, rev_only t=0.15 h=72)

| Symbol | alpha | sharpe | mdd | wr | pf | trades |
|---|---|---|---|---|---|---|
| **ETCUSDT** | **94.03** | **0.774** | 22.85 | 48.23 | 1.553 | 141 |
| **UNIUSDT** | 78.81 | 0.725 | 61.80 | 52.31 | 1.737 | 130 |
| LINKUSDT | 40.94 | 0.474 | 64.99 | 50.00 | 1.385 | 116 |
| LDOUSDT | 26.72 | 0.460 | 80.44 | 42.28 | 1.405 | 149 |
| DOGEUSDT | 43.16 | 0.447 | 65.61 | 44.64 | 1.382 | 112 |
| SOLUSDT | 41.65 | 0.391 | 20.79 | 51.00 | 1.168 | 100 |
| AVAXUSDT | 18.99 | 0.316 | 70.69 | 37.21 | 1.335 | 86 |
| HBARUSDT | 31.50 | 0.236 | 59.52 | 47.22 | 1.147 | 144 |
| AXSUSDT | 54.04 | 0.226 | 36.00 | 41.86 | 1.059 | 172 |
| COMPUSDT | -15.64 | -0.254 | 65.05 | 38.20 | 0.887 | 178 |

- alpha pos **9/10** (mean +41.42), sharpe pos **9/10** (mean 0.38)
- Best ETC: cutoff **2/5** (mdd ✅ + trades ✅; alpha 63%, sharpe 39%, wr 48<50, PF 1.55<2.0)

## Phase R-3 (perm test n=200, top 3)

| Symbol | alpha | sharpe | trades | **perm_p** | random_mean |
|---|---|---|---|---|---|
| **ETCUSDT** | 94.03 | 0.774 | 141 | **0.0250** ✅ | 18.31 |
| UNIUSDT | 78.81 | 0.725 | 130 | **0.1050** ❌ | -9.35 |
| LINKUSDT | 40.94 | 0.474 | 116 | **0.3950** ❌ | 3.79 |

## Hard Gate Evaluation (best candidate ETC)

- 정량 cutoff: alpha 94/150=63% ❌, sharpe 0.77/2.0=39% ❌, mdd 22.85✅, wr 48.23<50❌, PF 1.55<2.0❌ — **1/5**
- Robustness: perm_p 0.025 ✅, WF skipped, vf 미의존 ✅, trades 141 ✅ — **3/4**
- Total: **4/9**

→ Far below paper-seed candidates:
  - autocorr_regime LINK (seeded): alpha 116, sharpe 1.25, PF 3.33, perm 0.000 — 5/8
  - funding_dispersion ETC (seeded): alpha 138, sharpe 3.50, PF 3.72, perm 0.000 — 7/9

## Verdict: 🪦 graveyard (16th)

## Decisive lesson

**lag-2 PACF is a weak residual of lag-1 ACF in this market.**

The autocorr_regime paradigm already captures the dominant lag-1 dependence
signal (LINK perm 0.000, alpha 116, sharpe 1.25 — clean strong signal).
PACF[2] subtracts ρ_1² from ρ_2, leaving the direct lag-2 dependence. Real
market data has only weak residual lag-2 structure beyond lag-1 — typical
for AR(1)-dominated processes. Result: same family, ~70% magnitude vs
seeded autocorr_regime, doesn't pass elite cutoff.

ETC perm_p 0.025 = real signal exists, but magnitude inadequate. Hold-bars
(72 = 6h) was the only rescue from Hurst-trap (lower thresholds → sharpe
negative), suggesting the residual signal mostly fades within 6 hours.

**Future autocorr-family explorations not recommended:**
- lag-3+ PACF: even weaker residual after lag-1+lag-2 controlled
- ACF threshold variants: redundant with autocorr_regime
- Cross-symbol lag autocorrelation (lead-lag): different dimension, candidate
  but not for "autocorr family"

## Anti-pattern §3-G (provisional NEW)

**Family-extension paradigm**: extending a successful paradigm to a related
statistic in the same family (e.g. lag-1 → lag-2/3/PACF; mean → variance →
skew → kurt; rolling z → z² → z³) typically yields a weaker residual signal,
not a separate orthogonal signal. The first member captures the dominant
effect; subsequent members reflect residuals after the dominant effect is
subtracted. Only orthogonal *paradigm dimensions* (cross-section z vs
time-series z; price vs funding vs OI) yield genuinely independent signals.

Future paradigms should explore new dimensions, not within-family extensions.

## Artifacts
- `scripts/poc_partial_autocorr_regime.py` (PoC simulator)
- `scripts/poc_partial_autocorr_regime_r3.py` (perm test n=200)
- `r1_sol_baseline__metrics.json` + 27 sol_*  sweep csvs
- `r2_multi10_rev_t0.15_h72__metrics.json` + per_symbol.csv
- `r2_multi10_trend_t0.05_h72__metrics.json` (trend variant — sharpe 4/10 only)
- `r3_robust__{ETC,UNI,LINK}USDT.json`
- `r3_summary.csv`
