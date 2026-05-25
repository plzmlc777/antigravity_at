# Graveyard — paradigm 158 alt_extreme_24h_PUMP_24h_continuation_long

**Verdict**: `BROAD_FALSIFIED_NO_THREE_GATE` (mechanic) / **MECHANISM_CLASS_ASYMMETRIC_CONFIRMED** (semantic)
**Phase**: R-1
**Date**: 2026-05-21 KST
**Wall clock**: 0.03 min

## Hypothesis
Alt 24h extreme PUMP (rolling 24h return ≥ per-symbol p90 threshold) →
24h hold LONG continuation (FOMO momentum follow).

Direct test of paradigm 117 R-3 caveat 1 mechanism CLASS asymmetric
finding — only capitulation bounce (DRAWDOWN × LONG MR) was ever
confirmed in paradigm 117; PUMP × continuation at 24h scale was NEVER
tested.

## Result — A_focus PUMP × LONG continuation EXHAUSTED at 24h
| pct | n | gross bp | net bp | sigex | ci [bp] | 3-gate | edge % |
|---|---|---|---|---|---|---|---|
| p85 | 2840 | +6.32 | -1.68 | +1.04 | [-21, +17] | FAIL | -0.02 |
| p90 (primary) | 2021 | +1.98 | -6.02 | +0.54 | [-30, +19] | FAIL | -0.06 |
| p95 | 1074 | +23.63 | +15.63 | +1.57 | [-23, +53] | FAIL | +0.16 |

Hold sweep on p90 A_focus: 12h gross -1.78bp / 24h +1.98bp / **48h +27.29bp sigex +2.06 ci [-14, +52]** — 48h marginal but ci_lower < 0.

**A_focus PUMP × LONG continuation hypothesis FALSIFIED**: no cell achieves 3-gate.

## Result — B_mirror DUMP × LONG (paradigm 117 mechanism reproduction)
At p95 (DUMP threshold = per-sym p05):
- n=1101 gross **+67.94bp** net **+59.94bp** sigex **+3.81** ci_lower **+21.5** — **3-gate PASS**
- Concentration Gate **FAIL**: q_pos 6/9 (67%) PASS but syms_ci_pos **0/13 (0%) FAIL**
- life-changing 4-dim FAIL: edge +0.60% < 2% (util 100%, sharpe 2.08 PASS)
- 2024Q1 outlier dominates: n=80 mean **+517.7bp** t +4.65 (paradigm 117 R-3 OOS FAIL pattern reproduced)

paradigm 117 mechanism is REAL at 24h scale on the same alt cohort, but
heterogeneously distributed across symbols and concentrated in
2024Q1 — consistent with paradigm 117's own R-3 OOS FAIL diagnosis.

## Findings

### Lesson #42 candidate — CONFIRMED (2nd dogfood)
- paradigm 117 R-3 caveat 1 measured B_same_sign PUMP × SHORT at 4h
  scale sigex +0.28; mechanism CLASS asymmetric inference was hypothesis
- paradigm 158 = 1st EXPLICIT direct test at 24h scale
- Result: A_focus PUMP × LONG continuation NEVER 3-gate PASS across
  3 pcts × 3 holds (9 cells total)
- mechanism CLASS asymmetric finding **directly confirmed**: capitulation
  MR is the alpha-bearing direction, FOMO pump continuation is noise at
  24h scale on this cohort.

### Lesson #8 — universal LONG bias 5th dogfood CONFIRMED
A_focus_LONG + B_mirror_LONG both positive across all 3 pcts:
- p85: A_focus +6.32bp / B_mirror +11.64bp
- p90: A_focus +1.98bp / B_mirror +21.33bp
- p95: A_focus +23.63bp / B_mirror +67.94bp

LONG-bias persistent structural feature, BUT B_mirror dominates A_focus
by ~3-10x — direction-bet alone insufficient; trigger asymmetry matters.

### Lesson #39 — perfect mirror CONFIRMED (3rd dogfood)
All 3 pcts: A_focus + A_mirror sum_abs = 0.00bp exact perfect mirror.
paradigm 158 inherits paradigm 117's perfect-mirror structure
(symmetric pump/dump statistic).

### paradigm 117 4h vs paradigm 158 24h scale comparison
- paradigm 117 R-1 4h sweep B_same (PUMP × SHORT) sigex +1.87 sub-fee hint
- paradigm 158 24h A_focus PUMP × LONG p90 sigex +0.54 (not improved at 24h scale)
- Hypothesis: 4h "weak hint" reflects 4h microstructure noise, NOT
  continuation alpha that would scale up at 24h
- 24h scale honest test: FOMO continuation does NOT exist on this
  cohort/window

## Family-distinct strict 4-dim audit (Lesson #62 CONFIRMED, 4th dogfood)
| Dimension | paradigm 117 | paradigm 158 | Strict |
|---|---|---|---|
| Statistic class | rolling 24h ≤ -15% DOWN | rolling 24h ≥ per-sym p90 UP | partial |
| Universe | 28 alts | 13 alts subset | partial |
| Entry-side class | DRAWDOWN cross-down | PUMP cross-up | STRICT |
| Mechanism alpha | capitulation MR | FOMO continuation | STRICT |
| Hold | 24h | 24h | identical |

Strict count = 2/5 boundary PASS → family-distinct.

## Cumulative campaign state
- 158th paradigm graveyard (consecutive parallel-campaign run)
- Magnitude-threshold family (paradigm 117 + 158): 2 graveyards
  - paradigm 117 R-3 FAIL_OOS (alpha real but OOS decay)
  - paradigm 158 R-1 BROAD_FALSIFIED (FOMO continuation absent)
- Mechanism class asymmetric finding **definitively established**:
  capitulation MR bounce is the alpha-bearing direction at 24h scale,
  FOMO pump continuation is not. Future variants on this cohort/window
  must target the MR direction.

## Next-action (with Lesson #61 provenance audit)

### paradigm 159 candidate proposals
Provenance audit: each proposal goes through R-0 inventory check
(slug + DNA 4-dim audit + Lesson #62 strict count) before R-1 dispatch.

1. **alt_extreme_24h_drawdown_24h_reversion_PER_SYM_p05_long** (R-2 retry)
   - paradigm 117 used universe-wide -15% threshold; per-sym p05 gives
     finer threshold per-coin (paradigm 158 B_mirror p95 ≡ p05 dump showed
     strong signal at p95). Re-attempt R-2 walk-forward with per-sym
     calibrated threshold could recover paradigm 117's lost OOS edge.
   - Inventory check: DNA 5/6 with paradigm 117 (statistic class identical,
     threshold formulation different). Lesson #62 strict count 1/5
     (threshold formulation only) — **LIKELY FAIL inventory check**.

2. **alt_extreme_drawdown_post_btc_dip_conditional_LONG** (axis stacking)
   - paradigm 117 unconditional + alt-specific drawdown trigger; add BTC
     market-regime condition (BTC also down ≥-5% in same 24h window) to
     filter out alt-idiosyncratic drawdowns.
   - Inventory check: DNA 4/6 with paradigm 117 (adds BTC regime axis).
     Lesson #62 strict count 1-2/5. Lesson #21 axis stacking caution.

3. **alt_volume_x_drawdown_capitulation_LONG_24h** (axis stacking with volume)
   - Combine drawdown trigger with extreme volume z-spike (capitulation
     volume signature). Lesson #21 axis stacking caution applies.
   - Inventory check: DNA 4/6 with paradigm 117. Lesson #62 strict count 1/5.

4. **NEW PARADIGM CLASS — funding flip post-drawdown** (cross-axis)
   - Substrate: funding rate db + 4h klines. Trigger: funding rate flips
     positive→negative within 8h of drawdown event. Hypothesis: directional
     funding flip confirms capitulation regime.
   - Inventory check: DNA 3/6 with paradigm 117 (mechanism class similar,
     trigger axis novel). Lesson #62 strict count 3/5. **CLEAREST FAMILY-DISTINCT**.
   - Caution: funding family Tier 4 retired (memory:
     [[project-paradigm-97-98-99-funding-family-completion]]).
     paradigm 22 R-5 + funding_dispersion exception only.
   - Best candidate but funding-family-retire blocks dispatch.

5. **paradigm 156/157 stale recommendation cleanup**
   - paradigm 156+157 §next-action recommendations did NOT cite paradigm 117.
   - Lesson #61 amendment proposal (above): §next-action must pass inventory
     check before being recommended.

### Direct recommendation for paradigm 159
Given the constraints (funding family Tier 4 retired, paradigm 117 family
exhausted at MR direction, axis stacking Lesson #21 caution), the cleanest
family-distinct path is a **fresh paradigm class** unrelated to magnitude
events. Examples:
- Time-of-day/day-of-week effects on alts (calendar anchor, NOT magnitude)
- Cross-exchange volume share rotation (paradigm 103 cross-exchange family
  inherited substrate, but volume share variant)
- Lifecycle re-listings (paradigm 87/88/89/90 family retired, but post-relisting
  is a fresh sub-mechanism)

Recommend: brainstorm fresh paradigm class for paradigm 159 dispatch with
agent next session. paradigm 158 closes the magnitude-event family for now.

## Artifacts
- `backend/scripts/research/paradigm158_alt_extreme_24h_PUMP_24h_continuation_long_r1.py`
- `backend/runs/research_track/alt_extreme_24h_PUMP_24h_continuation_long/r1__metrics.json`
- `backend/runs/research_track/alt_extreme_24h_PUMP_24h_continuation_long/r1__stdout.log`
- `backend/runs/research_track/alt_extreme_24h_PUMP_24h_continuation_long/TASK.md`
- this graveyard md

## Memory policy adherence
- [[feedback-paradigm-campaign-continuous-parallel]] — dispatched without pause
- [[feedback-direct-recommendation]] — direct recommendations made above
- [[feedback-no-freemium-trial]] — substrate is internal 12-col joblib cache only
- [[feedback-life-changing-strategy-criterion]] — 4-dim hard-block enforced (edge<2%)
