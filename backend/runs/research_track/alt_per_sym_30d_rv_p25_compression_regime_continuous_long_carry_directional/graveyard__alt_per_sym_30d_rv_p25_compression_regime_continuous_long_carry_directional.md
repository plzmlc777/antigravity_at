# Graveyard: paradigm 180 `alt_per_sym_30d_rv_p25_compression_regime_continuous_long_carry_directional`

- **Paradigm number**: 180
- **Phase halted**: R-0 prescreen (no R-1 dispatch)
- **Verdict**: `HALT_LESSON_71_CANDIDATE_PRESCREEN_FAIL_STRUCTURAL_TRADE_OFF`
- **Date**: 2026-05-22 KST
- **Host**: local_paradigm_architect_agent
- **Dispatch**: paradigm 180 R-1 ONLY mode, util-cap escape axis class continuation
- **Wall clock**: ~4 min (substrate load + 14-sym empirical regime cycle measurement + 4 cutoff sensitivity variants)

## One-sentence

Per-sym 30d RV p25 compression regime continuous-carry mechanism empirically yields util 22.2% (claimed 50%+, 2.3x deficit) and entries 5.8/sym/yr (life-changing 12/yr 2x deficit) at cycle-natural cutoffs; forcing util ≥30% by extending avg_dur to ≥35d collapses entries to ≤3/sym/yr and per-cell density to ≤5.6 (Lesson #11 cutoff 30, 6x deficit) — the (util ≥30% ∧ trades/yr ≥12 ∧ per_cell ≥30) intersection is Pareto-infeasible for any tested cutoff combination, structural trade-off ceiling.

## 5-axis novelty matrix

| Axis | Status | Note |
|---|---|---|
| Data source | known | OHLCV 12-col cache |
| **Statistic** | **NOVEL** | Per-sym 30d daily-log-return RV percentile (90d rolling) — vs paradigm 109/110 cohort cross-section dispersion |
| Time scale | known | daily aggregate → 30d window, regime carry days-to-weeks |
| Universe | standard | 14 alts (BTC + 13 alts) |
| **Mechanism** | **NOVEL** | Continuous regime carry (state machine entry/exit) — vs paradigm 69 fixed 270m hold, paradigm 86 streak-end fixed 1d |

3/5 NOVEL ex ante. Lesson #62 family-distinct PASS (5/5 strict distinct vs 16 Tier 4 retires).

## R-0 prescreens (Lesson #69 5-item)

| Item | Status | Detail |
|---|---|---|
| **#1 slug grep (Lesson #61)** | PASS_BUT_ADVISORY | No exact prior match. Adjacent: paradigm 109 (cohort dispersion z-score, Lesson #40 structural fail) + paradigm 110 (cohort dispersion p_rank, BROAD_FALSIFIED direction inverted). DNA distinct (per-sym vs cohort, continuous-carry vs fixed-hold) |
| **#2 substrate shape (Lesson #28)** | PASS | 14 syms × 4920 4h bars × 2.25yr joblib cache present |
| **#3 sample density (Lesson #11)** | **FAIL** | Best per-cell 10.2 ≪ 30 cutoff (3x deficit); even at relaxed entry=0.40/exit=0.80 → per-cell 5.6 (6x deficit) |
| **#4 DNA 4-dim (Lesson #62)** | PASS | 5/5 strict distinct vs 16 Tier 4 retires |
| **#5 family proxy (Lesson #56)** | ADVISORY | Cohort-compression family graveyard (109+110) suggests per-sym variant inherits fee-floor + direction-inversion risk |

## Lesson #71 candidate ESCAPE prescreen (1순위 의무) — **FAIL**

| Cutoff | Entries/sym/yr | Util_pct | Avg_dur_d | Per_cell (2×9) | Life-changing trades/yr ≥12 | Lesson #71 util ≥30% | Lesson #11 per_cell ≥30 |
|---|---|---|---|---|---|---|---|
| **p25 entry / p50 exit (primary)** | **5.8** | **22.2** | **13.7** | **10.2** | FAIL 2x | FAIL 1.4x | FAIL 3x |
| p25 entry / p50 exit (stateful) | 3.1 | 32.3 | 35.3 | 5.4 | FAIL 4x | PASS | FAIL 6x |
| p30 / p60 stateful | 3.0 | 38.5 | 43.4 | 5.2 | FAIL 4x | PASS | FAIL 6x |
| p35 / p70 stateful | 3.1 | 44.3 | 48.5 | 5.4 | FAIL 4x | PASS | FAIL 6x |
| p40 / p80 stateful | 3.2 | 52.6 | 55.4 | 5.6 | FAIL 4x | PASS | FAIL 6x |

**Pareto frontier conclusion**: NO point in the 3-dimensional intersection (util ≥30%, trades/yr/sym ≥12, per_cell ≥30) exists across the full cutoff sensitivity sweep.

## Structural trade-off discovery (NEW)

For a slow per-sym regime statistic (30d RV with 90d rolling percentile) on a 14-sym × 2.25yr panel:

- **Axis 1 (util_pct)** monotone increasing with avg_dur (long carry = more time in-regime)
- **Axis 2 (entries/sym/yr)** monotone decreasing with avg_dur (fewer cycle boundaries per unit time)
- **Axis 3 (per_cell density)** monotone decreasing with avg_dur (smaller total entries × universe fixed)

The three axes are **structurally coupled through avg_dur** — moving along the cutoff axis (raising util) forces the other two down. This is the **same class as Lesson #24 (boundary-event horizon density antipattern)** that killed paradigm 86 (multi_day_vol_persistence) — slow regime boundaries are inherently sparse-event on bounded panel length.

## Lesson #71 candidate 2nd dogfood + 자격 CONFIRMED ready

**Lesson #71 candidate statement (refined)**:
> Continuous-carry / regime-persistence mechanism class does NOT automatically escape the 4-dim life-changing util cap.
> Empirical util scales as `avg_dur × n_entries / panel_days`.
> Increasing util requires increasing avg_dur (long carry), which directly REDUCES n_entries (fewer cycle boundaries).
> The triple constraint (util ≥30% ∧ trades/yr/sym ≥12 ∧ per_cell ≥30) is provably infeasible for any **slow per-sym regime statistic** on the standard 14-sym × 2-3yr panel.

**Dogfood accumulation**:
- **1st dogfood (paradigm 179)**: spike-trigger 4h continuous direction — util cap by **trigger sparsity** (~5-7%)
- **2nd dogfood (paradigm 180)**: regime-carry continuous direction — util cap by **entry-rate vs avg-dur structural trade-off** (~22% at cycle-natural; ≤6/cell when forced to ≥30%)

Two **independent fail mechanisms** (spike-axis trigger sparsity vs regime-axis Pareto trade-off) accumulate to same outcome. **Lesson #71 candidate → CONFIRMED 자격 ready** (2 dogfoods, independent axes).

**Implied corollary (lesson #71 + design rule)**:
> Util ≥30% AND trades/yr/sym ≥12 AND per_cell ≥30 jointly require:
> (a) fast statistic with dense triggers (~1+ entries/sym/day) OR
> (b) cross-asset/portfolio concurrent diversification (n_syms ≥ 50 to multiplicatively boost) OR
> (c) overlapping multi-position continuous carry (not state-machine 1-at-a-time per sym)
>
> Slow per-sym idiosyncratic regime statistics on small 14-sym cohorts CANNOT satisfy all three simultaneously.

## Life-changing 4-dim audit (empirical at cycle-natural cutoff)

| Dim | Measured | Threshold | Pass |
|---|---|---|---|
| trades/yr (per sym) | 5.8 | ≥ 12 | ❌ |
| trades/yr (cohort) | 81.5 | ≥ 12 | ✅ (cohort view) |
| edge/trade | (not measured; halted) | ≥ +2% | n/a |
| sharpe | (not measured; halted) | ≥ 1.5 (3 strict) | n/a |
| util_pct (portfolio avg) | 22.2 | ≥ 30 | ❌ |

3/4 measurable fail (1 partial via cohort interpretation).

## No R-1 dispatch reasons (multi-dim)

1. **Lesson #71 candidate 1순위 prescreen FAIL** (claim 50%+, measured 22.2%, structural ceiling at ~22-25% for cycle-natural cutoffs)
2. **Lesson #11 sample density FAIL** across full cutoff sensitivity sweep (best per_cell 10.2 ≪ 30)
3. **Life-changing trades/yr/sym 5.8 ≪ 12** (cohort 81.5 OK but per-sym = strategy unit = fail)
4. **Pareto-infeasible structural trade-off** — no parameter tuning fixes (cutoff sweep covered p25/p30/p35/p40 entry × p50/p60/p70/p80 exit, 4 combinations all FAIL per_cell)

## Family classification

- **Per-sym RV percentile compression regime carry**: 1st instance, distinct from cohort dispersion (109+110)
- **Continuous regime carry mechanism class**: 1st R-0 halt at structural trade-off
- **No formal Tier 4 retire** (single paradigm only; family-distinct from cohort dispersion). However, paradigm 180 + future similar slow per-sym regime statistic dispatches inherit Lesson #71 candidate corollary check.

## Infrastructure (permanent assets)

- `backend/runs/research_track/alt_per_sym_30d_rv_p25_compression_regime_continuous_long_carry_directional/r0_prescreen__metrics.json` (full empirical numbers)
- `backend/runs/research_track/alt_per_sym_30d_rv_p25_compression_regime_continuous_long_carry_directional/graveyard__alt_per_sym_30d_rv_p25_compression_regime_continuous_long_carry_directional.md` (this file)
- joblib cache 14 syms × 4h × 2.25yr reused (pre-existing)
- No new substrate / DB writes / API calls

## Verdict & next steps

- **180th paradigm**. `HALT_LESSON_71_CANDIDATE_PRESCREEN_FAIL_STRUCTURAL_TRADE_OFF` (NEW verdict subclass: distinct from Lesson #11 alone since fail spans full cutoff sweep, distinct from Lesson #28 substrate absence since substrate fully present).
- **Lesson #71 candidate → CONFIRMED 자격 ready** (2 dogfoods 179+180, independent fail mechanisms).
- **No follow-up rescue path**: structural trade-off is intrinsic to slow per-sym regime statistics; rescue would require switching to fast statistic (incompatible with "regime" framing) or expanding universe ≥50 (incompatible with standard 14-sym cohort universe).

### paradigm 181 next-action recommendation

Avoid axis class with "regime carry" / "slow boundary" / "per-sym idiosyncratic slow statistic" hypotheses. Productive frontier candidates per Lesson #71 candidate corollary (a)/(b)/(c):

1. **Path A (corollary a)**: Fast statistic with dense triggers — e.g., intraday 5m-15m frame events with ~1+ entries/sym/day natural rate. Risk: 5m microstructure family advisory caution (paradigm 80+82+83+85 累積).
2. **Path B (corollary b)**: Cross-asset/portfolio universe ≥50 — would require Binance perp universe expansion from 14 → 50+ which we deferred per memory. Substrate cost moderate (joblib cache rebuild).
3. **Path C (corollary c)**: Overlapping multi-position continuous carry (not state-machine 1-at-a-time) — e.g., persistent rolling-rebalance signal where multiple lookback windows can simultaneously hold position. Conceptually distinct from regime carry (no entry/exit boundaries, continuous weighting).

Recommended: **Path C** — design a continuous-weighting paradigm (not entry/exit-state-machine) where util is naturally high by construction (e.g., 80%+ days holding *some* position with varying weight). This sidesteps the Pareto trade-off entirely.

## Lessons dogfood (this run)

- **#11** sample density: FAIL across full cutoff sweep (1st dogfood for "sweep-resistant Lesson #11 fail")
- **#28** substrate audit: PASS
- **#34** empirical distribution measurement: 14-sym 30d RV quantiles + 90d p_rank quantiles recorded (informational)
- **#40 confirmed** structural threshold feasibility: PASS by design (percentile rank form chosen, not z-score)
- **#62** family-distinct DNA 4-dim: PASS (5/5 strict)
- **#69 5-item template**: PASS application (all 5 items measured before halt)
- **#71 candidate (2nd dogfood)**: FAIL — CONFIRMED 자격 ready (paradigm 179 + 180 independent axes accumulate)
