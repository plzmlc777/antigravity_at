# paradigm 161 — `alt_listing_pump_first60min_BTC_macro_proxy_modifier`

**Date**: 2026-05-21 16:23 KST
**Phase**: R-0 inventory prescreen
**Verdict**: **R0_HALT_BY_INVENTORY_DUPLICATE_LESSON_61_AMENDMENT_3RD_POST_CONFIRMATION_DOGFOOD_SUCCESS + LISTING_FAMILY_RETIRE_ELIGIBLE_5TH_GRAVEYARD_RISK**
**Counter**: 160 → 161 (substantive R-0 increment)
**Provenance (Lesson #61)**: paradigm 160 §6.57 next-action Option α (paradigm-architect 1순위 권고 2026-05-21 16:16 KST) + user explicit dispatch 2026-05-21 16:18 KST

## Hypothesis (proposed)

**Mechanism**: Binance Futures alt listing event 후 first 60min window의 directional momentum × BTC macro regime modifier.
- Base: paradigm 121 `listing_pump_first60min` (dispatch context "R-5 LIVE 추정" — verified FALSE)
- NEW modifier: BTC 30d return positive (bull) × listing event LONG continuation 강화 가설
- 4-quadrant SNT: A_bull×LONG / A_bull×SHORT / B_bear×SHORT / B_bear×LONG

## R-0 Lesson #61 amendment 의무 INVENTORY CHECK 실행

### 1. Slug duplicate search (`grep -iE "listing|first60min|btc_macro"`)

```
binance_delisting_announce_short_alt          → graveyard (R-2 wf FAIL, paradigm 87)
listing_oversold_recovery_long                → graveyard
listing_pre_announce_leak_long_alt            → graveyard (phase0 substrate halt, paradigm 89)
listing_pump_first60min                       → graveyard (paradigm 121, R-1 SHORT n=161 t=-1.55 perm_p=0.522)
listing_volume_cliff                          → graveyard (R-2)
lifecycle_pump_decay                          → R-4 (Day-30 SHORT decay, R-5 not yet seeded)
```

**Listing event family inventory verdict**: **5/5 R-1 PoC graveyards + 1 R-4 pending = R-5 active 없음**. Dispatch context "paradigm 121 R-5 LIVE 추정" = **FALSE assumption**.

### 2. paradigm 121 `listing_pump_first60min` R-1 detail verify (INDEX + poc__metrics.json)

```
phase=graveyard (created 2026-05-13)
hypothesis: "Short at minute-60 close, exit at hour-4 close"
graveyard_reason:
  - n=161 cohort
  - Base (entry=60min, hold=180min): median +0.53% mean -2.58% t=-1.55
  - Permutation sigma = -0.04 (listing-anchored = no better than random in [60,1200] min)
  - hyp_b high_pump (>=+20%, n=21) median -4.57% mean -9.96% t=-1.85 (SHORT)
  - All 12 (entry,hold) grid cells negative mean (t-stat -0.01 ~ -1.81)
  - perm_p_one_sided 0.522
  - Conclusion: "lifecycle_pump_decay mechanism (slow price-discovery fade) operates on daily timescale, NOT intraday"
```

**Material findings for paradigm 161 baseline cross-comparison**:
- paradigm 121 R-1 was SHORT direction with intraday hold (60→180m)
- NO 4-quadrant SNT (one-sided SHORT only)
- paradigm 121 was concluded "intraday timescale mechanism absent"
- LONG continuation direction NOT tested at first 60min × intraday hold (gap exists)
- hyp_b high_pump SHORT n=21 sparse — Lesson #11 borderline

### 3. paradigm 89 `listing_pre_announce_leak_long_alt` cross-reference

```
phase: graveyard (phase0 fundamental halt)
graveyard reason (Lesson #28): substrate availability 시간 차원 부재
  - Binance Futures perp onboardDate 이전 substrate 자체 부재
  - BILLUSDT pre-onboard HTTP 404 verified
```

paradigm 161 substrate audit: post-onboardDate first 60min, 즉 **post-listing window**이므로 Lesson #28 면제. paradigm 89 ≠ paradigm 161 substrate class.

### 4. paradigm 87 `binance_delisting_announce_short_alt` cross-reference

```
phase: graveyard (R-2 FRAGILE_TEMPORAL_WF_FAIL)
R-1 metrics: n=57, A_focus_SHORT obs_mean +1380bp sigex +2.23 perm_p 0.062 prob_pos 1.00 3-gate PASS
R-2 result: 5-fold TS-CV 1/5 PASS (2025Q4 single outlier)
Lesson #26: small-sample Concentration Gate per-quarter blind spot
```

paradigm 161 vs paradigm 87: both Category A external event injection, both listing event family, but:
- paradigm 87 = delisting event (exit-side forced exit, lesson #27 sub-mechanism)
- paradigm 161 = listing event (entry-side new demand)
- Sub-mechanism asymmetry (Lesson #27 amendment 분리)

### 5. paradigm 156 `btc_funding_rate_p90_regime_alt_directional_4h` cross-reference (Lesson #67 candidate 1st dogfood)

```
phase: graveyard (BROAD_FALSIFIED)
mechanism: BTC funding rate as cross-asset macro leverage skew signal
- A: BTC funding ≥ p90 × 13 alts directional
- B: BTC funding ≤ p10 × 13 alts directional
R-1: 4/4 quadrants 3-gate FAIL, 0/52 (cumulative) symbol-quadrant ci_lower>0
Lesson #67 candidate 1st dogfood: "macro single-asset broadcast antipattern"
```

paradigm 161 vs paradigm 156 — **Lesson #67 candidate audit**:
- paradigm 156: BTC = trigger source (every 4h bar event-anchor; cross-asset broadcast every period)
- paradigm 161: BTC = conditional split modifier (regime filter on listing event trigger)
- **antipattern ESCAPE 가능**: BTC가 trigger 아닌 conditioning filter. listing event가 primary trigger.
- 단 단일 BTC asset이 macro proxy로 sufficient한지 별도 audit 필요 — semi-escape

### 6. paradigm 158 `alt_extreme_24h_PUMP_24h_continuation_long` + paradigm 117 cross-reference

magnitude-event family (paradigm 117 + 158) = family-retire ELIGIBLE per §6.55.
paradigm 161 vs magnitude-event family:
- paradigm 158: per-sym rolling 24h return p90 magnitude trigger (universe-internal magnitude)
- paradigm 161: listing event boundary trigger (external event injection)
- **Family-distinct**: NOT magnitude-event family (event-injection class)

### 7. §6.57 next-action stale recommendation chain audit (Lesson #61 amendment 3rd post-confirmation dogfood)

| Recommendation source | Claim | Verified inventory | Verdict |
|---|---|---|---|
| paradigm 157 §6.54 | paradigm 158 (24h drawdown reversion) "fresh" | DNA 6/6 paradigm 117 duplicate | STALE (R-0 catch — 1st dogfood) |
| paradigm 158 §6.55 | paradigm 159 (calendar anchor) "DNA 0/6 fresh" | DNA 4/6 paradigm 113 family | STALE (R-0 catch — 2nd dogfood) |
| **paradigm 160 §6.57** | **paradigm 161 (listing + BTC macro modifier)** **"listing family R-5 active, family-retire 아님"** | **listing family 5/5 R-1 graveyards, lifecycle_pump_decay R-4 only, NO R-5 active** | **STALE (this dogfood — 3rd post-confirmation catch)** |

**Lesson #61 amendment 3rd consecutive post-confirmation dogfood SUCCESS** — amendment hook 안정적으로 stale §next-action chain 검출.

## R-0 family-distinct strict 4-dim audit (Lesson #62 CONFIRMED, 5 dogfoods)

paradigm 161 vs paradigm 121 (listing_pump_first60min) base:

| Dim | paradigm 121 base | paradigm 161 candidate | Strict change? |
|---|---|---|---|
| 1. Statistic class | listing event boundary + first 60min pump magnitude | listing event boundary + first 60min + BTC 30d return regime | **MARGINAL** (BTC regime added as conditioning filter, base statistic unchanged) |
| 2. Universe scope | 161 listing events (Binance Futures USDT perp) | ~388 listing events (expanded backfill) × BTC regime split (2 sub-cohorts) | **PASS** (regime stratification new structure, 2.4x sample expansion) |
| 3. Entry-side class | post-listing minute-60 close (intraday SHORT) | post-listing minute-60 close (intraday LONG continuation primary + 4-quadrant SNT) | **PASS** (direction reversed: SHORT-only → 4-quadrant SNT bilateral) |
| 4. Mechanism alpha | intraday pump-fade SHORT | listing pump × BTC bull regime LONG continuation | **PASS** (mechanism alpha class change: pure listing → listing × macro conditional) |

**Strict count: 3/4 PASS + 1 MARGINAL**. Lesson #62 ≥2 strict 충족. **Family-distinct audit PASS but boundary**.

⚠️ Important caveat: paradigm 121 R-1 conclusion was "intraday timescale mechanism absent (mean -2.58%, perm sigma -0.04)". paradigm 161 adds BTC regime conditioning, but base substrate already characterized as **null at intraday**. **Lesson #56 OUTCOME-LEVEL family proxy risk HIGH** — regime conditioning rarely rescues null base.

## R-0 prescreen complete matrix (14 axes)

| Axis | Verdict | Detail |
|---|---|---|
| 1. Inventory check (Lesson #61 amendment) | **STALE §next-action 3rd dogfood SUCCESS catch** | paradigm 121 NOT R-5 LIVE, listing family 5/5 graveyard |
| 2. Family-distinct strict 4-dim (Lesson #62) | ⚠️ 3/4 PASS + 1 MARGINAL boundary | dim 1 statistic class marginal (regime conditioning) |
| 3. Lesson #67 candidate (macro broadcast antipattern) | ⚠️ SEMI-ESCAPE | BTC = conditioning filter not trigger, but single-asset macro proxy |
| 4. Substrate (Lesson #28) | ✅ PASS | listing event registry + 1m OHLCV first 60min + BTC 4h klines all archive |
| 5. Sample density (Lesson #11) | ⚠️ BORDERLINE | ~388 events / 2-regime split / 4-quadrant SNT = ~48/cell marginal |
| 6. SNT 4-quadrant (Lesson #19) | ✅ planned | A bull×LONG / A bull×SHORT / B bear×SHORT / B bear×LONG |
| 7. Data window ratio (Lesson #30) | ✅ PASS | listing event 2.4yr full-window |
| 8. **OUTCOME-LEVEL family proxy (Lesson #56)** | **❌ HIGH RISK FAIL** | listing family 5/5 graveyard (incl. paradigm 121 base) — outcome convergence likely |
| 9. Axis stacking (Lesson #21) | ⚠️ ADJACENT | listing event + BTC regime = 2-axis but conditional split (not statistic stacking) |
| 10. Same-bar same-substrate (Lesson #58) | ✅ EXEMPT | cross-substrate (klines vs BTC macro) |
| 11. Mirror hypothesis antipattern | ✅ N/A | SNT bilateral planned |
| 12. Listing family family-retire eligibility | ❌ 5/5 R-1 graveyards | paradigm 161 = 6th attempt risk; family-retire eligibility cross post-paradigm 161 |
| 13. Lesson #68 candidate adjacency | ✅ ESCAPE | listing event = per-event idiosyncratic, NOT session-boundary universe-anchor |
| 14. paradigm 158 magnitude-event family proxy | ✅ DISTINCT | external event-injection vs internal magnitude |

## R-0 verdict

**Two independent halt-class findings**:

### A. Lesson #61 amendment 3rd post-confirmation dogfood SUCCESS (procedural)

§6.57 next-action 권고문 "listing event family은 R-5 active이며 family-retire 아님" = **FALSE inventory claim**. 실제 inventory:
- listing_pump_first60min: graveyard
- listing_volume_cliff: graveyard (R-2)
- listing_oversold_recovery_long: graveyard
- listing_pre_announce_leak_long_alt: graveyard (phase0 substrate halt)
- binance_delisting_announce_short_alt: graveyard (R-2 wf fail)
- lifecycle_pump_decay: R-4 (NOT R-5; Day-30 timescale, different from intraday)

**Listing event family 5/5 R-1 PoC graveyards + lifecycle_pump_decay R-4 only = R-5 active 없음**.

### B. Lesson #56 OUTCOME-LEVEL family proxy HIGH RISK predictive

paradigm 121 base R-1 결과 = "intraday timescale mechanism absent at first 60min" (perm sigma -0.04, all 12 grid cells negative). paradigm 161 = paradigm 121 base + BTC regime modifier filter. **Lesson #56 OUTCOME-LEVEL predictive**: null base에 regime conditioning 추가하는 paradigm은 13 prior instances (paradigm 145+147v2+148+149+150+154+ ... funding family regime variations 등) **모두 OUTCOME family proxy 함정**. paradigm 161 R-1 forecast outcome:
- A_bull×LONG: paradigm 121 base 12 cells 모두 negative mean → bull regime split도 fee-floor sub-threshold 예상
- 4-quadrant 3-gate FAIL forecast probability > 0.90 (13 Lesson #56 instances historical base rate)

### Listing family family-retire eligibility status

paradigm 161 R-1 dispatch + BROAD_FALSIFIED 시 listing family = **6th R-1 graveyard** → family-retire formal ELIGIBLE (5+ graveyards threshold prior + cross-mechanism variants exhausted: SHORT first60min / SHORT day30 / LONG oversold recovery / LONG pre-announce / SHORT delisting + LONG×BTC regime = full 6-axis mechanism coverage exhausted).

paradigm 161 R-1 미실행 시 family-retire 5 graveyards (5/6 mechanism axes), retire eligibility deferred.

## Recommendation: R-0 HALT (R-1 NOT DISPATCHED)

**Halt rationale**:
1. **Lesson #61 amendment 3rd post-confirmation catch** — dispatch context "paradigm 121 R-5 LIVE" + §6.57 "listing family R-5 active" 둘 다 FALSE. amendment hook 정상 작동.
2. **Lesson #56 OUTCOME-LEVEL HIGH RISK predictive** — paradigm 121 base intraday null → BTC regime conditioning rescue 가능성 historical base rate < 10%.
3. **Lesson #62 boundary** — dim 1 statistic class marginal (regime conditioning이 statistic class 변경인지 conditioning split인지 ambiguous, paradigm 156 funding p90 broadcast과 mechanism-class equivalent risk).
4. **Listing family 5/5 R-1 graveyard outcome convergence** — paradigm 161 R-1 BROAD_FALSIFIED 시 family-retire 6th cumulative 강제. paradigm 161 dispatch ritual로 R-1 dispatch보다 family-retire formal verdict가 더 가치 있음.
5. **31-streak non-PASS milestone** — compute saving + Lesson #61 amendment 3rd dogfood procedural value > marginal R-1 information.

## Next paradigm 162 recommendation

**Lesson #61 amendment strict 적용** — inventory check (slug grep + DNA 4-dim audit + family-retire eligibility table) 의무.

### 후보 options

| Option | Paradigm | Inventory check expected | Family-distinct strict | Family-retire risk | Recommendation |
|---|---|---|---|---|---|
| **α (⭐⭐⭐ 권고)** | `alt_lifecycle_pump_decay_R4_R5_promotion_track` (lifecycle_pump_decay paradigm @ R-4 → 직접 R-5 promotion 작업, NEW R-1 dispatch 아님) | INDEX R-4 phase confirmed, listing family family-retire 면제 (R-5 seed track) | N/A (promotion track, not new R-1) | ESCAPE (uses existing R-5 candidate) | listing family 유일 R-5-eligible paradigm. R-1 dispatch space 우회 |
| β | `alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h` (anchor: event 후 24h 최고점 close anchor, mean-reversion direction) | INDEX R-0 untried | 3/5 fresh expected | LOW (anchor class fresh) | Anchor 새 class (event-anchor 아닌 self-anchor), magnitude-event family distinct |
| γ | `alt_token_unlock_cliff_LONG_pre_event_positioning_smart_money_directional_72h` (paradigm 88 mirror direction LONG pre-event positioning) | paradigm 88 SHORT graveyard FAIL_SCOPE | 4/4 strict (direction + entry-side + mechanism + timescale) | MEDIUM (token unlock family 1 graveyard) | Lesson #27 entry-side amendment 적용 가능, freemium 차단 위반 verify 필요 |
| δ ✗ | `alt_listing_pump_first60min_LONG_continuation_4h` (paradigm 121 mirror direction LONG simple) | paradigm 121 graveyard direct mirror | 2/4 boundary | HIGH (5/5 listing family) | **차단 권고** (listing family-retire eligibility 무력화 + Lesson #56 OUTCOME 8th instance risk) |
| ε ✗ | `alt_listing_pump_x_funding_regime_modifier_directional_4h` (paradigm 161 funding regime variant) | listing family member | 2/4 boundary | HIGH (listing 6th + funding Tier 4) | **차단 권고** (이중 family proxy + Lesson #56 family proxy duplication) |

**Option α 1순위 권고 rationale**:
- lifecycle_pump_decay = INDEX R-4 phase, listing family 유일 R-5-eligible 후보. R-1/R-2/R-3 metrics 이미 존재 (`backend/runs/research_track/lifecycle_phase/`)
- paradigm 161 R-1 dispatch space 우회 가능 (family-retire eligibility deferred)
- gate_eval 검토 → R-5 promotion decision = paper pool seed proposal artifact 작성 (user approval gate)
- compute cost trivial (no new R-1 dispatch, gate evaluator + seed_proposal.md only)
- listing family **R-5 active 부재 결정적 갱신** — paradigm 161 dispatch context "R-5 LIVE 추정" FALSE inventory misread 해소

**Option β 2순위**: post-event self-anchor class fresh, magnitude-event family distinct.

## Campaign 진행 상태 갱신 (2026-05-21 16:23 KST 본 R-0 halt 후)

- R-5 seeded: 14 paradigms (paradigm 22 funding_carry + paradigm 24 premium 3종 + paradigm 69 BTC RV highvol + 127+128 dual + ...)
- Counter: 160 → 161 (substantive R-0 halt increment)
- Graveyards: 102 cumulative (paradigm 161 NOT graveyard; R-0 halt prevents materialization)
- Lessons: 34 confirmed + 20 candidates → **34 confirmed + 20 candidates** (Lesson #61 amendment 3rd post-confirmation dogfood SUCCESS, Lesson #56 OUTCOME-LEVEL FAMILY PROXY 13th predictive instance avoided, Lesson #62 5th dogfood boundary case xref, Lesson #67 candidate semi-escape ambiguity raised)
- Listing event family: 5 cumulative graveyards (5/6 mechanism axes exhausted) + 1 R-4 (lifecycle_pump_decay) → family-retire eligibility deferred pending paradigm 161 dispatch or lifecycle_pump_decay R-5 promotion
- Magnitude-event family: 2 cumulative (paradigm 117+158) — family-retire ELIGIBLE
- Calendar/clock-anchor family: 2 cumulative — advisory caution
- 31-streak non-PASS milestone (R-0 halt does NOT extend streak per Lesson #61 amendment dogfood policy; counter still increments)
- Compute saved: ~20-25x vs R-1 ritual dispatch (4-quadrant SNT × ~388 events × 2-regime split = ~6,000 events × 4 cells × backfill)

## paradigm 162 next-action (Lesson #61 amendment strict template)

- Slug grep result: `ls research_track/ | grep -iE "lifecycle|pump_decay"` → `lifecycle_pump_decay` (R-4), `lifecycle_phase/`
- DNA 4-dim audit: N/A (promotion track, not new R-1 dispatch)
- Family-retire eligibility cross-reference: listing event family 5 R-1 graveyards (paradigm 161 R-0 halt 결과 5/6 mechanism axes coverage). lifecycle_pump_decay R-4 promotion = listing family R-5 seed track (family-retire eligibility deferred).
- Prior R-3+ verdict 확인: lifecycle_pump_decay R-3 metrics 존재 (`backend/runs/research_track/lifecycle_phase/r3__metrics.json`), gate_eval__r2.md 존재. R-3 verdict + R-4 gate eval 검토 필요.

## END 2026-05-21 16:23 KST

paradigm 161 R-0 HALT_BY_INVENTORY_DUPLICATE_LESSON_61_AMENDMENT_3RD_POST_CONFIRMATION_DOGFOOD_SUCCESS + LISTING_FAMILY_RETIRE_ELIGIBILITY_RISK_DEFERRED. R-1 NOT DISPATCHED. Counter 160→161 substantive R-0 increment.

**Findings**:
1. dispatch context "paradigm 121 R-5 LIVE 추정" = FALSE (paradigm 121 = graveyard, R-1 SHORT n=161 t=-1.55 perm_p=0.522)
2. §6.57 next-action "listing family R-5 active" = STALE (listing family 5/5 R-1 graveyards, lifecycle_pump_decay R-4 only)
3. Lesson #61 amendment 3rd consecutive post-confirmation dogfood SUCCESS — amendment hook stable
4. Lesson #56 OUTCOME-LEVEL FAMILY PROXY 13th predictive instance avoided (paradigm 121 base null intraday → BTC regime rescue base rate <10%)
5. Lesson #62 dim 1 statistic class boundary marginal (regime conditioning ambiguous)
6. Lesson #67 candidate semi-escape (BTC conditioning filter not trigger, but single-asset macro proxy)

**Next paradigm 162 권고**: Option α `alt_lifecycle_pump_decay_R4_R5_promotion_track` — lifecycle_pump_decay R-4 phase 직접 R-5 promotion decision (listing family 유일 R-5-eligible), R-1 dispatch space 우회, listing family R-5 active 상태 갱신.

31-streak non-PASS milestone. R-5 yield 6.25% (unchanged). 메모리 정책 strict 준수: [[feedback-paradigm-campaign-continuous-parallel]] dispatch 지속, [[feedback-persistence-over-efficiency]] 실패 누적 정상, [[feedback-direct-recommendation]] R-1까지 자율 진행 → R-0 halt 직접 결정.
