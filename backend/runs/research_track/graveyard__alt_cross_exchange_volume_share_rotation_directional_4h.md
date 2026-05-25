# Paradigm 160 — `alt_cross_exchange_volume_share_rotation_directional_4h` GRAVEYARD

**Verdict**: `BROAD_FALSIFIED_FEE_FLOOR` (R-1 executed, 4-quadrant SNT, Lesson #56 12th instance + Lesson #39 sub-class A 4th dogfood + Lesson #8 6th dogfood + cross-exchange family Tier 4 retire 7th cumulative)
**Date**: 2026-05-21 16:16 KST
**Phase**: R-1 (executed, R-2 NOT dispatched)
**Sequence**: 160 (R-5 yield 10/160 = 6.25%, 31-streak non-PASS milestone)
**Compute committed**: 9.6s Bybit 4h backfill + 0.6s R-1 = ~10s total

## TL;DR
Bybit ↔ Binance Futures 24h cumulative quote-volume share z(7d) ≥|2|×4h hold directional: 4-quadrant SNT all gross |bp| ∈ [9.39, 10.03] sub-16bp fee floor. A_focus +10.03bp mechanically PASS sigex+4.90 but ci_lo -16.39 + 0/7 syms ci+ + perfect mirror A_focus vs A_mirror (within 0.01bp) = Lesson #39 sub-class A broad-uniform-negative. B_focus -9.39bp gross WRONG direction (mechanism inverted). Cross-exchange family Tier 4 retire (§6.45) **7th cumulative graveyard** reinforces fee-floor OUTCOME convergence on liquid 7-deep universe at 4h+ frame.

## Hypothesis
- **Trigger**: per-sym 4h `share = bybit_qv / (bybit_qv + binance_qv)` (quote-vol USDT), rolling 7d z-score, |z|≥2.0
- **Mechanism (claimed)**: bybit share spike → bybit-side aggressive flow → continuation LONG 4h; bybit share dump → binance-side aggressive flow → continuation SHORT 4h

## R-0 inventory prescreen (Lesson #61 amendment 2nd post-confirmation dogfood)

### Slug grep + DNA 4-dim audit (mandatory, performed)
- 6 prior cross-exchange family directories detected: 103/104/105/147v1/147v2/148
- Family-distinct strict 4-dim count: 2/4 boundary (statistic class + mechanism alpha new; universe + entry-side class shared)
- Cross-exchange family Tier 4 retire CONFIRMED at §6.45 (6 cumulative pre-160). paradigm 160 dispatched with informed user acceptance + Lesson #56 OUTCOME-level family proxy verify mandate.

### Family-distinct outcome
2/4 strict (boundary) — dispatch authorized but **OUTCOME proxy 12th instance confirmed**: family Tier 4 retire reinforces.

## R-1 4-quadrant SNT result

| Quadrant | n | gross_bp | net_bp | sigex | perm_p_above | ci_lo_bp | q_pos_t_ratio | syms_ci+ | 3-gate | conc |
|---|---|---|---|---|---|---|---|---|---|---|
| A_focus pos_z LONG | 1248 | **+10.03** | -5.97 | +4.90 | 0.0000 | -16.39 | 0.30 (3/10) | 0/7 | **FAIL** | **FAIL** |
| A_mirror pos_z SHORT | 1248 | -10.03 | -26.03 | +2.00 | 0.0255 | -37.44 | 0.00 (0/10) | 0/7 | FAIL | FAIL |
| B_focus neg_z SHORT | 634 | **-9.39** (inverted) | -25.39 | +0.77 | 0.2300 | -37.27 | 0.20 (2/10) | 0/7 | FAIL | FAIL |
| B_mirror neg_z LONG | 634 | +9.39 | -6.61 | +3.28 | 0.0005 | -19.22 | 0.30 (3/10) | 0/7 | FAIL | FAIL |

Window: 2024-02-07 .. 2026-04-30 (815d, 34146 rows). Triggers: pos_z=1248 (3.66%), neg_z=634 (1.86%). Lesson #11 PASS, Lesson #30 0.958 PASS.

## Failure axes (decisive)

### A. Lesson #56 OUTCOME-LEVEL family proxy 12th CONFIRMED instance (cross-exchange family)
- 7 cumulative cross-ex paradigm graveyards (103/104/105/147v1/147v2/148/160) all fee-floor sub-threshold or substrate-impossible
- Volume share axis was sub-axis "untouched" pre-paradigm 160 — verified untouched, but family OUTCOME convergence proxied
- **Mechanism**: cross-venue spread/imbalance/migration statistics are continuously arbitraged within ≤1 bar at 4h+ frame on liquid 7-deep universe → gross alpha permanently sub-fee-floor

### B. Lesson #39 sub-class A perfect mirror antipattern 4th dogfood (broad-uniform-negative)
- A_focus +10.03bp vs A_mirror -10.03bp (within 0.01bp = exact mirror)
- B_focus -9.39bp vs B_mirror +9.39bp (within 0.01bp = exact mirror)
- Trigger has zero directional information; mechanical sigex > 2.0 on LONG quadrants reflects only general 4h LONG drift (Lesson #8 LONG bias)
- Confirms: PASS_R1 mechanical on A_focus = substantively falsified at Lesson #39+#8 antipattern level

### C. Lesson #8 universal LONG bias 6th dogfood (CONFIRMED 자격 promotion reinforced)
- A LONG +10.03bp / B LONG +9.39bp both positive (gross before fee)
- A SHORT -10.03bp / B SHORT -9.39bp both negative
- B_focus claimed SHORT direction = WRONG direction (mechanism inverted)
- Asymmetry direction = 2024-2026 crypto bull regime baseline LONG drift, not volume share rotation alpha

### D. Lesson #16 Concentration Gate **0/7 syms ci+ across all 4 quadrants**
- A_focus per-sym (LONG): AVAX +13.57 / SOL +5.07 / DOGE +9.80 (positive but none ci_pos) / BCH -36.10 / LINK -20.84 deeply negative
- B_focus per-sym (SHORT): all negative gross (mechanism inverted on B side)
- No narrow-scope subset viable

### E. Lesson #62 family-distinct strict 5th dogfood (CONFIRMED 자격 reinforced 5 dogfoods)
- 2/4 strict count boundary case → dispatch executed → OUTCOME proxied
- Lesson #62 PASS does not protect against Lesson #56 OUTCOME-level family proxy (statistic class new ≠ outcome new in retired-axis family)
- Sub-finding: Lesson #62 + Lesson #56 joint application — Lesson #56 dominates over Lesson #62 boundary cases in retired-axis families

### F. Lesson #21 axis-stacking sub-finding 8th candidate (single-axis non-protection)
- Volume share is single-axis (statistic class single, mechanism single)
- No axis stacking, but broad-falsified → confirms axis-stacking is symptom not cause
- Single-axis novelty within retired-axis family is insufficient

### G. Lesson #61 amendment 2nd post-confirmation dogfood SUCCESS (procedural)
- Slug grep executed (6 prior cross-ex slugs detected)
- DNA 4-dim audit table provided (2/4 boundary)
- Family-retire eligibility cross-reference table provided (Tier 4 retire detected at §6.45)
- User dispatched with informed acceptance + Lesson #56 verify mandate → OUTCOME confirmed proxied
- Amendment template strengthening **effective**: paradigm 160 dispatched with full informed prior, outcome documented as expected family-proxy 12th instance

## Cross-exchange family Tier 4 retire — 7 cumulative reinforcement

| # | Paradigm | Statistic | Verdict | Net effect |
|---|---|---|---|---|
| 103 | funding spread bybit 8h | funding spread + z | BROAD_FALSIFIED_FEE_FLOOR | fee-floor sub |
| 104 | OI level diff bybit 4h | OI level diff + z | BROAD_FALSIFIED_PRIMARY_HOLD | upward-bias trap + fee-floor at 480m |
| 105 | funding spread bitget 8h | funding spread (illiquid) | DISPATCH_IMPOSSIBLE | substrate fail (Lesson #28) |
| 147v1 | OI lead-lag same-bar | OI lead-lag | DNA 6/6 duplicate p104 | inventory halt |
| 147v2 | OI lead-lag time-shift 4h | OI lead-lag | INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION | Lesson #56 5th instance |
| 148 | PRICE lead-lag 4h | PRICE lead-lag | BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG | LONG bias not lead-lag |
| **160** | **VOLUME SHARE rotation 4h** | **volume share z** | **BROAD_FALSIFIED_FEE_FLOOR + perfect mirror** | **OUTCOME 12th instance, family Tier 4 retire 7th cumulative** |

**Cross-exchange family Tier 4 retire reinforcement** — 4 distinct statistic classes (funding / OI / PRICE / VOLUME) all converged to fee-floor sub-threshold OUTCOME on liquid 7-deep universe at 1h+ frame. **Next cross-exchange variants must change Universe (illiquid mid-tier venue Lesson #28-prescreened) OR Frame (<1h sub-frame Lesson #21 axis-stacking risk) OR Mechanism (non-z-score statistical class).**

## Substrate diagnostic + permanent assets
- Bybit 4h klines V5 `/v5/market/kline` interval=240: backfilled 7 syms × 5106 bars (2024-01-01..2026-04-30), 9.6s wall, ~1MB total
- New permanent cache: `backend/runs/ohlcv_cache/bybit_klines_4h/{SYM}_4h.joblib` × 7
- Reuse: Bybit 4h kline with full OHLCV+volume+turnover available — schema upgrade from prior `[ts, close]` 15m cache (paradigm 148)
- Future cross-exchange volume-axis dispatches at 4h frame can reuse this cache (zero re-backfill cost)

## Signal distribution diagnostic (Lesson #34)
| metric | value |
|---|---|
| share median | 0.297 (bybit ~30% share baseline) |
| share_z median | -0.058 |
| p90 \|z\| | 1.700 |
| p95 \|z\| | 2.046 |
| p99 \|z\| | 2.803 |
| max \|z\| | 5.368 |
| frac \|z\|≥2.0 | 5.51% |
| frac \|z\|≥2.5 | 1.85% |
| frac \|z\|≥3.0 | 0.64% |

Symmetric trigger rate (Lesson #34 PASS), thresholds achievable, no structural infeasibility.

## Campaign state update (post §6.57)
- Cumulative graveyards: 159 → **160** (substantive R-1 increment)
- R-5 LIVE: **10** (unchanged)
- Non-PASS streak: 30 → **31** milestone
- R-5 yield: 10/160 = **6.25%**
- Lessons: 34 confirmed + 20 candidates → 34 confirmed + 20 candidates (Lesson #8 6th dogfood ELIGIBLE for promotion, Lesson #39 sub-class A 4th dogfood, Lesson #62 5th dogfood, Lesson #56 12th instance, Lesson #61 2nd post-confirmation dogfood)
- Cross-exchange family Tier 4 retire: **7 cumulative** (formal retire §6.45 + paradigm 160 7th reinforcement)
- D-Day 2026-06-03 D-13

## Persistence policy compliance
- Lesson #61 amendment 2nd post-confirmation dogfood SUCCESS — procedural amendment effective
- continuous-parallel + persistence amendment maintained
- 31-streak non-PASS milestone noted as statistical noise, dispatch continuation policy intact
