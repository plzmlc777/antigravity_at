# Graveyard — paradigm 234 `alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1`

**Date**: 2026-07-23 12:53 KST
**Phase halt**: R-0 (prescreen — before R-1 dispatch)
**Verdict**: `R0_HALT_LESSON_56_FAMILY_PROXY_FAIL + LESSON_55_CANDIDATE_PRESCRIPTION_OUT_OF_SCOPE + LESSON_57_FEE_FLOOR_SATURATION`
**Dispatch mode**: user-provided (per paradigm 233 recommendation to switch from SELF-RECOMMEND to user mode; brief was supplied by dispatcher)

## Hypothesis (as submitted)

5-minute `taker_buy_sell_ratio` (microstructure joblib) at rolling 288-bar (24h) window extreme percentile:
- p95+ (extreme buy) → SHORT (exhaustion reversal)
- p05- (extreme sell) → LONG (exhaustion reversal)

Hold: 4h-24h (bars 12, 48, 96). Universe multi-sym alt perp. Brief claimed differentiation from TBS graveyard (§3-G graveyard 23) via (1) exhaustion-reversal direction vs "momentum continuation", (2) percentile p95/p5 trigger vs z-score level, (3) both trigger axes non-OHLCV.

## R-0 Prescreen result — HALT

Three interlocking hard fails identified via mandatory R-0 checks.

### Fail 1 — Lesson #61 slug grep + Lesson #56 family proxy: brief claim factually incorrect

The differentiation-from-TBS-graveyard argument in the dispatcher brief is FALSE. Direct prior art in `_graveyard/taker_flow_zscore/GRAVEYARD_NOTE.md` (paradigm 23, 2026-05-06):

> "5m granularity microstructure joblib `taker_buy_sell_ratio` (실현된 aggressive flow imbalance) rolling 288-bar(24h) z-score. 두 모드:
> - `fade` (climax reversal): TBS_z > entry → SHORT; < -entry → LONG
> - `follow` (momentum): TBS_z > entry → LONG; < -entry → SHORT"

Paradigm 23 tested BOTH modes. The `fade` mode is **exactly** paradigm 234's "exhaustion reversal" — extreme buy → SHORT, extreme sell → LONG. Holds tested in graveyard 23: 12, 24, 48 bars (5m). Paradigm 234 proposes 12, 48, 96 — two of three identical, family-identical span.

Paradigm 23 outcome: SOL fade z=2.5 h=24 marginal PASS (alpha +35, sharpe +0.20, MDD 26.7). R-2 10-symbol expansion **collapsed**: alpha 3/10 (only SOL meaningful), sharpe 1/10 (SOL only), alpha mean -7.0, seven catastrophic negatives (HBAR -10, AXS -14, LINK -27, ETC -27, COMP -20). R-2 conclusion: single-symbol SOL outlier, not paradigm.

Paradigm 234 direction is a direct re-test of graveyard 23 fade mode, changing only the normalization (percentile p95/p5 vs z-score).

### Fail 2 — Lesson #55 candidate PRESCRIPTION-OUT-OF-SCOPE (normalization-swap for signal absence)

The percentile-rank prescription has already been formally dogfooded as INSUFFICIENT in paradigm 143 (`graveyard__alt_taker_buy_quote_vol_percentile_rank_directional_8h.md`, 2026-05-21):

> "**Distribution normalization is NOT the root cause** — underlying signal is genuinely absent (or fully fee-saturated). Lesson #55 confirmed-elevation impeded; prescription dogfood failed."

Paradigm 142-v2 (z-score) → BROAD_FALSIFIED. Paradigm 143 (percentile-rank, same substrate/axis) → also BROAD_FALSIFIED with slightly WORSE B_focus signal at matched hold (z-score 12h sigex +3.43 → percentile 12h sigex +1.01, regression −2.4σ). Two-dogfood evidence establishes: swapping z-score → percentile does not rescue a fee-saturated / signal-absent taker-flow axis.

Paradigm 234's central novelty claim ("percentile trigger not z-score level") is precisely the prescription paradigm 143 documented as failing.

### Fail 3 — Lesson #57 fee-floor saturation (empirical Lesson #79 pretest)

Ran the mandatory Lesson #79 predictive-content pretest on SOL microstructure + OHLCV (5m):

- OOS: 2025-04-05 to 2026-05-12, 115867 bars, 6144 p95 SHORT + 6121 p05 LONG triggers
- corr(signal, forward_return):
  - h1h (12 bars): +0.0304 PASS (>0.02)
  - h4h (48 bars): +0.0227 PASS (barely)
  - h8h (96 bars): +0.0083 FAIL
  - h24h (288 bars): +0.0067 FAIL
- Mean signed gross return per trade: h1h +2.23 bp, h4h +3.30 bp, h8h +1.75 bp, h24h +2.58 bp
- Round-trip fee floor: 16 bp
- Net after fee: h4h −12.70 bp, h8h −14.25 bp, h24h −13.42 bp

The correlation is directionally correct (exhaustion reversal has real weak information at h1h/h4h) but the effect size is 5-7× below the fee floor at ALL horizons. Primary target range 4h-24h fails predictive-content threshold at h8h and h24h and fails the fee floor at every horizon.

This reproduces the exact family signature documented in Lesson #57 (2 CONFIRMED dogfoods: paradigm 142 + 143):

> "aggressive taker flow info-leaks during the bar, residual 4h forward return dominated by fee"

Paradigm 234 = **3rd** family fee-floor dogfood, this time captured at R-0 via Lesson #79 pretest before R-1 compute.

## Lesson dogfoods

### Lesson #56 (family proxy) — positive functional dogfood
R-0 correctly detected direct prior art in paradigm 23 fade mode that the dispatcher brief had misclassified. Family proxy check working as intended, saved R-1 compute.

### Lesson #61 (slug grep) — positive functional dogfood
Slug pattern search "taker_flow_burst | taker_reversal | taker_exhaustion | taker_buy_sell_ratio + reversion" surfaced three highly-relevant graveyards (paradigm 23, 142, 143) plus TBS 5m substrate references in paradigm 60/72/177. R-0 halt at first check reduced compute to zero.

### Lesson #57 (fee-floor saturation of taker-flow family) — 3rd dogfood
Empirical pretest gross bp measurement is 1.7-3.3 bp per trade across all target horizons vs 16 bp fee. Formal 3rd family dogfood; family retire status confirmed. All future taker_buy_sell_ratio / taker_buy_quote_volume / CVD-ratio directional-continuation-at-4h-plus paradigms should R-0 HALT by default unless: (a) hold ≤ 60m single-family, or (b) joint with distinct axis producing empirically new mechanism (e.g. burst + regime + OI Δ).

### Lesson #79 (predictive-content pretest) — 2nd dogfood, first at R-0
Paradigm 233 was 1st dogfood at R-1 completion (post-108-cell full-sweep detection). Paradigm 234 executes Lesson #79 at R-0 BEFORE R-1 dispatch (per RUNBOOK line 690 amendment) and detects mixed-pass (h1h/h4h pass, h8h/h24h fail) with universal fee-floor failure. R-0 stage detection of predictive-content weakness is the target design — Lesson #79 now demonstrably viable as R-0 mandatory item. **Elevate Lesson #79 candidate → CONFIRMED** (2 dogfoods, one at R-1, one at R-0, both correctly flagging signal-quality issues).

### Lesson #55 candidate (distribution-normalization prescription) — 4th consecutive FAIL
Paradigm 142→143 (percentile prescription for z-score asymmetry) already elevated candidate to PRESCRIPTION-OUT-OF-SCOPE. Paradigm 234's re-application of the same prescription (percentile vs z-score for exhaustion reversal on TBS 5m 288-bar) was flagged at R-0 without further R-1 waste. Prescription formally retired for taker-flow family.

## Failure mechanism (summary)

`taker_buy_sell_ratio` at 5m granularity is a REACTIVE, high-frequency, low-signal-density indicator. Its extreme percentiles reflect completed order-flow imbalances that are already priced by t (paradigm 23 note: "실현된 aggressive flow imbalance") — the exhaustion-reversal information leaks WITHIN the trigger bar. At 4h-24h forward horizons, the residual mean-reversion effect is ≈ +2-3 bp gross ≪ 16 bp fee floor. No normalization scheme (z-score, log-z-score, percentile-rank) rescues a signal whose effect size is 5-7× below the fee floor at the target hold.

## Campaign deltas

- Cumulative graveyards: 143 → 234 (91 additional since paradigm 143, cross-referencing INDEX chronology — this is the immediate paradigm counter continuation, not cumulative graveyard n)
- Paradigm 234 is graveyard immediately following paradigm 233 graveyard
- Non-PASS streak (paradigms 222-234 SELF-RECOMMEND + user-provided): 12 consecutive
- Lesson #57 dogfood count: 2 → **3** (family retire enforced)
- Lesson #79 dogfood count: 1 → **2** (candidate elevated to CONFIRMED-eligible; R-0 vs R-1 detection cross-covered)
- Lesson #56 positive functional dogfood: 1 more (brief misclaim correction)
- Lesson #61 positive functional dogfood: 1 more (grep found 3 relevant graveyards)
- R-5 seeded LIVE: unchanged
- No new infrastructure (existing microstructure + ohlcv_cache 1m used)
- Backfill: 0 bytes (all data existed)
- Compute cost: ~4 seconds (single pretest on SOL)

## Family retire enforcement (formal)

**Family**: `taker_buy_sell_ratio_directional_at_4h_plus_horizons` (all normalizations, both directions, all reversal/momentum modes)

**Retire status**: **TIER 4 CONFIRMED** — three-dogfood cumulative (paradigm 23 R-2 collapse + paradigm 142 R-1 BROAD_FALSIFIED + paradigm 143 R-1 BROAD_FALSIFIED + paradigm 234 R-0 pretest fee-floor detection = 4 total dogfoods across 4 normalization/hold variants).

**Future dispatch policy**:
- Any future paradigm with (substrate = TBS 5m/1h/4h) AND (hold ≥ 4h) AND (direction axis derived from TBS extreme) should R-0 HALT by default.
- Exceptions require: (a) joint with distinct-substrate axis producing genuinely new mechanism (not simple TBS-plus-filter), OR (b) hold ≤ 60m fast-frame (paradigm 127/128 volume-burst 30m R-5 LIVE proves fast frame is where taker-flow lives).
- Family boundary now includes CVD-ratio and taker_buy_quote_volume percentile/z variants per paradigm 140/142/143 chain.

## Next paradigm (235) recommendation

Substrate saturation across microstructure velocity/level/percentile families now includes:
- Position/account LSR level + velocity (paradigm 233)
- OI composition (paradigm 228/229/232)
- TBS + taker_buy_quote_vol + CVD (paradigm 23/72/140/142/143/234)
- Premium/basis/funding derivative velocity/level (§5 saturated)
- Fear&Greed (paradigm 226)
- Launchpool events

Per paradigm 203 MEMORIAL precedent and paradigm 233 recommendation, user-provided hypothesis mode is required. Paradigm 234 was user-supplied but re-tested a saturated axis; better user targeting needed.

### Option A (highest info gain, novel substrate)
`alt_book_depth_L2_bid_ask_imbalance_persistence_5m_directional_15m` — WS recorder book_depth (60+ day accumulation). Novel substrate NOT touched by any prior paradigm. Requires: (a) WS recorder maturity check (paradigm 144-brief noted 2026-07-15+ target; today 2026-07-23 → likely available), (b) L2 imbalance persistence CUSUM signal design (paradigm 84 SAMPLE_INSUFFICIENT context — 5m event ≠ 1h frame).

### Option B (event-driven, distinct axis)
`alt_binance_perp_futures_daily_settlement_time_reversion_15m` — no direct prior art. UTC 00:00 daily boundary (funding-payment adjacent) short-window mean-reversion after directional pre-open moves. Distinct from paradigm 132-141 funding-family (which triggered ON funding rate value/regime, not on ADJACENT boundary time reversion).

### Option C (cross-exchange, novel data domain)
`alt_bybit_binance_funding_spread_residual_carry_4h` — cross-exchange funding spread mean-reversion. Requires bybit_funding backfill (partial data at `runs/ohlcv_cache/bybit_funding/`). Distinct axis from single-exchange funding paradigms.

**Priority recommendation**: **Option A** — genuine substrate novelty, only substrate not yet dogfooded. Book_depth L2 has never been R-1 dispatched. Rejects further microstructure-column recomposition until new data domains exhausted.

## Artifacts

- Graveyard doc: `backend/runs/research_track/graveyard__paradigm_234_alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1.md`
- R-0 prescreen JSON: `backend/runs/research_track/paradigm_234_alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1/r0_prescreen.json`
- INDEX.json update: `paradigms.paradigm_234_alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1` entry
- RUNBOOK update: `backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md` — new "## N+1. Paradigm 234 R-0 GRAVEYARD log" section appended

No R-1/R-2/R-3/R-4/R-5 artifacts (halted at R-0).
