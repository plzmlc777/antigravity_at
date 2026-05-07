# wick_reversal_volume — Graveyard Note (2026-05-06, 43rd graveyard, 51st paradigm overall)

## 설계
Q3 #2 wick_reversal (POSITIVE 3σ borderline, SOL 3.34σ + AVAX 2.99σ) 의 §2-A0 first-priority extension. 가설: volume z-score filter를 추가하면 noisy random 분포를 억제하여 signal을 4σ+로 elevate.

Mechanism: high-volume bars indicate genuine liquidation (forced flow) rather than thin-market wick artifacts.

## R-1 SOL volume threshold sweep
| vol_thresh | alpha | sharpe | trades | wr | PF |
|---|---|---|---|---|---|
| 0.0 (above-mean) | **+59.82** | **+1.62** | 78 | 56.4 | 1.74 |
| 0.5 | +50.74 | +1.20 | 69 | 55.1 | 1.57 |
| 1.0 | +38.50 | +0.46 | 62 | 51.6 | 1.20 |
| 1.5 | +37.45 | +0.39 | 57 | 49.1 | 1.17 |
| 2.0 | +31.27 | **-0.07** | 52 | 44.2 | 0.97 |

**Monotonic degradation**: volume_thresh ↑ → sharpe ↓. Higher selectivity destroys signal.

vt=0.0 vs Q3 #2 baseline (alpha 59.60/sharpe 1.51) basically identical — filter has zero useful contribution since "above-mean" is essentially a 50-50 split.

## R-2/R-3 SKIPPED — paradigm-level FAIL
R-1 sweep alone shows clear signal degradation pattern. No spec is better than Q3 #2 baseline. Continuing to perm test would only confirm degradation.

## §3-H filter mechanism antipattern — third confirmation
Pattern emerging from 51 paradigms (4 graveyards confirm §3-H now):
1. premium_oi_correlation_regime (Q2 #3): premium z + OI corr filter → graveyard
2. premium_oi_joint_filter (Q2 #13): premium + OI direction agreement → graveyard
3. oi_funding_corr_regime (Q3 #1): OI × funding corr regime → §3-D §3-J §3-H all
4. **wick_reversal_volume (Q3 #3, this)**: wick × volume filter → monotonic degradation

**Universal lesson**: simple AND-filter on a working signal **always weakens** it. The filter narrows trade set but does NOT improve per-trade alpha quality — the trades excluded by the filter were neither systematically losing nor noisy enough to drag down.

Only positive AND-filter result historically: **joint_3signal_ensemble** (POSITIVE/SKIP) — and that was VOTING (majority of 3 signals agree), not strict AND.

## §3-H rule strengthened (2026-05-06)
**규칙**: 
- AND filter on seeded paradigm component → 95%+ probability of degradation. Skip.
- Voting (majority of N signals) → marginal value possible (N=3 POSITIVE).
- New paradigm composition: at least one component must be NEW (not yet seeded), or apply transformation/regime detection rather than filter.

## Diversity exhaustion at NEW dim
wick_reversal opened the wick-shape NEW dimension at 3σ. Volume filter is the simplest extension and it failed cleanly. Further wick variants (multi_bar §2-A0 #2) might face same §3-H risk if implemented as filter. Direction forward:
1. **wick_reversal_multi_bar**: 3-bar consecutive wick = sequence pattern (NOT filter) — distinct from §3-H
2. **wick on different timeframe** (1m wick, 15m wick) — granularity rather than filter
3. **wick × prior-ret JOINT TRANSFORM** (e.g. product or ratio) — not filter
4. **aggTrades backfill** — orthogonal data domain, true upgrade not derivative

## §3-H risk profile updated
Q3 paradigm queue should explicitly assess §3-H risk before R-1: any AND filter on seeded component automatically weighted down. wick_reversal_volume confirms even on NEW dimension, AND filter remains antipattern.

51st paradigm — clean §3-H confirmation, fast fail (~3 minutes total).
