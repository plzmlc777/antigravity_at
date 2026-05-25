# paradigm 166 — `alt_cross_exchange_oi_divergence_bybit_vs_binance_directional_4h`

**Status**: R-0 INVENTORY HALT — R-1 NOT DISPATCHED
**Verdict**: `R0_HALT_BY_DNA_DUPLICATE_PARADIGM_104_PRIOR_R1_BROAD_FALSIFIED_PRIMARY_HOLD`
**Date**: 2026-05-21 21:35 KST
**Counter**: 165 → 166 (substantive R-0 increment per paradigm 138/139/140/151/154/155/159/161/163/164/165 precedent)
**Dogfood**: Lesson #69 5-item strict template **3rd post-candidate** dogfood — Lesson #69 formal CONFIRMED-eligible reinforcement; Lesson #61 amendment **7th consecutive post-confirmation** SUCCESS (permanent asset eligible); Lesson #56 OUTCOME-LEVEL family proxy NEUTRAL (halt cause upstream DNA duplicate, not proxy outcome prediction); Lesson #62 boundary DNA 4-dim audit **HARD FAIL** vs paradigm 104.

## Hypothesis (proposed but blocked)

Bybit ↔ Binance OI (Open Interest) divergence × per-symbol directional 4h hold.

- **Trigger statistic**: per-sym OI divergence ratio = `(bybit_OI - binance_OI) / mean(bybit_OI, binance_OI)`, rolling 7d z-score
- **Threshold**: |z|≥2
- **Universe**: 7 deep-syms (paradigm 103/104 cohort — AVAX/BCH/BNB/DOGE/LINK/SOL/XRP)
- **Hold**: 4h primary + 8h/12h sweep
- **Substrate**: Bybit V5 OI archive + Binance OI 5m archive (both prior-verified)

## Lesson #69 5-item strict template result (3rd post-candidate dogfood)

### Item 1 — Lesson #61 amendment slug grep (CRITICAL — direct prior-art found)

`ls research_track/ | grep -iE "cross_exchange|bybit|oi_divergence|oi_lead_lag|funding_spread"`:

```
alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h               (paradigm 148, GRAVEYARD)
alt_bybit_to_binance_lead_lag_oi_delay_directional_4h                  (paradigm 147v2, GRAVEYARD)
alt_cross_exchange_volume_share_rotation_directional_4h                (paradigm 160, GRAVEYARD)
cross_exchange_funding_spread_binance_bitget_alt                       (paradigm 105 illiquid venue, GRAVEYARD)
cross_exchange_funding_spread_binance_bybit_alt_directional_8h         (paradigm 103, GRAVEYARD)
cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h  (paradigm 104, GRAVEYARD) ← DNA EXACT MATCH
```

**Verdict**: paradigm 104 = `cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h` **2026-05-19 09:00 KST R-1 EXECUTED** — BROAD_FALSIFIED_PRIMARY_HOLD. **Same statistic, same universe, same hold, same substrate** as proposed paradigm 166. The statistic name "OI divergence ratio" vs "OI level differential" is a re-labeling; both reduce to per-symbol cross-venue OI imbalance z-score on identical 7-sym universe + 4h primary hold. **HARD FAIL on Item 1**.

### Item 2 — Lesson #28 amendment substrate-shape audit (3rd post-amendment opportunity)

- **Substrate-existence**: Bybit V5 OI + Binance OI 5m archive — **both verified** (paradigm 104 backfill 325.5s wall-clock, 7/7 deep-syms × 869d = 100% data window ratio)
- **Substrate-shape**:
  - Bybit V5 `/v5/market/open-interest` intervalTime=1h cursor pagination → n=20,857 bars/sym (verified)
  - Binance OI 5m archive (`data.binance.vision`) → n=20,847 bars/sym resampled 1h (verified)
- **Cache permanent**: `backend/runs/ohlcv_cache/{binance_oi,bybit_oi}/{SYM}_1h.joblib` (paradigm 104 resource asset)
- **Verdict**: PASS (substrate fine, but moot — halt cause upstream Item 1 DNA duplicate)

### Item 3 — Lesson #11 sample density (per quadrant per quarter)

paradigm 104 measured directly:
- z=2.5 chosen (largest density-passing threshold)
- A_focus n=3,425 / 10 quarters ALL ≥30
- B_focus n=2,774 / 10 quarters ALL ≥30
- |z|≥2 (proposed paradigm 166 threshold): n=7,174 / 6,763 — even denser
- **Verdict**: PASS (strong, moot due to upstream halt)

### Item 4 — DNA 4-dim audit table vs paradigm 104 (Lesson #62 strict count)

| Dimension | paradigm 104 (R-1 GRAVEYARD) | paradigm 166 (proposed) | Strict count |
|---|---|---|---|
| **Statistic** | `(binance_OI − bybit_OI)` 30d-median-norm + 30d z-score on 1h frame | `(bybit_OI − binance_OI) / mean(both)` rolling 7d z-score | **NOT STRICT** — sign-convention flip + normalization scale change (median-30d vs mean-rolling-7d) is algebraic re-labeling, both reduce to cross-venue OI imbalance per-sym z-score |
| **Universe** | 7 deep-syms (AVAX/BCH/BNB/DOGE/LINK/SOL/XRP) | 7 deep-syms (identical cohort) | **NOT STRICT** — exact match |
| **Entry-side trigger** | \|z\|≥2.5 directional both sides | \|z\|≥2 directional both sides | **NOT STRICT** — threshold relaxation within paradigm 104 sweep already measured (z=2.0 cell n=7,174 / 6,763) |
| **Mechanism alpha** | cross-venue OI imbalance reveal direction | cross-venue OI imbalance reveal direction | **NOT STRICT** — identical mechanism statement |
| **Hold horizon** | 4h primary + 60m/480m/1440m sweep | 4h primary + 8h/12h sweep | **NOT STRICT** — 4h primary identical, 8h/12h cells already swept (480m / not measured 720m but 1440m showed monotonic continuation) |

**Strict count: 0/5** — Lesson #62 **HARD FAIL** (required ≥2/5). DNA duplicate confirmed.

### Item 5 — Family-proxy cross-reference (Lesson #56 OUTCOME-LEVEL, NEUTRAL here)

Cross-exchange family Tier 4 retire **7 cumulative graveyards**:
- paradigm 103 `cross_exchange_funding_spread_binance_bybit_alt_directional_8h` (2026-05-19, BROAD_FALSIFIED_FEE_FLOOR)
- paradigm 104 `cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h` (2026-05-19, BROAD_FALSIFIED_PRIMARY_HOLD) ← **DNA EXACT MATCH to paradigm 166**
- paradigm 105 `cross_exchange_funding_spread_binance_bitget_alt_illiquid_venue` (illiquid venue path #1 closeout)
- paradigm 147v1 / v2 `bybit_to_binance_lead_lag_oi_delay` (Tier 4 retire)
- paradigm 148 `bybit_to_binance_lead_lag_PRICE_delay` (Tier 4 retire)
- paradigm 160 `cross_exchange_volume_share_rotation` (Tier 4 retire, fee-floor)

**Lesson #56 OUTCOME-LEVEL prediction NEUTRAL** — paradigm 166 halt is **upstream DNA duplicate** (Item 1+4), not downstream OUTCOME proxy. The OUTCOME-LEVEL family proxy framework predicts the cross-exchange family would converge on fee-floor / primary-hold trap outcomes; this prediction was already realized by paradigm 104 itself. Lesson #56 instance counter does **not** advance for this halt (different halt mechanism).

## Verdict tree

1. **Item 1 slug grep HARD FAIL** — paradigm 104 prior-art exact match
2. **Item 4 DNA 4-dim audit 0/5 strict HARD FAIL** (Lesson #62 boundary)
3. Item 2 substrate PASS (moot)
4. Item 3 sample density PASS (moot)
5. Item 5 family-proxy NEUTRAL (halt cause upstream)

**Cumulative halt signal**: 2 HARD FAIL + 2 moot PASS + 1 NEUTRAL = **R-0 inventory halt unambiguous**

## Cross-comparison: paradigm 104 R-1 result summary (already-measured, paradigm 166 would duplicate)

From paradigm 104 GRAVEYARD.md:

### 4-quadrant SNT (focus z=2.5 / hold 240m primary)
| Quadrant | n | net (bp) | gross (bp) | sigex | perm_p | ci_lower | 3-gate |
|---|---|---|---|---|---|---|---|
| A_focus (Binance↑ + LONG) | 3,425 | +9.70 | +25.70 | +7.09 | **0.988** | +2.05 | **FAIL (perm_p)** |
| A_mirror (Binance↑ + SHORT) | 3,425 | −41.70 | −25.70 | −5.96 | 0.000 | −49.21 | FAIL |
| B_focus (Bybit↑ + SHORT) | 2,774 | −21.12 | −5.12 | −0.83 | 0.206 | −29.12 | FAIL |
| B_mirror (Bybit↑ + LONG) | 2,774 | −10.88 | +5.12 | +1.63 | 0.952 | −18.85 | FAIL |

### 16bp fee floor
- A_focus gross +25.70bp **>** 16bp fee floor (no Lesson #56 BROAD_FALSIFIED_FEE_FLOOR)
- BUT perm_p=0.988 due to **upward-bias pool drift trap** (Lesson #32 variant)

### Hold sweep (primary 240m FAIL + 480m PASS but Life-changing 4-dim FAIL)
| Hold | gross | perm_p | 3-gate | Concentration | Life-changing edge/trade |
|---|---|---|---|---|---|
| 240m primary | +25.70 | 0.988 | FAIL | FAIL (2/7 syms ci_pos) | n/a |
| 480m | +42.11 | 0.045 | PASS | PASS (4/7 syms, 8/10 q) | **0.26% FAIL** ≥2% |
| 1440m | +92.78 | 0.000 | PASS | PASS (4/7 syms, 8/10 q) | **0.77% FAIL** ≥2% |

### Concentration Gate (A_focus z=2.5 / 240m)
- 2/7 syms ci_pos (BCH +28.58 / DOGE +25.32 only); 3/7 strongly **negative** (AVAX −31.57 / BNB −30.25 / SOL −57.55)
- Per-quarter: 7/10 pos_t but 2024Q4 single-quarter +69.73 carries 36% cumulative mean (paradigm 87 lesson #26 single-fold-driven antipattern)

### paradigm 104 §4 next-action explicit (relevant to paradigm 166):

> "Halt at R-1. No R-2 spawn — life-changing 4-dim FAIL even at PASSING longer holds rules out paradigm 104 advancement."
> "Re-classify path #3 as 'partial-mechanism with horizon constraint'."

## Why paradigm 165 §next-action stale recommendation = Lesson #61 amendment 7th post-confirmation dogfood SUCCESS

paradigm 165 explicitly authored `paradigm_166_recommendation_cross_exchange_OI_divergence_axis` as `next_action` (INDEX.json line 1867). Lesson #61 amendment requires R-0 provenance audit on prior-paradigm next-action to catch stale recommendations.

**Audit result**: paradigm 165 R-0 halt date 2026-05-21 21:30 KST; paradigm 104 R-1 graveyard date 2026-05-19 09:00 KST. paradigm 165's recommendation was authored 2 days **after** paradigm 104 had already executed R-1 on the exact same hypothesis. paradigm 165's author (paradigm-architect orchestration) did **not** cross-reference paradigm 104 when issuing the recommendation — same blind spot as paradigm 156/157/158/161/163 chain.

**Lesson #61 amendment 7th consecutive post-confirmation SUCCESS** — paradigm 166 R-0 inventory halt catches the stale recommendation chain. Per Lesson #61 amendment formal CONFIRMED policy, 7th-consecutive eligible advances toward **permanent asset status** (8th-consecutive triggers permanent asset elevation at next ratification batch).

## Cross-exchange family Tier 4 retire reinforcement (7 cumulative confirmed)

Memory pin [[project-paradigm-103-cross-exchange-funding-spread]] + [[project-paradigm-104-cross-exchange-oi-level]] + paradigm 147v1/147v2 + 148 + 160 + (paradigm 105 illiquid venue path #1 closeout) explicitly closed cross-exchange family axis space.

Per paradigm 104 §next-action: "Path #1 (illiquid venue) still untouched but tier-4 advisory caution should be raised given 2 consecutive primary-horizon falsifications." → subsequently 147+148+160 closed remaining sub-axes. **Cross-exchange family axis space exhausted**. paradigm 166 proposed re-attempt on **already-measured** statistic falls under Tier 4 retire scope.

paradigm 22 R-5 (funding_dispersion ETCUSDT) remains sole exception.

## Lessons confirmed in this R-0

| Lesson | Status | Evidence |
|---|---|---|
| **Lesson #61 amendment** | **7th consecutive post-confirmation SUCCESS** (permanent asset elevation 8th-eligible) | paradigm 165 §next-action stale recommendation caught |
| **Lesson #62** | DNA 4-dim **HARD FAIL 0/5 strict** (boundary fail mode, 10th cumulative boundary dogfood) | All 5 dims duplicate of paradigm 104 |
| **Lesson #69** | **3rd post-candidate dogfood SUCCESS** (formal CONFIRMED-eligible) | 5-item strict template executed; Item 1+4 produced unambiguous HARD FAIL signal pre-dispatch |
| **Lesson #28 amendment** | **3rd post-amendment dogfood NEUTRAL** | Substrate-shape audit PASS but moot — halt cause upstream DNA duplicate, not substrate |
| **Lesson #56** | NEUTRAL non-instance | Halt is upstream DNA duplicate, not downstream OUTCOME proxy; instance counter unchanged 16 |
| **Lesson #21** | NEUTRAL non-violation | paradigm 166 hypothesis is single-axis, not axis stacking |
| Cross-exchange family Tier 4 retire | **7 cumulative reinforcement** (paradigm 166 would have been #8 reattempt) | 103+104+105+147v1+147v2+148+160 |

## Next-action recommendation

### paradigm 167 dispatch priorities (Lesson #61 amendment 8th-eligible permanent asset elevation opportunity)

**Critical constraint update**:
- Cross-exchange family **8 cumulative graveyard-or-blocked** (now including paradigm 166 R-0 halt) — formal Tier 4 retire **decisive**
- Funding family **11 cumulative** (per paradigm 156 graveyard line 1819)
- Taker imbalance family **3 cumulative + Lesson #57 formal CONFIRMED ratified** (paradigm 165 §next-action user directive)
- OI velocity family **2 cumulative** (paradigm 71/86)
- 35-streak non-PASS milestone reached

### Recommended candidates for paradigm 167 (axes not yet retired)

1. **Option α — Funding rate spike isolated trigger with mean reversion direction** (single-asset, single-axis, mean-reversion frame, family-distinct from continuation funding direction)
   - Family-distinct strict count expected 3-4/5 vs funding family (continuation vs mean-reversion is mechanism-level distinct, not statistic-level)
   - BUT: funding family Tier 4 retire ratified — Lesson #56 OUTCOME-LEVEL family proxy 17th-instance high prior risk
   - Caution: paradigm 96 funding sign flip already mapped mean-reversion vs continuation distinction

2. **Option β — Realized volatility cluster duration regime (Hurst exponent or rescaled range)** on alt-coins
   - Statistic distinct from BTC RV (paradigm 67/69) and per-sym idiosyncratic
   - Universe BTC vol regime stratify (LOW vol filter inversion of paradigm 69 highvol)
   - 5-axis novelty expected 3/5 NOVEL

3. **Option γ — Listing-event-anchored variant** (paradigm 138/139/140 family but with new sub-mechanism)
   - lifecycle_pump_decay R-5 PROMOTION APPROVED 2026-05-21 20:14 KST → paper sessions live
   - Variant ideas: post-Day-30 mean-reversion bounce (paradigm 88 reframe) / Day-1 long-only without bear filter / pre-listing announcement window (Lesson #28 substrate-shape verified blocked)

4. **Option δ — Mark-index basis dislocation** (single-exchange Binance perp vs index, no cross-exchange)
   - Substrate: Binance markPriceKlines archive (Lesson #28 substrate-shape verified prior)
   - Family-distinct strict count expected 4-5/5 (single-exchange, basis axis untouched in dispatch history)
   - 5-axis NOVEL ex ante expected 3-4/5

**Recommendation: Option δ** (Mark-index basis dislocation single-exchange) — family-distinct strict count highest, substrate-shape pre-verified, axis untouched.

## Resources committed

- **Task md**: `backend/runs/research_track/alt_cross_exchange_oi_divergence_bybit_vs_binance_directional_4h/TASK.md` (this file)
- **No R-1 script generated** (R-0 halt pre-dispatch)
- **No backfill executed**
- **Wall-clock**: ~5 min (inventory check only)
- **Compute saved**: ~6 min R-1 + ~5 min backfill (paradigm 104 cache already permanent asset) = ~11 min total

## Counter increment

164 → 165 → **166** (substantive R-0 increment per memory pin [[project-paradigm-97-98-99-funding-family-completion]] + paradigm 138/139/140/151/154/155/159/161/163/164/165 precedent — R-0 halt with novel lesson dogfood counts as paradigm-architect substantive turn).

**Lessons invoked count: 7** (#21 NEUTRAL, #28 amendment 3rd dogfood NEUTRAL, #56 NEUTRAL non-instance, #61 amendment 7th SUCCESS, #62 HARD FAIL 0/5 boundary, #69 3rd post-candidate SUCCESS formal CONFIRMED-eligible, cross-exchange family Tier 4 retire 7→8 cumulative reinforcement)
