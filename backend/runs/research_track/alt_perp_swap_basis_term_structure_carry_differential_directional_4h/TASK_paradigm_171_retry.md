# paradigm 171 — paradigm 169 retry (post-paradigm 170 funding DB unblock)

**Dispatch date**: 2026-05-21 22:30 KST
**Slug**: `alt_perp_swap_basis_term_structure_carry_differential_directional_4h` (paradigm 169 동일 slug)
**Verdict**: `SAMPLE_INSUFFICIENT_SUBSTRATE_SHAPE_HALT_2ND` (R-0 prescreen, no R-1 dispatch)
**Phase reached**: R-0
**Paradigm classification**: substantive R-0 increment as paradigm 171 (paradigm 169 entry unchanged; new finding = 3M quarterly futures axis substrate-shape FAIL distinct from paradigm 169's funding DB axis FAIL)

## Hypothesis (unchanged from paradigm 169)
- **Mechanism**: per-symbol cross-tenor carry differential
  - Trigger statistic: `(8h perp funding rate annualized) - (3M quarterly futures implied basis annualized)`, rolling 7d z-score
  - |z|>=2 carry differential dislocation → 4h directional convergence (mean-reversion)
- **Universe (claimed post-paradigm 170)**: 10 deep syms (ADA/BCH/BNB/BTC/DOT/ETH/LINK/LTC/SOL/XRP)
- **Hold**: 4h primary + 8h/12h sweep
- **Substrate (claimed post-paradigm 170)**:
  - ✅ binance_funding_rate DB 10 syms × 2.25yr × 24,660 records (paradigm 170 unblocked)
  - ⚠️ 3M quarterly futures substrate — Item 2 audit STRICT 의무 (paradigm 169 R-0 HALT focal point)

## R-0 inventory prescreen — Lesson #69 5-item strict template (6th post-CONFIRMED dogfood)

### Item 1: Lesson #61 amendment PERMANENT slug grep
- `ls research_track/ | grep -iE "perp_basis|term_structure|carry_differential|quarterly|3M|funding_vs"` → hits:
  - `alt_perp_swap_basis_term_structure_carry_differential_directional_4h` (paradigm 169 graveyard, current slug)
  - `alt_bvol_implied_vol_term_structure_inversion_directional_4h` (graveyard)
  - `alt_funding_carry_x_oi_decoupling_4h_cross_r5_hybrid_directional` (graveyard)
  - `funding_carry` (paradigm 22 R-5 LIVE)
- Retry context: same slug — Lesson #61 amendment permanent retry exemption (paradigm 169 substrate-shape FAIL resolution attempt)
- No new DNA 5/6 duplicate detected
- **Verdict**: Slug grep PASS (retry exempted)

### Item 2: Lesson #28 amendment substrate-shape audit STRICT (6th post-CONFIRMED dogfood, CRITICAL)

**Substrate-existence**:
- Binance USDS-M `/fapi/v1/exchangeInfo` quarterly contracts:
  - Only **2 pairs**: BTCUSDT_260626 (CURRENT_QUARTER), ETHUSDT_260626 (CURRENT_QUARTER) + 260925 (NEXT_QUARTER) duplicates
  - Unique base pairs: **{BTCUSDT, ETHUSDT} = 2 syms**
- Binance COIN-M `/dapi/v1/exchangeInfo` quarterly contracts:
  - **5 pairs**: BTCUSD, ETHUSD, XRPUSD, BNBUSD, SOLUSD
- Binance Vision archive depth verification (per-sym historical quarterly contract count):
  - **USDS-M (`futures/um/daily/klines/`)**:
    - BTCUSDT_*: 24 quarterly contracts (2021-03-26 ~ 2026-09-25) — **5yr coverage**
    - ETHUSDT_*: 24 quarterly contracts (2021-03-26 ~ 2026-09-25) — **5yr coverage**
    - **No other USDT-margin quarterly pairs exist**
  - **COIN-M (`futures/cm/daily/klines/`)**:
    - BTCUSD_*: 27 contracts (2020-09 ~ 2026-09) — **6yr**
    - ETHUSD_*: 27 contracts (2020-09 ~ 2026-09) — **6yr**
    - XRPUSD_*: 26 contracts (2020-12 ~ 2026-09) — **5.5yr**
    - BNBUSD_*: 26 contracts (2020-12 ~ 2026-09) — **5.5yr**
    - SOLUSD_*: 11 contracts (2024-09 ~ 2026-09) — **1.7yr (BELOW 2.25yr)**
    - No COIN-M quarterly for ADA/BCH/DOT/LINK/LTC

**Substrate-shape STRICT (cross-source consistent margin)**:
- paradigm 170 funding DB = **USDS-M (USDT-margin) 8h funding rate**
- paradigm 171 cross-tenor differential requires **same-margin** quarterly basis (theoretical coherence):
  - USDT-perp funding × USDT-quarterly basis (USDS-M) → BTC, ETH only = **2 syms** intersection
  - USDT-perp funding × USD-quarterly basis (COIN-M) → **cross-margin mismatch** (different trader cohorts, different margin currencies — basis non-comparable)

**Cross-margin feasibility analysis**:
- USDT-margin perpetual funding signals positioning crowding in USDT-margin USDS-M instrument cohort
- USD-margin (inverse) COIN-M quarterly basis signals carry in USD-margin instrument cohort
- These reflect **economically separable** trader populations (US institutional USD vs retail/crypto-native USDT)
- Convergence/arbitrage mechanism requires **same-margin pair** for the differential to represent tradable carry
- **Verdict**: cross-margin mixing NOT a valid recovery path

**Strict same-margin intersection (paradigm 170 funding DB ∩ USDS-M quarterly)**:
- Universe: **{BTCUSDT, ETHUSDT} = 2 syms × 2.25yr**

### Item 3: Lesson #11 sample density (per-quarter per-cell ≥ 30 cutoff)
- 2 syms × 2.25yr × 4h bars = **9,855 total obs**
- |z|>=2 trigger rate (gaussian both-tails ~5%) = **493 events**
- 4-quadrant SNT per-quadrant = **123 events**
- per-quadrant per-quarter (9 quarters in 2.25yr) = **13.7 events << 30 cutoff**
- Relaxation attempt: z>=1.5 (~13% rate) → per-quadrant per-quarter ≈ **36 events marginal** but inflates false-discovery risk significantly
- **Verdict**: Lesson #11 STRUCTURAL FAIL (n=13.7 << 30; relaxation does not recover within statistically defensible bounds)

### Item 4: Lesson #62 DNA 4-dim audit table (CONFIRMED, retry exemption)
| Dim | paradigm 22 R-5 funding_carry | paradigm 171 | Distinct? |
|-----|-------------------------------|--------------|-----------|
| Statistic class | single funding rate 30d z-score | cross-tenor (funding × quarterly basis) differential 7d z-score | YES |
| Universe | HBAR/AXS/COMP narrow seed | BTC/ETH (post Item 2 shrink) | YES (disjoint) |
| Entry-side | funding 8h boundary z spike MR | term structure carry |z|>=2 4h | YES |
| Mechanism alpha | funding mean-reversion | cross-tenor convergence | YES |
- Strict count: **4/5 distinct** — Lesson #62 PASS (retry reaffirms paradigm 169 boundary classification)
- vs paradigm 169 (self-retry): same slug, retry exempted
- **Verdict**: Lesson #62 PASS (DNA differentiation maintained — but moot given Items 2+3 HALT)

### Item 5: Lesson #56 family-proxy OUTCOME-LEVEL cross-reference (17+ instances cumulative)
- Funding family Tier 4 retire 11 cumulative: OUTCOME would be fee-floor sub-threshold convergence
- Basis/markPrice 4h MR family Tier 4 retire 5 cumulative: OUTCOME would be 4h-frame MR sub-fee saturation
- Liquidity-microstructure 4h-frame conjunction family Tier 4 retire 4 cumulative: NOT directly applicable
- paradigm 171 sits **between** funding family + basis family at cross-tenor sub-axis
- Pre-execution prediction: even if substrate were available, R-1 likely gross ~5-15bp < 16bp fee floor → Lesson #56 18th instance candidate
- **Verdict**: Lesson #56 advisory caution (moot given prescreen HALT)

## Halt rationale (joint Lesson #28 amendment + Lesson #11, 2nd consecutive)
1. **Lesson #28 amendment substrate-shape HALT (2nd, different axis from paradigm 169)**:
   - paradigm 169 axis: funding DB coverage 4 syms × 1yr → unblocked by paradigm 170 (10 syms × 2.25yr)
   - **paradigm 171 axis: 3M quarterly futures USDS-M coverage limited to BTC/ETH only** (2 syms)
   - Cross-margin mixing (USDT-perp × USD-quarterly) economically incoherent — NOT a recovery path
   - Strict same-margin intersection: 2 syms × 2.25yr
2. **Lesson #11 sample density STRUCTURAL FAIL**: per-quarter per-quadrant n=13.7 << 30 cutoff (relaxation does not recover)
3. **Joint halt 2-axis prescreen failure** — R-1 dispatch IMPOSSIBLE despite paradigm 170 funding DB unblock

## Cross-comparison: paradigm 22 R-5 baseline vs paradigm 171
- **Cohort disjoint**: paradigm 22 (HBAR/AXS/COMP perp funding only) vs paradigm 171 (BTC/ETH USDT-perp funding × USDT-quarterly basis)
- **DNA differentiation 4/5 strict** but cross-comparison non-overlapping (apples-to-oranges)
- paradigm 22 R-5 baseline: 8h funding 30d z-score MR — still LIVE
- paradigm 171 status: blocked by **3M quarterly futures USDS-M structural scarcity**, not by mechanism falsification

## Recovery paths (advisory only — not auto-execute)
1. **COIN-M perp funding DB backfill** (NEW infrastructure task):
   - Backfill USD-margin perp funding for BTC/ETH/XRP/BNB/SOL × 2.25yr
   - Enables same-margin pair: COIN-M perp funding × COIN-M quarterly basis
   - Cohort: 5 syms × 2.25yr → per-quadrant per-quarter ~34 events PASS Lesson #11 marginal
   - SOL × 1.7yr quarterly coverage marginal (still below 2.25yr) — effective 4 syms × 2.25yr + SOL partial
   - Requires new fetcher (different endpoint than USDS-M funding) — wall-clock similar to paradigm 170 (~9-30s)
   - Free unlimited Binance REST ([[feedback-no-freemium-trial]] compliant)
2. **Drop paradigm 171 retry concept entirely**:
   - cross-tenor funding × quarterly basis differential is structurally limited at USDT-perp side (only BTC/ETH)
   - paradigm-22 R-5 single-tenor funding remains the only viable carry axis
   - Funding family Tier 4 retire already absorbed 11 sub-class variants

## Lesson dogfood outcomes
- **Lesson #69 6th post-CONFIRMED dogfood**: 5-item strict template SUCCEEDED at catching substrate-shape FAIL **2nd consecutive** (different axis from 5th dogfood)
- **Lesson #28 amendment SUCCESSFUL 2nd consecutive**: same paradigm slug, different substrate-shape axis (funding DB → quarterly futures) — substrate-shape audit must check **every** required substrate independently, not just primary
- **Lesson #11**: density prescreen prevented n=13.7 R-1 dispatch (2 syms × 2.25yr universe collapse)
- **Lesson #62**: DNA 4/5 differentiation maintained even at 2nd HALT
- **Lesson #61 amendment retry exemption verified**: paradigm 171 = paradigm 169 retry, but new finding (USDS-M quarterly limited to BTC/ETH) is substrate-shape sub-axis distinct from paradigm 169's funding DB axis FAIL

## paradigm 172 next-action 권고
Priority order:
1. **Option α (1순위, recommended)**: drop cross-tenor funding × quarterly basis paradigm class entirely — structural USDS-M quarterly scarcity is permanent (Binance has only listed BTC/ETH USDT-quarterly contracts since 2021, no expansion in 5yr), no recovery foreseeable. Add to family proxy advisory: "USDT-margin cross-tenor funding × quarterly basis: 2-sym permanent ceiling, do not retry without USDS-M quarterly listing expansion."
2. **Option β (2순위)**: COIN-M perp funding DB backfill as infrastructure task (5 syms × 2.25yr unlocks marginal Lesson #11 PASS at sub-grade cohort) — recovery cost ~9-30s, but downstream PASS probability low given funding family Tier 4 retire 11 sub-class FAIL pattern
3. **Option γ (3순위)**: pivot to other family-distinct axis — paradigm 22 R-5 expansion narrow-scope (BTC/ETH/SOL/LINK 등 deep cohort candidates), or funding term structure cross-tenor variant (8h vs 3d rolling using paradigm 170 funding DB only, no quarterly side needed)

## Counter
- Graveyards: 169 → **170** (paradigm 171 R-0 HALT 2nd substantive increment)
- Non-PASS streak: 38 → **39**
- Paradigm counter: 170 → **171**
- R-5 yield: 11/171 = **6.43%**
- Tier 4 family retires: 15 unchanged
- Lesson dogfoods: Lesson #69 6th post-CONFIRMED + Lesson #28 amendment 6th post-CONFIRMED + Lesson #11 4th post-CONFIRMED
