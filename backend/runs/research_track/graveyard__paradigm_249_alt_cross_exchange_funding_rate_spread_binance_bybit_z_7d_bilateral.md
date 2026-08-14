# Graveyard: paradigm_249_alt_cross_exchange_funding_rate_spread_binance_bybit_z_7d_bilateral

- **Paradigm number**: 249
- **Phase halted**: R-1 (G1 backtest + tier3_gate G1 FAIL)
- **Verdict**: `BROAD_FALSIFIED_NO_AXIS_SYNTHESIS` (Lesson #39 sub-class A CONFIRMED — 7th dogfood application)
- **Date**: 2026-08-08 KST
- **Host**: Mint (autonomous dispatch)
- **Runtime**: R-1 backtest 2.9s, tier3_gate <1s

## One-sentence

Cross-venue Binance-Bybit funding rate spread rolling 30d z-score carries **zero directional information** at 7d hold: A_focus + A_mirror net returns sum to exactly -16bp (= -2×fee) across all 6 threshold×hold combinations — perfect symmetric mirror antipattern (Lesson #39 sub-class A), with tier3_gate G1 FAIL on the spuriously PASS_WEAK "best cell" (n=6, t=0.22).

## Predecessor paradigm 103 (2026-05-19)

Same substrate + universe + statistic + direction axes (4/5 DNA overlap; only hold dim differs). Paradigm 103 tested holds 60m/240m/480m/1440m → BROAD_FALSIFIED_FEE_FLOOR verdict, noted "A_focus 1440m sigex +2.12 still has ci_lower likely negative (not measured)". Runbook §N+5 explicitly recommended extending to 7d hold to close that untested branch.

**Result of 7d extension**: The antipattern deepens. At 8h/240m hold (paradigm 103) the spread had marginal directional information compressed below the 16bp fee floor. At 5d/7d/10d hold (paradigm 249) the spread has NO directional information at all — the A_focus and A_mirror cells are perfect mathematical negatives (sum = -16bp exactly = -2×0.08% fee).

## 5-axis DNA vs paradigm 103

| Axis | Status vs 103 |
|---|---|
| Data source | SAME (Binance × Bybit funding) |
| Statistic | SAME family (spread + rolling z; 30d window vs 90d) |
| Time scale | DIFFERENT (7d hold vs 8h/240m/1440m) |
| Universe | SAME (7 alts w/ dual-venue coverage) |
| Mechanism | SAME (cross-venue positioning imbalance) |

**4/5 SAME** — borderline DNA re-execution justified only by hold-axis novelty and explicit runbook recommendation. Now closed.

## Lesson #79 pretest (G0 stage)

|| SOL OOS corr | SOL full corr | BTC OOS corr | BTC full corr |
|---|---|---|---|---|
| spread_z vs fwd_7d_return | +0.0929 | +0.0302 | +0.1367 | +0.0440 |

Passed |corr| ≥ 0.02 cutoff on both symbols. **Lesson #79 alone is INSUFFICIENT** — a correlation of +0.09 at the daily aggregation level does not translate into net-positive edge above 16bp fee at extreme z thresholds. Even |corr|=0.14 for BTC did not save the R-1.

**Refinement candidate for Lesson #79**: predictive-content pretest with |corr| ≥ 0.02 admits mechanism-inverted or n-limited signals that fail R-1. Consider adding a bucket-sign consistency check (BTC bucket table showed z<=-2 → +116bp LONG-consistent but z>2 → +186bp SHORT-INCONSISTENT — should have flagged).

## 4-quadrant SNT results (Lesson #19, SOLUSDT primary, full data)

| Quadrant | T | hold | n | gross_bp | net_bp | sigex | ci_lo_bp | perm_p | verdict |
|---|---|---|---|---|---|---|---|---|---|
| A_focus (z≥+T→SHORT) | 1.5 | 5d | 18 | -273.4 | -281.4 | -0.94 | -764.5 | 0.310 | FAIL |
| A_mirror (z≥+T→LONG) | 1.5 | 5d | 18 | +273.4 | +265.4 | +0.96 | -194.2 | 0.331 | FAIL |
| A_focus | 2.0 | 5d | 6 | +586.6 | +578.6 | +2.17 | +24.7 | 0.106 | **PASS_WEAK** (spurious) |
| A_mirror | 2.0 | 5d | 6 | -586.6 | -594.6 | -2.18 | -1067 | 0.099 | FAIL |
| A_focus | 1.5 | 7d | 14 | -315.1 | -323.1 | -0.43 | -1214 | 0.526 | FAIL |
| A_mirror | 1.5 | 7d | 14 | +315.1 | +307.1 | +0.46 | -614 | 0.544 | FAIL |
| A_focus | 2.0 | 7d | 5 | +395.1 | +387.1 | +1.02 | -146 | 0.395 | FAIL |
| A_mirror | 2.0 | 7d | 5 | -395.1 | -403.1 | -1.01 | -1255 | 0.373 | FAIL |
| B_focus (z≤-T→LONG) | 1.5 | 5d | 15 | +85.1 | +77.1 | +0.10 | -502 | 0.837 | FAIL |
| B_mirror | 1.5 | 5d | 15 | -85.1 | -93.1 | -0.08 | -750 | 0.805 | FAIL |
| B_focus | 2.0 | 5d | 9 | +31.7 | +23.7 | -0.07 | -794 | 0.958 | FAIL |
| B_mirror | 2.0 | 5d | 9 | -31.7 | -39.7 | +0.09 | -1060 | 0.930 | FAIL |
| B_focus | 1.5 | 7d | 13 | +86.9 | +78.9 | +0.05 | -694 | 0.873 | FAIL |
| B_mirror | 1.5 | 7d | 13 | -86.9 | -94.9 | -0.03 | -974 | 0.854 | FAIL |
| B_focus | 2.0 | 7d | 8 | +11.8 | +3.8 | -0.09 | -1085 | 0.997 | FAIL |
| B_mirror | 2.0 | 7d | 8 | -11.8 | -19.8 | +0.12 | -1381 | 0.979 | FAIL |

(10d and T=2.5 cells omitted — same pattern; all FAIL, several INSUFFICIENT_SAMPLES.)

## Lesson #39 sub-class A antipattern — perfect symmetric mirror

Every {T, hold} A_focus/A_mirror pair sums to exactly -16bp (= -2 × 0.08% fee):

| T | hold | A_focus_net_bp | A_mirror_net_bp | sum_bp | exact -16bp? |
|---|---|---|---|---|---|
| 1.5 | 5d | -281.4 | +265.4 | -16.0 | YES |
| 1.5 | 7d | -323.1 | +307.1 | -16.0 | YES |
| 1.5 | 10d | -406.0 | +390.0 | -16.0 | YES |
| 2.0 | 5d | +578.6 | -594.6 | -16.0 | YES |
| 2.0 | 7d | +387.1 | -403.1 | -16.0 | YES |
| 2.0 | 10d | +438.9 | -454.9 | -16.0 | YES |

Same holds for B_focus + B_mirror pairs. **Direction-agnostic mechanism** — the trigger identifies dates where the fwd return happens to be non-zero in one direction, but the sign of that return is not predicted by the sign of the spread. Whichever direction you pick, the mirror gets exactly the opposite gross return.

Lesson #39 sub-class A verdict: "trigger has zero directional info, joint signal is pure direction-bet + fee drag."

## Spurious "PASS_WEAK" cell (T=2.0, hold=5d, A_focus)

The R-1 selector flagged (T=2.0, hold=5d, A_focus_shortHigh) as PASS_WEAK due to:
- n=6 trades
- sigex=+2.17 (barely above weak-gate 1.5)
- ci_lower_bp = +24.7 (barely positive)
- perm_p_two = 0.106 (barely above 0.10)

But its A_mirror twin cell (n=6, sigex=-2.18, ci_upper=-121bp, perm_p=0.099) is the perfect mathematical inverse. This is not a signal — it's a coin flip on 6 events where the outcome distribution happens to have non-zero mean.

**tier3_gate.py G1 confirmation**: n=6 < 20, time-weighted t = 0.22 (< 1.5 required), decay_ratio 0.41 (recent 1/3 edge 3.27% < past 1/3 edge 8.00% — declining). **G1 FAIL. Overall FAIL.** G2 PASSED (edge_after_1bar=5.79% > friction 0.10%, cycle_margin 5.0) but G1 blocks.

## Lesson #82 timestamp lookahead guard

Verified compliant. Entry price = `open_utc00.shift(-1)` (open of day AFTER trigger day). Exit price = `open_utc00.shift(-1 - hold_days)`. Spread signal computed at end of trigger day using funding rates through 16:00 UTC (3rd 8h cycle), with entry the following day at 00:00 UTC = ≥8h gap. No lookahead.

## Substrate freshness confirmed

- Binance funding SOL: 2991 rows through 2026-08-08
- Bybit funding SOL: 3035 rows through 2026-08-08 (extended today via ccxt V5)
- Merged spread daily n=354 dates (2023-11-15 → 2026-04-15 with 3-cycle-complete filter)
- OHLCV 1m cache: 862 midnight opens (2023-11-15 → 2026-08-01 range)

## Lessons stamped

- **Lesson #11 sample density** (9th application): T=2.5 cells INSUFFICIENT_SAMPLES (n≤5); T=2.0 A-side cells n=5-6 (marginal)
- **Lesson #19 Symmetric Negative Test joint-trigger** (executed correctly): all 4 quadrants in single batch, mirror-relationship revealed antipattern
- **Lesson #26 → tier3_gate G1** (6th application of automated post-R1 verification): correctly caught spurious PASS_WEAK due to sample size + time-weighted t
- **Lesson #28 substrate audit** (6th dogfood): PASS — Bybit V5 extended to current, Binance DB current
- **Lesson #39 sub-class A perfect symmetric mirror antipattern** (7th confirmed dogfood): all A_focus+A_mirror pairs sum exactly to -16bp (= -2×fee), zero directional info
- **Lesson #56 outcome-level family proxy**: cross-venue spread axis distinct from single-exchange level z (PASS at G0)
- **Lesson #61 slug grep**: OVERLAP found w/ paradigm 103 — proceeded on hold-axis novelty per runbook §N+5, now formally closed
- **Lesson #62 DNA 5-dim**: 4/5 SAME with 103; hold-axis novelty exhausted at 5d/7d/10d
- **Lesson #79 predictive-content pretest** (refinement candidate): |corr|≥0.02 admits mechanism-inverted/small-n signals; consider adding bucket-sign consistency check

## Family closure — cross-exchange funding spread

Cross-exchange funding rate spread family now exhausted across hold dimension:
- 8h cycle (paradigm 103): BROAD_FALSIFIED_FEE_FLOOR
- 240m (paradigm 103 sweep): FAIL
- 480m (paradigm 103 sweep): FAIL
- 1440m (paradigm 103 sweep): asymmetric signal noted but ci_lower not measured
- 5d / 7d / 10d (paradigm 249): BROAD_FALSIFIED_NO_AXIS_SYNTHESIS (Lesson #39 sub-class A)

**Total attempts**: 103 (Binance×Bybit 8h family), 104 (Binance×Bybit OI), 105 (Binance×Bitget substrate-fail), 249 (Binance×Bybit 7d hold extension). **4/4 fail across all tested time scales.**

**Family retire strengthened.** Re-open trigger: paid feed for illiquid venue with ≥1y history, or novel statistic axis (not spread level or z of spread — perhaps spread cross-symbol dispersion or spread-of-spread cross-venue meta-basket).

## Cross-references

- Predecessor: paradigm 103 (`cross_exchange_funding_spread_binance_bybit_alt_directional_8h`) — 8h fee-floor
- Sibling: paradigm 104 (`alt_bybit_to_binance_oi_delay_lead_lag_directional_4h`) — OI spread, Lesson #35 candidate
- Sibling: paradigm 105 (`cross_exchange_funding_spread_binance_bitget`) — substrate fail
- Lesson #39 predecessors: sub-class A paradigm 108, sub-class B paradigm 110

## Artifacts

- R-0 prescreen: `backend/runs/research_track/paradigm_249_alt_cross_exchange_funding_rate_spread_binance_bybit_z_7d_bilateral/r0_prescreen.json`
- R-1 script: `backend/scripts/research/paradigm249_cross_exchange_funding_spread_r1.py`
- R-1 metrics: `backend/runs/research_track/paradigm_249_alt_cross_exchange_funding_rate_spread_binance_bybit_z_7d_bilateral/r1_metrics.json`
- R-1 best-cell trades (spurious PASS_WEAK): `backend/runs/research_track/paradigm_249_alt_cross_exchange_funding_rate_spread_binance_bybit_z_7d_bilateral/r1_best_cell_trades.json`
- tier3_gate result (G1 FAIL): `backend/runs/research_track/paradigm_249_alt_cross_exchange_funding_rate_spread_binance_bybit_z_7d_bilateral/tier3_gate__SOLUSDT.json`
- Bybit funding cache (persistent, extended): `backend/runs/ohlcv_cache/bybit_funding/*.joblib` (8 files, through 2026-08-08)

## Halt confirmation

- R-1 only executed. R-2/R-3/R-4 NOT spawned. No enqueue to `tier_promotion_queue.json`.
- No live-session touch, no paper spec created.
- INDEX.json updated to register paradigm 249 → R1_GRAVEYARD.
