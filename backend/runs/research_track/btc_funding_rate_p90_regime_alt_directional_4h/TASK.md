# paradigm 156 — `btc_funding_rate_p90_regime_alt_directional_4h`

**Created**: 2026-05-21 15:30 KST
**Provenance**: paradigm 155 §next-action Option β (paradigm-architect 1순위 권고, Lesson #61 chain)
**Path**: continuous-parallel campaign turn 27, axis class change post btc_rv_p90 family Tier 4 ratification

## Hypothesis

**Mechanism**: BTC funding rate가 cross-asset leverage skew macro signal로 작동하는지 검증.
- BTC funding p90 (extreme bullish positioning, leverage tilt up) regime에서 13 alts directional 4h hold
- BTC funding p10 (extreme bearish positioning, leverage tilt down) regime에서 13 alts directional 4h hold
- 4-quadrant Symmetric Negative Test (Lesson #19 의무): A focus / A mirror / B same-sign / B mirror

**Universe**: 13 alts (paradigm 69 verified) — BTC excluded (trigger source)
**Trigger**: BTC funding rate 8h cycle p90 (high) OR p10 (low) regime
**Entry**: BTC funding boundary 직후 (cycle close +0min anchor)
**Hold**: 4h primary, sweep {4h, 8h, 12h}
**Substrate**: `binance_funding_rate` DB (BTCUSDT 1y) + alt 12-col klines 4h

## R-0 inventory prescreen — 10-axis audit

### 1. Funding family Tier 4 retire family-distinct 4-dim strict audit (Lesson #62 CONFIRMED, ≥2 strict required)

| Dimension | Funding family (96-99) prior | paradigm 156 | Strict change? |
|---|---|---|---|
| **Statistic class** | per-sym funding z-score / sign flip / cs velocity / regime stratify | **BTC-only funding p90/p10 regime** (single-sym macro signal) | ✅ **STRICT** — single-sym macro vs per-sym statistic class entirely different |
| **Universe scope** | per-sym (funding axis on trader symbol itself) | **BTC-trigger × 13 alts (decoupled trigger-target)** | ✅ **STRICT** — cross-asset macro proxy vs per-sym self-conditioning |
| **Entry-side mechanism** | funding event boundary (sign flip / strict z-threshold) | **regime filter (continuous high state, p90/p10 percentile)** | ✅ **STRICT** — categorical event vs continuous regime classifier |
| **Mechanism alpha source** | per-sym funding sign flip / cs dispersion / velocity | **BTC leverage spillover contagion** (macro → cross-asset) | ✅ **STRICT** — micro single-symbol funding signal vs macro contagion |

**Strict count: 4/4** — Lesson #62 ≥2 strict 충족 ✅ family-distinct PASS

### 2. Funding rate substrate availability (Lesson #28)

- `binance_funding_rate` DB BTCUSDT verified: **1095 rows, 364-day span (2025-05-03 → 2026-05-03)**
- p90 events (funding ≥ p90 threshold): **141 cycles** (12.9%)
- p10 events (funding ≤ p10 threshold): **110 cycles** (10.0%)
- BTC funding p90 events × 13 alts = **1,833 alt-events** (A focus)
- BTC funding p10 events × 13 alts = **1,430 alt-events** (B same-sign)
- Substrate availability ✅ PASS

### 3. Lesson #11 sample density prescreen

- A focus 4-quadrant per-cell: 1,833 / 4 quarters / 4 quadrants = **115 events/cell** (>30 cutoff) ✅
- B same-sign 4-quadrant per-cell: 1,430 / 4 quarters / 4 quadrants = **89 events/cell** (>30 cutoff) ✅
- A mirror / B mirror same n (just direction flip) ✅
- Lesson #11 ✅ PASS

### 4. Lesson #19 Symmetric Negative Test 4-quadrant 의무

- A focus: BTC funding p90 × **alt LONG** (continuation, "leverage up → momentum up follow")
- A mirror: BTC funding p90 × **alt SHORT** (reversal, "extreme bullish positioning → mean revert")
- B same-sign: BTC funding p10 × **alt SHORT** (continuation, "leverage down → momentum down follow")
- B mirror: BTC funding p10 × **alt LONG** (reversal, "extreme bearish positioning → mean revert")
- 4-quadrant 측정 의무 ✅ included in R-1 script

### 5. Lesson #30 data window ratio

- BTC funding DB span: 364 days
- Mint full window 추정 (paradigm-architect local context): paradigm 22 R-5 시드 시점 funding DB ~1y → 365 days
- Ratio: 364/365 = **99.7%** ≥30% ✅ NOT advisory-only
- ⚠️ Local 1m OHLCV cache BTC only 142 days, SOL 795 days — kline-side coverage **per-symbol heterogeneous**
- Mitigation: 4-quadrant SNT uses 4h klines (smaller cache requirement), DB fallback active

### 6. Lesson #62 retiming reframe family-distinct (CONFIRMED, dogfood #4)

- paradigm 156 is NOT a retiming reframe of paradigm 22 (paradigm 22 = per-sym funding z-score; paradigm 156 = BTC-only p90 regime)
- Strict 4-dim audit shows 4/4 strict changes (see §1) — Lesson #62 ✅ PASS

### 7. Lesson #56 OUTCOME-LEVEL family proxy audit

- Funding family graveyards (73+79+96+97+98+99+147+148): all per-sym funding statistic single-axis variants
- paradigm 156 = **BTC-only macro regime × 13 alts** — outcome dimension distinct (macro contagion alpha source)
- 4-dim strict ≥3 changes (§1: 4/4) → OUTCOME-LEVEL proxy **ESCAPE** ✅ PASS

### 8. Lesson #21 axis stacking

- Single axis (BTC funding regime threshold) × single mechanism (leverage spillover contagion)
- Axis stacking 부재 ✅ PASS

### 9. Lesson #58 same-bar same-substrate

- BTC funding (DB substrate, BTC symbol) vs alt return (12-col klines, alt symbol) — **cross-substrate + cross-symbol**
- Lesson #58 exemption applies (cross-substrate auto-exempt) ✅ PASS

### 10. Mirror hypothesis antipattern

- paradigm 156 is sign-conditional bilateral (A focus + B same-sign 둘 다 의도된 가설) — not mirror antipattern
- paradigm 22 R-5 LONG mean-reversal direction vs paradigm 156 directional alt cross-asset = different mechanism class
- paradigm 70 (mirror antipattern reference): paradigm 70 = paradigm 69 mirror SHORT same trigger; paradigm 156 = NEW trigger source (BTC funding vs BTC RV)
- Mirror antipattern ✅ PASS (NOT applicable, sign-cond bilateral is core hypothesis structure)

### R-0 prescreen verdict: **ALL 10 AXES PASS → R-1 DISPATCH AUTHORIZED**

## R-1 protocol (STRICT, R-2 자동 진행 금지)

### Metrics per quadrant
- n_events (total + per-quarter + per-symbol)
- gross_ret_mean_bp / median_bp / std_bp
- net_ret_mean_bp (after 8bp round-trip fee)
- signal_t_excess (vs perm null, fee-aware)
- ci_lower_bp / ci_upper_bp (bootstrap 1000)
- perm_p (block permutation, n=200)
- Concentration: per-quarter t (q_measurable / q_pos_t / ratio), per-symbol bootstrap (syms_measurable / syms_ci_pos / ratio)

### Verdict tree
1. 4/4 quadrants 3-gate FAIL → `BROAD_FALSIFIED`
2. ≥1 quadrant 3-gate PASS + Concentration PASS → `PASS_R1_FULL` (R-2 user approval pending)
3. 3-gate PASS + Concentration FAIL → Lesson #20 narrow-scope 4-cond audit:
   - 4-cond ALL PASS → life-changing 4-dim:
     - 4/4 PASS → `NARROW_SCOPE_CANDIDATE`
     - any FAIL → `NARROW_SCOPE_LIFE_CHANGING_FAIL`
   - partial FAIL → `CONCENTRATED_R1_PASS` (R-2 halt)
4. **No R-2 auto-promote** — user gate strict

## Output artifacts

- code: `backend/scripts/research/paradigm156_r1.py`
- metrics: `backend/runs/research_track/btc_funding_rate_p90_regime_alt_directional_4h/r1__metrics.json`
- task: this file
- graveyard (if applicable): `graveyard__btc_funding_rate_p90_regime_alt_directional_4h.md`

## Next action provenance (Lesson #61)

paradigm 156 dispatch authorized by:
1. paradigm 155 §next-action Option β (paradigm-architect agent 1순위 권고 2026-05-21 15:20 KST)
2. user explicit dispatch 2026-05-21 15:26 KST with R-0 10-axis prescreen instruction
3. funding family Tier 4 retire cross-reference 의무 명시 사용자 컨텍스트
