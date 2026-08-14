# Graveyard — paradigm 246 `alt_funding_rate_sign_flip_sustained_N_event_bilateral_4h_1d`

**Date**: 2026-08-06 (KST)
**Mode**: SELF-RECOMMEND autonomous daily cron dispatch
**Phase halted**: R-0 prescreen (R-1 not dispatched)
**Verdict**: `R0_HALT_COMPOUND_LESSON_61_SLUG_GREP_DIRECT_HIT_LESSON_62_DNA_5_OF_6_DUPLICATE_LESSON_56_OUTCOME_FAMILY_PROXY_LESSON_55_PRESCRIPTION_RESCUE_OUT_OF_SCOPE`

---

## 1. Hypothesis (rejected at R-0)

Binance USDT-M perp 8h `funding_rate` changes sign after N consecutive same-sign 8h periods → bilateral directional predictive content over 4h–48h.

- Trigger: `sign(funding[t]) != sign(funding[t-1])` AND `same_sign_streak_prior >= N` for N ∈ {3, 7, 14}
- Hold sweep: {4h, 12h, 24h, 48h}
- 4-quadrant SNT bilateral: A neg→pos + LONG/SHORT, B pos→neg + SHORT/LONG
- Universe: 14-sym alt cohort (standard Binance perp)
- Fee floor: 16 bp round-trip (Lesson #56)

The dispatch brief framed this as "genuinely NEW conditioning axis" over paradigms 135/139/141/172/243 (which use continuous z, product-with-CVD, z-neg-only, term-structure, skewness respectively — all distinct statistic classes from sign-flip).

---

## 2. R-0 findings — compound halt

### 2.1 Lesson #61 slug grep — DIRECT HIT (12th cumulative dogfood)

`grep -rl "sign_flip|zero_crossing|funding.*flip|flip.*funding|sign.*change.*funding|funding.*sign.*change" backend/runs/research_track/` returns 3 files, all in one predecessor:

| Predecessor | Paradigm # | Date | Verdict | Location |
|---|---|---|---|---|
| `funding_rate_sign_flip_event_alt_long_4h` | **96** | 2026-05-19 | **BROAD_FALSIFIED** | `backend/runs/research_track/funding_rate_sign_flip_event_alt_long_4h/r1/` |

Paradigm 96 tested the **exact same trigger class** (categorical sign-flip event on 8h Binance funding) with the **exact same 4-quadrant SNT bilateral direction axis** on a 13-alt cohort (12 measurable, BNBUSDT effectively absent). Hold sweep 4h/8h/12h. Sample density n=6,934 events (347/346 per cell for A/B).

Paradigm 96 R-1 summary explicitly closes the family:

> "Sign-flip categorical transform class is now documented as graveyard — no further sign-flip variants without different direction/horizon/conditioning hypothesis."

The current proposal offers "N-consecutive-same-sign prescreen" as its conditioning novelty. Sections 2.3–2.4 analyze whether that clause is met.

### 2.2 Paradigm 96 empirical falsification (uniform, structural)

**A LONG focus @ hold 240m (4h)** — the current proposal's A_focus arm:

| Metric | Value | Verdict |
|---|---|---|
| n_events | 3,448 | abundant |
| mean_bp | **−16.47** | anti-alpha (below fee floor by ~32bp) |
| obs_t | −4.77 | strongly negative |
| signal_t_excess | −3.15 | anti-alpha vs null |
| perm_p | **0.000** | permutation null NEVER matches observation |
| ci_lower_bp / ci_upper_bp | −23.71 / −9.74 | CI entirely negative |
| prob_positive (null) | 0.0 | zero probability observation is upside |
| three_gate | FAIL | 0/3 gates passed |

**A_LONG_focus concentration**:

| Dim | Measurable | Passing | Ratio | Gate |
|---|---|---|---|---|
| Per-quarter (pos_t) | 10 | 2 | 0.20 | **FAIL** (< 0.50) |
| Per-symbol (ci_pos) | 12 | **0** | 0.00 | **FAIL** (< 0.30) |

**Zero out of twelve measurable symbols** have a CI-positive lower bound. The anti-alpha is uniform across the full alt cohort. Not a single symbol shows even marginal upside.

**Hold sweep A LONG focus** (Lesson #20 cond3 input):

| Hold | mean_bp | sig_t_excess |
|---|---|---|
| 240m (4h) | −16.47 | −3.15 |
| 480m (8h) | −15.94 | −2.82 |
| 720m (12h) | −16.39 | −2.43 |

Monotonic anti-alpha at −16bp regardless of horizon. Extending to 24h/48h (as the current proposal does) would widen exposure to the same drift, not escape it. Paradigm 96 did not test 24h/48h, but the horizon-invariance of the −16bp drift across 4h→12h (a 3x horizon expansion with essentially zero change in per-trade edge) strongly implies the drift extends beyond 12h as well.

**Full 4-quadrant SNT verdict @ hold 240m**:

| Quadrant | n | mean_bp | obs_t | sig_t_ex | perm_p | ci_lower_bp | three_gate |
|---|---|---|---|---|---|---|---|
| A LONG focus | 3,448 | −16.47 | −4.77 | −3.15 | 0.000 | −23.71 | FAIL |
| A SHORT mirror | 3,448 | +0.47 | +0.14 | +3.22 | 1.000 | −6.26 | FAIL (fee-floor saturation) |
| B LONG same-sign | 3,440 | −6.11 | −1.70 | −0.11 | 0.432 | −13.22 | FAIL |
| B SHORT mirror | 3,440 | −9.89 | −2.76 | +0.35 | 0.662 | −16.78 | FAIL |

**0/4 quadrants pass** — this is BROAD_FALSIFIED, not narrow. The A_mirror (SHORT on pos→neg flip) is the only quadrant with positive sig_t_excess (+3.22) but CI straddles zero (−6.26 to +7.20) and perm_p=1.00 — pure fee-floor saturation. Paradigm 96 R-1 summary noted this as "possible follow-up R-1 candidate" only in the sense that mean is not structurally negative — but the edge is too thin to clear 16bp fees.

### 2.3 Lesson #62 DNA 5-dim overlap — HARD FAIL 5/6 (14th cumulative dogfood)

| Dim | paradigm 96 | paradigm 246 | Match |
|---|---|---|---|
| Statistic | categorical sign_flip event (pos→neg \| neg→pos) | categorical sign_flip event + N-streak prescreen | **YES** (base statistic identical; N-streak is preconditioning filter on same base — see §2.4) |
| Substrate | `binance_funding_rate` 8h + OHLCV 1m | `binance_funding_rate` 8h + OHLCV 1m | **YES** (identical) |
| Signal type | event_anchored_bilateral_per_sym_4quadrant_SNT | event_anchored_bilateral_per_sym_4quadrant_SNT | **YES** (identical) |
| Universe | 13-alt Binance perp (12 measurable) | 14-sym alt cohort (same core pool) | **YES** (effectively identical) |
| Direction axis | bilateral (LONG+SHORT via 4-quadrant SNT) | bilateral (LONG+SHORT via 4-quadrant SNT) | **YES** (identical) |
| Hold frame | 4h / 8h / 12h | 4h / 12h / 24h / 48h | **PARTIAL** (2/4 identical: 4h + 12h; 24h/48h are horizon extension of same drift) |

**5/6 overlap = DNA duplicate ceiling** per paradigm-architect halt rule and Lesson #62. Same 5/6 ratio that triggered paradigm 242 vs paradigm 22 (LSR) and paradigm 245 vs paradigm 103 (cross-exchange funding).

### 2.4 Lesson #55 prescription-rescue-scope — OUT OF SCOPE (6th cumulative dogfood)

Lesson #55 permits a rescue prescription (added filter/conditioning) when the predecessor's failure shows **heterogeneous subset structure** — some symbols or some periods with ci_pos or pos_t alpha that a filter could isolate.

Paradigm 96 A_LONG_focus subset structure:

- **Per-symbol ci_pos: 0 / 12** — literally zero symbols have any positive CI lower bound. Uniform anti-alpha.
- **Per-quarter pos_t: 2 / 10** — 80% of quarters are negative-t. The 2 positive-t quarters (2024Q1 t=+0.22 with only n=29 and 2024Q3 or similar) are not statistically distinguishable from noise.
- **perm_p = 0.000** — the null permutation distribution NEVER reaches the observed statistic. This is a structural anti-alpha, not a noisy positive.

An N-consecutive-same-sign filter selects a temporal subset of the same event class. It does not select a different symbol subset, a different direction, a different mechanism, or a different substrate. Given the predecessor's uniform anti-alpha across the full 12-symbol cohort and 10-quarter window, no subset selectable a-priori by an N-streak filter is expected to reverse the sign.

Concretely: if longs are structurally hurt when funding flips pos→neg after ANY prior condition, longs are not going to be structurally helped when the flip is preceded by a longer sustained-positive streak (which if anything means more crowded long positioning, more of the same mechanism).

**Verdict: L55 prescription-rescue OUT OF SCOPE.** The N-streak variant does not meet the "different direction/horizon/conditioning hypothesis" clause in paradigm 96's family-close statement because:
- Direction: same bilateral 4-quadrant
- Horizon: 2/4 identical + 2/4 same-drift extension
- Conditioning: filter on same event class, not new mechanism

### 2.5 Lesson #56 outcome-family proxy FAIL (22nd cumulative dogfood)

Family = `funding_rate_categorical_boundary_event_bilateral`. Family falsification evidence:

- 4/4 quadrants FAIL at hold 240m
- 0/12 syms with ci_pos in A_LONG focus
- Monotonic −16bp mean_bp across 4h/8h/12h hold sweep
- perm_p = 0.000 (structural, not noise)

Mechanism-invariance of the proposed variation:
- N-streak preconditioning selects a temporal subset of the same event class
- Direction axis unchanged
- Hold extension to 24h/48h widens exposure to the same anti-alpha drift (monotonicity confirmed 4h→12h)

**Family proxy FAIL.** Any variant within this family requires either (a) direction inversion with independent evidence the mirror side clears fees, or (b) genuinely new statistic class (not a filter on the same event).

### 2.6 Lesson #77 substrate diversity — PASS-in-letter, moot

Substrate = `binance_funding_rate` (non-OHLCV). Passes L77 letter but same substrate family as paradigm 96 — does not offset the DNA duplicate halt (paradigm 231, 238 precedent: L77 pass is necessary-but-not-sufficient).

### 2.7 Lessons #11, #28, #30, #40 — moot

All would pass at the substrate level (data available, sample density adequate, structural threshold binary/observable). Moot because compound R-0 halt precedes any dispatchable prescreen action.

---

## 3. Compute saved

- R-1 dispatch (12 syms × 12 cells for N ∈ {3,7,14} × hold ∈ {4,12,24,48} × 4 quadrants): ~10 min
- R-2 multi-sym expansion + WF: ~20 min
- R-3 robustness: ~15 min
- Zero backfill bytes (funding_rate table already in DB per paradigm 96 audit; would not have triggered download regardless)
- **Total saved: ~45 min compute + zero bandwidth**

---

## 4. Lesson updates

### Cumulative dogfood counters (no novel lesson)

| Lesson | Description | Cumulative dogfoods after paradigm 246 |
|---|---|---|
| #61 | slug grep direct-hit | **12** |
| #62 | DNA 5-of-6 duplicate | **14** |
| #55 | prescription-rescue scope | **6** |
| #56 | outcome-family proxy | **22** |

### No novel lesson candidate

Paradigm 246 is a textbook compound R-0 halt. All applicable lessons already exist and were correctly applied. No novel failure mode observed.

The self-recommend autonomous dispatch produced this hypothesis without cross-checking the slug grep first — the pattern of proposing "sustained-N variant of already-graveyard-classified event mechanism" is now the 3rd such SELF-RECOMMEND filter-rescue attempt (after paradigm 242 LSR-rescue and paradigm 245 cross-exchange-rescue). The pattern of failure is stable enough that a **SELF-RECOMMEND prescreen-audit rule** should be added: when self-recommending, the agent must first slug-grep the proposed mechanism family before generating hypothesis text. This procedural note is entered as an **inline agent-behavior note**, not a new numbered lesson.

---

## 5. Next paradigm (247) recommendations

Inherited from paradigm 245 §5 rank list (still current; no updates warranted):

1. **`alt_perp_index_price_deviation_from_spot_index_percentile_bilateral_4h`** — mark vs spot index basis deviation z-score. Novel substrate (perp-index basis), distinct from funding/LSR/OI/TBS/sign-flip retired families. Existing binance spot + perp OHLCV or `mark_price_kline` endpoint.

2. **`alt_orderbook_liquidity_asymmetry_top10_depth_bid_ask_ratio_bilateral_1d`** — L2 book snapshot bid/ask depth ratio at daily frequency. Requires book_depth substrate audit for coverage ≥180d.

3. **`alt_binance_perp_daily_settlement_time_reversion_15m`** — UTC 00:00 daily boundary reversion window. Fast-frame Lesson #57 exception.

### BANNED addendum (updated for paradigm 247+)

- **NEW**: Any additional funding rate categorical sign-flip variant on the Binance USDT-M perp 14-alt cohort. Paradigm 96 empirically retired all 4 quadrants across full hold sweep and full cohort at n=6,934. N-streak / hold-extension / quadrant-narrowing rescues are inadmissible unless the proposal introduces a **new substrate family** OR a **direction-inverting mechanism** (not a filter). The A_SHORT_mirror positive-sig_t_excess (+3.22) with perm_p=1.00 is fee-floor-saturated and cannot be rescued by any known method.
- All prior BANNED entries from paradigms 242, 245 graveyards inherited.

---

## 6. Meta-observation

Paradigm 246 is the **12th L61 slug-grep dogfood**, **14th L62 DNA 5-of-6 dogfood**, **22nd L56 outcome-family-proxy dogfood**, and **6th L55 prescription-rescue-scope dogfood**. Compound halt severity: 4 independent lessons converge on the same R-0 verdict.

The SELF-RECOMMEND dispatch pattern for paradigm 246 (3rd filter-rescue attempt in the recent queue after paradigms 242, 245) suggests the agent's hypothesis-generation prior is drifting toward "add a filter to a broadly-known mechanism family" — a known-failure prior per Lesson #55. Recommendation for the SELF-RECOMMEND path:

> Before drafting hypothesis text, the agent should execute `grep -rl {mechanism_slug_family}` and verify no direct-hit predecessor exists. If a direct hit surfaces, either (a) select an entirely different substrate family, or (b) if the predecessor is R-1 CONCENTRATED (not BROAD_FALSIFIED), consider a Lesson #55 rescue with explicit heterogeneity-subset evidence. Broadly-falsified predecessors are NOT rescuable by filter/hold-extension/quadrant-narrowing.

This is entered as an agent-behavior note, not a numbered lesson (procedural, not empirical).

---

## 7. Artifacts

- Graveyard doc (this file): `backend/runs/research_track/graveyard__paradigm_246_alt_funding_rate_sign_flip_sustained_N_event_bilateral_4h_1d.md`
- R-0 prescreen JSON: `backend/runs/research_track/paradigm_246_alt_funding_rate_sign_flip_sustained_N_event_bilateral_4h_1d/r0_prescreen.json`
- INDEX.json entry: `paradigm_246_alt_funding_rate_sign_flip_sustained_N_event_bilateral_4h_1d`
- No R-1 code written, no funding_rate or OHLCV backfill triggered.
- Prior paradigm 96 verdict (referenced): `backend/runs/research_track/funding_rate_sign_flip_event_alt_long_4h/r1/r1_summary.md`
- Prior paradigm 96 metrics (referenced): `backend/runs/research_track/funding_rate_sign_flip_event_alt_long_4h/r1/r1_metrics.json`
- No paper spec written. No `tier_promotion_queue.json` modification.
