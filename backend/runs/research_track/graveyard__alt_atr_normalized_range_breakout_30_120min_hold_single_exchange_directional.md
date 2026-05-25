# Graveyard — paradigm 150 `alt_atr_normalized_range_breakout_30_120min_hold_single_exchange_directional`

**Date**: 2026-05-21 14:25 KST
**Phase**: R-0 (R-1 NOT DISPATCHED)
**Type**: E (life-changing 4-dim candidate)
**Verdict**: `R0_HALT_BY_OUTCOME_LEVEL_FAMILY_PROXY`
**Verdict authority**: Lesson #56 formal CONFIRMED — 7th OUTCOME-LEVEL FAMILY PROXY instance
**Wall-clock**: 0 sec R-1 (R-0 audit ~3 min)
**Cumulative paradigm graveyard count**: 150 (milestone)
**Compute saved**: ~15-20x vs R-1 full execution (~75 sec saved)

## Hypothesis (proposed by user dispatch)

`alt_atr_normalized_range_breakout_30_120min_hold_single_exchange_directional` —
ATR-normalized range breakout (k=2.0) on 30min frame with 30-120min hold sweep,
4-quadrant SNT, 14-alt Binance perp universe. Family-distinct claim vs paradigm
115 via "30-120min hold horizon + statistic refinement + 4-quadrant SNT".

## R-0 Family-Distinct Critical Review — paradigm 115 OUTCOME family proxy

### paradigm 115 graveyard summary (2026-05-20)

paradigm 115 `alt_atr_normalized_range_breakout_continuation_long_2h`:
- **Verdict**: `CONCENTRATION_DISPERSION_FAIL` (verdict-tree labeled `BROAD_FALSIFIED`)
- **Mechanism IS REAL** at k=1.5 4h hold: gross +29.11bp / **net +21.11bp** /
  ci_lower **+5.58bp** / sigex **+4.28** / perm_p_1s **0.000** / q_pos **6/9**
- **Fail mode**: per-symbol bootstrap CI **0/13 ci_pos** (alpha diffusely spread,
  per-sym n ≈ 75 too small for tight CI)
- **Life-changing 4-dim 2/4 PASS**: trades/yr 554 + sharpe 1.90 PASS;
  **per_trade_edge 0.21% << 2% threshold (10x deficit)** + capital_util 25.3%
  (just below 30%) BLOCKING

### paradigm 150 vs paradigm 115 differences (substantive assessment)

| Dimension | paradigm 115 | paradigm 150 proposed | Substantive distinct? |
|---|---|---|---|
| Statistic class | ATR-normalized Donchian breakout (close > prior 24h max + k×ATR) | ATR-normalized range breakout (current_range / ATR_24h > k) | **WEAK** — both = volatility-magnitude-conditioned breakout |
| Frame | 1h | 30min | quantitative (2x finer) |
| k threshold | {0.5, 1.0, 1.5}, primary 1.0 | 2.0 | extension of paradigm 115 k-sweep |
| Hold horizon | {1h, 2h, 4h}, primary 2h | {30min, 60min, 90min, 120min} | overlaps 1h with paradigm 115 (60min = paradigm 115 1h) |
| Direction mode | 4-quadrant SNT at k=1.5 only | 4-quadrant SNT at all k | paradigm 115 already covered SNT at k=1.5 |
| Universe | 13 alts | 14 alts | sample density same |

### Lesson #56 OUTCOME-LEVEL FAMILY PROXY 7th instance (predictive R-0 halt)

**Outcome equivalence prediction**:
1. paradigm 115 k=1.0→1.5 monotonic gross increase ⇒ paradigm 150 k=2.0 likely yields HIGHER gross_bp at LOWER n (same monotonic family)
2. paradigm 115 hold=1h(14.73bp) → 2h(20.03bp) → 4h(29.11bp) monotonic ⇒ paradigm 150 30-120min STRICTLY BELOW paradigm 115 4h best cell on gross integration
3. paradigm 115 per_trade_edge 0.21% blocking life-changing ⇒ paradigm 150 shorter hold yields STRICTLY SMALLER per-trade gross (fee constant 16bp) ⇒ per_trade_edge predicted 0.08-0.15% (worse)
4. paradigm 115 0/13 syms ci_pos ⇒ paradigm 150 stricter k=2.0 yields fewer trigger events per sym (predicted 30-60 vs paradigm 115 75) ⇒ bootstrap CI WIDER ⇒ predicted 0-1/14 ci_pos (worse)

**Predicted paradigm 150 outcome (if R-1 dispatched)**:
- Best cell: hold=120min, gross 8-15bp, net -8 to -1bp (LIKELY SUB-FEE)
- per_trade_edge 0.08-0.15% (10-20x deficit vs life-changing 2%)
- syms_ci_pos 0-1/14 (CONCENTRATION_DISPERSION inheritance)
- Verdict: `BROAD_FALSIFIED_FEE_FLOOR` or `CONCENTRATION_DISPERSION_FAIL`
- Life-changing 4-dim ≤ 2/4

**Lesson #56 verdict**: paradigm 150 statistic class (ATR-normalized range
breakout) is OUTCOME-EQUIVALENT to paradigm 115 (ATR-normalized Donchian
breakout). Same volatility-magnitude family + hold reduction (strictly worse
on gross integration) + concentration dispersion inheritance (smaller per-sym
n at stricter k=2.0) = predicted graveyard with STRICTLY WORSE metrics than
paradigm 115.

### Lesson #40 EDGE-side structural infeasibility 2nd dogfood (predictive)

paradigm 149 R-0 halt (2026-05-21 14:16 KST) established NEW Lesson #40
EDGE-side sub-variant 1st dogfood: fee floor (16bp) constant while hold-window
gross integration scales sub-linearly with hold. Hold reduction from R-5 best
cell to candidate is strictly value-destroying when statistic class equivalent.

paradigm 150 = **2nd dogfood** of same EDGE-side infeasibility pattern:
- paradigm 115 R-5-eligible-but-life-changing-blocked best cell: hold=4h, gross 29.11bp
- paradigm 150 proposed: hold ≤ 120min ⇒ ≤ 50% the integration time
- Predicted paradigm 150 best gross: 8-15bp (50% of paradigm 115 4h) — marginal sub-fee
- Lesson #40 EDGE-side advances candidate → 2nd dogfood, 1 more for formal CONFIRMED

### Recommendation provenance audit — NEW Lesson #61 candidate 1st dogfood

**paradigm 149 §6.46 next-action recommendation flaw**:
- Recommended paradigm 150 = "Option (a) 30-120min hold + ATR-normalized range
  breakout (paradigm 127 R-5 adjacent)"
- Citation: paradigm 127 R-5 60-90min hold frame precedent only
- **MISSED**: paradigm 115 ATR-normalized Donchian breakout graveyard (2026-05-20,
  1 day prior), which is the IMMEDIATELY ADJACENT statistic-class neighbor

**NEW Lesson #61 candidate (1st dogfood)**:
> R-0 next-action recommendations from prior-paradigm graveyards MUST cross-reference
> adjacent-axis confirmed-graveyard paradigms BEFORE proposing as 'Surviving
> direction'. paradigm-architect R-0 inventory_check skill should add
> 'next-action-recommendation provenance audit' — re-verify all adjacent-axis
> paradigms in INDEX.json graveyard list against proposed candidate
> statistic+frame+hold combination.

Promotion pathway: candidate → CONFIRMED after 2nd dogfood.

## Family-distinct vs other R-5 / graveyard paradigms

| Reference paradigm | Distinct? | Notes |
|---|---|---|
| paradigm 115 (ATR-norm Donchian breakout) | **WEAK distinct, OUTCOME-equivalent** | Primary halt cause |
| paradigm 116 (volume-confirmed ATR breakout) | weak distinct (no volume axis) | axis-redundant graveyard precedent |
| paradigm 117 (24h extreme drawdown reversion) | distinct (continuation vs reversion) | R-2 PASS → R-3 OOS FAIL precedent |
| paradigm 127 R-5 (1m volume burst × 60-90min LONG) | distinct (volume-event vs range-magnitude) | hold-frame precedent only |
| paradigm 69 R-5 (BTC RV cross-asset) | partial distinct (per-sym vs cross-asset) | Lesson #56 medium risk |
| paradigm 133 (vol-of-vol) | distinct (level vs 2nd moment) | statistic distinct |

## Lesson confirmations / advancements (paradigm 150 R-0 halt)

- **Lesson #56 OUTCOME-LEVEL FAMILY PROXY**: 6 → **7 instances cumulative**
  (formal CONFIRMED since 5 instances; 7th reinforces)
- **Lesson #40 EDGE-side structural infeasibility sub-variant**: 1 → **2 dogfoods**
  (paradigm 149 1st + paradigm 150 2nd). 1 more for formal CONFIRMED.
- **NEW Lesson #61 candidate (1st dogfood)**: R-0 next-action provenance audit
- **Lesson #44 amendment 34th xref**: xref'd paradigm 115 + 116 + 117 + 127 R-5 +
  69 R-5 + 133 (6 paradigms)
- **Lesson #11 sample density**: PASS overwhelming (does NOT rescue Lesson #56)
- **Lesson #19 SNT 4-quadrant design**: COMPLIANT
- **Lesson #28 substrate availability**: 30min frame requires 1m resample
  (substrate POSSIBLE but not independent advantage over paradigm 115 1h)
- **Lesson #30 data window ratio**: PASS (14 syms × 820d full window)
- **Lesson #45 HMM prohibition**: COMPLIANT (pure parametric ATR rolling)
- **Lesson #59 candidate avoidance**: COMPLIANT (single-exchange)
- **Lesson #60 candidate avoidance**: COMPLIANT (hold ≥ 30min, not sub-5min)

## Tier 4 family retire eligibility advance

**ATR-normalized magnitude breakout family** (NEW eligibility advance):
- paradigm 115 graveyard (CONCENTRATION_DISPERSION_FAIL, life-changing 2/4 with
  per_trade_edge 0.21% blocking)
- paradigm 150 R-0 halt (predictive OUTCOME-equivalent under harder conditions)
- Cumulative: 1 graveyard + 1 R-0 predictive halt = eligible for **family-level
  retire advisory** (not yet formal Tier 4 — requires 1 more R-1 graveyard for
  formal eligibility)
- Note: paradigm 116 (volume-confirmed ATR breakout) is axis-redundant — counts
  as related but not pure-ATR-norm-magnitude class
- **Advisory**: future paradigms with ATR-normalized magnitude breakout statistic
  class + hold < 4h should provide explicit family-distinct rationale beyond
  hold/k parameter variation

## Halt decision rationale

**Primary cause**: Lesson #56 OUTCOME-LEVEL FAMILY PROXY 7th instance —
paradigm 150 statistic class is OUTCOME-equivalent to paradigm 115 graveyard
family with strictly worse expected metrics (shorter hold = smaller gross
integration window, fee constant 16bp, stricter k=2.0 reduces per-sym n
exacerbating concentration dispersion).

**Secondary cause**: Lesson #40 EDGE-side structural infeasibility 2nd
predictive dogfood — hold reduction from paradigm 115 4h best cell (gross
29.11bp) to paradigm 150 ≤120min strictly value-destroying.

**Tertiary cause**: paradigm 149 §6.46 next-action recommendation engine
inheritance flaw (Lesson #61 candidate 1st dogfood) — missed paradigm 115
adjacent-axis graveyard cross-reference.

**Milestone consideration**: paradigm 150 milestone integrity served by R-0
halt with rigorous family-proxy analysis over ritual R-1 dispatch yielding
predicted BROAD_FALSIFIED outcome. Honest 21-streak non-PASS preferred to
manufactured PASS_R1 followed by R-2 walk-forward FAIL (paradigm 87
antipattern).

## Next paradigm 151 recommendations

Given 21-streak non-PASS + cross-exchange Tier 4 + funding Tier 4 + sub-5min
momentum continuation Lesson #60 + ATR-magnitude breakout family retire
advisory + Lesson #56 OUTCOME-LEVEL 7-instance evidence base:

**Surviving directions** (all require fresh R-0 design — no zombie inheritance):
- (A) **Path D from paradigm 150 R-0**: Token unlock cliff entry-side IMMEDIATE
  demand (Lesson #27 amendment compliant) — distinct from paradigm 87/88/90
  graveyard family. Substrate verification first. **⭐⭐ medium recommend**.
- (B) **Path E from paradigm 150 R-0**: User-brainstorm genuinely-novel data
  domain not yet attempted. 21-streak suggests adjacent-axis refinement
  exhausted. **⭐⭐⭐ exploratory, high uncertainty**.
- (C) **paradigm 115 R-2 EXPANSION** (paradigm 115 graveyard §Recommended Next
  Action Option A): re-use paradigm 115 statistic at 4h hold k=1.5, expand
  universe to 25+ alts to test Concentration Gate per-sym ci_pos resolution.
  Blocker: even if Concentration PASSES, per_trade_edge 0.21% still life-changing
  blocked. **⭐ low (rediscovers paradigm 115 life-changing block)**.

**RECOMMENDED (메타)**: **Path A (token unlock cliff entry-side IMMEDIATE)**
pending substrate verification, or **Path B (user-brainstorm session)** for
genuinely-novel data domain pivot. The 21-streak non-PASS + 7 Lesson #56
instances signal that adjacent-axis refinement search-space is saturated —
genuinely-new substrate or genuinely-new statistic class required, not
parameter variation of confirmed-graveyard families.

## Files

- r0 prescreen: `backend/runs/research_track/alt_atr_normalized_range_breakout_30_120min_hold_single_exchange_directional/r0_prescreen.json`
- this graveyard: `backend/runs/research_track/graveyard__alt_atr_normalized_range_breakout_30_120min_hold_single_exchange_directional.md`
- xref paradigm 115 graveyard: `backend/runs/research_track/graveyard__alt_atr_normalized_range_breakout_continuation_long_2h.md`
- xref paradigm 149 graveyard (Lesson #40 EDGE-side 1st dogfood): `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md §6.46`

## INDEX update

- name: alt_atr_normalized_range_breakout_30_120min_hold_single_exchange_directional
- paradigm_number: 150
- phase: graveyard
- type: E
- verdict_code: R0_HALT_BY_OUTCOME_LEVEL_FAMILY_PROXY
- halt_phase: R-0
- r1_dispatched: false
- date: 2026-05-21
- counter: 149 → 150 (milestone)

KST: 2026-05-21 14:25
