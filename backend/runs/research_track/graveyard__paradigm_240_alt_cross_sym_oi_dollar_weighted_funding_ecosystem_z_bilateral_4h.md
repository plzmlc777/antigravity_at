# Graveyard — paradigm 240: alt_cross_sym_oi_dollar_weighted_funding_ecosystem_z_bilateral_4h

**Date**: 2026-07-29
**Final phase**: R-0-GRAVEYARD (halt before R-1 dispatch)
**Verdict**: `SAMPLE_INSUFFICIENT_STRUCTURAL_ASYMMETRY_DWFE_DISTRIBUTION`
**Lessons cited**: #11 (sample density), #23 (boundary sparse trigger), #28 (substrate availability), #40 (structural asymmetry)

## Hypothesis
OI-dollar-weighted aggregate funding ecosystem z-score:
```
DWFE(t) = sum_i [OI_usd_i(t) * funding_i(t)] / sum_i [OI_usd_i(t)]
DWFE_z(t) = (DWFE - roll_mean_90) / roll_std_90
```
Bilateral mean-reversion at |DWFE_z| >= 2.0.

## R-0 Substrate + Empirical Prescreen

### Substrate reality (Lesson #28)
- `binance_funding_rate`: 26 syms, 2023-11-15 → 2026-07-28 (2.7yr)
- `binance_open_interest_hist` (interval_str='5m'): **14 syms only**, **2026-04-05 → 2026-07-28 (114 days = ~4 months)**
- Overlap universe = 14 syms (AVAX/AXS/COMP/DOGE/ETC/HBAR/JUP/LDO/LINK/PYTH/SOL/TON/UNI/WLD)
- OI 1d interval has only 6 syms × 30 days — even worse.

Aligned funding+OI at 8h funding timestamps yields **681 raw aggregate timestamps**, **592 measurable after 90-period rolling-z warmup**.

### Empirical DWFE distribution (built from full 592 measurable window)
| Percentile | DWFE (bp) | DWFE_z |
|---|---|---|
| min | -25.03 | **-9.19** |
| p01 | -4.21 | -3.11 |
| p10 | -0.95 | — |
| p50 | -0.01 | — |
| p90 | +0.50 | — |
| p99 | +0.93 | **+1.87** |
| max | +6.08 | +4.29 |
| mean | -0.22 | — |
| std  | 1.44 | — |

Distribution is **heavily asymmetric-negative** — the sampled window (Apr → Jul 2026) had universe DWFE persistently negative (aggregate funding leaned short-biased), so z-scores concentrate on the negative tail. p99 of z is only +1.87, meaning the SHORT trigger at z>=+2.0 is **structurally infeasible-sparse in this window**.

### Trigger event counts (Lesson #11 / #23)
| T | LONG (z≤-T) | SHORT (z≥+T) | Total | Trigger rate | Min quadrant | Pass ≥30/quad? |
|---|---|---|---|---|---|---|
| 1.5 | 44 | 13 | 57 | 9.63% | 13 | FAIL |
| 2.0 (primary) | 28 | 5 | 33 | 5.57% | **5** | **FAIL** |
| 2.5 | 17 | 3 | 20 | 3.38% | 3 | FAIL |
| 3.0 | 9 | 3 | 12 | 2.03% | 3 | FAIL |

At **every tested threshold**, the SHORT quadrant is below Lesson #11/23 floor of 30 events. Even the relaxed T=1.5 fails (13 SHORT triggers).

### Root causes
1. **Lesson #28 substrate insufficient**: OI substrate covers only 114 days. This is too short (a) to smooth a persistent regime bias out of the aggregate DWFE distribution and (b) to accumulate the events needed for a 12-cell threshold×hold sweep with Bonferroni multiple-testing survival (Lesson #62 needs perm_p ≤ 0.004).
2. **Lesson #40 structural asymmetry**: DWFE is technically bilateral (can be pos or neg), but in the current 4-month sample the empirical distribution's positive tail is far shallower than the negative tail (max z only +4.29 vs min z -9.19; p99 only +1.87). The bilateral entry logic depends on both quadrants being adequately populated; this window structurally violates that.
3. **Lesson #11 sample density**: Even accepting LONG-only variant (which the hypothesis does not propose), n_long=28 at T=2.0 falls short of the 30/cell floor once we further stratify by hold (2h/4h/8h) and TS-CV folds. Per-cell density collapses.
4. **Lesson #62 multiple testing**: 4 thresholds × 3 holds = 12-cell sweep would require perm_p ≤ 0.004; with n_short<15 in any cell, permutation resolution alone cannot achieve that.

### Sub-hypothesis rescue considered — REJECTED
- **Long-only variant** (drop bilateral): Would need to reframe as unilateral mean-reversion trigger only on z≤-T. Original hypothesis explicitly proposes bilateral mechanism ("captures macroscopic funding burden"), and the mechanism claim is symmetric (over-leveraged long → reversal AND over-leveraged short → bounce). Dropping the short side abandons the mechanism claim; belongs in a separate paradigm registration.
- **Percentile-rank reformulation** (per Lesson #40 rescue prescription): Applicable when the raw signal is non-negative aggregate. Here the signal is signed, so reformulation would not help — the underlying imbalance is truly asymmetric in the sample, not a distribution-side artifact.
- **Backfill OI history 2yr**: Would require large REST-API scrape (14 syms × 5m × 2.5yr ≈ 3.7M rows). Per backfill discipline (10GB cap, no parallel downloader), this is a substantial infrastructure task, not an R-0 rescue. Enqueue as infrastructure candidate, not paradigm 240 revival.

## Decision
Halt at R-0. Do not dispatch R-1. Register in INDEX as `R-0-GRAVEYARD`.

## Follow-up recommendations
1. **Infrastructure task candidate**: Backfill `binance_open_interest_hist` at 15m or 1h interval for 14+ syms × 2yr, to enable a substrate window that spans multiple funding-regime cycles. Bandwidth estimate: 15m × 14 syms × 730d ≈ 980k rows via REST (well under 10GB). This unlocks paradigm 240 revival and several adjacent ecosystem-aggregate paradigms.
2. **Adjacent paradigm proposal**: Once OI substrate is expanded, an alternative formulation using per-quantile-rank of DWFE (empirical CDF) instead of parametric z-score could sidestep the asymmetric distribution issue.
3. **Sub-family lesson**: Ecosystem-aggregate signals over ≤6-month OI windows are prone to persistent one-sided regime bias — treat "bilateral" claims with skepticism until ≥12-month substrate exists.

## Artifacts
- `backend/scripts/research/paradigm_240_r0_diagnostic.py`
- `backend/runs/research_track/paradigm_240_.../r0_diagnostic.json`
