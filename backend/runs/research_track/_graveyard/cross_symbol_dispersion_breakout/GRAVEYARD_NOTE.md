# cross_symbol_dispersion_breakout — Graveyard Note (2026-05-05)

## Hypothesis
Cross-section std of 5m log returns across 10 paper-pool universe at each
instant measures market vol dispersion. Compression regime (low pct
dispersion) = coiled-spring breakout in recent direction. Expansion regime
(high pct) = chaos reversal of recent direction.

## Distinct from prior paradigms
- cross_symbol_correlation_regime (graveyard, perm 0.17-0.39): contemporaneous
  CORRELATION matrix avg → market co-movement regime
- This paradigm: cross-section STD of returns (vol spread regime)
- Same cross-section family — §3-G family-extension risk anticipated

## Phase R-1+R-2 (10 paper-pool, multiple specs)

Default thresholds (p_low=0.20/p_high=0.80, hold=24):

| spec | alpha_pos | sharpe_pos | sharpe_mean | trades |
|---|---|---|---|---|
| low_only | **0/10** | 0/10 | -3.367 | 35,968 |
| high_only | 0/10 | 0/10 | -2.183 | 36,035 |
| both | 0/10 | 0/10 | -2.134 | 43,615 |

→ ~3500 trades/symbol — fee-bleeding overactive.

Extreme threshold sweep (p_low=0.05, p_high=0.95, hold=72), all 6 variants:

| spec | alpha_pos | sharpe_pos | sharpe_mean | trades |
|---|---|---|---|---|
| pl=0.05 ph=0.95 both | 4/10 | 5/10 | **-0.028** | 14,844 |
| pl=0.05 ph=0.95 low_only | 4/10 | 2/10 | -1.038 | 11,429 |
| pl=0.10 ph=0.95 both | 2/10 | 4/10 | -0.216 | 15,876 |
| (others) | 1-4/10 | 1-3/10 | -0.5 to -1 | 11k-16k |

best (extreme/both): sharpe_mean ≈ 0 with 5/10 sharpe pos — borderline noise
class, not signal.

## Verdict: 🪦 graveyard (20th). R-3 perm test SKIPPED (decisive R-2 fail)

## Lesson — anti-pattern §3-G 3rd confirmation: cross-section family saturation

The cross-section paradigm family now has 3 attempts:
- ✅ **funding_dispersion** (cross-section FUNDING RATE z) — seeded ETC, perm 0.000
- 🪦 cross_symbol_correlation_regime (cross-section CORR matrix) — graveyard
- 🪦 cross_symbol_dispersion_breakout (cross-section VOL std) — graveyard

Pattern: cross-section in PRICE/VOL data domain produces noise (corr, vol);
cross-section in FUNDING RATE domain produces signal (funding_dispersion).

Hypothesis: 5min price/vol cross-section is dominated by market-wide systemic
movement (BTC dominance, news-driven crypto-wide swings) → low informational
content for individual-symbol prediction. Funding rates are per-symbol leverage
positioning — cross-section measures peer-relative crowd extremes, which
genuinely predicts reversal.

→ **Cross-section family also saturated** (1/3 hit rate). Future cross-section
exploration only meaningful in non-price/vol data domains (positioning, OI,
basis spread when 1y backfilled).

## Anti-pattern §3-G refined (2026-05-05 update)

Family-extension is anti-pattern when within the SAME data domain:
- autocorr family (lag-1 seeded → lag-2 graveyard)
- funding family (level seeded → window/flip/acceleration graveyard)
- cross-section price/vol family (corr graveyard → dispersion graveyard)

Cross-section family is NOT one monolithic "domain" — different data sources
behave differently. funding_dispersion succeeded because funding rate domain
has crowd-positioning signal that price/vol cross-section lacks.

## Artifacts
- `scripts/poc_cross_symbol_dispersion_breakout.py`
- `r2_multi10_{low_only,high_only,both}__per_symbol.csv` (3 baseline)
- `extreme_pl{0.05,0.10}_ph{0.90,0.95}_{low_only,high_only,both}__per_symbol.csv` (12 extreme sweeps)
