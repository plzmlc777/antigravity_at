# Graveyard — alt_wikipedia_pageview_attention_spike_bilateral_1d_to_3d

**Paradigm #**: 243
**Phase halted**: R-1
**Verdict**: `R1_GRAVEYARD` — full-sweep 12-cell scan (4 quadrants × 3 holds) yielded zero cells with three-gate PASS, and universal concentration failure (max syms_ci_pos = 2/10, below Lesson #16 threshold of 3/10).
**Date**: 2026-08-03

## Hypothesis (rejected)

Per-symbol daily Wikipedia page-view count (log-transformed, rolling 30d z-score) as a non-OHLCV **attention** signal for Binance USDT-perp bilateral 1d-3d directional trades.
Academic precedent: Moat et al. 2013 (PLoS ONE), Kim et al. 2016 (Finance Research Letters) — Wikipedia views as a leading indicator of asset price moves via attention-driven retail demand.

## Substrate (built successfully — the failure is signal-side, not substrate-side)

- Wikimedia REST API, free, no auth, 2024-01-02 → 2026-05-12 (862 days, 2.36 years)
- 10 of 12 candidate symbols mapped and fetched (SOL and NEAR articles failed n≥500 threshold)
- Trigger density (z ≥ +1.5 or z ≤ -1.5 on 30d log-view baseline): 670 hi events + 562 lo events, per-quarter per-quadrant ≈ 56-67 events → Lesson #11 PASS.
- Substrate is genuinely non-OHLCV per Lesson #77 (web attention, not price/volume/OI/funding derivative).

## What killed it

### 1. Three-gate failed in all 12 cells

| Quadrant | Hold | net_bp | signal_t_excess | ci_lower_bp | perm_p | 3-gate |
|---|---:|---:|---:|---:|---:|---|
| A_focus  | 1d | +15.2  | 1.48 | -20.9  | 0.527 | FAIL |
| A_focus  | 2d | +42.9  | 1.82 | -7.6   | 0.104 | FAIL |
| A_focus  | 3d | +64.8  | **1.92** | **+1.3** | **0.049** | FAIL (t_excess<2.0) |
| A_mirror | 1d | -47.2  | -1.23 | -85.4 | 0.103 | FAIL |
| A_mirror | 2d | -74.9  | -1.66 | -127.7 | 0.025 | FAIL |
| A_mirror | 3d | -96.8  | -1.77 | -163.1 | 0.031 | FAIL |
| B_focus  | 1d | -20.8  | -0.06 | -55.3  | 0.479 | FAIL |
| B_focus  | 2d | -39.6  | -0.67 | -89.7  | 0.241 | FAIL |
| B_focus  | 3d | -79.7  | -1.63 | -139.9 | 0.032 | FAIL |
| B_mirror | 1d | -11.2  | -0.00 | -44.5  | 0.593 | FAIL |
| B_mirror | 2d | +7.6   | 0.63  | -37.5  | 0.760 | FAIL |
| B_mirror | 3d | +47.7  | 1.62  | -8.9   | 0.105 | FAIL |

The closest cell (A_focus 3d) had signal_t_excess=1.92 (below the ≥2.0 bar) with ci_lower barely positive. Even if we relax to 3-gate, concentration is the second killer.

### 2. Concentration Gate — universal failure (Lesson #16)

Across ALL 12 cells, syms_ci_pos ≤ 2 of 10 symbols (max ratio 0.20, requires ≥ 0.30 = 3/10). The tiny positive means in A_focus and B_mirror 3d are driven by a small handful of symbol-specific outliers, not a broad per-symbol edge. This is exactly the failure mode Lesson #16 was written to catch: a universe-wide statistic that vanishes at the per-symbol level.

### 3. Lesson #79 pretest — informational only, not a halt

BTC z_log_views vs next-day BTC return: Pearson corr = +0.022, t_hi = +0.88, t_lo = +0.88. Both t-stats non-zero (so not a strict Lesson #79 halt), but the striking pattern is that **BOTH** hi AND lo triggers show ~+28 bp mean next-day return. This suggests the Wikipedia-view z-score captures general market ACTIVITY level (both directions of price move draw web attention), not directional information — an information-carrying signal about volume/attention that is not a directional predictor.

### 4. Cross-quadrant symmetry check (Lesson #39)

A_focus / A_mirror are near-perfect mirrors (as they must be by construction) but the A_focus edge (+15 to +65 bp) minus the A_mirror antipode (-47 to -97 bp) suggests fee-floor dominates the mirror: the raw gross drift is genuinely positive (attention-day next-3d gross return ≈ +80bp per event pool), but this is dominated by the pool's own drift (crypto market broadly up over 2024-2026) rather than a spike-conditional signal. This is a classic Lesson #39 sub-class A pattern — the trigger has little independent directional information above the market drift.

## Why the academic result did not replicate

- Moat et al. 2013 used equities (Google search + Wikipedia), a market where the effect was ~1-3% over a week and where transaction costs are 5-20 bp — allowing the effect to survive.
- On Binance perpetuals in 2024-2026, round-trip fee is 16 bp and the observed net edge (even in the best A_focus 3d cell) is ~65 bp with a 95% CI barely straddling zero.
- Crypto attention/price causality has been amply arbitraged since 2013 — the retail-cascade mechanism the academic paper documented is now too weak to overcome fees in perpetual futures.
- Lesson #56 outcome-family proxy: general "retail attention → directional demand" family has been repeatedly graveyarded in Research Track (Fear & Greed / paradigm 226, LSR, taker buy). Wikipedia views is a novel substrate but the mechanism class (retail-attention → directional edge) has been broadly falsified for crypto perps.

## Lessons reinforced (no new lesson needed)

- Lesson #16 (Concentration Gate): universe-mean-positive can hide 1-2/N symbol drivers. Both A_focus 3d and B_mirror 3d had marginally positive means but only 1-2 syms with ci_lower > 0.
- Lesson #19 (4-quadrant SNT): the two focus quadrants gave opposing signs, and both mirrors were consistent — SNT correctly showed the "spike-continuation" hypothesis is weak (not consistent across sign of trigger).
- Lesson #37 (hold sweep): all three hold horizons swept, none rescued.
- Lesson #56 (family proxy): "retail attention → crypto perp direction" broadly retired; Wikipedia views does not escape the family verdict despite substrate novelty.
- Lesson #77 (non-OHLCV substrate preferred): the substrate itself is high-quality non-OHLCV, but substrate novelty does not create a signal where the underlying causal mechanism is already arbitraged out.

## Recommendation for future paradigm-architect dispatches

- **Do NOT re-propose Wikipedia views on Binance perps** with any threshold / hold combination. All 12 cells swept.
- **A_focus 3d is the closest to interesting** (signal_t_excess=1.92, ci_lower=+1.3bp) but concentration failure (1/10 syms) means it would fail even under a relaxed relaxation.
- If a future paradigm is proposed on the "attention → crypto price" family, first document how it escapes the Lesson #56 family proxy — mere substrate novelty is not sufficient.
- Wikipedia views MAY still carry information in a **volume/volatility** paradigm (both hi and lo triggers show +28bp next-day return in BTC, which is consistent with attention → activity, not attention → direction). Future proposal could test |return| or realized-vol as the y-variable, but that lands in a family already heavily explored.

## Artifacts

- Code:
  - `backend/scripts/research/paradigm243_r0_wikipedia_pageview_prescreen.py`
  - `backend/scripts/research/paradigm243_r1_wikipedia_pageview_bilateral.py`
- Metrics:
  - `backend/runs/research_track/alt_wikipedia_pageview_attention_spike_bilateral_1d_to_3d/r0_prescreen.json`
  - `backend/runs/research_track/alt_wikipedia_pageview_attention_spike_bilateral_1d_to_3d/r1__metrics.json`
- Raw cache:
  - `backend/runs/research_track/alt_wikipedia_pageview_attention_spike_bilateral_1d_to_3d/wiki_views_cache.json` (10 syms × 500-862 days of Wikipedia daily page views)
