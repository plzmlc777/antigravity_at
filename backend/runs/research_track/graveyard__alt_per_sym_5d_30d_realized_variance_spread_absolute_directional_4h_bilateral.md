# paradigm 195 graveyard — RV absolute spread (5d_mean_var - 30d_mean_var) z-spike 4-quadrant SNT

**Slug**: `alt_per_sym_5d_30d_realized_variance_spread_absolute_directional_4h_bilateral`
**Counter**: paradigm 195 (substantive)
**Date**: 2026-05-22
**Phase**: R-1 graveyard
**Verdict**: `BROAD_FALSIFIED_CONCENTRATION_FAIL`
**Host**: hcp_local (2.25yr ohlcv_cache_12col)
**Predecessor**: paradigm 194 ratio formulation CONCENTRATED_R1_PASS

## Hypothesis recap

paradigm 194와 same axis class (RV term-structure) but **absolute spread** formulation. 매 4h bar에서 per-sym 5d mean variance - 30d mean variance **raw difference** → 90d rolling z-score → z≥+2 spike trigger. 4h forward window directional bilateral 4-quadrant SNT.

**Lesson #40 dual-function test (CRITICAL)**: paradigm 194 ratio (5d_var / 30d_var) is bounded below by 0 → per-sym CI tight (0-14.3% syms_ci_pos). Hypothesis: absolute spread (unbounded) liberates CI dispersal → paradigm 195 concentration ≥ 30% → ratio-compression IS limiter.

## R-0 prescreen results

- **Lesson #61 slug grep audit**: `rv_spread|variance_spread|vol_spread|term_structure_spread`: 0 prior. PASS.
- **Lesson #11 sample density**: z>=+2 panel 3669/58814 (6.24%), expected per-cell per-quarter 203.8 — PASS (>=30)
- **Lesson #34 empirical distribution**: panel z percentiles p1=-1.81 / p50=-0.11 / p99=4.61. Right-skewed (vol expansion 12x more common than contraction).
- **Lesson #40 structural threshold feasibility**: z>=+2 reachable (6.24%) + z<=-2 reachable (0.52%) — bilateral CONFIRMED unlike paradigm 194 ratio.
- **Lesson #21 axis stacking**: single derived statistic, no stacking. PASS.
- **Lesson #28 substrate availability**: 14/14 syms × 4201 bars × 2.25yr verified. PASS.
- **Lesson #62 family-distinct**: paradigm 194 same axis class but distinct formulation (absolute vs ratio). Lesson #70 R-1 graveyard follow-up scope.

## R-1 4-quadrant SNT × 4-hold sweep (16 cells)

| cell | n | gross_bp | net_bp | obs_t | sigex | perm_p_above | ci_lower_bp | 3gate | conc | syms_ci_pos | lc4 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A_focus_h4h  | 580 | +9.18  | +1.18   | +0.10 | +1.17 | 0.124 | -23.31 | False | False | 0/14 | False |
| A_mirror_h4h | 580 | -9.18  | -17.18  | -1.40 | -0.38 | 0.642 | -41.08 | False | False | 0/14 | False |
| B_same_h4h   | 577 | -16.32 | -24.32  | -1.99 | -0.90 | 0.810 | -48.59 | False | False | 0/14 | False |
| B_mirror_h4h | 577 | +16.32 | +8.32   | +0.68 | +1.68 | 0.044 | -14.13 | False | False | 0/14 | False |
| A_focus_h8h  | 580 | +49.40 | +41.40  | +2.41 | +3.18 | 0.001 | **+7.77** | **True**  | False | 0/14 | False |
| A_mirror_h8h | 580 | -49.40 | -57.40  | -3.34 | -2.64 | 0.994 | -90.58 | False | False | 0/14 | False |
| B_same_h8h   | 577 | -3.84  | -11.84  | -0.66 | +0.09 | 0.457 | -48.93 | False | False | 0/14 | False |
| B_mirror_h8h | 577 | +3.84  | -4.16   | -0.23 | +0.48 | 0.311 | -37.17 | False | False | 0/14 | False |
| **A_focus_h12h** | **580** | **+71.03** | **+63.03** | **+3.20** | **+3.82** | **0.000** | **+23.51** | **True**  | False | 1/14 | False |
| A_mirror_h12h | 580 | -71.03 | -79.03 | -4.02 | -3.43 | 1.000 | -115.71 | False | False | 0/14 | False |
| B_same_h12h   | 577 | -37.86 | -45.86 | -2.23 | -1.64 | 0.957 | -87.52 | False | False | 0/14 | False |
| B_mirror_h12h | 577 | +37.86 | +29.86 | +1.45 | +2.05 | 0.019 | -7.49 | False | False | 0/14 | False |
| **A_focus_h24h** | 580 | +104.71 | **+96.71** | +3.24 | +3.68 | 0.000 | **+39.86** | **True** | False | 1/14 | False |
| A_mirror_h24h | 580 | -104.71 | -112.71 | -3.77 | -3.38 | 1.000 | -172.38 | False | False | 0/14 | False |
| B_same_h24h   | 577 | -90.26 | -98.26 | -3.80 | -3.42 | 1.000 | -148.99 | False | False | 0/14 | False |
| **B_mirror_h24h** | 577 | +90.26 | **+82.26** | +3.18 | +3.64 | 0.000 | **+35.67** | **True** | False | 1/14 | False |

**Sweep summary**:
- 4 cells three-gate PASS: A_focus_h8h, A_focus_h12h, A_focus_h24h, B_mirror_h24h
- 0 cells concentration PASS (max syms_ci_pos 1/14 = 7.1%, below 30% threshold)
- 0 cells life-changing 4-dim PASS

## Lesson #40 dual-function verdict: REJECTED

paradigm 194 (ratio) vs paradigm 195 (absolute) direct comparison in 3-gate PASS cells:

| cell | p194 sigex | p195 sigex | Δsigex | p194 syms_ci_pos | p195 syms_ci_pos | Δsyms |
|---|---|---|---|---|---|---|
| A_focus_h8h  | +2.31 | +3.18 | +0.87 | 1/14 | 0/14 | -1 |
| A_focus_h12h | +3.42 | +3.82 | +0.40 | 2/14 | 1/14 | -1 |
| A_focus_h24h | +3.07 | +3.68 | +0.62 | 2/14 | 1/14 | -1 |
| B_mirror_h24h | +2.72 | +3.64 | +0.92 | 0/14 | 1/14 | +1 |

**Result**: paradigm 195 sigex IMPROVES uniformly (+0.40 to +0.92, panel-mean signal stronger) but per-sym CI dispersal **REMAINS at universe limit** (max 1/14 = 7.1% vs p194 max 2/14 = 14.3% — actually marginally worse on average).

**Verdict**: `DUAL_FUNCTION_REJECTED` — absolute spread is NOT a per-sym alpha dispersal limiter. The ratio-compression in paradigm 194 was NOT the bottleneck. Concentration failure is a **universe-level structural limit** of the RV term-structure axis class itself, not formulation-induced.

**Mechanism explanation**: vol expansion bars (whether measured as ratio or absolute spread) capture a panel-wide regime feature (BTC-correlated vol spikes), not sym-idiosyncratic alpha. The signal magnitude scales with panel-wide regime intensity but per-sym noise dominates per-sym CI bounds. This is a universe-cohort property, not a statistic-formulation property.

## Lesson #42 7th dogfood verdict: CONFIRMED_HOLD_DEPENDENT

B_mirror vs B_same comparison across 4 holds:

| hold | B_mirror net_bp | B_mirror sigex | B_same net_bp | B_same sigex |
|---|---|---|---|---|
| 4h  | +8.32  | +1.68 | -24.32 | -0.90 |
| 8h  | -4.16  | +0.48 | -11.84 | +0.09 |
| 12h | +29.86 | +2.05 | -45.86 | -1.64 |
| 24h | **+82.26** | **+3.64** | **-98.26** | **-3.42** |

**B_mirror monotonically outperforms B_same across all 4 holds** — capitulation mean-reversion pattern (vol expansion + bar DOWN → LONG reversal) confirmed for absolute spread axis class, same as paradigm 194 ratio (hold-dependent).

**Cross-paradigm Lesson #42 chain**: 117/158/162/179/193/194/195 = 7/7 dogfoods CONFIRMED capitulation MR pattern. Lesson #42 universal across vol/drawdown/price-level/RV-ratio/RV-absolute axis classes.

**Important caveat**: B_mirror_h24h 3-gate PASS but conc FAIL (syms_ci_pos 1/14 = 7.1%), so Lesson #42 captures **panel-mean** pattern not actionable per-sym alpha at this universe.

## XRP cross-statistic-class winner verify: FALSIFIED

paradigm 194 (ratio): XRP A_focus_h12h n=43 mean=+189.78bp ci_lo=**+77.05bp** (ONLY ci_pos sym alongside LINK)
paradigm 195 (absolute): XRP A_focus_h12h n=40 mean=+67.94bp ci_lo=**-72.82bp** (LOST ci_pos status)

**XRP is NOT cross-statistic-class universal winner**. paradigm 194's XRP edge was ratio-specific (XRP's bounded vol distribution interacted favorably with ratio compression). LINK is the sole consistent winner (paradigm 194: +117.55bp ci_lo +3.43 / paradigm 195: +145.30bp ci_lo +26.28).

**Implication**: per-sym alpha attribution is FORMULATION-DEPENDENT, not axis-class-universal. Cross-paradigm sym winners are unreliable unless replicated across multiple formulation variants.

## Sparse-strict life-changing 4-dim audit

Best cell A_focus_h12h:
- trades_per_year: 580 / 2.25 = 257.8/yr → **PASS** (≥12)
- per_trade_edge_pct: 63.03 bp = 0.63% → **FAIL** (≥2.0% required)
- capital_util_pct: 257.8 × 12h / (365×24h) × 100 = 35.3% → **PASS** (≥30%)
- sharpe_ann: ~2.0 → **PASS** (≥1.5)

**FAIL** life-changing 4-dim on per-trade edge dimension (0.63% << 2.0% required). Same constraint as paradigm 194 (0.45% edge). Even with best-cell sigex 3.82, per-trade economics insufficient for life-changing strategy.

## paradigm 196 next-action recommendation

**RV term-structure axis class EXHAUSTED**:
- paradigm 69 BTC universal RV LEVEL → R-5 seeded (special case high-vol regime)
- paradigm 86 boundary streak persistence → SAMPLE_INSUFFICIENT
- paradigm 193 30d drawdown depth z → graveyard
- paradigm 194 5d/30d RV ratio z → CONCENTRATED_R1_PASS (3 cells 3gate but 0 conc)
- paradigm 195 5d/30d RV absolute spread z → BROAD_FALSIFIED_CONCENTRATION_FAIL (4 cells 3gate but 0 conc)

**Cumulative evidence**: RV term-structure axis universe-level concentration limit at 14-sym crypto alt cohort. Further formulation variants (e.g., log-ratio / Z-scored variance ratio / volatility risk premium) UNLIKELY to break per-sym CI dispersal floor given paradigm 194+195 confirmation.

**paradigm 196 candidate paths** (NEW axis class required):
1. **Cross-asset correlation regime breakdown** — BTC×ETH×SOL pairwise correlation z-score regime shift, NOT a vol/RV axis
2. **Liquidation cascade event-anchored** — Binance liquidation feed → cluster events → forward window (substrate availability prescreen needed)
3. **Funding-flip × OI-velocity 2D** — funding family Tier 4 retire but new joint-event axis stacking exception (Lesson #21 caveat)
4. **Time-of-day × volatility regime** — calendar anchor × vol stratify (paradigm 86 boundary lesson + calendar-DOW family combined)
5. **Open interest term structure (OI 1d vs OI 30d ratio)** — directly mirrors RV term-structure but on OI substrate, ESCAPES universe-level limit if OI dynamics decouple from vol regime

Recommended: **paradigm 196 = open interest term-structure (path 5)** — direct axis-class transplant from RV to OI substrate, leverages paradigm 22 funding_carry success on OI substrate (OI Mint cache available), tests whether universe-level concentration limit is RV-specific or universal across momentum-like axes.

## INDEX.json update

`INDEX.json` entry registered with verdict `BROAD_FALSIFIED_CONCENTRATION_FAIL`, sweep summary, and Lesson #40 dual-function rejection finding.

Backup: `INDEX.json.bak_paradigm195`.

## Lesson #69 5-item summary

1. **Verdict**: BROAD_FALSIFIED_CONCENTRATION_FAIL — 4 cells 3-gate PASS but 0 conc PASS, 0 lc4 PASS, max syms_ci_pos 1/14 = 7.1%
2. **Mechanism finding**: paradigm 194 ratio-compression NOT the limiter — absolute spread sigex +0.40~+0.92 stronger but per-sym CI dispersal unchanged (universe-level limit confirmed)
3. **Lesson #40 dual-function REJECTED**: ratio-compression and per-sym alpha dispersal are INDEPENDENT dimensions; ratio formulation is Lesson #40 compliance choice without dispersal trade-off
4. **Lesson #42 7th dogfood CONFIRMED hold-dependent**: B_mirror monotonically outperforms B_same across 4 holds, capitulation MR universal across RV-ratio + RV-absolute formulations
5. **paradigm 196 next**: NEW axis class required (RV term-structure exhausted at 14-sym crypto alt cohort), recommend OI term-structure transplant (path 5) or cross-asset correlation regime (path 1)
