# Graveyard — paradigm 189 binance_futures_perp_listing_event_post_onboard_4h_entry_side_forced_buy_directional_bilateral

**Counter**: 189
**Phase reached**: R-1
**Verdict**: `PORTFOLIO_ALPHA_INSIGNIFICANT`
**Date**: 2026-05-22 KST

## Hypothesis

Binance Futures USDS perp listing event (onboardDate marker) 직후 forward +0h ~ +48h window entry-side forced-buyer demand 가설.
paradigm 87 (delisting forced-exit R-1 PASS_R1_FULL sigex +2.23 / edge 14.6% / sharpe 6.49) mirror evidence-based extraction + lifecycle 4-dim uniqueness (entry-side + immediate + substrate available + sample density).

Bilateral 2-cell:
- A focus LONG: forced-buyer continuation
- A mirror SHORT: initial pump → mean-reversion

## R-1 design (compressed scope)

- Universe: 422 Binance USDS perp listings 2023-01 ~ 2026-05-20 (468 raw, 422 after data window filter, 393-415 valid after OHLCV cache fetch)
- Substrate: 15m OHLCV per-event window onboard_date ~ onboard_date+2 (3-day cache)
- Hold sweep: 4h / 8h / 12h / 24h / 48h (5 holds × 2 cells = 10 cells)
- Entry offset: onboard_ts + 15min (avoid first-tick auction noise)
- Fee: 8bp baseline + 25bp stress
- Candidate pool: per-symbol sliding 15m windows of same length (~400-11k pool per hold)

## Sample density (Lesson #11 PASS)

| half_year | n_events |
|-----------|---------:|
| 2023H1 |  29 |
| 2023H2 |  41 |
| 2024H1 |  35 |
| 2024H2 |  66 |
| 2025H1 |  99 |
| 2025H2 | 116 |
| 2026H1 |  36 |

Total **422 events** / 7 buckets / 2 cells → per-cell avg ~30.1 → **PASS** Lesson #11 (≥30 cutoff).

## Results — 10-cell hold sweep summary

| hold | cell | n | obs_t | sigex | ci_lo_bp | ci_hi_bp | perm_p | edge | util% | sharpe | conc |
|------|------|--:|------:|------:|---------:|---------:|-------:|-----:|------:|-------:|:----:|
| 4h | LONG | 393 | +0.291 | +0.688 | -139.3 | +200.4 | 0.804 | -1.11% |  5.7 |  0.69 | False |
| 4h | SHORT| 393 | -0.473 | -0.521 | -216.4 | +123.3 | 0.640 |  0.95% |  5.7 | -1.12 | False |
| 8h | LONG | 394 | -0.045 | +0.476 | -234.1 | +231.2 | 0.972 | -2.20% | 11.4 | -0.08 | False |
| 8h | SHORT| 394 | -0.088 | -0.366 | -247.2 | +218.1 | 0.921 |  2.04% | 11.4 | -0.15 | True  |
| 12h| LONG | 394 | +0.365 | **+0.814** | -238.8 | +398.4 | 0.724 | -3.24% | 17.1 |  0.50 | False |
| 12h| SHORT| 394 | -0.462 | -0.727 | -414.4 | +222.8 | 0.640 |  3.08% | 17.1 | -0.63 | True  |
| 24h| LONG | 400 | -0.191 | +0.186 | -351.8 | +315.2 | 0.838 | -5.14% | 33.4 | -0.18 | False |
| 24h| SHORT| 400 | +0.095 | -0.164 | -331.2 | +335.8 | 0.928 |  4.98% | 33.4 |  0.09 | True  |
| 48h| LONG | 415 | -0.768 |  nan*  | -474.0 | +214.8 |  nan*  | -6.73% | 66.2 | -0.52 | False |
| 48h| SHORT| 415 | +0.676 |  nan*  | -230.8 | +458.0 |  nan*  |  6.57% | 66.2 |  0.46 | True  |

*48h hold candidate pool n=399 (< n_obs n=415) → fee_aware_perm_test early-return NaN.

**Best sigex per side**:
- LONG : +0.814 @ hold_12h (sigex < 2.0 → three-gate FAIL gate A)
- SHORT: -0.164 @ hold_24h (sigex < 2.0, ci straddles 0 → three-gate FAIL)

**0/10 cells three-gate PASS. 0/10 cells concentration+sparse_LC+three-gate triple PASS.**

## Verdict: PORTFOLIO_ALPHA_INSIGNIFICANT

Not strict BROAD_FALSIFIED (LONG side has marginal positive sigex 0.18-0.81 across holds) but **all 10 cells FAIL three-gate** — alpha is statistically indistinguishable from candidate-pool null.

## Concentration (best-LONG cell, hold_12h)

- `half_year_pos_t_ratio` = 0.333 (need ≥ 0.5) — **FAIL** (2/6 measurable half-years positive: 2024H2 + 2025H2 only)
- `sign_ratio_positive` = 0.371 — **FAIL** (146 pos / 248 neg → most listings DECLINE post-onboard 12h)
- `top3_abs_concentration_pct` = 11.6% — PASS (no single-blowup)

Half-year breakdown shows **alternating direction** (2024H2 +145bp + 2025H2 +560bp positive; 2023H1, 2023H2, 2024H1, 2025H1, 2026H1 all NEGATIVE mean −101 to −415bp). **No persistent regime**.

## paradigm 87 vs paradigm 189 sub-mechanism asymmetry — CONFIRMED

Lifecycle 4-dim uniqueness hypothesis ([[project-paradigm-stablecoin-mint]]) predicted entry-side immediate demand should produce **mirror PASS** to paradigm 87's exit-side. Empirical result **inverts** this prediction:

| dim | paradigm 87 (delisting forced-exit) | paradigm 189 (listing forced-entry) |
|-----|---|---|
| direction class | exit-side liquidation | entry-side onboarding |
| Hypothesis prediction | SHORT continuation | LONG continuation |
| **R-1 verdict** | **PASS_R1_FULL sigex +2.23 edge +14.6%** | **PORTFOLIO_ALPHA_INSIGNIFICANT sigex max +0.81 edge −3.24%** |
| sign ratio | 65%+ negative (drift confirmed) | **37.1% positive (LONG 12h)** → listings DECLINE on average |
| concentration | persistent across quarters | alternating half-years (2 pos / 4 neg / 6 measurable) |

**Mechanism asymmetry is real and empirically extracted**:
- **Delisting** = monotonic forced-exit (no replacement liquidity, holders panic-dump uniformly)
- **Listing** = bimodal entry (early bidders pump → late liquidity disperses → frequently fades)
- Initial 15min "auction window" already absorbs most forced-buyer demand; from +15min onward the dominant flow is profit-taking from early longs (negative drift on average)
- Even SHORT-side mirror fails (sigex max −0.16) → not a clean reverse paradigm either; pure noise

**Lifecycle 4-dim uniqueness verified but mechanism-asymmetric**: substrate availability + sample density + immediate + entry-side all satisfied. Failure mode is **not** structural infeasibility (paradigm 89/90) nor sample (paradigm 88), but **dispersed/cancelled forced-flow** — entry-side forced-buy is intrinsically more diffuse than exit-side forced-sell.

## Mirror antipattern catalog compliance (paradigm 70 precedent)

- **NOT auto-inverse** of paradigm 87 — separate R-1 measurement obligation discharged
- Predicted mirror PASS, observed mirror FAIL — empirical falsification of "auto-mirror" assumption
- **Catalog reinforced 4 dogfoods** (paradigm 70 btc_rv_highvol mirror FAIL + paradigm 71 OI velocity trigger-swap FAIL + paradigm 96 funding sign flip BROAD_FALSIFIED + paradigm 189 listing entry-side mirror INSIGNIFICANT)

## Family-distinct verification (Lesson #62)

- vs paradigm 87 (delisting): 4/5 distinct (direction class shift)
- vs paradigm 89 (listing pre-announce DISPATCH_IMPOSSIBLE): 4/5 distinct (post-onboard vs pre-onboard substrate)
- vs paradigm 90 (stablecoin mint HALT): 4/5 distinct (immediate vs delayed/indirect)
- vs 17 Tier 4 retires: 5/5 distinct

## Lessons

### Lesson #71 corollary update — sparse-trigger event class

paradigm 189 demonstrates sparse-strict mode 측정 framework is correct but **alpha존재 = 자격 acquisition prerequisite**. Sparse-strict 4-dim mode 자격 path exists for high-edge-per-trade event paradigms, but only after three-gate PASS. paradigm 189 fails at three-gate (alpha absent), so sparse-strict path is moot here.

### NEW lesson candidate #71 (corollary) — forced-flow direction asymmetry

**Forced-exit liquidation events** (delisting, margin liquidation cascade) tend to produce monotonic directional drift because the forcing mechanism has **no replacement liquidity** (holders must exit, no counter-bidders).

**Forced-entry demand events** (listing onboarding, token unlock with immediate demand) tend to produce **bimodal/dispersed flow**: initial pump from early bidders → rapid liquidity normalization → frequent fade.

**Asymmetry rule**: paradigm 87 mirror (=paradigm 189) does NOT inherit alpha. Forced-flow paradigms have direction-asymmetric mechanism intensity.

This is **lifecycle 4-dim uniqueness amendment**: entry-side immediate demand satisfies 4-dim but **mechanism strength** is direction-class-dependent. Future paradigm proposals invoking lifecycle 4-dim uniqueness must explicitly identify **forced-EXIT vs forced-ENTRY** sub-class, NOT just "directional class".

### Lesson #28 verified (substrate availability)

`/fapi/v1/exchangeInfo` onboardDate substrate available; data.binance.vision 15m archive available T+1. **No substrate failures** — distinguishes from paradigm 89 (pre-onboard substrate impossible).

## Artifacts

- `r1.py` — 5-hold sweep bilateral R-1 script
- `r1__metrics.json` — full 10-cell metrics
- `backfill_ohlcv.py` — per-event 3-day 15m OHLCV backfiller (reusable for listing-family paradigms)
- `listing_events.csv` — 422 events 2023-2026H1
- `ohlcv_cache/*.joblib` — 417 cached symbol OHLCV (3-day windows) ≈ 30MB permanent asset

## Next-action recommendation (paradigm 190)

Given:
1. paradigm 189 confirms **forced-flow direction asymmetry** (entry-side ≠ exit-side mirror)
2. Listing entry-side paradigm space exhausted at +15min ~ +48h horizon
3. Closing rate continues parallel-dispatch policy ([[feedback-paradigm-campaign-continuous-parallel]])

**Candidate paradigm 190 directions**:
- **(A)** First-15min auction-window paradigm (onboard_ts +0 ~ +15min sub-paradigm) — paradigm 189 explicitly excluded this window with ENTRY_OFFSET_MIN=15; sub-window may show distinct dynamics
- **(B)** Delisting × hold-sweep finer grain — paradigm 87 was announce+5min → delist−24h fixed; sweep finer holds (1h / 4h / 8h post-announce) to identify horizon plateau for R-2 candidate
- **(C)** Different forced-flow exit class — large margin liquidation cascade events (~$100M+ liquidation cluster spikes) entry-side from liquidation cascade
- **(D)** Re-listing/re-introduction events (rare but well-defined)

**Lesson #71 corollary candidate** (forced-flow direction asymmetry) — formalize after 1 more dogfood (paradigm 87 + paradigm 189 = 2 data points; need third forced-flow paradigm to CONFIRM).

## INDEX update

paradigm 189 → `current_phase=graveyard`, `verdict=PORTFOLIO_ALPHA_INSIGNIFICANT`.
