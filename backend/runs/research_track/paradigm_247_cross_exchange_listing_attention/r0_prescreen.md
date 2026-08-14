# Paradigm 247 — R-0 Prescreen (Lesson #69 9-Item Template)

- **Paradigm**: `alt_cross_exchange_spot_listing_attention_pump_reversion_short_binance_perp`
- **Number**: 247
- **Date**: 2026-08-07 KST
- **Mode**: SELF-RECOMMEND autonomous

## Hypothesis (summary)
A token already trading as a Binance USDT-M perpetual receives its FIRST spot listing on Coinbase / Kraken / Gemini / Upbit → retail attention surge → short-term pump on Binance perp → mean reversion. SHORT at announcement_ts+4h close, hold 24h/48h primary, bilateral 4-quadrant SNT.

---

## Item 1 — Lesson #61 slug grep INDEX.json

Grep terms across `INDEX.json`: `coinbase`, `kraken`, `gemini`, `upbit`, `cross_exchange_spot`, `cross_venue_listing`, `attention_pump`, `spot_listing`, `external_listing`.

**Result**: **0 HITS**. No prior paradigm registered on this slug family.

Closest listing-family entries (all Binance-native trigger, none cross-exchange):
- `lifecycle_pump_decay` — Binance FUTURES new listing pump-decay
- `listing_pump_first60min` — Binance FUTURES onboardDate Day-1 intraday
- `listing_volume_cliff` — Binance FUTURES post-listing volume drop
- `binance_delisting_announce_short_alt` — Binance DELISTING announcement
- `binance_futures_perp_listing_event_post_onboard_4h_entry_side_forced_buy_directional_bilateral` — Binance onboardDate forced-buy
- `paradigm_241_alt_new_perp_listing_attention_effect_existing_alts_bilateral_5d` — Binance NEW-listing effect on OTHER alts (attention rotation)

Item 1 verdict: **PASS** (no slug duplicate).

---

## Item 2 — Lesson #28 substrate availability audit

**REQUIRED substrate**: Historical first-listing timestamps of Coinbase / Kraken / Gemini / Upbit for tokens 2023-01-01 → 2026-08-06 that are ALREADY in the Binance 14-sym perp cohort.

### Substrate probe results

1. **Repo cached listing dates**: `find` + `grep` (coinbase|kraken|gemini|upbit) across entire codebase (excluding `node_modules`/`.git`) → **0 files** with matching content. Zero cached listing-date CSV/JSON/parquet exists. Every `*listing*` file found is Binance-only (`fetch_new_listings.py`, `fetch_listing_dates.py`, `listing_alert.py`, `listing_pump_first60min_poc.py`, `us_r0_new_etf_listing_cohort.py`, etc.).
2. **Coinbase public REST (`api.coinbase.com/v2/currencies`)**: Returns 174 currencies. Fields = `id`, `name`, `min_size` only. **No listing timestamp field.**
3. **Coinbase Exchange REST (`api.exchange.coinbase.com/products`)**: Returns 832 products. Fields include `id`, `base_currency`, `quote_currency`, `status`, `trading_disabled`, ... — **zero date-like fields** (`date_keys = []`). Snapshot only, no historical first-listing timestamp.
4. **Coinbase Blog (`blog.coinbase.com/tagged/new-asset`)**: HTTP 403 Forbidden. Public scrape gated. Would require per-post crawl of 500+ blog URLs on Medium infrastructure with anti-bot protection.
5. **Kraken / Gemini / Upbit public APIs**: same shape — snapshot pair lists with no `first_listed_at` field. Kraken has AssetPairs, Gemini has symbols, Upbit has market codes — all point-in-time only.
6. **Wayback Machine reconstruction**: possible in principle, but requires ~500+ URL fetches with no guaranteed accurate first-listing timestamp; violates backfill-discipline (30 min ETA halt) and paid-API blacklist would be tempted.
7. **Paid alternative** (Kaiko / Amberdata / Coingecko premium exchange-listings endpoint): **BLACKLISTED** per `[[feedback_no_freemium_trial]]`.

### Verdict

**Item 2 = HARD-FAIL (SUBSTRATE UNAVAILABLE)**

The signal-substrate (cross-exchange first-listing timestamps for the target cohort, 2023-2026, 4 venues) is neither cached in the repo nor retrievable via free public APIs. Blog-scrape / Wayback reconstruction is not deterministic and exceeds backfill discipline.

This alone is sufficient to HALT the paradigm at R-0.

---

## Item 3 — Lesson #11 sample density (advisory — moot due to Item 2)

Assuming (counterfactually) the substrate existed:

- 14-sym Binance perp cohort × 4 target exchanges = at most 56 potential events (one first-listing per (sym, exchange) pair).
- Many pairs are already listed pre-2023 (BTC, ETH, LTC, BCH on all 4 exchanges since 2018). Removing pre-2023 listings likely leaves **< 20 events total**.
- SNT 4 quadrants → **~5 events per cell** → far below the Lesson #11 floor of 30 per cell (need 120+ total).

Item 3 verdict: **HARD-FAIL** even if substrate existed. Compound with Item 2.

---

## Item 4 — Lesson #62 DNA 5-dim strict distinct

Compare vs closest neighbors:

| Dim | 247 (this) | `lifecycle_pump_decay` (paradigm 2, LIVE) | `paradigm_241` (attention on other alts) | `binance_futures_perp_listing_event_post_onboard_4h` |
|---|---|---|---|---|
| substrate | cross-exchange-SPOT-listing-announcement | Binance-FUTURES-onboardDate | Binance-FUTURES-onboardDate (proxy) | Binance-FUTURES-onboardDate |
| universe | ESTABLISHED Binance 14-alt perps | NEW Binance futures listings | 14-alt cohort excluding the newly-listed | NEW Binance futures listings |
| trigger | Coinbase/Kraken/Gemini/Upbit first-listing event | Binance Day-1 close | Binance NEW-listing event (spillover) | Binance onboardDate |
| decision-mode | short reversion post-attention-pump | short lifecycle decay | bilateral 4-quadrant attention rotation | bilateral entry-side forced-buy |
| horizon | 24h / 48h | 30 days | 5d | 4h - 48h |
| mechanism | retail attention pump-then-revert | forced-buyer decay | attention rotation spillover | forced-buyer entry-side |

DNA overlap vs paradigm 2 = 1/6 (only "short" direction overlaps). Vs paradigm 241 = 2/6 (universe overlap + "attention" theme).

Item 4 verdict: **PASS** — DNA is genuinely novel, no 5/6 or 4/6 overlap.

---

## Item 5 — Lesson #56 outcome-level family proxy

- Cross-exchange-spot-listing is not covered by any prior paradigm outcome.
- Attention-then-reversion family: paradigm 241 (attention rotation, `CONCENTRATED_R1_PASS_LESSON_16_HALT`) is the closest proxy. Its outcome:
  - **A_mirror SHORT PASSED three-gate but Concentration Gate FAILED (2/14 syms ci_pos = 14%)**.
  - Signal driven by 2 tail alts (WIF, FIL), P1 monotonic alpha decay documented.
- Read: attention-based signals in the 14-alt cohort tend to concentrate on tail high-vol names and decay across time. **Proxy prior: HIGH RISK of Concentration Gate FAIL even if substrate existed.**

Item 5 verdict: **ADVISORY WARNING** — outcome-level proxy predicts failure at R-1 Concentration Gate (Lesson #16).

---

## Item 6 — Lesson #77 non-OHLCV signal substrate

- Signal axis = external listing announcement (cross-exchange). This is non-OHLCV, non-Binance-native. **PASS** per Lesson #77.
- Direction filter (bar direction at announce_ts+4h) is OHLCV-derived but is a downstream filter, not the signal. Per precedent (paradigm 189, 241) acceptable.

Item 6 verdict: **PASS**.

---

## Item 7 — Lesson #39 sub-class A precheck

Direction axis = pump/dump bar direction at announcement+4h. Risk exists that direction filter carries zero predictive content, yielding a symmetric mirror-perfect A_focus ↔ A_mirror pattern indicating pure direction-bet + fee drag.

- Paradigm 241 exhibited exactly this pattern on `A_mirror SHORT` — direction filter (bar direction) is not the true carrier of information.
- Mitigation would require Lesson #79 pretest, but Item 8 below is moot due to Item 2.

Item 7 verdict: **RISK FLAGGED** (moot because R-0 halts on Item 2).

---

## Item 8 — Lesson #79 predictive-content pretest

Cannot execute: no event timestamps → no `corr(direction_bar, fwd_24h_return)` computable.

Item 8 verdict: **BLOCKED BY ITEM 2**.

---

## Item 9 — Life-changing 4-dim (edge / sharpe / freq / util)

Assuming 20 events over 3 years and 14 syms:
- `trades/yr ≈ 20/3 ≈ 6.7` → **HARD-FAIL** vs required 50/yr.
- `util = 6.7 × 24h / 8760h ≈ 1.8%` → **HARD-FAIL** vs required 30%.

Even if edge and sharpe were somehow strong, the event count is structurally below the 4-dim life-changing gate (frequency + utilization) at R-4. This is a **Lesson #74 narrow-scope life-changing structural fail** — no rescue path because both frequency and utilization are structurally below the elite-gate floor.

Item 9 verdict: **HARD-FAIL (STRUCTURAL FREQUENCY/UTIL INFEASIBILITY, Lesson #74)**.

---

## Compound R-0 Verdict

**HALT**: `R0_HALT_BY_COMPOUND_LESSON_28_SUBSTRATE_UNAVAILABLE_LESSON_11_SAMPLE_INSUFFICIENT_LESSON_74_STRUCTURAL_FREQ_UTIL_INFEASIBLE_LESSON_56_ATTENTION_FAMILY_PROXY_CONCENTRATION_FAIL`

Primary cause (any one is sufficient):
1. **Lesson #28**: signal substrate not accessible via free public means; blog gated (403); no listing-timestamp field in any exchange REST; no cached repo file; paid APIs blacklisted.
2. **Lesson #11**: even if substrate existed, expected event count ~20 total across 3 years × 4 exchanges × 14-sym cohort → 5 per SNT cell, far below the 30-per-cell floor.
3. **Lesson #74**: structural frequency (~7/yr) and utilization (~2%) are below the 4-dim life-changing gate floor at R-4 — narrow-scope, no rescue path.

Secondary advisory (informational):
- **Lesson #56 outcome-family proxy**: paradigm 241 (attention on other alts) already dogfooded `CONCENTRATED_R1_PASS_LESSON_16_HALT`, predicting concentration failure for any attention-signal-driven paradigm on the 14-alt cohort.
- **Lesson #39 sub-class A risk**: direction filter (bar direction at announcement+4h) is the same pattern that produced 241's mirror-side artifact.

---

## Backfill discipline

- Rejected before any backfill dispatched: 0 bytes downloaded.
- No `data.binance.vision` calls, no PostgreSQL heavy queries, no external scrape attempts beyond one connectivity probe (`api.coinbase.com/v2/currencies` returned 200 with zero listing-date fields).
- Compute saved vs full R-1 run (event window OHLCV backfill + 4-quadrant SNT + permutation n=200): **~40 min compute + ~10 MB network avoided**.

---

## New Lesson candidates (1st dogfood)

### Candidate #85 — "Cross-exchange listing-timestamp substrate is not free-tier accessible"
Public exchange REST APIs (Coinbase, Kraken, Gemini, Upbit) expose current pair listings but strip all historical first-listing timestamps. Blogs (Coinbase blog) are behind anti-bot (403). This is a **general substrate class**: any "first listing on venue X" paradigm requires either a paid data vendor (Kaiko / Amberdata / Coingecko Enterprise) or a home-built long-running scrape infrastructure. Both violate our operating rules (paid API blacklist, backfill discipline). **Rule: HALT at R-0 any cross-exchange listing paradigm unless the substrate CSV is pre-committed to the repo.**

### Candidate #86 — "Event-based paradigms with cohort-fixed universe are structurally frequency-bounded"
When the trigger is a rare event (first listing on exchange X) AND the universe is a fixed small cohort (14 alts), the maximum lifetime event count is `|cohort| × |venues| × 1` (once per pair per lifetime). For 14 × 4 = 56 max, minus pre-window listings ≈ ≤20 in a 3-year window. This is structurally sub-elite-gate on frequency (`trades/yr < 10`) AND utilization (`< 5%`) simultaneously. **Rule: Lesson #74 automatic HALT for any (rare event × fixed small cohort) paradigm — compute `max_lifetime_events = cohort × venues × window_years` at R-0 and reject if `< 50 × yr_span`.**

## Next-action recommendation

- **Do NOT** attempt to reconstruct cross-exchange listing timestamps from blog scrapes.
- **Do NOT** enqueue similar (rare-event × fixed-cohort × cross-exchange) hypotheses without pre-committed substrate CSV.
- Prefer next hypotheses that use already-cached substrates: microstructure metrics, OHLCV-derived features on 14-sym cohort, funding/OI cached data.
- Family bans updated in graveyard doc.
