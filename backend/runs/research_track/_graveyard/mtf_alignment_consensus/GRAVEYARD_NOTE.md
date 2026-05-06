# mtf_alignment_consensus — Graveyard Note (2026-05-06)

## Hypothesis
alignment_score = sign(R_5m) + sign(R_1h) + sign(R_4h) ∈ {-3, ..., +3}.
|align| ≥ MIN_ALIGN → enter sign(align) (continuation) or -sign(align) (fade).

## Distinct from prior paradigms (cross-timeframe within-symbol consensus)
NEW dimension not previously explored. Theoretical orthogonality with all
seeded paradigms (autocorr lag-1 single-TF, funding 8h, cross-symbol
lead-lag).

## Phase R-1 SOL — catastrophic over-trading

alignment distribution (very dense, NOT rare-event):
- |align|=3: 22042+21345 = 43387 (19% of bars)
- |align|=1: 34621+34087 = 68708 (30% of bars)
- align=0: 936 (0.4%)

16 sweeps (align ∈ {2,3} × dir ∈ {follow,fade} × hold ∈ {6,12,24,48}):

| spec | trades | alpha | sharpe | mdd |
|---|---|---|---|---|
| align=3 follow h=6 | 13948 | -66.42 | -13.65 | 100.0 |
| align=3 follow h=48 | 2421 | -52.44 | -2.07 | 90.0 (best!) |
| align=3 fade h=48 | 2475 | -55.49 | -2.11 | 93.3 |
| align=2 fade h=48 | 2472 | -56.23 | -2.19 | 93.7 |

**All 16 sweeps**: sharpe -2 to -14, mdd 90-100% (capital wipeout). No spec
yielded positive alpha or sharpe.

## Phase R-2 (10 paper-pool, best SOL spec align=3 fade h=48)

- alpha pos **0/10** (mean -47.55), sharpe pos **0/10** (mean -1.621)
- mdd 90-98% across all symbols
- 25,223 total trades

## Verdict: 🪦 graveyard (20th). R-3 perm test SKIPPED (decisive R-1/R-2 fail)

## Decisive lesson — multi-TF momentum continuation hypothesis is FALSE for crypto 5m

The hypothesis "5m/1h/4h alignment → next bars continue" is fundamentally
WRONG at this granularity:

1. **5m sign is noisy** (random-walk-like at 5-min granularity). Adding 1h
   and 4h signs filters some of that, but |align|=3 occurs TOO frequently
   (19% of bars = ~3 times/hour) — not a rare strong signal but a common
   regime indicator.
2. **|align|=3 mid-trend = peak/trough proximity**: by the time 3
   timeframes align, momentum is often exhausted. fade hypothesis
   (-sign(align)) was tested and equally fails — meaning neither
   continuation NOR reversal is predictable from MTF alignment alone.
3. **Over-trading without edge**: at 19% of bars with entry triggers,
   fee bleeding alone destroys equity. mdd 100% indicates persistent
   small losses adding to capital wipeout.

This is different from the §3-A rare-event Hurst-trap (where threshold
lowering kills sharpe). Here, even VERY rare specs (|align|=3, 19%) fail —
paradigm doesn't have edge at any threshold level.

## Conclusion: cross-TIMEFRAME consensus paradigm NOT viable in 5m crypto

Future explorations should avoid: any paradigm relying on multi-timeframe
sign agreement at 5min. 1h+4h alignment alone (without 5min noise) might
still have value for daily timeframe paradigms — TBD when daily setups
become elite-gate candidates.

## Artifacts
- `scripts/poc_mtf_alignment_consensus.py` (PoC simulator)
- `r1_sol_baseline*` (initial R-1)
- `sol_a{2,3}_{follow,fade}_h{6,12,24,48}__per_symbol.csv` (16 SOL sweeps)
- `r2_multi10_a3_fade_h48__per_symbol.csv` (R-2 best spec, 0/10 paradigm fail)
