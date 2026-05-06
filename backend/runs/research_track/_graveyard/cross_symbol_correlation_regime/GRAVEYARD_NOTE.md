# cross_symbol_correlation_regime — Graveyard Note (2026-05-05)

## Hypothesis
Rolling 288-bar (24h) average pairwise correlation across the 10-symbol paper-pool universe (HBAR/AXS/COMP/DOGE/LDO/SOL/AVAX/LINK/UNI/ETC) defines a market dispersion regime. High avg-corr (> 0.85, q90) regime = "all together" market move → fade recent direction (mean-revert as macro pressure releases). Low avg-corr regime = idiosyncratic. Direction signal: target's recent 12-bar pct change.

## Distinct from prior 13 graveyard + 2 seeded
- All graveyard/seeded paradigms operate on single-symbol time-series (moments, autocorr, funding rate)
- This paradigm is **pool-wide cross-section dispersion** — average off-diagonal of N×N correlation matrix over rolling window
- Orthogonal regime dimension (passes self-check criterion 3 in runbook §8)

## Phase R-1 (SOLUSDT)
| Spec | direction | filter | hi/lo | alpha | sharpe | trades |
|---|---|---|---|---|---|---|
| baseline | fade | both | 0.65/0.35 | -55.87 | -2.66 | 3821 |
| q10/q90 follow | follow | both | 0.85/0.555 | -42.96 | -3.99 | 801 |
| q10/q90 fade | fade | both | 0.85/0.555 | +1.72 | -0.57 | 801 |
| fade lo_only | fade | lo_only | 0.85/0.555 | small | -0.84 | 226 |
| fade hi_only | fade | hi_only | 0.85/0.555 | small | -0.38 | 575 |
| follow lo_only | follow | lo_only | 0.85/0.555 | small | -1.93 | 227 |
| follow hi_only | follow | hi_only | 0.85/0.555 | -ve | -3.53 | 574 |

avg_corr distribution: mean 0.715, q10 0.555, q50 0.731, q90 0.85 — market is structurally co-moving.

R-1 single-SOL: all sharpe < 0; best fade hi_only -0.38. Single-symbol fail criterion (need alpha+ sharpe+).

## Phase R-2 (10 paper-pool symbols, fade hi_only)

### Spec extreme (hi=0.90, lo=0.50, hold=24, dir=12)
- alpha pos **10/10** (mean +54.84), sharpe pos **10/10** (mean 0.481)
- Best LDO: alpha **91.28** / sharpe 0.749 / mdd 69.22 / wr 52.38 / **PF 2.046** — cutoff 2/5 (PF + WR)
- Best UNI: alpha 49.65 / sharpe 0.558 / mdd 61.09 / wr 48.51 / PF 1.645 — cutoff 0/5
- Best DOGE: alpha 56.28 / sharpe 0.556 / mdd 57.08 / wr 45.10 / PF 1.584 — cutoff 0/5
- Best AXS: alpha 58.6 / sharpe 0.10 / PF 1.26 — cutoff 0/5

### Spec h72 (hi=0.85, lo=0.555, hold=72, dir=24)
- alpha pos 9/10 (mean +56.04), sharpe pos 10/10 (mean 0.484)
- Best AXS: alpha 109.81 / sharpe 0.803 / mdd 59.7 — cutoff 0/5
- Best UNI: alpha 93.14 / sharpe 0.811 / mdd 66.99 — cutoff 0/5

**MDD systematically 50-80%** across all symbols and specs (cutoff 28%). Buy-hold OOS strongly negative (-36% to -67%) → fade direction generates "alpha" partially via negative-market downside protection.

## Phase R-3 (perm test n=200, fade hi_only extreme spec)

| Symbol | alpha | sharpe | mdd | wr | pf | trades | **perm_p** | random_mean |
|---|---|---|---|---|---|---|---|---|
| LDOUSDT | 91.28 | 0.749 | 69.22 | 52.38 | 2.046 | 105 | **0.170** ❌ | 34.21 |
| UNIUSDT | 49.65 | 0.558 | 61.09 | 48.51 | 1.645 | 101 | **0.395** ❌ | 19.41 |
| DOGEUSDT | 56.28 | 0.556 | 57.08 | 45.10 | 1.584 | 102 | **0.225** ❌ | -19.03 |

**All perm_p > 0.05.** Random-shuffle alpha mean 19-34 (LDO/UNI), -19 (DOGE) — random shuffles routinely produce comparable alpha → real signal not distinguishable from noise.

## Verdict: 🪦 graveyard

### Decisive failures
1. perm_p 0.170 / 0.395 / 0.225 all > 0.05 — failed robustness gate
2. Best alpha 91 < 150 cutoff (61% of cutoff). Best PF 2.046 (LDO). All MDD > 50% (cutoff 28%)
3. funding_window_anomaly perm_p=0.095 / vol_regime_breakout 0.115-0.135 / funding_flip 0.125+ pattern repeated — alpha 10/10 + sharpe 10/10 systematic-looking but actually downside-protection artifact in negative-drift OOS window

### Lesson
- 5min cross-symbol correlation (mean 0.715 across pool) is structurally too high → "low" vs "high" regime band too narrow to provide robust edge
- Pool-wide dispersion regime as a paradigm dimension is orthogonal to all prior single-symbol paradigms but **at 5min granularity, the regime signal lacks edge in conjunction with simple directional triggers**
- Multi-symbol consistency (alpha 10/10 pos, sharpe 10/10 pos) is NOT robustness — perm test still required to separate true signal from systematic biases (e.g. fade-direction in negative-drift OOS)

### Future variants to consider (not auto-promote)
- Daily cross-correlation regime (longer timeframe may have wider dispersion bands)
- Pairwise-corr **shock** event (sudden regime change) instead of regime level threshold
- Cross-corr × volatility joint signal

## Artifacts
- `r1_sol_*__metrics.json` (7 R-1 sweeps)
- `r2_multi10_*__metrics.json` (3 R-2 multi-symbol)
- `r3_robust__{LDO,UNI,DOGE}USDT.json` (3 R-3 perm tests)
- `r3_summary.csv`
- `scripts/poc_cross_symbol_correlation_regime.py` (kept for archive — universe loader + rolling avg-pairwise-corr utility could be reused)
- `scripts/poc_cross_symbol_correlation_regime_r3.py` (kept for archive)
