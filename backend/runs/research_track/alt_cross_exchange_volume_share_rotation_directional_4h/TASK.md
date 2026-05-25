# Paradigm 160 TASK — alt_cross_exchange_volume_share_rotation_directional_4h

**Dispatched**: 2026-05-21 16:14 KST
**Phase**: R-1 (EXECUTED)
**Result**: `BROAD_FALSIFIED_FEE_FLOOR` (4-quadrant SNT, Lesson #56 12th instance OUTCOME-LEVEL family proxy)

## Hypothesis
Bybit ↔ Binance Futures 24h cumulative volume share rotation × per-symbol
directional 4h hold.

- **Trigger**: per-sym 4h bar `share = bybit_qv / (bybit_qv + binance_qv)` (quote-volume USDT).
  Rolling 7d (42 × 4h bars) z-score. `|z| ≥ 2.0`.
- **Mechanism (claimed)**: bybit share spike → bybit-side aggressive flow → continuation LONG 4h;
  bybit share dump → binance-side aggressive flow → continuation SHORT 4h.

## R-0 inventory prescreen (Lesson #61 amendment 2nd post-confirmation dogfood)

### Slug grep (mandatory)
```
ls research_track/ | grep -iE "cross_exchange|volume_share|bybit"
→  alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h
   alt_bybit_to_binance_lead_lag_oi_delay_directional_4h
   cross_asset_volume_share_high_alt_long_1d
   cross_exchange_funding_spread_binance_bitget_alt
   cross_exchange_funding_spread_binance_bybit_alt_directional_8h
   cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h
```

### Cross-exchange family graveyard cumulative table (Tier 4 retire confirmed at §6.45)
| # | Paradigm | Statistic class | Verdict |
|---|---|---|---|
| 103 | cross_exchange_funding_spread_binance_bybit_8h | funding spread + z | BROAD_FALSIFIED_FEE_FLOOR |
| 104 | cross_exchange_oi_level_differential_binance_bybit_4h | OI level diff + z | BROAD_FALSIFIED_PRIMARY_HOLD |
| 105 | cross_exchange_funding_spread_binance_bitget_8h | funding spread (illiquid venue) | DISPATCH_IMPOSSIBLE |
| 147v1 | bybit_to_binance_lead_lag_oi_same_bar | OI lead-lag (same-bar) | DNA 6/6 inventory halt |
| 147v2 | bybit_to_binance_lead_lag_oi_delay_4h | OI lead-lag (time-shift) | INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION |
| 148 | bybit_to_binance_lead_lag_PRICE_delay_4h | PRICE lead-lag | BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG |
| **160** | **cross_exchange_volume_share_rotation_4h** | **volume share z** | **BROAD_FALSIFIED_FEE_FLOOR** (this dispatch) |

Cumulative: **7 cross-exchange family graveyards** (8 incl. cross_asset paradigm 94/95 volume share family Tier 4 retire is a separate axis).

### Family-distinct strict 4-dim audit vs prior cross-ex 6
| Dim | priors | paradigm 160 | Strict |
|---|---|---|---|
| Statistic class | funding spread / OI lead-lag / PRICE lead-lag | volume share rotation z | ✅ STRICT NEW |
| Universe | 7 deep-syms | 7 deep-syms | identical |
| Entry-side class | funding/OI/price spike z | volume share spike z | ⚠ partial (z-class same, axis different) |
| Mechanism alpha | cross-ex arbitrage / lead-lag | liquidity migration drift | ✅ STRICT NEW |

Strict count: **2/4 boundary** (Lesson #62 ≥2 strict 충족, dispatch authorized).

## R-1 4-quadrant SNT result

| Quadrant | n | gross_bp | net_bp | sigex | perm_p | ci_lo_bp | q_pos | syms_ci+ | 3gate | conc |
|---|---|---|---|---|---|---|---|---|---|---|
| A_focus_pos_z_LONG | 1248 | **+10.03** | -5.97 | +4.90 | 0.0000 | -16.39 | 0.30 | 0/7 | FAIL | FAIL |
| A_mirror_pos_z_SHORT | 1248 | -10.03 | -26.03 | +2.00 | 0.0255 | -37.44 | 0.00 | 0/7 | FAIL | FAIL |
| B_focus_neg_z_SHORT | 634 | **-9.39** (WRONG direction) | -25.39 | +0.77 | 0.2300 | -37.27 | 0.20 | 0/7 | FAIL | FAIL |
| B_mirror_neg_z_LONG | 634 | +9.39 | -6.61 | +3.28 | 0.0005 | -19.22 | 0.30 | 0/7 | FAIL | FAIL |

Window: 2024-02-07..2026-04-30 (815d, 34146 rows, 100% data window ratio Lesson #30 PASS).
Triggers: pos_z=1248 (3.66%), neg_z=634 (1.86%). |z|≥2.0 empirical 5.51% (Lesson #11 per-cell ≫30 PASS).

## Verdict reasoning

### 1. **BROAD_FALSIFIED_FEE_FLOOR** (primary)
All 4 quadrants gross |bp| ∈ [9.39, 10.03] — all sub-16bp fee floor.
A focus gross +10.03bp positive direction confirmed (consistent with bybit-spike→LONG continuation thesis), but net -5.97bp after fee, ci_lo -16.39, 0/7 syms ci+.

### 2. **Lesson #56 OUTCOME-LEVEL family proxy 12th instance** (cross-exchange family)
- Cross-exchange 6 prior graveyards all fee-floor sub-threshold or substrate-impossible
- Paradigm 160 7th cross-ex graveyard, OUTCOME same fee-floor convergence
- **Cross-exchange family Tier 4 retire 7 cumulative** (formal retire §6.45 + paradigm 160 reinforcement)

### 3. **Lesson #39 perfect mirror antipattern (sub-class A broad-uniform-negative) 4th dogfood**
- A_focus +10.03bp vs A_mirror -10.03bp: **exact perfect mirror** (within 0.01bp)
- B_focus -9.39bp vs B_mirror +9.39bp: **exact perfect mirror** (within 0.01bp)
- Trigger has zero directional info (Lesson #39 sub-class A definition)
- Mirror PASS (mechanical sigex+) but ci negative + concentration 0/7 = no real alpha

### 4. **Lesson #8 universal LONG bias 6th dogfood**
- A LONG (bybit spike → LONG) gross +10.03bp / B LONG (bybit dump → LONG) gross +9.39bp
- Both directional LONG quadrants positive but indistinguishable from baseline 4h LONG drift in 2024-2026 crypto bull regime
- A SHORT and B SHORT both negative gross → leverage-shock magnitude/general upward bias
- Paradigm 160 LONG-positive but B_focus_SHORT WRONG direction = mechanism inverted

### 5. **Lesson #21 axis stacking sub-finding** (volume share single-axis FAIL)
- Volume share rotation z-score = single statistic, single mechanism (liquidity migration)
- No axis stacking, yet broad-falsified
- Consistent with volume share family (paradigm 94/95 cross-asset Tier 4 retire) extending to cross-exchange axis

### 6. **Lesson #16 Concentration Gate** all 4 quadrants 0/7 syms ci+
- per-symbol bootstrap CI lower bp: all negative across all 4 quadrants
- A_focus best sym AVAX +13.57bp ci_lo -19.72 (still negative)
- A_focus worst sym BCH -36.10bp (deeply negative)
- No symbol-level alpha → not even narrow-scope viable

### 7. **Lesson #30 data window ratio** 815d/851d = 0.958 PASS (Mint-grade)

## Substrate audit (Lesson #28)

| Source | Endpoint | n bars/sym | Window |
|---|---|---|---|
| Binance 4h klines | `ohlcv_cache_12col` | 4920 | 2024-02-01 .. 2026-04-30 |
| Bybit 4h klines | V5 `/v5/market/kline` interval=240 | 5106 | 2024-01-01 .. 2026-04-30 (backfilled this dispatch, 9.6s wall) |
| Paired (inner join) | open_time match | 4837 per sym × 7 = 34146 | 2024-02-07 .. 2026-04-30 |

Bybit 4h klines cache `backend/runs/ohlcv_cache/bybit_klines_4h/` is new permanent asset (∼1MB total, 7 syms × ~140KB).

## Mechanism diagnostic (paradigm 160 → cross-exchange family lessons)

**Liquidity migration ≠ directional alpha**:
- Bybit share spike (bybit-side aggressive flow): real microstructure event but **directional bias absorbed by Binance perp price** within same 4h bar (cross-venue price arbitrage forces same-bar convergence)
- 4h forward return shows only general LONG-direction bias (10bp ≈ 0.25bp/hour ≈ 4h drift consistent with annualized ~22% from 2024-2026 bull regime)
- B side (bybit dump = binance aggressive) gross -9.39bp WRONG direction → either mechanism story incorrect, or sub-class B binance aggressive is **distribution-side** rather than accumulation-side

**Cross-exchange family universal pattern (7 cumulative)**:
| Statistic | Family fee-floor outcome | Reason |
|---|---|---|
| funding spread (103/105) | fee-floor sub | rate-difference too small (≤14bp gross) |
| OI level/lead-lag (104/147) | fee-floor sub | OI diff arbitrage absorbed cross-venue |
| PRICE lead-lag (148) | fee-floor sub + directional bias | no genuine lead-lag, just bull-drift |
| VOLUME share rotation (160) | fee-floor sub + perfect mirror | volume migration absorbed same-bar |

**Universal mechanism**: cross-exchange spread/imbalance/migration statistics on **liquid majors (7-deep universe)** are **continuously arbitraged within ≤1 bar at 4h+ frame** → gross alpha sub-fee-floor.

## Files
- backfill: `backend/scripts/research/paradigm160_backfill_bybit_4h.py`
- R-1: `backend/scripts/research/paradigm160_r1.py`
- metrics: `backend/runs/research_track/alt_cross_exchange_volume_share_rotation_directional_4h/r1/r1__metrics.json`
- task: this file
- graveyard: `backend/runs/research_track/graveyard__alt_cross_exchange_volume_share_rotation_directional_4h.md`
- bybit 4h cache (permanent): `backend/runs/ohlcv_cache/bybit_klines_4h/{SYM}_4h.joblib` × 7

## Lesson cross-references
- Lesson #56 CONFIRMED 12th instance (cross-exchange family OUTCOME-LEVEL proxy)
- Lesson #62 CONFIRMED 5th dogfood (family-distinct 2/4 strict, dispatch authorized but OUTCOME proxied)
- Lesson #39 sub-class A 4th dogfood (perfect mirror antipattern, broad-uniform-negative)
- Lesson #8 universal LONG bias 6th dogfood (LONG-positive both A and B, SHORT-negative both)
- Lesson #21 axis stacking sub-finding 7th candidate (single-axis volume share also fails)
- Lesson #16 Concentration Gate 0/7 syms ci+ all 4 quadrants
- Lesson #30 data window ratio PASS 0.958
- Lesson #61 amendment 2nd post-confirmation dogfood (slug grep + DNA 4-dim + family-retire cross-reference table all executed, identified Tier 4 retire family + dispatch with informed acceptance)
