# time_of_day_seasonality — Graveyard Note (2026-05-05)

## Hypothesis
Certain UTC hours-of-day exhibit persistent forward-return bias across the
training window (Asian/EU/US sessions overlap, exchange margin call hours,
funding boundaries adjacent to liquidity gaps). bias[h] = mean forward N-bar
log return per hour h in train_frac=0.5 IS period. Test period entries:
bias[h] > +entry_thresh → LONG, < -entry_thresh → SHORT, hold N bars.

## Distinct from prior paradigms
- All single-symbol moment / autocorr / funding-rate paradigms ignore time
- funding_window_anomaly (graveyard): used 8h funding boundaries with z-score
  reversal — distinct from 24h-cycle hour bias
- 24h cycle bias is pure time-axis effect dimension

## Phase R-1 (SOLUSDT) — anti-pattern detected

bias_max 6.59 bps (IS bias magnitude inherently small).

| spec | trades | alpha | sharpe |
|---|---|---|---|
| ez=2bps/h=12 | 6890 | -66.07 | **-6.44** |
| ez=4bps/h=6 | 6391 | -65.89 | **-10.13** |
| ez=4bps/h=12 | 3234 | -58.02 | -4.79 |
| ez=4bps/h=24 | 2847 | -56.39 | -3.29 |
| ez=4bps/h=36 | 2086 | -59.68 | -4.05 |
| ez=6bps/h=6 | 2410 | -51.82 | -5.35 |
| ez=6bps/h=12 | 1228 | -26.68 | -2.54 |
| ez=6bps/h=24 | 1227 | -31.63 | -2.10 |
| ez=6bps/h=36 | 869 | -29.49 | -1.84 |
| ez=8bps+ | 0 (above bias_max) | 33.49 (BH only) | 0 |

All non-zero-trade specs sharpe < 0. SOL R-1 fail criterion (alpha+ sharpe+).

## Phase R-2 (10 paper-pool, ez=6bps/h=12)

bias_max ranges 6.5 (ETC) ~ 11.93 (LINK) bps across symbols.

- alpha pos: **2/10** (AVAX +6.84, ETC -8.20 closest)
- sharpe pos: **1/10** (AVAX 0.19 only)
- alpha mean -18.85%, sharpe mean -0.944
- 18,328 total trades

Far worse than every prior multi-symbol-consistency-but-perm-fail graveyard
(funding_window_anomaly: alpha 10/10 / sharpe 5/10; vol_regime_breakout: alpha
10/10 / sharpe ~6/10). Even surface consistency absent.

## Decisive failure: in-sample optimization anti-pattern

bias[h] estimated from train period's mean forward return per hour-of-day
captures noise more than signal. With 24 hour bins × ~115k 5min bars = ~4800
bars/bin in train, the IS bias has wide CI (~1bps standard error per bin)
relative to the bias magnitude (max 6-12 bps). Multiple-comparison expected
false-positive count: ~2-3 hours show "significant" bias by chance alone.

OOS the bias signs flip randomly — even-driven bias was train-period noise.
This is a textbook in-sample optimization failure that no R-3 perm test
would rescue (perm test on price would just confirm randomness; perm test on
the bias map itself reveals it's random fluctuation that doesn't generalize).

## R-3 perm test SKIPPED

R-1 + R-2 evidence is decisive — no candidate symbol has sharpe ≥ +1.0,
let alone the cutoff 2.0. Spending compute on perm test would not change
the verdict.

## Verdict: 🪦 graveyard (15th)

## Lesson — anti-pattern §3-F (NEW)
**In-sample optimization paradigm**: any paradigm that estimates a parameter
set or bias map from a train period and applies it to OOS suffers from
multiple-testing inflation. Estimated quantities (bias[h], best-fit
parameters per symbol) carry IS noise that does not generalize.

Successful paradigms in this track all use **data-derived signals computed
in real-time** (rolling z-score, lagged autocorrelation, cross-section z) —
never a "discovered best parameter from train period." This rules out time-
of-day, day-of-week, calendar-event, and similar table-lookup paradigms.

Future candidate paradigms should be screened on this dimension at design
time (anti-pattern §3-F in runbook).

## Artifacts
- `scripts/poc_time_of_day_seasonality.py`
- `r1_sol_baseline__metrics.json`
- `sol_h{6,12,24,36}_t{2,4,6,8,12}bps__metrics.json` (16 sweeps)
- `r2_multi10_t6bps_h12__metrics.json`
