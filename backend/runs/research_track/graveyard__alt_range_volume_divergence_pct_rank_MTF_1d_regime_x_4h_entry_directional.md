# Graveyard — paradigm 154 `alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional`

**Date**: 2026-05-21 15:12 KST
**Phase halt**: R-0 (R-1 NOT DISPATCHED)
**Verdict**: `R0_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION` (Lesson #62 candidate 2nd dogfood + Lesson #56 CONFIRMED 8th instance + Lesson #21 sub-finding 7th candidate + Lesson #63 candidate 2nd predictive dogfood)
**Counter**: 153 → **154** (substantive R-0 increment)
**Non-PASS streak**: 24 → **25**

## Hypothesis (rejected at R-0)

MTF dual confirmation — 1d 1y rolling pct rank vol regime stratify × 4h 90d rolling pct rank entry. Same statistic class as paradigm 153 (range/vol divergence pct rank) with 1d regime conditioning layer added.

## R-0 composite halt rationale

### Lesson #62 candidate 2nd dogfood — Family-distinct strict 4-dim audit FAIL

paradigm 154 vs paradigm 153:
- **Trigger statistic class**: IDENTICAL (range/vol divergence pct rank; window 30d→90d = parameter tweak, NOT class change)
- **Entry-side class**: IDENTICAL (4h trigger-bar close, immediate; regime gate = filter, NOT entry-side reclassification)
- **Mechanism first-principles**: partial change only (regime conditioning claim, but core directional thesis MR/CONT unchanged)
- **Substrate**: partial change only (same Binance klines source, additional 1d frame is resampling)

Strict changes: **0/4** (threshold ≥2 required)
Partial changes: 2/4 (still insufficient — Lesson #62 strict defines structural change, not stacked filtering)

**Lesson #62 promotion**: candidate (1st dogfood paradigm 151 entry-side retiming) → **CONFIRMED 자격 reached** (2 dogfoods bidirectional, p151 entry-timing variant + p154 frame-stacking variant).

### Lesson #56 CONFIRMED OUTCOME-LEVEL family proxy — 8th instance

range_volume_divergence family chain:
- paradigm 110 BROAD_FALSIFIED_DIRECTION_INVERTED (precedent)
- paradigm 115 DIFFUSE_POSITIVE
- paradigm 137 GRAVEYARD
- paradigm 150 R0_HALT_BY_OUTCOME_LEVEL_FAMILY_PROXY
- paradigm 152 HALT_STRUCTURAL_ASYMMETRY
- paradigm 153 BROAD_FALSIFIED
- **paradigm 154 = 8th instance** (R-0 halt)

Lesson #56 CONFIRMED since 5 instances (paradigm 147 v2). 8th occurrence categorically reinforces OUTCOME-LEVEL family proxy gate.

OUTCOME-LEVEL prediction: paradigm 154 R-1 HIGH-regime cell would reproduce paradigm 153 fee-floor outcome with smaller n (since regime filter shrinks sample by ~30%).

### Lesson #21 CONFIRMED sub-finding — MTF axis stacking degeneracy 7th candidate

paradigm 154 explicit 2-axis stack:
- Axis 1: 1d range-vol divergence pct rank regime
- Axis 2: 4h range-vol divergence pct rank entry

**Critical degeneracy**: 1d divergence = approximate aggregation of 6 × 4h divergences on SAME bar data. Two axes are NOT statistically independent — autocorrelation of SAME statistic at different time scales.

Precedents:
- paradigm 83 (oi_5m_latent_regime k=4): 4/4 clusters BROAD_FALSIFIED (-27σ to -58σ)
- paradigm 81 (rolling beta 4-cell sign-cond): cell PASS but concentration FAIL 3/13 alts isolated

Lesson #21 sub-finding 7th candidate dogfood: "MTF stacking of SAME statistic class on SAME substrate".

### Lesson #63 candidate 2nd predictive dogfood

Lesson #63 (1st dogfood paradigm 153): "structural fix ≠ mechanism alpha resurrection".

paradigm 154 framing: paradigm 153 mechanism alpha was tested + verified ABSENT at bar level. Regime conditioning is alpha resurrection attempt via stacking, NOT via new mechanism story.

R-0 halt prevents materialization → Lesson #63 candidate 2nd predictive dogfood, promotion path: candidate → CONFIRMED 자격 reached.

## Lessons applied & dogfooded

- **Lesson #11** sample density — PASS (~1,000 events / 4 quadrant / 250 per-cell); does NOT rescue from Lesson #62/#56/#21 categorical halt
- **Lesson #19** 4-quadrant SNT — NOT executed (R-0 halt upstream)
- **Lesson #21** MTF axis stacking same-statistic degeneracy — **7th candidate dogfood**
- **Lesson #30** data window 91.7% — PASS (advisory only)
- **Lesson #44** family-distinct cross-reference — **38th xref dogfood** (8-paradigm range_volume chain)
- **Lesson #56** OUTCOME-LEVEL family proxy — **8th instance CONFIRMED reinforcement**
- **Lesson #58** same-bar same-substrate corr healthy zone — N/A deferred (paradigm 152 PASS inherited)
- **Lesson #61** R-0 next-action provenance audit — paradigm 153 graveyard option 2 (MTF dual confirmation) **directly executed** — Lesson #61 dogfood SUCCESS (provenance audit prevented blind execution by surfacing Lesson #62/#56/#21 categorical halt)
- **NEW Lesson #62 candidate** retiming reframe ≠ family-distinct — **2nd dogfood → CONFIRMED 자격 reached**
- **NEW Lesson #63 candidate** structural fix ≠ mechanism alpha resurrection — **2nd predictive dogfood → CONFIRMED 자격 reached**

## Range_volume_divergence family — Tier 4 RETIRE candidate

- Cumulative: 110+115+137+150+152+153+154 = **7 graveyards** in range/range-volume axis
- 3 distinct statistic classes attempted: z-score (p152) / pct rank (p153) / MTF regime × pct rank (p154)
- All structural feasibility paths exhausted at bar-level + MTF stack
- **Tier 4 retire eligibility**: YES (≥5 graveyards + axis exhaustion across statistic classes)
- Consistent with prior Tier 4 retires: funding family / cross-exchange OI / ATR-normalized magnitude / HMM / sub-5min momentum

## Artifacts

- `backend/scripts/research/paradigm154_r0_prescreen.py` (compile clean, executed 2026-05-21 15:12 KST, wall clock ~0.5s)
- `backend/runs/research_track/alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional/r0_prescreen.json`
- `backend/runs/research_track/alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional/TASK.md`

## Counter

- Graveyards: 153 → **154**
- R-5 LIVE: 10 (unchanged)
- Non-PASS streak: 24 → **25**
- R-5 yield: 10/154 = **6.49%**
- Lessons: 34 confirmed + 17 candidates → **34 confirmed + 17 candidates** (Lesson #62 candidate → CONFIRMED 자격 promoted; Lesson #63 candidate 2nd dogfood → CONFIRMED 자격 reached; Lesson #21 sub-finding 7th candidate). Formal promotion to confirmed pending Q3 §6.51 ratification.
- Q3 §6.51 next entry

## Lesson #61 dogfood SUCCESS

paradigm 153 graveyard §next-action option 2 explicitly recommended "Cross-timeframe regime layer — e.g., 1d divergence regime × 4h entry trigger (MTF dual confirmation), to test whether higher-TF regime context resurrects alpha".

paradigm 154 was dispatched per this recommendation. R-0 prescreen, applying Lesson #61 provenance audit + Lesson #62 strict family-distinct 4-dim check, REJECTED the recommendation as non-family-distinct (0/4 strict dim change).

**Meta-finding**: paradigm 153 §next-action authored its own halt at R-0. This is the intended behavior of Lesson #61 — next-action recommendations are not licenses to dispatch but provenance trails subject to the same R-0 gate the original paradigm would have been.

## Next paradigm 155 recommendation

| Option | Path | Recommendation |
|---|---|---|
| **α** | paradigm 22 R-5 funding cross-frame VALIDATION | ratification track (separate lane) |
| **β** | paradigm 69 R-5 macro proxy resume (`btc_realized_vol_p90_alt_directional_4h_resume`) | ⭐⭐⭐ |
| γ | lifecycle pump-decay sub-spec variant | Lesson #61 + #62 ≥2 dim audit required |
| δ | lifecycle live mode wait 2026-05-29+ | substrate accumulation track |

**메타 권고 1순위**: **Option β** — paradigm 69 R-5 macro proxy resume. substrate always available, family fully orthogonal to range_volume_divergence (BTC RV cross-asset, not bar-level divergence), R-5 mechanism time-robust validation self-value, Lesson #56 OUTCOME-level proxy SELF-validation track (paradigm 69 IS the R-5 reference for outcome family proxy detection).
