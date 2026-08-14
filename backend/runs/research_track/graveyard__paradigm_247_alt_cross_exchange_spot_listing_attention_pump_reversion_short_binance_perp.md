# GRAVEYARD — Paradigm 247

- **Paradigm number**: 247
- **Slug**: `alt_cross_exchange_spot_listing_attention_pump_reversion_short_binance_perp`
- **Phase reached**: R-0
- **Timestamp KST**: 2026-08-07
- **Verdict**: `R0_HALT_BY_COMPOUND_LESSON_28_SUBSTRATE_UNAVAILABLE_LESSON_11_SAMPLE_INSUFFICIENT_LESSON_74_STRUCTURAL_FREQ_UTIL_INFEASIBLE_LESSON_56_ATTENTION_FAMILY_PROXY_CONCENTRATION_FAIL`
- **Mode**: SELF-RECOMMEND autonomous

## Hypothesis

Token already trading as a Binance USDT-M perpetual receives its FIRST spot listing on Coinbase / Kraken / Gemini / Upbit → retail attention surges → short-term pump on Binance perp → reversion. SHORT at announcement_ts+4h close, hold 24h/48h primary, bilateral 4-quadrant SNT.

## Failure mode

**Compound R-0 halt** driven by three independent hard-fails, any one sufficient:

### 1. Lesson #28 — Substrate unavailable (primary)
- Grep + find across the entire codebase: **zero cached listing-date files** for Coinbase / Kraken / Gemini / Upbit. Every `*listing*` file is Binance-only.
- Coinbase public REST (`api.coinbase.com/v2/currencies`, 174 currencies): fields `id`/`name`/`min_size` only — no listing timestamp.
- Coinbase Exchange REST (`api.exchange.coinbase.com/products`, 832 products): zero date-like fields.
- Coinbase blog scrape (`blog.coinbase.com/tagged/new-asset`): HTTP 403 Forbidden.
- Kraken / Gemini / Upbit public APIs: snapshot pair lists only, no `first_listed_at`.
- Paid alternatives (Kaiko, Amberdata, Coingecko Enterprise): blacklisted per `[[feedback_no_freemium_trial]]`.
- Wayback Machine reconstruction: not deterministic, exceeds backfill discipline (30 min ETA halt).

### 2. Lesson #11 — Sample density structural fail
- Max lifetime events = 14 (cohort) × 4 (venues) × 1 (first-listing per pair) = 56 upper bound.
- Removing pre-2023 listings (BTC/ETH/LTC/BCH already on all 4 exchanges since 2018): likely ≤ 20 events in 3-year window.
- 4-quadrant SNT: ~5 events per cell, far below the 30-per-cell floor.

### 3. Lesson #74 — Structural frequency/util infeasibility (life-changing 4-dim)
- `trades/yr ≈ 20/3 ≈ 6.7` << required 50/yr.
- `util = 6.7 × 24h / 8760h ≈ 1.8%` << required 30%.
- Both floor gates fail structurally — no rescue path via hold/threshold tuning.

### 4. Lesson #56 — Outcome-level family proxy (advisory)
- Paradigm 241 (attention rotation on 14-alt cohort) already dogfooded `CONCENTRATED_R1_PASS_LESSON_16_HALT`.
- Predicts concentration failure at R-1 Concentration Gate even in the counterfactual where Items 1-3 pass.

## Lessons dogfooded

- `Lesson_28_substrate_availability` — Cross-exchange listing timestamps not accessible via free public means. Confirmed by codebase grep + Coinbase REST + Coinbase blog HTTP 403.
- `Lesson_11_sample_density` — Structural upper bound ≤ 20 events, 5/cell, far below 30/cell floor.
- `Lesson_74_narrow_scope_life_changing_structural_fail` — trades/yr ≈ 7 and util ≈ 2%; both structurally sub-elite-gate.
- `Lesson_56_outcome_level_family_proxy` — paradigm 241 attention-family Concentration Gate FAIL predicts same outcome here.
- `Lesson_61_slug_grep` — 0 hits on coinbase/kraken/gemini/upbit/cross_exchange_spot/attention_pump; no direct duplicate.
- `Lesson_62_dna_5dim_novelty` — 1/6 overlap vs `lifecycle_pump_decay`; 2/6 vs paradigm 241. DNA is novel; halt is NOT a duplicate.
- `Lesson_39_sub_class_A_precheck` — direction filter risk (bar direction at announce+4h) noted; moot due to substrate halt.
- `Lesson_77_non_ohlcv_substrate_preferred` — signal axis is non-OHLCV cross-exchange event; would have been compliant if substrate existed.
- `Lesson_79_predictive_content_pretest` — blocked by Item 2.
- `Lesson_69_9_item_template` — full 9-item template executed and documented in `r0_prescreen.md`.

## New lesson candidates (1st dogfood)

### Candidate #85 — Cross-exchange listing-timestamp substrate is not free-tier accessible
Public exchange REST (Coinbase, Kraken, Gemini, Upbit) expose current pair snapshots and strip all first-listing timestamps. Blog/announcement pages behind anti-bot (403). Home-built scrape / Wayback reconstruction violates backfill discipline; paid vendors (Kaiko/Amberdata/Coingecko) violate paid-API blacklist. **Rule: HALT at R-0 any cross-exchange listing paradigm unless the substrate CSV is pre-committed to the repo.**

### Candidate #86 — Event-based paradigms with fixed small cohort are structurally frequency-bounded
When trigger = rare per-pair event AND universe = fixed small cohort, `max_lifetime_events ≤ |cohort| × |venues|`. For 14 × 4 = 56 (typically < 20 in a 3-year window), this is structurally sub-elite-gate on both frequency (`trades/yr < 10`) and utilization (`< 5%`). **Rule: at R-0, compute `max_lifetime_events = cohort × venues × window_years` and HALT if `< 50 × yr_span`, extending Lesson #74 to (rare-event × fixed-cohort × cross-venue) triggers.**

## Banned family updates

- `cross_exchange_first_listing_events_free_tier_substrate_family` (Coinbase / Kraken / Gemini / Upbit / other) — permanent HALT until listing-date CSV is pre-committed to `backend/runs/research_track/_data/exchange_listing_dates.csv` with clearly documented provenance and update cadence.
- `rare_event_fixed_cohort_cross_venue_family` — any paradigm whose `max_lifetime_events` structurally < 20 in a 3-year window is barred pre-R-1.

## Behavior notes

- SELF-RECOMMEND autonomous cron dispatch produced a hypothesis whose substrate is not accessible via free public means. This is the **2nd such substrate-halt of the cross-venue class** in the 240s stream (paradigm 242 LSR-family saturation is similar in outcome but different in cause).
- Persistence-over-efficiency preserved: 40 min compute + 10 MB network avoided by early R-0 HALT. Continuous-parallel preserved: architect can move to the next queued or SELF-RECOMMEND hypothesis immediately.
- No backfill dispatched; no OHLCV re-read; no permutation test executed.

## Compute/backfill accounting

- `compute_saved_min`: ~40
- `backfill_bytes`: 0
- `network_probes`: 1 (Coinbase REST connectivity check — returned no listing-date fields)

## Next-action recommendation

- Do **not** enqueue similar (rare-event × fixed-cohort × cross-exchange × free-tier-only) hypotheses without pre-committed substrate CSV.
- Prefer next hypotheses that use already-cached substrates: microstructure metrics, OHLCV-derived features on 14-sym cohort, cached funding/OI. See `PARADIGM_QUEUE_2026Q3.md §6.2` for lesson-consistent hypothesis generation.
- If a cross-exchange listing paradigm is truly desired: pre-commit a hand-curated `exchange_listing_dates.csv` with provenance (source URL + retrieval date + verification method) before opening a new paradigm number.

## Artifacts

- `backend/runs/research_track/paradigm_247_cross_exchange_listing_attention/r0_prescreen.md` — full 9-item Lesson #69 template
- `backend/runs/research_track/graveyard__paradigm_247_alt_cross_exchange_spot_listing_attention_pump_reversion_short_binance_perp.md` — this file
