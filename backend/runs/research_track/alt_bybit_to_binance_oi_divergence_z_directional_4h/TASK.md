# paradigm 187 — `alt_bybit_to_binance_oi_divergence_z_directional_4h`

**Status**: R-0 INVENTORY HALT — R-1 NOT DISPATCHED
**Verdict**: `R0_HALT_BY_DNA_DUPLICATE_TRIPLE_PRIOR_PARADIGM_104_R1_BROAD_FALSIFIED_PLUS_PARADIGM_166_R0_INVENTORY_HALT`
**Date**: 2026-05-22 10:15 KST
**Counter**: 186 → 187 (substantive R-0 increment per paradigm 138/139/140/151/154/155/159/161/163/164/165/166/167 precedent)
**Dogfood**: Lesson #69 5-item strict template post-CONFIRMED **Nth dogfood** SUCCESS (Items 1+4 HARD FAIL = R-0 halt unambiguous); Lesson #61 amendment **9th consecutive post-confirmation** SUCCESS — paradigm 186 §next_action_recommendation path (B) "fresh paradigm dimension (cross-asset / event-anchored / microstructure)" was correctly issued, but **the proposed slug `alt_bybit_to_binance_oi_divergence_z_directional_4h` selected by dispatch falls inside cross-exchange OI divergence family Tier 4 retire** (paradigm 104 R-1 + paradigm 166 R-0). Lesson #62 boundary DNA **HARD FAIL 0/5 strict** vs paradigm 104 (identical mechanism + universe + hold + statistic class + substrate paths).

## Hypothesis (proposed but blocked)

Bybit ↔ Binance per-sym 4h-interval OI **divergence z-score** trigger.

- **Trigger statistic**: per-sym OI divergence = `(Bybit_OI / Bybit_OI_30d_mean) - (Binance_OI / Binance_OI_30d_mean)` normalized → 90d rolling z-score
- **Threshold**: |z|≥2 directional both sides (4-quadrant SNT)
- **Universe**: 7 deep-syms (paradigm 103/104 cohort — AVAX/BCH/BNB/DOGE/LINK/SOL/XRP)
- **Hold**: 4h primary + 8h/12h sweep
- **Substrate**: Bybit V5 OI archive + Binance OI 5m archive (both verified prior-art)
- **Direction**: 4-quadrant SNT bilateral (A focus Bybit>Binance + UP + LONG / A mirror UP + SHORT / B same-sign DOWN + SHORT / B mirror DOWN + LONG)

## Lesson #69 5-item strict template post-CONFIRMED dogfood result

### Item 1 — Lesson #61 amendment slug grep (CRITICAL — TRIPLE prior-art found)

`ls research_track/ | grep -iE "cross_exchange_oi|bybit_oi|oi_divergence|cross_ex_oi|venue_oi"`:

```
alt_cross_exchange_oi_divergence_bybit_vs_binance_directional_4h        (paradigm 166, R-0 INVENTORY HALT 2026-05-21)
cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h   (paradigm 104, R-1 BROAD_FALSIFIED_PRIMARY_HOLD 2026-05-19) ← DNA EXACT MATCH
```

**Verdict**: Both prior paradigms cover the exact mechanism proposed (per-sym Binance vs Bybit OI imbalance z-score normalized + |z|≥2 trigger + 7 deep-syms + 4h primary hold). The current slug `alt_bybit_to_binance_oi_divergence_z_directional_4h` is the **3rd generation** of the identical hypothesis class — only the slug naming changes ("bybit_to_binance" word order + statistic naming convention "divergence_z" vs "level_differential" vs "divergence_bybit_vs_binance"). **HARD FAIL on Item 1**.

### Item 2 — Lesson #28 amendment substrate-shape audit

- **Substrate-existence**: paradigm 104 prior verified Bybit V5 OI + Binance OI archive — both PERMANENT ASSET caches (`backend/runs/ohlcv_cache/{binance_oi,bybit_oi}/{SYM}_1h.joblib`, 7 syms × 2 venues, paradigm 104 backfill 325.5s wall-clock, 869d data window ratio 1.000)
- **Substrate-shape**: 1h frame at 4h hold is fine; no shape problems
- **Verdict**: PASS (substrate fine, but **moot** — halt cause upstream Item 1 DNA duplicate)

### Item 3 — Lesson #11 sample density (per quadrant per quarter)

paradigm 104 directly measured (already in graveyard):
- z=2.0: A_focus n=7,174 / B_focus n=6,763, all 10 quarters ≥30
- z=2.5: A_focus n=3,425 / B_focus n=2,774, all 10 quarters ≥30 (chosen as focus)
- Current task message proposed |z|≥2 → already-measured at paradigm 104 z=2.0 cell

**Verdict**: PASS (strong, moot due to upstream halt)

### Item 4 — DNA 4-dim audit table vs paradigm 104 (Lesson #62 strict count)

| Dimension | paradigm 104 (R-1 GRAVEYARD) | paradigm 187 (proposed) | Strict count |
|---|---|---|---|
| **Statistic class** | `(binance_OI − bybit_OI)` 30d-median-norm + 30d z-score on 1h frame | `(bybit_OI/bybit_30d_mean) − (binance_OI/binance_30d_mean)` then 90d rolling z-score | **NOT STRICT** — sign-convention flip + 30d→90d window relaxation + median→mean normalization are algebraic re-labelings; both reduce to cross-venue OI imbalance per-sym z-score |
| **Universe** | 7 deep-syms (AVAX/BCH/BNB/DOGE/LINK/SOL/XRP) | 7 deep-syms (identical cohort) | **NOT STRICT** — exact match |
| **Entry-side trigger** | \|z\|≥2.5 directional both sides + sweep to z=2.0 (n=7,174/6,763) | \|z\|≥2 directional both sides | **NOT STRICT** — paradigm 104 sweep already measured z=2.0 cell |
| **Mechanism alpha** | cross-venue OI imbalance reveals capital flow direction | cross-venue OI imbalance reveals capital flow imbalance direction | **NOT STRICT** — identical mechanism statement |
| **Hold horizon** | 4h primary + 60m/480m/1440m sweep | 4h primary + 8h/12h sweep | **NOT STRICT** — 4h primary identical, 8h (=480m) cell already swept, 12h (=720m) interpolatable between 480m PASS and 1440m PASS measurements |

**Strict count: 0/5** — Lesson #62 **HARD FAIL** (required ≥2/5). DNA duplicate confirmed at maximum strength.

This is the **identical DNA audit result** that paradigm 166 produced on 2026-05-21 (0/5 strict), which itself is the second-generation of paradigm 104. paradigm 187 = **3rd generation re-attempt of the same hypothesis**.

### Item 5 — Family-proxy cross-reference (Lesson #56 OUTCOME-LEVEL)

Cross-exchange family Tier 4 retire **8 cumulative graveyards** (per paradigm 166 audit):
- paradigm 103 `cross_exchange_funding_spread_binance_bybit_alt_directional_8h` (BROAD_FALSIFIED_FEE_FLOOR)
- paradigm 104 `cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h` (BROAD_FALSIFIED_PRIMARY_HOLD) ← **DNA EXACT MATCH**
- paradigm 105 `cross_exchange_funding_spread_binance_bitget_alt_illiquid_venue` (Tier 4 illiquid venue path closeout)
- paradigm 147v1 / v2 `bybit_to_binance_lead_lag_oi_delay` (Tier 4 retire)
- paradigm 148 `bybit_to_binance_lead_lag_PRICE_delay` (Tier 4 retire)
- paradigm 160 `cross_exchange_volume_share_rotation` (Tier 4 retire, fee-floor)
- paradigm 166 `alt_cross_exchange_oi_divergence_bybit_vs_binance_directional_4h` (R-0 INVENTORY HALT 2026-05-21)

paradigm 187 would be **9th cumulative blocked instance**. paradigm 22 R-5 funding_dispersion ETCUSDT remains sole family exception.

**Lesson #56 OUTCOME-LEVEL prediction NEUTRAL** — halt is upstream DNA duplicate Item 1+4, not downstream OUTCOME proxy. Instance counter unchanged.

## Verdict tree

1. **Item 1 slug grep HARD FAIL** — paradigm 104 + paradigm 166 dual prior-art match
2. **Item 4 DNA 4-dim audit 0/5 strict HARD FAIL** (Lesson #62 boundary — identical result to paradigm 166)
3. Item 2 substrate PASS (moot)
4. Item 3 sample density PASS (moot)
5. Item 5 family-proxy NEUTRAL (halt cause upstream)

**Cumulative halt signal**: 2 HARD FAIL + 2 moot PASS + 1 NEUTRAL = **R-0 inventory halt unambiguous (3rd generation)**

## Why dispatch message claimed "5/5 strict distinct" (factual error)

The dispatch task message §Lesson #62 section asserted:
> "**5/5 strict distinct**: statistic class: cross-venue OI ratio z-score (NEW); universe: 7 deep syms (paradigm 103 cohort); entry-side: 4h spike-trigger event (sparse-trigger class); mechanism: cross-exchange capital flow imbalance (NEW); hold: 4h fixed (standard)"

**Factual error**: this claim is **inverted from reality**.
- "statistic class: NEW" — FALSE. Cross-venue OI ratio z-score = paradigm 104 statistic with normalization-window swap (30d↔90d, median↔mean) and sign convention. Both reduce to same cross-venue OI imbalance.
- "universe: 7 deep syms (paradigm 103 cohort)" — explicit IDENTITY admission, not distinctness.
- "entry-side: 4h spike-trigger event" — paradigm 104 entry-side IDENTICAL (4h frame, |z|≥2-2.5 trigger).
- "mechanism: cross-exchange capital flow imbalance (NEW)" — FALSE. paradigm 104 graveyard §Cross-paradigm 103 comparison explicit: "OI level differential carries stronger signal than rate differential" = same cross-venue OI capital flow mechanism.
- "hold: 4h fixed (standard)" — paradigm 104 hold IDENTICAL.

**Correct count: 0/5 strict distinct.** The dispatch message §Lesson #62 reasoning made the same blind-spot error that paradigm 166's audit (paradigm 165 §next-action authored 2 days post-paradigm 104 R-1 graveyard) had already caught and documented.

## Lesson #61 amendment 9th consecutive post-confirmation dogfood SUCCESS

paradigm 186 §next_action_recommendation explicitly offered:
> "paradigm 187 = (A) continuous-weighting framework 14-sym universe Tier 4 retire formal decision; OR (B) framework abandon + fresh paradigm dimension (cross-asset / event-anchored / microstructure). Recommendation A — 4 sub-modes 4/4 life-changing FAIL implies framework structural limit not parameter tuning."

**Dispatch deviation**: dispatch user message selected path (B) "fresh paradigm dimension" but landed in **cross-exchange OI divergence family which is Tier 4 retired** (paradigm 104 + 166). The dispatch task message §slug header explicitly cited `paradigm 103 family 잔여 path 3순위 (cross-ex OI divergence)` — this is incorrect: cross-ex OI divergence is **not a remaining path #3** but the **already-executed path** with prior graveyard.

**Lesson #61 amendment 9th consecutive post-confirmation SUCCESS** — R-0 inventory halt catches the stale dispatch recommendation chain (paradigm 186 → user → paradigm 187 proposal). The cross-reference between paradigm 186 §next-action "fresh dimension" and paradigm 166/104 prior graveyards was not performed at dispatch authoring time.

## Cross-exchange family Tier 4 retire reinforcement (9 cumulative confirmed at paradigm 187 R-0)

Memory pin [[project-paradigm-103-cross-exchange-funding-spread]] + [[project-paradigm-104-cross-exchange-oi-level]] + paradigm 147v1/147v2 + 148 + 160 + 105 illiquid + paradigm 166 R-0 + paradigm 187 R-0 = **9 cumulative blocked instances**. Cross-exchange family axis space **definitively exhausted** at this 9th cumulative instance. paradigm 22 R-5 (funding_dispersion ETCUSDT) remains sole exception.

paradigm 166 §next-action explicit:
> "Recommendation: Option δ (Mark-index basis dislocation single-exchange) — family-distinct strict count highest, substrate-shape pre-verified, axis untouched."

However paradigm 167 R-0 (2026-05-21 22:36 KST) subsequently demonstrated that paradigm 166's Option δ recommendation was itself a stale recommendation — basis arbitrage family also has 4 prior graveyards (paradigm 105/111/121/131). Both paradigm 166 and paradigm 167 next-action paths were stale (Lesson #61 amendment 7th + 8th consecutive dogfood at the time).

## Cross-paradigm 104 R-1 result summary (already-measured, paradigm 187 would duplicate)

From paradigm 104 GRAVEYARD.md (re-stated here for dispatch operator clarity):

### 4-quadrant SNT (focus z=2.5 / hold 240m primary)
| Quadrant | n | net (bp) | gross (bp) | sigex | perm_p | ci_lower | 3-gate |
|---|---|---|---|---|---|---|---|
| A_focus (Binance↑ + LONG) | 3,425 | +9.70 | +25.70 | +7.09 | **0.988** | +2.05 | **FAIL (perm_p)** |
| A_mirror (Binance↑ + SHORT) | 3,425 | −41.70 | −25.70 | −5.96 | 0.000 | −49.21 | FAIL |
| B_focus (Bybit↑ + SHORT) | 2,774 | −21.12 | −5.12 | −0.83 | 0.206 | −29.12 | FAIL |
| B_mirror (Bybit↑ + LONG) | 2,774 | −10.88 | +5.12 | +1.63 | 0.952 | −18.85 | FAIL |

### 16bp fee floor + upward-bias trap
- A_focus gross +25.70bp **>** 16bp fee floor (no Lesson #56 BROAD_FALSIFIED_FEE_FLOOR)
- BUT perm_p=0.988 due to **upward-bias pool drift trap** (Lesson #32 variant)

### Hold sweep (primary 240m FAIL + 480m PASS but Life-changing 4-dim FAIL)
| Hold | gross | perm_p | 3-gate | Concentration | Life-changing edge/trade |
|---|---|---|---|---|---|
| 60m | +9.96 | 1.000 | FAIL | n/a | n/a |
| 240m primary | +25.70 | 0.988 | FAIL | FAIL (2/7 syms ci_pos) | n/a |
| 480m | +42.11 | 0.045 | PASS | PASS (4/7 syms, 8/10 q) | **0.26% FAIL** ≥2% |
| 1440m | +92.78 | 0.000 | PASS | PASS (4/7 syms, 8/10 q) | **0.77% FAIL** ≥2% |

### Concentration Gate (A_focus z=2.5 / 240m)
- 2/7 syms ci_pos (BCH +28.58 / DOGE +25.32 only); 3/7 strongly negative (AVAX −31.57 / BNB −30.25 / SOL −57.55)
- Per-quarter: 7/10 pos_t but 2024Q4 single-quarter +69.73 carries 36% cumulative mean (paradigm 87 lesson #26 single-fold-driven antipattern)

### paradigm 104 §next-action explicit (still authoritative for paradigm 187):
> "Halt at R-1. No R-2 spawn — life-changing 4-dim FAIL even at PASSING longer holds rules out paradigm 104 advancement."
> "Re-classify path #3 as 'partial-mechanism with horizon constraint'."

## Lesson #42 prediction verify (B mirror cell — dispatch claim)

The dispatch message claimed B mirror would be the 5th dogfood for Lesson #42. **Already measured at paradigm 104**:
- B_mirror (Bybit↑ + DOWN bar + LONG reversal direction approximation): paradigm 104 measured B_focus (Bybit↑ + SHORT) gross −5.12bp / sigex −0.83 + B_mirror (Bybit↑ + LONG) gross +5.12bp / sigex +1.63 / perm_p 0.952 — **3-gate FAIL** on both ci_lower and perm_p.
- Bybit-led capitulation MR direction (B mirror cell as proposed): **NOT PASS** at paradigm 104 measurement. Lesson #42 prediction outcome from prior data = **FAIL** (not 5th dogfood SUCCESS).

## Lesson #71 corollary path C test (dispatch claim)

Dispatch claimed paradigm 187 would test Lesson #71 corollary path C on sparse-trigger event utilization (per-sym 1.6% utilization). **Already measured implicitly at paradigm 104**: A_focus z=2.5 trigger n=3,425 over 7 syms × 869d × 4h = 36,498 4h-bars → trigger rate 9.4% × 4h hold / 24h = 1.57% effective per-sym capital occupancy. Life-changing 4-dim at 480m PASSING variant: edge 0.26%/trade << 2%, util 131% nominal (overlap artifact, normalized to ~30-40%) — **edge dimension FAIL**, not utilization dimension.

paradigm 187 would not test Lesson #71 corollary path C in a discriminative way — paradigm 104 already demonstrated the cross-exchange OI divergence sparse-trigger paradigm fails on **edge/trade** not on **utilization**. Path C corollary test inapplicable.

## Lessons confirmed in this R-0

| Lesson | Status | Evidence |
|---|---|---|
| **Lesson #61 amendment** | **9th consecutive post-confirmation SUCCESS** | Dispatch task message §slug derivation from paradigm 186 §next-action path (B) "fresh dimension" landed in cross-exchange family Tier 4 retired axis — provenance audit caught at R-0 |
| **Lesson #62** | **HARD FAIL 0/5 strict** vs paradigm 104 (12th cumulative boundary dogfood) | All 5 dims duplicate of paradigm 104 |
| **Lesson #69** | **Post-CONFIRMED dogfood SUCCESS** (5-item template Items 1+4 unambiguous HARD FAIL signal pre-dispatch) | 5-item strict template executed; Item 1+4 produced unambiguous HARD FAIL |
| **Lesson #28 amendment** | **Post-amendment dogfood NEUTRAL** | Substrate-shape audit PASS but moot — halt cause upstream DNA duplicate |
| **Lesson #56** | NEUTRAL non-instance | Halt is upstream DNA duplicate, instance counter unchanged 17 |
| **Lesson #21** | NEUTRAL non-violation | Single-axis hypothesis (cross-venue OI ratio z = single derived statistic), not stacking |
| **Lesson #42** | **PRIOR-MEASURED FAIL** (not 5th dogfood SUCCESS) | B mirror cell already measured at paradigm 104 (sigex +1.63 perm_p 0.952 ci_lower −18.85 = 3-gate FAIL) |
| **Lesson #71 corollary path C** | **INAPPLICABLE** | paradigm 104 already showed sparse-trigger event paradigm fails on edge/trade not utilization |
| **Cross-exchange family Tier 4 retire** | **9 cumulative reinforcement** (paradigm 187 would be #9 reattempt) | 103+104+105 illiquid+147v1+147v2+148+160+166 + paradigm 187 R-0 |

## Next-action recommendation for paradigm 188

Per memory [[feedback-persistence-over-efficiency]] + [[feedback-paradigm-campaign-continuous-parallel]] dispatch must continue. Per memory [[feedback-direct-recommendation]] one direct recommendation.

### Critical constraint state (post-paradigm 187 R-0 halt)

- **Continuous-weighting framework family** (paradigm 181/184/185/186): 4 consecutive sub-mode FAIL; paradigm 186 §next-action explicitly recommended (A) **Tier 4 retire formal decision** for the framework class
- **Cross-exchange family**: 9 cumulative blocked (paradigm 22 R-5 only exception) — definitively exhausted
- **Funding family**: 11 cumulative graveyard (paradigm 22 R-5 narrow exception)
- **Basis/markPrice 4h MR sub-axis**: 5 cumulative blocked (paradigm 22/24 R-5 daily-frame follow exceptions only)
- **Taker imbalance family**: Lesson #57 formal CONFIRMED + Tier 4 ratified
- **OI velocity family**: Tier 4 (paradigm 71/86)
- **Higher-order moment family**: Tier 4 CONFIRMED candidate
- **Range estimator family**: Tier 4 CANDIDATE
- **Stateful CP family**: advisory caution
- **Stale-recommendation chain in INDEX**: paradigm 165 → 166 next-action stale (caught 167) → 167 next-action stale (subsequent verification needed) → 186 next-action path (B) stale (caught 187 here)

### Direct recommendation: paradigm 188 = **continuous-weighting framework family Tier 4 retire formal ratification + paradigm 186 §next-action path (A) execute**

Rationale (single direct recommendation per [[feedback-direct-recommendation]]):
1. paradigm 186 §next-action **path (A) was the explicit recommended option** ("Recommendation A — 4 sub-modes 4/4 life-changing FAIL implies framework structural limit not parameter tuning") and was bypassed by dispatch for path (B), which produced the present R-0 halt.
2. Cross-exchange family is **9-cumulative exhausted** — proposing another axis-distinct cross-exchange OI variant (paradigm 187 attempted) violates Tier 4 retire boundary.
3. Continuous-weighting framework formal Tier 4 retire is a **lesson-bookkeeping operation** (not a new R-1 dispatch). It can be ratified as a documentation-only paradigm 188 increment, with the substantive R-0 increment justification being "formal family Tier 4 ratification + paradigm-architect family-retire registry update".
4. After paradigm 188 documentation ratification, paradigm 189 can pivot to a **substantively unexplored axis** (Lesson #61 amendment 10th-eligible permanent-asset boundary).

### Candidate axes for paradigm 189 (post-188 family closure) — UNRETIRED axis space scan

These are candidate axes where prior-art search (Item 1 slug grep) shows **zero or one prior R-1 instance**:

1. **Microstructure tick-level imbalance** (sub-1-minute frame, 12-col WS recorder forward-collection-dependent — paradigm 187 [[project-paradigm-pre-funding-window-divergence]] noted WS recorder accumulating)
2. **Cross-asset macro coupling** (FRED yield curve / VIX / DXY × crypto 4h, paradigm 75/81/118/130 correlation family at 4 graveyards Tier 4 candidate — caution, may also be exhausted)
3. **lifecycle_pump_decay R-5 LIVE validation feedback loop** (paradigm 127/128 active since 2026-05-21, Day-7 baseline 2026-05-28 — first paper signal opportunity but not R-1 dispatch class)
4. **OI-Premium 5m joint paradigm 24 R-5 expansion** (memory [[project-oi-price-decoupling-paradigm]] — DOGE/SOL/LDO 9.0σ/5.4σ/5.7σ paradigm 22 family expansion, R-5 expansion lane open per [[feedback-persistence-over-efficiency]] dispatch continuity)

**Primary recommendation paradigm 189**: Option 4 — **paradigm 22 R-5 family expansion** (premium index z-score paradigm). R-5 expansion lane is the highest-confidence next-action and was the original [[feedback-life-changing-strategy-criterion]] success path. Cross-exchange/funding/OI-velocity/markPrice/range/higher-moment families are 7 retired families; expanding existing R-5 PASS paradigms is the structurally unblocked path.

## Resources committed

- **Task md**: `backend/runs/research_track/alt_bybit_to_binance_oi_divergence_z_directional_4h/TASK.md` (this file)
- **No R-1 script generated** (R-0 halt pre-dispatch)
- **No backfill executed**
- **Wall-clock**: ~6 min (inventory check + DNA audit + lesson dogfood documentation)
- **Compute saved**: ~6 min R-1 + paradigm 104 cache permanent asset reuse = ~6 min total (compared to paradigm 166 R-0 ~11 min, this audit benefited from paradigm 166 already-documented DNA table)

## Counter increment

186 → **187** (substantive R-0 increment per memory pin [[project-paradigm-97-98-99-funding-family-completion]] + paradigm 138/139/140/151/154/155/159/161/163/164/165/166/167 precedent — R-0 halt with multi-lesson dogfood counts as paradigm-architect substantive turn).

**Lessons invoked count: 9** (#21 NEUTRAL single-axis, #28 amendment post-confirmation dogfood NEUTRAL, #42 prior-measured FAIL non-instance, #56 NEUTRAL non-instance instance counter unchanged 17, #61 amendment 9th consecutive post-confirmation SUCCESS, #62 HARD FAIL 0/5 strict 12th cumulative boundary, #69 post-CONFIRMED 5-item template SUCCESS, #71 corollary path C INAPPLICABLE, cross-exchange family Tier 4 retire 8→9 cumulative reinforcement)

## Memory compliance audit (dispatch §STRICT 의무)

- [[feedback-no-freemium-trial]]: PASS (no external paid/freemium API; substrate is paradigm 104 PERMANENT ASSET cache + Bybit V5 public REST + Binance Vision public archive)
- [[feedback-life-changing-strategy-criterion]]: applied — paradigm 104 prior data shows edge 0.26-0.77% << 2%/trade life-changing 4-dim FAIL even at PASSING horizons; paradigm 187 retry would inherit same failure mode
- [[feedback-persistence-over-efficiency]]: COMPLIANT — paradigm 187 R-0 halt is **not** a campaign pause; dispatch continues via paradigm 188 documentation ratification + paradigm 189 family-distinct dispatch
- [[feedback-paradigm-campaign-continuous-parallel]]: COMPLIANT — R-0 halt is a routine dispatch outcome (DNA duplicate prevention), not a policy-level pause
- [[feedback-direct-recommendation]]: COMPLIANT — one direct paradigm 188 + 189 recommendation issued (no AskUserQuestion option menu)
- [[project-paradigm-campaign-closing-rate-snapshot-2026-05-19]]: paradigm 187 R-0 halt **does not advance R-5 yield numerator** (no R-1 dispatched) but **advances cumulative graveyard denominator** to 187 paradigm-count (precise R-5 yield TBD on INDEX update). Snapshot relevance: campaign continues per [[feedback-paradigm-campaign-continuous-parallel]]
