# Graveyard: intra_symbol_spot_perp_lead_lag_alt_5m

- **Paradigm number**: 108
- **Phase halted**: R-1 BROAD_FALSIFIED (Symmetric Negative Test + 45-cell sweep + Concentration + Lesson #21 axis-alone all FAIL)
- **Verdict**: BROAD_FALSIFIED_FEE_FLOOR
- **Date**: 2026-05-20 KST
- **Host**: Mint (mint@183.99.228.81 sole live operating server)
- **Dispatch**: /new-paradigm-frontier continuous-parallel policy 6th dispatch (103+104+105+106+107+108)

## One-sentence

Intra-exchange (Binance) cross-venue (spot vs perp) 5m frame cross-correlation lag function paradigm BROAD_FALSIFIED — `mean|corr@τ=0|=0.981` on BTC 6m sample reveals same-venue arbitrage tightness too high for 5m granularity (90% windows lag-zero lockstep), and 4-quadrant Symmetric Negative Test + 45-cell hold×threshold sweep all FAIL with best gross 5.51bp ≪ 16bp fee floor (2.9x deficit); Lesson #21 axis-alone test confirms no joint synthesis (corr_alone 4.03bp > joint 2.94bp).

## 5-axis novelty matrix (re-confirmed at dispatch)

| Axis | Status | Note |
|---|---|---|
| Data source | NOVEL | Intra-symbol spot↔perp leg decomposition (spot = perp/(1+premium)), distinct from paradigm 23 cross-symbol BTC→alts and paradigm 103/104 cross-exchange |
| Statistic | NOVEL | Cross-correlation lag function (argmax\|corr[τ]\|), not z-score level/velocity/dispersion |
| Time scale | known | 5m frame |
| Universe | NOVEL | Intra-symbol bilateral pair, not cross-section |
| Mechanism | known | Lead-lag venue timing (paradigm 23 family adjacent) |

3/5 NOVEL passed. **Novelty did not protect against fee-floor mechanism failure** — joining Lesson pattern from paradigms 84/85/89/105/106 (5-axis NOVEL is independent of substrate/mechanism alpha).

## Family-distinct claim verified

- Distinct from 8th family retire `cross_exchange_single_axis_alt_directional_8h_240m` (cross-exchange single-axis, paradigm 103+104+105). This paradigm is intra-exchange cross-venue.
- Adjacent to paradigm 23 `cross_symbol_lead_lag` R-5 seeded (BTC→alts cross-symbol). This paradigm is intra-symbol bilateral.
- **New paradigm class proven structurally fee-bound at 5m frame** — same-exchange arbitrage closes lag within sub-bar timescale.

## R-0 prescreen results

| Lesson | Status | Detail |
|---|---|---|
| #11 sample density | PASS | Projected 1,222/cell across 16 cells |
| #23 trigger rate | **ANTIPATTERN** | 0.554% ≪ 1.5% threshold on BTC 6m (3x below). Dispatch proceeded for completeness — confirmed at R-1 as expected |
| #28 substrate-time-dim | PASS | 14/14 syms perp 1m (n=1,241,280) + 5m premium (n=209,952) joblib verified |
| #30 data window ratio | PASS | 1.99yr (727d) / 2.4yr full = 83% ≥ 30% |
| #32 universe-baseline-coherent | applied | Lesson #21 axis-alone subsumes baseline-coherent comparison |
| #34 empirical distribution | **CRITICAL FINDING** | **mean\|τ*\|=0 for 90% of windows / mean\|corr@τ=0\|=0.981** → mechanism alpha excluded ex ante |

## R-1 4-quadrant Symmetric Negative Test (primary 60m hold)

| Quadrant | n | gross_bp | net_bp | signal_t_excess | ci_lower_bp | perm_p | 3-gate |
|---|---|---|---|---|---|---|---|
| A_focus (perp-leads + perp-up → spot LONG) | 5,155 | +2.08 | −13.92 | **−1.107** | **−15.94** | 0.177 | **FAIL** |
| A_mirror (perp-leads + perp-up → spot SHORT) | 5,155 | −2.08 | −17.92 | −4.802 | – | 0.000 | FAIL |
| B_same (spot-leads + spot-up → perp LONG) | 5,551 | +3.49 | −12.51 | +0.548 | −14.57 | 0.702 | FAIL |
| B_mirror (spot-leads + spot-up → perp SHORT) | 5,551 | −3.49 | −19.49 | −5.857 | – | 0.000 | FAIL |

**All 4 quadrants FAIL.** No SPLIT_PARADIGM signal. A_focus +2.08bp vs A_mirror exact −2.08bp = perfect symmetry → trigger has zero directional information.

## R-1 45-cell hold×threshold sweep (Lesson #37 full-sweep verdict scan)

- Holds: {15m, 30m, 60m, 120m, 240m}
- |τ*| thresholds: {≥1, ≥2, ≥3}
- corr@τ* thresholds: {≥0.5, ≥0.7, ≥0.85}
- **Result**: 0/45 PASS
- Best gross: **+5.51bp** (τ≥3, corr≥0.85, 240m hold) ≪ 16bp fee floor

## R-1 Concentration Gate

| Dimension | n_total / measurable | n_pos | ratio | Gate |
|---|---|---|---|---|
| Quarters (9 quarters 2024Q2~2026Q2) | 9 | 0 | **0.0%** | FAIL (≥30% required) |
| Symbols (14 alts) | 14 | 0 | **0.0%** | FAIL (≥30% required) |

All 9 quarter t-statistics in [−6.20, −2.66] — uniformly broad negative across time. All 14 symbol ci_lower < 0 — uniformly broad negative across universe. **No symbol/quarter concentration** = decisive broad-falsification, not cherry-pick artifact.

## Lesson #21 axis-alone dogfood (explicit synthesis test)

| Condition | n | gross_mean_bp | net_t |
|---|---|---|---|
| corr@τ*≥0.7 alone (any \|τ*\|) | 11,841 | **+4.03** | −16.93 |
| \|τ*\|≥2 alone (any corr) | 11,067 | +3.04 | −17.77 |
| Joint (corr≥0.7 AND \|τ*\|≥2) | 10,320 | **+2.94** | −17.27 |

**Joint signal is WEAKER than either axis alone.** Definitive proof of no alpha synthesis. corr_alone (4.03bp) > joint (2.94bp) by 1.09bp = adding the lag axis actively reduces alpha. **Lesson #21 dogfood SUCCESS** — joint paradigm refuted by single-axis decomposition.

## Life-changing 4-dim gate (applied per spec)

| Dim | Value | Threshold | Pass |
|---|---|---|---|
| trades/yr | 2588.1 | ≥ 12 | ✅ |
| capital util | 29.54% | ≥ 30% | ❌ borderline |
| edge/trade | **−0.139%** | ≥ +2% | ❌ massive deficit |
| approx sharpe | **−9.3** | ≥ 3 | ❌ massive deficit |

3/4 FAIL — `NARROW_SCOPE_LIFE_CHANGING_FAIL` verdict NOT applicable (Lesson #20 4-cond not met, primary cell failed). Default to BROAD_FALSIFIED_FEE_FLOOR.

## Mechanism falsification — qualitative

**Why same-venue spot↔perp is structurally tight at 5m**:
- Binance internal market-making bots arbitrage spot↔perp basis within sub-second timescales
- 5m bar OHLC aggregation washes out any sub-bar lead-lag
- mean|corr@τ=0|=0.981 (BTC 6m, ~52,000 5m windows) indicates near-perfect contemporaneous price discovery
- The 1% rare windows with |τ*|>0 are microstructure noise (data sync jitter, single-bar liquidity gaps), not exploitable mechanism

**Why this differs from paradigm 23 (R-5 seeded cross-symbol BTC→alts)**:
- Cross-symbol = different assets with separate price discovery processes → genuine lead-lag exists (paradigm 23 measured this and gated)
- Intra-symbol cross-venue = same asset with arbitrage-bonded venues → no lead-lag exists at 5m

## NEW Lesson candidates emerging (orchestrator decision)

### Candidate Lesson #38 — Same-venue arbitrage tightness antipattern

**Rule**: Intra-exchange (same exchange) spot↔perp lead-lag paradigms are structurally fee-floor bound at 5m frame because exchange-internal arbitrage closes the lag faster than 1 bar (mean|corr@τ=0| > 0.98 confirmed on Binance BTC 6m).

**Why**: Same-exchange market makers eliminate basis differences within sub-second windows, so 5m bar aggregation captures only contemporaneous prices.

**How to apply**:
- Intra-exchange spot↔perp lead-lag dispatch at 5m frame → automatic R-0 prescreen FAIL.
- Cross-VENUE lead-lag feasible ONLY across exchanges (Binance↔OKX/Bybit) OR different time scales (HFT sub-second, not 5m frame).
- Intra-exchange variants at 1m frame are EVEN tighter (a fortiori blocked).

### Candidate Lesson #39 — Symmetric perfect mirror antipattern

**Rule**: When A_focus and A_mirror gross returns are exactly negatives (±k bp around zero), the trigger has zero directional information — direction signal comes purely from the input direction axis, joint trigger is effectively a direction-bet + fee drag.

**Why**: A_focus +2.08bp / A_mirror exact −2.08bp pattern indicates the trigger conditions (|τ*|≥2 AND corr@τ*≥0.7) carry no predictive content for forward return — the sign comes only from the perp_direction axis input. This is a distinct fail mode from Lesson #19 SNT (where mirror typically differs from focus by 8bp fee asymmetry, indicating direction-asymmetric microstructure).

**How to apply**:
- R-1 verdict tree: when A_focus + A_mirror sum ≈ 0 within fee floor noise, classify as `BROAD_FALSIFIED_NO_AXIS_SYNTHESIS` (Lesson #21 dogfood) without proceeding to multi-symbol R-2.
- Trigger axis effectiveness pre-test: compute axis-alone single-direction signals before R-1 dispatch (Lesson #21 prescreen extension).

## Infrastructure notes (orchestrator reference)

- Premium index 1m frequency does NOT exist on Mint — only daily aggregates and 5m. Hypothesis reformulated to 5m granularity (perp 5m resampled from ohlcv 1m, spot derived via `spot = perp / (1 + premium)`).
- 5m premium joblib coverage: 14/14 syms × ~209,664 bars × 1.99yr span 2024-05-15 to 2026-05-13.
- Mint BTCUSDT ohlcv_1m count = 1,241,280 verified (Mint execution confirmed).
- `_perm_utils` signature: requires candidate_pool_returns. n_pool = 2,934,840 (14 syms × 209,664 5m bars × 1.0 fwd_60m density) >> n_obs (5,155–5,551) → cleanly passed.
- _perm_utils signal_t_excess all 4 quadrants in [−5.86, +0.55] — pure null behavior, no lift above fee drift.

## Artifacts

- R-1 script: `backend/scripts/research/intra_symbol_spot_perp_lead_lag_alt_5m_r1.py`
- Metrics JSON: `backend/runs/research_track/intra_symbol_spot_perp_lead_lag_alt_5m/r1__metrics.json`
- R-0 dist pickle (ephemeral): `/tmp/r0_btc_6m_xcorr.pkl` (Mint /tmp, expected gone)
- Wall clock: 48.4 seconds R-1 + ~30s R-0 prescreen = ~80s total

## Verdict & next steps

- **108번째 graveyard**. `BROAD_FALSIFIED_FEE_FLOOR` final.
- New advisory caution (1-dispatch only, not formal Tier 4 retire): `intra_exchange_cross_venue_5m_frame_lead_lag` — needs second dispatch from same family to formalize retire.
- Adjacent variants still open (require independent R-0):
  - 1m frame on same exchange (a fortiori tighter, near-certain pre-fail)
  - Cross-EXCHANGE spot↔perp lead-lag (different exchange = potentially looser arbitrage; substrate prep needed)
  - Different statistic on same-exchange pair (mark vs index leg decomposition, depth book imbalance lead-lag, etc.)
- Lesson candidates #38 + #39 staged for confirmation via second dogfood (requires another dispatch encountering same pattern).
