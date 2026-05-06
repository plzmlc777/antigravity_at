# information_entropy_regime — Graveyard Note (2026-05-05)

## Hypothesis
Shannon entropy of binned 5m log returns over rolling 288-bar window. Low
entropy regime = compressed market (returns clustered) → continuation entry.
High entropy regime = chaotic market → reversal entry.

## Distinct from prior paradigms
- moments family (graveyard): single distribution shape statistic
- autocorr/partial_autocorr (lag-1 seeded, lag-2 graveyard): time-axis dependence
- entropy: distribution UNCERTAINTY/INFORMATION (multi-modal sensitive)

But practical reality: discrete binned entropy on Gaussian-like 5m returns
is dominated by std component (= vol). Differential entropy ∝ log(σ) for
normal returns. Multi-modal/skewed distributions register slightly different,
but the dominant signal is just vol level dressed up.

## Phase R-1 (SOLUSDT) — Hurst-trap pattern

| spec | trades | alpha | sharpe |
|---|---|---|---|
| both p=0.20/0.80 | 2220 | -52.24 | -2.58 |
| low_only p=0.20 | 1088 | -13.92 | -1.04 |
| high_only p=0.80 | 1147 | -43.72 | -3.19 |
| low_only p=0.10 h=48 | 326 | +15.37 | -0.24 |
| high_only p=0.90 h=48 | 355 | -0.71 | -1.01 |
| **low_only p=0.05 h=72 dir=24** | **145** | **+28.54** | **+0.16** |

threshold 극단에서만 sharpe 양수 — rare-event anti-pattern §3-A 시사.

## Phase R-2 (10 paper-pool, low_only p=0.05/h=72/dir=24)

| Symbol | alpha | sharpe | mdd | wr | pf | trades |
|---|---|---|---|---|---|---|
| **LDOUSDT** | **117.98** | **1.283** | 23.91 | 46.84 | 1.366 | 158 |
| **UNIUSDT** | 62.46 | 0.565 | 20.36 | 43.45 | 1.162 | 145 |
| LINKUSDT | 44.66 | 0.302 | 10.27 | 46.58 | 1.062 | 146 |
| SOLUSDT | 28.54 | 0.156 | 23.49 | 45.52 | 1.035 | 145 |
| HBARUSDT | (?) | ... | ... | ... | ... | ... |

- alpha pos 9/10 (mean +42), sharpe pos 5/10 (mean -0.26)
- Best LDO: cutoff **1/5** (mdd ✅; alpha 79%, sharpe 64%, wr 47<50, PF 1.37<2.0)

## Phase R-3 (perm test n=200, LDO/UNI)

| Symbol | alpha | sharpe | trades | **perm_p** | random_mean |
|---|---|---|---|---|---|
| LDOUSDT | 117.98 | 1.283 | 158 | **0.0600** ⚠️ | 25.79 |
| UNIUSDT | 62.46 | 0.565 | 145 | **0.1600** ❌ | -16.46 |

LDO perm 0.06 = 12/200 random shuffles ≥ real alpha — borderline FAIL (>0.05).

## Hard Gate (best LDO): **4/9**
- 정량 1/5 (mdd만)
- Robustness 3/4 (perm 0.06 borderline fail + trades 158 + vf 미의존)

→ same magnitude class as partial_autocorr ETC (4/9, perm 0.025): both fail
elite gate by similar margins. No paper-seed candidate.

## Comparison vs seeded paradigms
| paradigm | symbol | alpha | sharpe | PF | perm_p | gate |
|---|---|---|---|---|---|---|
| funding_dispersion | ETC | 138 | 3.50 | 3.72 | 0.000 | 7/9 ✅ seeded |
| autocorr_regime | LINK | 116 | 1.25 | 3.33 | 0.000 | 5/8 ✅ seeded |
| funding_carry | AXS | 149 | 1.48 | 2.53 | 0.000 | 6/8 ✅ seeded |
| partial_autocorr | ETC | 94 | 0.77 | 1.55 | 0.025 | 4/9 🪦 grave |
| **information_entropy** | **LDO** | **118** | **1.28** | **1.37** | **0.06** | **4/9 🪦 grave** |

→ Seeded paradigms uniformly perm 0.000 with PF ≥ 2.5; weak paradigms cluster
at perm 0.025-0.10 with PF ~1.4. Decisive separation.

## Verdict: 🪦 graveyard (17th)

## Lesson — entropy is not orthogonal to vol/moments

Practical discrete entropy on 5m log returns is dominated by std component
(differential entropy ∝ log(σ) for normal). Multi-modal sensitivity exists
in theory but is washed out by Gaussian dominance in real returns. So this
paradigm partially overlaps `vol_regime_breakout` (graveyard) and the
moments family (skew/kurt graveyard), explaining the same weak-signal class
result (perm 0.060, sharpe 1.28).

Future direction: if information-theoretic measures are explored, prefer
**transfer entropy** or **mutual information across symbols** (cross-symbol
information flow) — those are genuinely different from single-series
distribution measures.

## Artifacts
- `scripts/poc_information_entropy_regime.py` (PoC simulator)
- `scripts/poc_information_entropy_regime_r3.py` (perm test)
- `r1_sol_baseline*.json`, `sol_low_only*.json`, `sol_high_only*.json`,
  `sol_low_only_extreme*.json`, `sol_low_extreme_long*.json`
- `r2_multi10_low_extreme__metrics.json` + per_symbol.csv
- `r3_robust__{LDO,UNI}USDT.json`, `r3_summary.csv`
