# Graveyard — realized_correlation_regime_universe_alt_directional_4h

**Date**: 2026-05-20 KST 16:10
**Phase**: R-1
**Verdict**: `DIFFUSE_POSITIVE_CONCENTRATION_FAIL_LIFE_CHANGING_FAIL`
**Host**: Mint `mint@183.99.228.81`

## One-line summary

14-sym Binance perp universe 91-pair avg realized correlation z-score panic regime (z > +2 at 14d-window) shows statistically real but operationally insufficient LONG mean-revert alpha: per-trade edge caps at 1.50%/trade (24h hold) < 2% life-changing floor, despite 5/5 quarters positive t and 12/12 alts mean positive.

## DNA

- Substrate: 14-sym 1m OHLCV joblib cache (canonical Mint set: ADA/AVAX/BCH/BNB/BTC/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP)
- Statistic: 91-pair universe-aggregate Pearson correlation, rolling, z-scored vs trailing 90d
- Decision: bidirectional z-polarity (z>+2 LONG panic mean-revert vs z<-2 SHORT decorrelation continuation)
- Time scale: 1h trigger × 4h primary hold (sweep 2/4/8/24h) × 30d primary corr window (sweep 14/30/60d)
- Universe shape: aggregate scalar (collapses 91 pairs into 1 series)

## Why graveyard (mechanism CONFIRMED real)

1. **Primary cell (z=2.0, hold=4h, corr_w=30d) all 4 quadrants FAIL three-gate** (Lesson #37 antipattern of primary-only-inspection: would falsely conclude BROAD_FALSIFIED_FEE_FLOOR).
2. **Full sweep (96 cells) reveals 5 non-primary 3-gate PASSing cells** ALL in A_focus (panic × LONG), all with corr_w=14d (faster window) or relaxed z=1.5 at longer holds.
3. **DIFFUSE_POSITIVE Lesson #41 signature**: best cell (cw=14d z=2.0 hold=8h) pool sigex=+5.19, ci_lower=+29.90 bp, perm_p=0.000, **12/12 alts mean positive, 5/5 quarters positive t**, but per-sym n=71 < 100 → 0/12 syms_ci_pos.
4. **Life-changing 4-dim hard-blocker**: best per_trade_edge = 1.50% (cw=14d z=2.0 hold=24h) << 2% threshold. Hold extension beyond 24h reduces capital_util sub-linearly while edge growth stalls.
5. **Lesson #41 amendment** dictates: even if R-2 universe expansion (28+ perps) would recover syms_ci_pos, per-trade edge ceiling is structural (homogeneous diffuse mechanism, not concentrated few-name alpha) → R-5 seed disqualified.

## Lessons dogfooded

- **Lesson #37** (full sweep verdict scan) — 3rd dogfood, **formal CONFIRMED**. Primary-only would have missed real mechanism.
- **Lesson #41** (DIFFUSE_POSITIVE + amendment life-changing block) — 3rd dogfood, **formal CONFIRMED amendment**. Pool-real + per-sym-diffuse + edge<2% → graveyard preempts R-2.
- **Lesson #20 NARROW_SCOPE_LIFE_CHANGING_FAIL** — 5th dogfood verdict category.
- **Lesson #19 SNT** — 4-quadrant joint test obligatory, all 4 measured in single R-1 batch (PASS).
- **Lesson #26 amendment** — n_measurable_quarters >= 4 ✓ (5/5 at best cell, no temporal blind spot).
- **Lesson #32 universe-baseline-coherent** — primary cell drift-coherent (confirms primary FAIL), non-primary 14d-window cells break drift coherence (confirms non-primary signal real).

## Family-distinct status

Universe-aggregate scalar correlation regime: 1st graveyard in this sub-class. **Not** sufficient for Tier 4 family retire (precedent ≥3 graveyards needed). Adjacent unexplored axes:
- Cross-section dispersion of pairwise correlations (instead of aggregate scalar) — different statistic shape, per-sym concentration recovery plausible
- Correlation velocity (Δcorr) instead of level z — different time-derivative axis
- Correlation regime × BTC vol regime conditional (paradigm 69 substrate) — adds external conditioning

## R-2 disposition

**DECLINED per Lesson #41 amendment**. Pool mechanism real, per-trade edge ceiling structural at ~1.5%, no expected R-2 expansion path crosses 2% life-changing floor.

## Cross-reference

- INDEX entry: `realized_correlation_regime_universe_alt_directional_4h` (status=graveyard)
- Metrics: `backend/runs/research_track/realized_correlation_regime_universe_alt_directional_4h/r1__metrics.json`
- R-1 FAIL report: same dir / `r1_FAIL.md`
- Stdout log: same dir / `r1__stdout.log`
- Skill ref: `.claude/agents/paradigm-architect/skills/lesson_prescreen_checklist.md` §Lesson #37 + #41
