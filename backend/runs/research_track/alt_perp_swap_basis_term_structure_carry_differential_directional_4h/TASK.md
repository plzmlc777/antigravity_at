# paradigm 169 — alt_perp_swap_basis_term_structure_carry_differential_directional_4h

**Dispatch date**: 2026-05-21 22:11 KST
**Verdict**: `SAMPLE_INSUFFICIENT_SUBSTRATE_SHAPE_HALT` (R-0 prescreen)
**Phase reached**: R-0 (no R-1 dispatch)

## Hypothesis
- **Mechanism**: per-symbol cross-tenor carry differential
  - Trigger statistic: `(8h perp funding rate annualized) - (3M quarterly futures implied basis annualized)`, rolling 7d z-score
  - |z|>=2 carry differential dislocation → arbitrage-driven 4h directional convergence
- **Universe (claimed)**: 7 deep-syms cross-tenor 3M quarterly liquid
- **Hold**: 4h primary + 8h/12h sweep
- **Substrate (claimed)**: Binance funding DB + Binance quarterly futures 3M expiry kline archive

## R-0 inventory prescreen — Lesson #69 5-item strict template (5th post-CONFIRMED dogfood)

### Item 1: Lesson #61 amendment slug grep (permanent application, 8-streak prior)
- `ls research_track/ | grep -iE "perp_basis|term_structure|carry_differential|quarterly|3M|funding_vs"` → 5 hits:
  - `alt_bvol_implied_vol_term_structure_inversion_directional_4h` (graveyard)
  - `alt_funding_carry_x_oi_decoupling_4h_cross_r5_hybrid_directional` (graveyard)
  - `funding_carry` (paradigm 22 R-5 LIVE)
- No DNA 5/6 overlap (no prior paradigm combined perp funding × quarterly futures cross-tenor differential)
- **Verdict**: Slug grep PASS (no duplicate)

### Item 2: Lesson #28 amendment substrate-shape audit (CONFIRMED, permanent application)
- **Substrate-existence**:
  - Binance USDS-M `fapi` exchangeInfo: only **2 USDT quarterly pairs** (BTCUSDT, ETHUSDT) → insufficient
  - Binance COIN-M `dapi` exchangeInfo: **5 active CURRENT_QUARTER pairs** (BTCUSD, ETHUSD, XRPUSD, BNBUSD, SOLUSD)
  - Binance Vision archive (S3): 217 quarterly contract directories across 14 pairs, BTC/ETH/XRP/BNB: 24-25 contracts (2020+), full 2.25yr stitchable
- **Substrate-shape**:
  - **SOLUSD quarterly archive: only 9 contracts (2024-09..2026-09), ~1.7yr coverage** — BELOW 2.25yr
  - **Funding DB substrate per-sym coverage** (decisive constraint):
    - BTCUSDT/ETHUSDT/LINKUSDT/SOLUSDT: n=1095-1117, range 2025-05..2026-05 = **only 1yr**
    - XRPUSDT/BNBUSDT/BCHUSDT/LTCUSDT/ADAUSDT/DOTUSDT: **n=0 funding substrate missing**
  - **Cross-source matching constraint**: paradigm 169 requires BOTH funding × quarterly futures available simultaneously for same time window
- **Intersection viable cohort (funding ≥1yr ∩ quarterly futures archive)**:
  - BTC, ETH, LINK with ~1yr overlap
  - SOL: 1yr funding ∩ 1.7yr quarterly = ~10mo effective (SOL quarterly starts 2024-09, funding starts 2025-05)
  - Effective: **3-4 syms × ~1yr** — NOT 7 syms × 2.25yr
- **Verdict**: Substrate-shape FAIL — claimed cohort scope unavailable

### Item 3: Lesson #11 sample density (per-quarter n ≥ 30 cutoff)
- 3-sym viable (BTC/ETH/LINK), 1yr × 4h bars = 6,570 total obs
- |z|≥2 trigger rate (gaussian both-tails ~5%) = 328 events
- 4-quadrant SNT per-cell = 82 events
- per-quadrant per-quarter (1yr = 4 quarters) = **20.5 events << 30 cutoff**
- 4-sym extended (BTC/ETH/LINK/SOL 1yr overlap): per-qcell per-quarter = **27.4 events < 30 cutoff**
- **Verdict**: Lesson #11 FAIL — sample density structurally insufficient

### Item 4: Lesson #62 DNA 4-dim audit (CONFIRMED, 11 boundary dogfoods)
| Dim | paradigm 22 R-5 funding_carry | paradigm 169 | Distinct? |
|-----|-------------------------------|--------------|-----------|
| Statistic class | single funding rate 30d z-score | cross-tenor (funding × quarterly basis) differential 7d z-score | YES |
| Universe | HBAR/AXS/COMP seed | BTC/ETH/LINK/(SOL) — disjoint | YES |
| Entry-side | funding 8h boundary z spike MR | term structure carry |z|≥2 4h | YES |
| Mechanism alpha | funding mean-reversion | cross-tenor convergence | YES |
- **Expected strict count vs paradigm 22: 4/5** (statistic + universe + entry + mechanism distinct)
- vs basis/markPrice 4h MR family Tier 4 retire (5 cumulative): cross-tenor differential NOT single-tenor basis (statistic class distinct)
- vs funding family Tier 4 retire (11 cumulative): cross-tenor arbitrage NOT single-rate variant (statistic class distinct)
- **Verdict**: Lesson #62 PASS (DNA differentiation strong — but moot given Items 2+3 HALT)

### Item 5: Lesson #56 family-proxy OUTCOME-LEVEL cross-reference (15 instances cumulative)
- funding family Tier 4 retire 11 cumulative: OUTCOME would be fee-floor sub-threshold convergence
- basis/markPrice 4h MR Tier 4 retire 5 cumulative: OUTCOME would be 4h-frame MR sub-fee saturation
- liquidity-microstructure 4h-frame conjunction Tier 4 retire 4 cumulative: NOT directly applicable (no liquidity proxy in paradigm 169)
- paradigm 169 sits **between** funding family + basis family — Lesson #62 DNA differentiation strong, BUT both adjacent retire families predict fee-floor saturation at 4h frame
- Pre-execution prediction: even if substrate were available, R-1 likely gross ~5-15bp < 16bp fee floor → **Lesson #56 16th instance candidate**
- **Verdict**: Lesson #56 advisory caution (moot given prescreen HALT)

## Halt rationale (joint Lesson #28 amendment + Lesson #11)
1. **Lesson #28 amendment substrate-shape HALT**: claimed 7 deep-syms × 2.25yr unavailable
   - Quarterly futures archive: BTC/ETH/XRP/BNB/BCH/LTC/ADA/DOT/LINK (9 pairs full 2.25yr+) — substrate exists
   - Funding DB: only 4 syms (BTC/ETH/LINK/SOL) × 1yr coverage — substrate-shape FAIL
   - **Cross-source matching** reduces to ≤4 syms × ≤1yr
2. **Lesson #11 sample density HALT** (consequential): per-quarter per-quadrant SNT cell n=20.5-27.4 << 30 cutoff
3. **Joint halt 2-axis prescreen failure** — R-1 dispatch IMPOSSIBLE under current substrate

## Cross-comparison: paradigm 22 R-5 baseline vs paradigm 169
- **Cohort disjoint**: paradigm 22 (HBAR/AXS/COMP perp funding only) vs paradigm 169 (BTC/ETH/LINK/SOL perp funding × quarterly futures)
- **DNA differentiation 4/5 strict** but cross-comparison non-overlapping (apples-to-oranges)
- paradigm 22 R-5 baseline: 8h funding 30d z-score MR — still LIVE
- paradigm 169 status: blocked by substrate-shape, not by mechanism falsification

## Recovery paths (advisory only)
1. **Funding DB backfill expansion**: backfill BNBUSDT/XRPUSDT/BCHUSDT/LTCUSDT/ADAUSDT/DOTUSDT 2.25yr funding history → unlocks 8 viable syms × 2.25yr cohort, ~Lesson #11 strong PASS. Free unlimited Binance REST (kline + funding) — 2-4hr backfill estimated. Requires user authorization (no auto-backfill, [[feedback-no-freemium-trial]] OK)
2. **Reduced scope variant**: 3-sym × 1yr × |z|≥1.5 (relaxed threshold) — per-quadrant per-quarter ~30 marginal. Still high false-discovery risk
3. **Alternate cross-tenor proxy**: use **realized basis** (perp price - quarterly close) instead of implied basis. Same substrate constraint applies — moot

## Lesson dogfood outcomes
- **Lesson #69 5th post-CONFIRMED dogfood**: 5-item strict template SUCCEEDED at catching substrate-shape FAIL before R-1
- **Lesson #28 amendment**: substrate-existence (PASS) ≠ substrate-shape (FAIL) — exact pattern memorialized
- **Lesson #11**: density prescreen prevented n<30 R-1 dispatch (sub-fee noise risk)
- **Lesson #62**: DNA 4/5 differentiation confirmed even at HALT — paradigm-architect ratifies family-distinct boundary on cross-tenor axis (NOT same as funding single-rate / basis single-tenor families)

## Next action (paradigm 170)
- Lesson #69 6th post-CONFIRMED strict dogfood
- Candidate: **funding DB backfill 2.25yr 8-sym expansion** as infrastructure task (NOT new paradigm) OR **alternate term-structure variant**:
  - paradigm 170A: BVOL implied vol term structure inversion variant (already graveyard — exclude)
  - paradigm 170B: OI term structure (perp OI vs quarterly OI ratio) — substrate audit needed
  - paradigm 170C: Cross-exchange perp-vs-perp funding spread sub-axis (paradigm 103 already done Bybit, 167 done Bitget — substrate exhausted)
  - paradigm 170D: Volume term structure (perp vol vs quarterly vol ratio z-score) — substrate audit needed
- **Recommended**: paradigm 170 = **funding DB backfill infrastructure task** first (unlocks paradigm 169 retry + future funding-axis variants if any)
