# funding_acceleration — Graveyard Note (2026-05-05)

## Hypothesis
Per-symbol Δfunding (first difference of funding rate) z-score reversal.
Δfunding > +ENTRY_Z → rate ramping up rapidly = long crowd accumulating →
SHORT entry; Δfunding < -ENTRY_Z → LONG entry. Exit at |z| < EXIT_Z, SL,
or max_hold.

## Distinct from prior funding paradigms
- funding_carry (seeded HBAR/AXS/COMP): rate LEVEL z (perm 0.000)
- funding_dispersion (seeded ETC): cross-section rate z (perm 0.000)
- funding_window_anomaly (graveyard): 5min seasonality at 8h boundaries
- funding_flip (graveyard): rate sign change continuation
- **funding_acceleration**: rate CHANGE z (positioning ramp speed)

## Phase R-1+R-2 (10 paper-pool, default ez=2.0/xz=0.5/mh=15/lb=30)

| Symbol | alpha | sharpe | mdd | wr | pf | trades |
|---|---|---|---|---|---|---|
| **COMPUSDT** | 54.12 | **1.524** | 8.63 | 50.00 | **1.916** | 20 |
| **SOLUSDT** | 57.16 | 1.125 | 14.53 | 61.11 | 1.633 | 18 |
| **ETCUSDT** | 57.94 | 1.012 | 10.62 | 63.16 | 1.588 | 19 |
| AXSUSDT | 40.92 | 0.90 | 21.1 | 58.6 | 1.314 | 29 |
| UNIUSDT | 48.24 | 0.51 | 14.8 | 50.0 | 1.245 | 20 |
| AVAXUSDT | 43.88 | 0.28 | 10.0 | 39.1 | 1.121 | 23 |
| DOGEUSDT | 28.05 | -0.76 | 18.2 | 42.1 | 0.725 | 19 |
| LDOUSDT | 36.42 | -1.03 | 25.8 | 43.5 | 0.641 | 23 |
| LINKUSDT | 26.20 | -1.57 | 26.5 | 40.9 | 0.539 | 22 |
| HBARUSDT | 29.91 | -1.96 | 25.7 | 47.8 | 0.441 | 23 |

- alpha pos **10/10** (mean +42.28), sharpe pos 6/10 (mean 0.003)
- COMP best cutoff 3/5 (mdd, wr, PF 96% near miss)

Sweep ez × xz (12 specs): all sharpe_mean 0 ± 0.2 stuck. ez=3.0 sparse
(27 trades total) — Hurst-trap signal weak. weak-signal cluster pattern.

## Phase R-3 (perm test n=200, COMP/SOL/ETC)

| Symbol | alpha | sharpe | trades | **perm_p** | random_mean |
|---|---|---|---|---|---|
| COMPUSDT | 54.12 | 1.524 | 20 | **0.095** ❌ | 31.24 |
| SOLUSDT | 57.16 | 1.125 | 18 | 0.105 ❌ | 39.96 |
| ETCUSDT | 57.94 | 1.012 | 19 | 0.165 ❌ | 46.03 |

**All perm_p > 0.05**. random_mean 31-46 = 2/3 of real alpha — funding rate
distribution itself produces comparable alpha by chance. Real signal not
distinguishable from noise at p=0.05 threshold.

## Hard Gate (best COMP): **3/9**
- 정량 3/5 (mdd ✅ + wr ✅ + sharpe 76% near miss; alpha 36%, PF 96% near miss)
- Robustness 0/4 (perm 0.095 fail, WF skipped, vf 미의존 ✅, trades 20 < 30)

→ Below partial_autocorr ETC (4/9) and information_entropy LDO (4/9). Weak.

## Verdict: 🪦 graveyard (19th)

## Decisive lesson — anti-pattern §3-G (family-extension) 2nd confirmation

- funding_carry HBAR (seeded): alpha 108, sharpe 1.87, PF 3.06, perm 0.000
- funding_acceleration COMP (graveyard): alpha 54, sharpe 1.52, PF 1.92, perm 0.095

The 1st derivative of a seeded paradigm's signal is a weak residual: rate
acceleration is LARGELY EXPLAINED BY rate level (extreme levels are reached
through extreme acceleration). The acceleration signal carries some
incremental information (perm 0.095 borderline = real but weak), but the
dominant predictive content is already in funding_carry's level z.

This confirms anti-pattern §3-G with a 2nd case:
1. partial_autocorr_regime (lag-2 PACF) was weak residual of autocorr_regime (lag-1)
2. funding_acceleration (Δfunding) is weak residual of funding_carry (level)

Future paradigm exploration must avoid within-domain derivatives/transforms
of seeded paradigms. Truly orthogonal dimensions only:
- Cross-symbol info flow (transfer entropy, lead-lag with proper coverage)
- New data domain (OI/positioning/L2 microstructure when 1y backfilled)
- Multi-timeframe interaction (e.g., daily vol regime gate × intraday reversal)

## Funding domain saturation note

Funding domain explored paradigms (5 total):
- funding_carry (level z) — ✅ seeded
- funding_dispersion (cross-section z) — ✅ seeded
- funding_window_anomaly (timing seasonality) — 🪦 graveyard
- funding_flip (sign change) — 🪦 graveyard
- **funding_acceleration (Δrate z) — 🪦 graveyard**

→ Funding domain has yielded 2 robust paradigms (level + cross-section) and
3 weak/null variants. Domain reasonably saturated. Future paradigm should
favor non-funding data domains.

## Artifacts
- `scripts/poc_funding_acceleration.py` (PoC simulator)
- `scripts/poc_funding_acceleration_r3.py` (perm test n=200)
- `r1_r2_baseline__metrics.json` + per_symbol.csv
- `sweep_ez{1.5,2.0,2.5,3.0}_xz{0.3,0.5,1.0}__per_symbol.csv` (9 sweeps)
- `r3_robust__{COMP,SOL,ETC}USDT.json`, `r3_summary.csv`
