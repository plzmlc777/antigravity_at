# Graveyard — paradigm 112 `smart_dumb_money_divergence_alt_directional_4h`

**Verdict**: `SAMPLE_INSUFFICIENT`
**Phase halted at**: R-1 (Lesson #11 prescreen)
**Date (KST)**: 2026-05-20
**Wall clock**: 0.09 min
**Substrate**: `binance_positioning_metric` (top_long_short_position + global_long_short_account, 5m, 14 alts, 35d)
**Data window ratio (Lesson #30)**: 0.049 (35d / 720d archive) — verdict is ADVISORY ONLY

## Hypothesis

Two LSR sources expose smart-vs-dumb money positioning:
- `top_long_short_position` (whale / large-position size-weighted)
- `global_long_short_account` (retail account count headcount)

Mechanism: when smart money percentile rank ≥ 0.95 AND dumb money percentile rank ≤ 0.05 AND gap > 0.85 in same 5m bar → LONG 4h continuation. Mirror direction for SHORT.

4-quadrant Symmetric Negative Test designed per Lesson #19.

## Novelty self-check (3/5 NOVEL ex ante)

| Axis | Status | Note |
|------|--------|------|
| Statistic | NOVEL | dual percentile rank cross-source divergence (gap-based, two distinct metric_type tables) |
| Universe | NOT NOVEL | 14-alt cohort (paradigm 69/110) |
| Frame | NOT NOVEL | 5m × 4h hold (paradigm 80/83 territory) |
| Mechanism | NOVEL | smart-dumb DIVERGENCE class (cross-source disagreement) |
| Trigger | NOVEL | dual percentile-rank conjunction + gap threshold |

## R-0 / R-1 Prescreens

### Lesson #11 — Sample density (HALT)

- A_focus raw triggers (smart_HIGH + dumb_LOW + gap > 0.85): **1383**
- B_same raw triggers (smart_LOW + dumb_HIGH + gap < -0.85): **227**
- Decimation factor (≥ 4h gap per sym): 48 (5m × 48 = 240min)
- Post-decimation pool estimates:
  - A: 1383 / 48 = **28.8 trades** (< 30 floor)
  - B: 227 / 48 = **4.7 trades** (< 30 floor, deeply insufficient)
- Single-quarter window (35d) → per-quarter floor inapplicable; pool-level n must ≥ 30

**Result**: BOTH directional cells fail post-decimation pool n ≥ 30 floor.

### Lesson #30 — Data window ratio (compounding)

- Panel days: 35 (positioning_metric backfill window)
- Full archive available: 720d (~24 months) at `binance.vision`
- Ratio: **0.049 (4.9%)** << 30% threshold
- Verdict reliability: ADVISORY ONLY
- Even with full-window backfill, sample density would scale linearly: ~5.9x more triggers → A ~170, B ~28. A would barely cross floor, B remains structurally rare.

### Lesson #34 — Empirical distribution (diagnostic)

- top_pr p95 = 0.997, glob_pr p95 = 0.993 — both saturate at extreme percentiles (rolling 30d ECDF)
- gap p99 = 0.94, gap max = 0.99, gap min = -0.999 — gap > 0.85 is genuinely rare (~3% of bars)
- gap median = 0.07 — smart-dumb positioning is **slightly positively skewed** (top whales lean more bullish than retail on average) but divergence ≥ 0.85 is tail event

### Lesson #28 — Substrate availability

Both metric_types present in DB (`top_long_short_position`, `global_long_short_account`), 14 syms, 5m granularity. Verified columns via `information_schema`. No substrate block; failure is sample density not availability.

**Note**: OHLCV 5m coverage gap — DOGEUSDT, AVAXUSDT, LINKUSDT 1m OHLCV truncated at 2026-04-03 (~2-3 days only). Effective universe for forward returns is 11 syms not 14. Independent of Lesson #11 verdict but documented for future re-run.

## Stage outputs (none — halted pre-compute)

3-gate, Concentration Gate, axis-alone diagnostic, hold sweep, life-changing 4-dim — all skipped due to Lesson #11 halt.

## Lessons / Meta

### Lesson #11 dogfood (Nth)
Sample density prescreen correctly halted before wasted compute. ~5 sec total wall clock to identify infeasibility — exactly the design intent of the prescreen.

### Lesson #30 confirmed at 4.9% extreme
Lowest data_window_ratio observed in continuous-parallel campaign (previous low: paradigm 94 8.5%). Confirms the advisory-only rule still allows halt at Lesson #11 since absolute counts are below floor regardless of ratio.

### Smart-dumb divergence axis prematurely classified
With current 35d substrate, the strictest joint trigger (gap > 0.85) is structurally rare. Possible follow-up paths:

1. **Soft conjunction (gap > 0.50)**: would raise A_focus to ~10-15k raw / ~200-300 post-decimation. Risk: dilutes mechanism to general "top-leans-long-when-retail-leans-short" → likely fee-floor bound and converges with paradigm 23/72 single-axis TBS family (Tier 4 retired).

2. **Full-window backfill**: extend `binance_positioning_metric` to 720d via `binance.vision/futures/um/daily/metrics/`. Would push A to ~170 post-decimation (barely above floor). B remains insufficient (~28 estimated). Marginal feasibility.

3. **Hybrid universe expansion**: include BTC/ETH/major caps (currently excluded from 14-alt cohort). +6 syms × 720d → ~16x sample. But changes paradigm DNA from "alt cohort" to "major caps + alts".

4. **Continuous backfill + re-dispatch 2026-Q3 end**: collect ~90+ more days organically, re-dispatch with same trigger. Cost: 0 active compute, 90d wait.

### Family classification

Sub-class: cross-source positioning divergence. Distinct from:
- §3-G TBS single-axis (paradigm 23/72) — single source
- Funding family (paradigm 22/73/79/96/97/98/99) — different source axis
- premium/OI joint events (paradigm 80/82/83/85) — derivative-vs-spot divergence

**Family retire**: NO — only 1 graveyard in this sub-class, premature. Path 1-4 above keep options open. Reclassify only after 2+ graveyards or substrate extension attempt.

## Files

- R-1 script: `backend/scripts/research/paradigm112_smart_dumb_money_divergence_alt_directional_4h_r1.py`
- Metrics: `backend/runs/research_track/smart_dumb_money_divergence_alt_directional_4h/r1__metrics.json`
- Stdout: `backend/runs/research_track/smart_dumb_money_divergence_alt_directional_4h/r1__stdout.log`
- Graveyard: this file

## Next paradigm recommendation

Per `PARADIGM_QUEUE_2026Q3.md` §1, remaining ⭐⭐ candidates worth dispatching:
- `funding_premium_oi_4signal_majority` — ensemble voting (different paradigm class, §3-G strong but mixes seeded paradigms)
- `hmm_regime_premium` — NEW statistical approach (HMM), premium 1d substrate
- `change_point_detection_premium` — CUSUM/Bayesian, same premium 1d substrate

Or defer 2026-Q3 close and await positioning_metric backfill extension for paradigm 112 re-dispatch.
