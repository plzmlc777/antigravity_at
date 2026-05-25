# paradigm 220 R-0 HALT GRAVEYARD

**slug**: `alt_per_sym_4h_ohlc_range_to_body_ratio_30d_rolling_z_spike_directional_4h_bilateral`
**date**: 2026-05-25 KST
**verdict**: `SAMPLE_INSUFFICIENT_STRUCTURAL_THRESHOLD_INFEASIBLE`
**lesson**: #40 (paradigm 109+110 confirmed-자격) — **3rd cross-class dogfood, formal confirmation candidate**
**phase**: R-0 (pre-R-1 prescreen halt)

## Hypothesis
per-sym 4h OHLC `(high - low) / (|close - open| + 1e-9)` → 30d rolling z-score → |z|≥+2 bilateral spike trigger × bar direction × 4-quadrant SNT 4h forward.

## Lesson #69 9-item template results
- **Item 1 (Lesson #61 name grep)**: PASS — zero collision in INDEX.json + filesystem
- **Item 2 (Lesson #28+72 substrate)**: PASS — 21 syms × 4h × 2.24yr cache verified, all 12 cols present (high/low/close/open complete). hold=4h × granularity=4h match PASS.
- **Item 3 (Lesson #11 sample density)**: **PARTIAL FAIL** — see Item below.
- **Item 4 (Lesson #62 DNA 4-dim 5/5)**: PASS distinct vs paradigm 124 (4th moment) / 211 (term structure) / 195+196 (cross-sym vol) / 219 (VWAP) / 127+128 (volume burst) — geometric ratio statistic class formally novel.
- **Item 5 (Lesson #56 family-proxy)**: NEW range/body composite class.
- **Item 6 (alpha decay 5+ pattern)**: not measured — halted at Item 3+40 before era stratify reached.
- **Item 7 (Lesson #39 sub-class A SNT structural integrity)**: PRE-EMPTED — see Lesson #40 below (sub-class A check moot when one trigger set empty).
- **Item 8 (Concentration + Temporal Independence)**: not measured.
- **Item 9 (Life-changing 4-dim structural)**: not measured.

## Lesson #40 STRUCTURAL FAIL (decisive)

`range/body` = `(high − low) / (|close − open| + ε)` is a **non-negative aggregate statistic with hard floor ≈ 1.0** (high − low ≥ |close − open| by OHLC definition; min observed = 1.0066 across 20 syms).

Right-skewed distribution (BTC p50=2.38, p90=10.78, p99=96.83, max=689.2). Rolling 30d z-score's lower tail is structurally bounded — when ratio dips toward its floor, z does not reach −2 because dispersion (σ) is dominated by the upper tail.

### Empirical (20 alts × 2.24yr × 4h × 30d rolling z)
- **z ≥ +2 events**: 1,926 total (mean 96.3/sym, viable)
- **z ≤ −2 events**: **5 total (mean 0.2/sym, 1/20 syms with any)**
- z.min mean across syms: −0.71
- z.min min (best-case sym): **−2.72**
- z.max mean: +15.76 (heavy right tail confirmed)
- Per-cell expected n (cell A: z≥+2 × bar UP × 4 quarters): ~107
- Per-cell expected n (cell B: z≤−2 × bar DOWN × 4 quarters): **~0.3 (≪ 30 cutoff)**

Cell B trigger set is structurally empty → SNT 4-quadrant bilateral test impossible → Lesson #19 joint-trigger requirement cannot be satisfied → R-1 dispatch infeasible.

## Lesson #40 promotion candidacy
- paradigm 109 (vol/RV-like non-negative) — 1st confirmed-자격 dogfood
- paradigm 110 (sub-class B mechanism-inverted derivative) — 2nd confirmed-자격 dogfood
- **paradigm 220 (OHLC range/body geometric ratio) — 3rd cross-class dogfood, novel statistic family**

Recommend Lesson #40 elevation from **confirmed-자격 → CONFIRMED** with cross-class extension note: applies to any aggregate statistic with structural lower bound (vol/RV/ATR/range/|return|/non-negative ratios), not just std/var/count/magnitude.

## Reformulation options (for future paradigm dispatch)
Lesson #40 prescribes:
1. **Percentile rank** of ratio (not z-score) → symmetric 4-quadrant achievable
2. **log(ratio)** → reshape distribution toward symmetric
3. **Ratio compression** e.g. `(high − low) / (high + low)` (bounded [0,1])
4. **Absolute threshold** on ratio (e.g. ratio ≥ 10 high-indecision / ratio ≤ 1.2 strong-conviction) instead of z-score

Each option becomes a distinct paradigm hypothesis and must re-pass Item 1-9 + family-distinct 5/5 strict.

## Family-distinct strict 5/5 audit (post-hoc, informational)
PASS — statistic class novel; but family classification moot under R-0 HALT.

## Lesson #39 sub-class A/B verification
PRE-EMPTED — SNT 4-quadrant infeasible due to one trigger set empty. sub-class A risk (unsigned × bar direction tautology) was the concern; Lesson #40 structural failure supersedes.

## Lesson #42 22nd dogfood (B mirror cell)
NOT MEASURABLE — B mirror requires cell B trigger which is structurally empty.

## Alpha decay Pattern P1 9th consecutive / 2026 era-universal 7th
NOT MEASURABLE — no R-1 execution.

## Lesson #67/#68/#70 ESCAPE
PASS (per-sym idiosyncratic, continuous rolling, NEW geometric class) — but moot under R-0 HALT.

## paradigm 221 next-action 권고
Recommended next dispatch (range/body geometry class continuation, Lesson #40 reformulation option 3):

**slug**: `alt_per_sym_4h_ohlc_range_compression_high_low_norm_30d_rolling_pct_rank_spike_directional_4h_bilateral`

- statistic: `(high − low) / (high + low)` — bounded [0,1], symmetric percentile rank achievable
- trigger: rolling 30d percentile rank ≥ 95 (high-volatility-share regime) / ≤ 5 (compressed regime)
- direction: × bar direction × 4-quadrant SNT
- substrate: identical 20 alts × 4h cache
- estimated viability: both cell A and cell B trigger sets symmetric ~5% rate → ~1,200 events/cell over 2.24yr × 20 syms, per-cell × 4 quarters ~67 PASS Lesson #11
- Item 7 SNT structural integrity: cell A (high rank) vs cell B (low rank) disjoint trigger sets, magnitudes need empirical cross-set verification
- Item 9 Life-changing 4-dim STRUCTURAL prescreen: still sparse-trigger 4h bilateral 본질 — capital util ceiling 위험 [[feedback-item-9-life-changing-structural-prescreen]] paradigm 215/218/219 precedent risk
