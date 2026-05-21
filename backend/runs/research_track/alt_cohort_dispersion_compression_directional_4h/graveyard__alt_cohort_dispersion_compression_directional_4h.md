# Graveyard — paradigm 109 `alt_cohort_dispersion_compression_directional_4h`

**Date**: 2026-05-20 KST
**Verdict**: `SAMPLE_INSUFFICIENT` (refined: `SAMPLE_INSUFFICIENT_STRUCTURAL_THRESHOLD_INFEASIBLE`)
**Phase halted at**: R-0 prescreen (Lesson #11 + #23 fail downstream of structural infeasibility)
**Wall clock**: ~4 min total (script ~9s + diagnosis)
**Host**: mint@183.99.228.81

## One-line summary

z_disp ≤ −2 is **impossible by construction** in 2.36yr 13-alt panel; cross-section std is non-negative so its rolling z-score lower tail is bounded by `(−rolling_mean / rolling_std) ≈ −1.92`.

## R-0 prescreen results

| Lesson | Check | Result | PASS |
|--------|-------|--------|------|
| #11 sample density | per-cell ≥30 in 4-quadrant × 4-quarter | 0 / 0 (n_trigger=0) | FAIL |
| #23 trigger rate | ≥1.5% empirical | 0.00% | FAIL |
| #28 substrate audit | 13/13 alts joblib cache 2.36yr | 13/13 | PASS |
| #30 data window ratio | panel ≥30% of full | 100% | PASS |
| #34 empirical distribution | σ_cs and z_disp distributions | measured (see below) | (informational) |

## Empirical distribution finding (Lesson #34 + structural)

```
σ_cs (cross-section std of 13-alt 1h forward log-return) quantiles:
  p1   = 0.001399    (1.4 bp / hr)
  p5   = 0.001886
  p10  = 0.002214
  p50  = 0.004073
  p90  = 0.008687
  p99  = 0.018758   (right-skewed, heavy upper tail)

z_disp (rolling-30d z-score of σ_cs) quantiles (n=20,328 hourly):
  min   = -1.9195   ← absolute floor across entire 2.36yr panel
  p0.5  = -1.3035
  p1.0  = -1.2437
  p2.5  = -1.1369
  p5.0  = -1.0407
  p50   = -0.2572
  p95   = +1.8790
  p99   = +3.8759
  p99.5 = +4.9278
  max   = +24.3074  ← strongly right-skewed; upper tail unbounded

Trigger counts:
  z ≤ −2.5: 0
  z ≤ −2.0: 0      ← hypothesis primary trigger: ZERO events in 2.36yr
  z ≤ −1.5: 7      ← still <30 per-cell (n_quarters=10)
  z ≤ −1.0: 1,323  ← but this is just bottom 6.5% noise, not "compression"
```

## Structural diagnosis

Cross-section σ is a **non-negative aggregate statistic**. Its rolling-window distribution is right-skewed because:
1. Hard zero floor (σ ≥ 0 by definition).
2. Variance estimators have asymmetric upper tail (extreme high-volatility events drive σ_cs upward).
3. Rolling mean of σ_cs ≈ 0.004, rolling std ≈ 0.002 — so the negative z lower bound is approximately `(0 − μ) / σ = -2.0` only if σ_cs can hit zero, which is essentially never (idiosyncratic noise across 13 alts always produces some cross-section spread).

Empirical floor observed: `z_disp.min() = -1.92`. Cannot reach −2.0 even at single-tick extremes.

This is **distinct from prior halt classes**:
- Not Lesson #23 low trigger rate (rate is exactly 0, not just sparse)
- Not Lesson #28 substrate absence (substrate fully present)
- Not Lesson #11 cell density artifact (cells are exactly 0, not <30)
- Not Lesson #21 axis stacking (axes never test-triggered)

It is a **statistic-shape × threshold-form incompatibility**: symmetric z-score thresholds (form valid for paradigm 69 highvol where vol is also non-negative but the threshold is *upper-tail* z>p90) cannot apply to *lower-tail* z on non-negative statistics.

## Lesson candidate (proposed for /paradigm-architect prescreen update)

### Candidate lesson — "Non-negative aggregate statistic admits only upper-tail z thresholds"

**ID**: candidate `non_negative_aggregate_zscore_one_sided_floor`

**Statement**: When the statistic S is structurally non-negative (S ∈ {std, var, count, magnitude, dispersion, range, ATR, |return|, drawdown, ...}), its rolling-window z-score distribution is right-skewed with empirical lower bound ≈ −1.5 to −2.0 (often shallower). **Symmetric z thresholds (z ≤ −2) on such statistics are achievable only via:**
- Percentile rank (e.g., S ≤ rolling_p10)
- Log-transform first, then z (log S more symmetric)
- Ratio compression (S / rolling_mean ≤ 0.5)
- Absolute threshold (S ≤ literal value)

**Prescreen rule (proposed)**:
```
IF hypothesis_trigger uses z_threshold ≤ T<0 on statistic_S:
  AND statistic_S is structurally non-negative:
    THEN measure empirical z_S.min() over panel
    IF z_S.min() > T:
      HALT_BY_STRUCTURE — re-formulate using percentile/log/ratio/absolute form
```

**First dogfood**: paradigm 109 (this run). z_disp.min() = -1.92 vs threshold = -2.0 → impossible.

## Hypothesis-rescue paths (for orchestrator queue evaluation)

Three reformulations preserve the cohort-uniformity-regime novelty (5-axis: statistic NOVEL, universe NOVEL, mechanism NOVEL) while making the trigger achievable. Recommend orchestrator register as **separate paradigms** (p110/p111/p112) — not the same paradigm with different trigger because the statistic dimension changes.

| Path | Form | Expected trigger rate | Sample density |
|------|------|----------------------|----------------|
| R1 | σ_cs ≤ rolling_30d_quantile(0.05 or 0.10) | 5–10% (by construction) | per-cell 50–100, passes Lesson #11 |
| R2 | z on log(σ_cs) ≤ −2 (symmetric after log) | 1–2.5% est. | per-cell 10–30 (marginal Lesson #11) |
| R3 | σ_cs(t) / rolling_30d_mean(σ_cs) ≤ 0.5 | needs measurement | unknown |
| R4 (decline) | abandon — file lesson candidate only | n/a | n/a |

Recommended: **R1 percentile_rank_compression** — cleanest, highest sample density, novelty preserved. Could be auto-registered as paradigm 110 after orchestrator review.

## Files

- Mint: `/home/mint/auto_trading/backend/runs/research_track/alt_cohort_dispersion_compression_directional_4h/r1__metrics.json`
- Mint: `/home/mint/auto_trading/backend/scripts/research/paradigm109_alt_cohort_dispersion_compression_r1.py`
- This graveyard: `backend/runs/research_track/graveyard__alt_cohort_dispersion_compression_directional_4h.md` (to be staged by orchestrator)

## Lessons dogfood (this run)

- #11 (failed downstream of structural)
- #19 (4-quadrant test designed in script but never triggered due to 0 events)
- #23 (failed — exactly 0%)
- #28 (PASS substrate complete)
- #30 (PASS window ratio 100%)
- #34 (informational — empirical distribution measured first time on cross-section dispersion stat)

## Mechanism intuition retained (negative result)

The hypothesis was: cross-section dispersion compression → cohort uniformity → BTC-directional cascade. The **mechanism may still be valid**, but at much milder compression levels (e.g., σ_cs in bottom decile of last 30 days, not z<-2). Worth re-testing via rescue path R1.

The negative result is informative: it tells us that the **strict** form of cohort uniformity (extreme std collapse) does not occur in real crypto perp markets — markets always have some idiosyncratic noise across 13 alts (lower bound z ≈ -1.92). A real implementation would have to settle for a "relative compression" definition.
