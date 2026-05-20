# Graveyard — paradigm 124 `alt_realized_kurtosis_extreme_signed_directional_2h`

**Date** 2026-05-20 20:36 KST
**Phase reached** R-1 (full panel, 4-quadrant SNT)
**Verdict** `BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE`
**Counter** 124 (123 → 124)

## Hypothesis

1h rolling realized kurtosis on 5m intra-bar log-returns (12-bar window) joint with 3rd-moment skewness sign as a one-sided liquidation cascade proxy. Trigger: excess kurt top-decile (p90 > 2.401) AND |skew| > 1.0. Direction: sign-matched LONG (skew > 0) or SHORT (skew < 0). Forward hold: 2h.

**Family-distinct claim vs paradigm 65/66** (3rd-moment skewness alone): 4th moment kurtosis is NEW statistic class, joint conjunction (kurt as primary trigger, skew as direction selector), 5m vs 1m frame base. 3/6 DNA dims distinct.

## R-0 prescreen (PASS_BUT_ADVISORY)

| Item | Value |
|---|---|
| Panel | 2.77M 5m bars, 13 alts × 2.03y |
| excess_kurt p90 | 2.401 |
| \|skew\| chosen threshold | 1.0 (joint rate 8.72%) |
| Joint trigger total | 241,258 (pos 125,899 / neg 115,359) |
| measurable quarters | **10/10 ALL** per quadrant |
| stratified n=50×4q A_focus | gross **+42.77bp** net +26.77bp t=5.00 |
| stratified n=50×4q B_focus | gross −20.27bp net −36.27bp t=−3.28 |
| A_focus sign flips | 1 (signs: -,+,+,+) |
| B_focus sign flips | **2** (signs: -,-,+,-) → Lesson #46 sub-amendment advisory |
| R-0 verdict | `R0_PASS_BUT_ADVISORY_PER_QUARTER_SIGN_FLIP_LESSON_46_SUB` |

## R-1 result (full panel, 4-quadrant SNT)

| Quadrant | n | gross_bp | net_bp | obs_t | sci/13 | q_pos/10 | 3-gate | edge≥2% |
|---|---|---|---|---|---|---|---|---|
| **A_focus skew_pos × LONG** | 125,893 | **+5.49** | −10.51 | −24.53 | 0/13 | 1/10 | FAIL | FAIL |
| A_mirror skew_pos × SHORT | 125,893 | −5.49 | −21.49 | −50.14 | 0/13 | 0/10 | FAIL | FAIL |
| **B_focus skew_neg × SHORT** | 115,355 | **+1.25** | −14.75 | −28.32 | 0/13 | 1/10 | FAIL | FAIL |
| B_mirror skew_neg × LONG | 115,355 | −1.25 | −17.25 | −33.12 | 0/13 | 1/10 | FAIL | FAIL |

`null_t` / `signal_t_excess` / `perm_p` are NaN per quadrant (fee_aware_perm_test n_obs > n_pool×2 limit; observed at paradigm 83 first).

## Failure analysis

**Magnitude collapse R-0 → R-1**. Stratified n=50×4q R-0 estimated A_focus gross +42.77bp (t=5.00) but full panel n=125,893 yields gross +5.49bp — **~8× collapse**.

Mechanism diagnosis:
1. **R-0 stratification artifact (positive)**. n=50×4q sample (n_total=200) drew the *first* 50 chronological triggers per quarter. Joint trigger rate 8.72% is high (vs paradigm 123 3.6%, paradigm 122 4.4%), so quarter-anchored first-50 sample falls within a localized cluster — geographic time-clustering bias amplified gross. Lesson #46 advisory (B_focus 2 sign flips) correctly flagged fragility before R-1.
2. **A_focus gross > 0 but fee-bound**. Both focus quadrants are gross-positive (+5.49 / +1.25 bp), implying the directional hypothesis is *weakly correct* but magnitude is small fraction of the 16bp fee floor. Same pattern as paradigm 103 (`cross_exchange_funding_spread` gross +12-14bp < 16bp floor).
3. **Mirror-pair sum nonzero but small**. A focus + mirror = 0 (by construction); A_focus gross +5.49 (real, fee-bound) → Lesson #39 sub-class A pattern (broad uniform negative net, exact-symmetric trigger noise from fee).
4. **0/13 alts ci_pos in ALL four quadrants**. No single symbol carries a fee-clearing signal even in A_focus direction. Joint kurt + skew trigger is a market-wide weak indicator, not a per-symbol mechanism.

## Lessons applied (all PASS gates at R-0, FAIL at R-1)

| Lesson | At R-0 | At R-1 |
|---|---|---|
| #11 sample density | PASS (10/10 quarters) | n/a |
| #16 concentration | n/a | 0/13 sci → FAIL (all quadrants) |
| #19 SNT 4-quadrant | applied | applied (all 4 negative net) |
| #21 axis stacking | PASS (single moment-class) | n/a |
| #22 frame-grade 5m | PASS (2.77M bars) | n/a |
| #28 substrate | PASS (1m → 5m resample) | n/a |
| #30 data window | PASS (99.4%) | n/a |
| #34 empirical distribution | applied | n/a |
| #39 sub-class manual | n/a | A-arm + B-arm = sub-class A (broad uniform negative) |
| #40 structural threshold | PASS (moments unbounded) | n/a |
| #41 amendment edge-first | n/a | FAIL (max edge −0.105% << 2%) |
| #44 amendment xref (5th dogfood) | PASS (paradigm 65/66 explicitly distinct) | Mechanism distinction confirmed but neither direction (continuation nor MR) salvageable |
| #45 family-distinct | PASS (explicit moments) | n/a |
| #46 AMENDMENT REFINEMENT (2nd dogfood) | **CONFIRMED 2nd dogfood** — stratified detected A_focus +42.77bp / B_focus −20.27bp asymmetry + B_focus 2 sign-flips advisory | Full panel confirmed sub-amendment advisory was correctly skeptical: B_focus realized fragility (full +1.25bp), A_focus magnitude collapse (full +5.49bp vs stratified +42.77bp) |

## Lesson #46 AMENDMENT REFINEMENT — 2nd dogfood CONFIRMED 자격 충족

Two consecutive paradigms (123 + 124) now show stratified n=50×4q + per-quarter sign-flip detection:
- **paradigm 123** (1st dogfood): R-0 stratified PASS → R-1 BROAD_FALSIFIED — stratification didn't over-promise.
- **paradigm 124** (2nd dogfood): R-0 stratified A_focus +42.77bp t=5.00 → R-1 collapse to +5.49bp. **Sub-amendment per-quarter sign-flip advisory correctly flagged B_focus 2 flips as fragility marker**, predicting R-1 failure.

→ **Promote Lesson #46 SUB-AMENDMENT (per-quarter sign-flip advisory) to CONFIRMED 자격** alongside main AMENDMENT REFINEMENT.

**NEW Lesson #46-B candidate**: R-0 stratified n=50×4q magnitude inflation factor. If R-0 stratified gross exceeds *empirical full-window gross* by >5×, treat R-0 advisory as upper bound and lower R-1 expectation accordingly. Two dogfoods (paradigm 124: 8× inflation from +42.77 → +5.49) needed for confirmation.

## Family / axis impact

**Higher-order moment family** (3rd + 4th moments on intra-bar log-returns) now 3 graveyards:
- paradigm 65 — 3rd moment z-trigger MR (1m frame)
- paradigm 66 — 3rd moment z-trigger momentum (1m frame)
- paradigm 124 — 4th + 3rd joint top-decile sign-matched (5m frame) ← NEW

**Recommendation**: Higher-order moment family **Tier 4 retire CANDIDATE** (1 graveyard remaining to formal Tier 4; needs paradigm × hold × frame × direction-logic variant to exhaust). All directions (MR / momentum continuation / joint sign-matched) and frames (1m / 5m) and statistic classes (3rd-only / 4th + 3rd) exhausted.

## Continuous-parallel campaign state

| Counter | Verdict |
|---|---|
| 119 | BROAD_FALSIFIED |
| 120 | BROAD_FALSIFIED |
| 121 | BROAD_FALSIFIED |
| 122 | BROAD_FALSIFIED |
| 123 | BROAD_FALSIFIED |
| **124** | **BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE** ← **6 consecutive** |

Continuous-parallel 6-run streak. Axis exhaustion signal continues. D-Day 2026-06-03 Day 30 baseline D-13.

## Next candidate recommendation

**Path 1 (axis novelty)**: `alt_intra_bar_signed_volume_imbalance_post_zero_cross_alt_directional_2h`
- Statistic: 5m intra-bar **signed taker-buy/sell ratio** (taker_buy_volume - taker_sell_volume) / total_volume, accumulated, **zero-crossing event** = directional inflection. Forward hold 2h LONG (positive zero-cross) / SHORT (negative).
- Family-distinct: paradigm 72 (taker_buy_vol family Tier 4 retired) was *level-based aggressive volume*, NOT zero-cross inflection event. Lesson #44 amendment xref required: taker family already retired.
- **REJECTED** — Lesson #44 amendment 6th dogfood likely HALT (taker-side family Tier 4 formal retire blocks this directly).

**Path 2 (data substrate novelty)**: `binance_ws_orderflow_imbalance_5min_aggregation_alt_directional_30m`
- Requires WS recorder data (paradigm 60+ days needed, 2026-07-15 earliest).
- **DEFER** — substrate not ready.

**Path 3 (mechanism axis pivot)**: `alt_5m_funding_announce_minute_10_pre_anchor_oi_velocity_z_directional_45m` — temporal anchor (8h funding boundary, hardcoded UTC 00/08/16) × OI velocity sign-matched directional. Hold 45m (pre-boundary 30min + boundary 15min).
- Family-distinct: paradigm 122 (intraday_session_open × OI) was anchor 00:00 UTC daily-cycle, NOT 8h funding boundary. Paradigm 80 (`oi_premium_5m_decoupling`) was premium × OI joint level, NOT temporal anchor. paradigm 113 was hour-of-day anchor without OI. Distinct combo.
- **CAUTION** — Lesson #21 axis stacking risk (temporal anchor + OI is paradigm 122 antipattern, BROAD_FALSIFIED). 8h funding boundary is finer-grain anchor and OI velocity (vs paradigm 122 OI acceleration) is statistic variant. Still axis-stacking pattern.

**Path 4 (statistic class true novelty — RECOMMENDED)**: `alt_realized_quarticity_normalized_bipower_jump_event_alt_directional_2h`
- Statistic: realized **quarticity** (4th moment of returns) divided by bipower variation (jump-robust scale) — **Barndorff-Nielsen jump test statistic**. Detects discrete jumps separate from continuous volatility.
- Trigger: jump statistic > 3.0 (95th percentile of standardized jump signature) AND |1-bar log-return| > 0.5%.
- Direction: jump direction (sign of jumping return). Forward hold 2h.
- Family-distinct: NEW statistic class (bipower variation + quarticity ratio — Andersen-Bollerslev 2007 paper). NOT 3rd moment, NOT plain kurtosis. Jump-robust scale normalizes for volatility regime. Lesson #44 amendment xref: paradigm 65/66/124 are pure moments (no scale normalization), paradigm 67/68/69 are RV-based (no 4th order). Truly distinct.
- **RECOMMENDED** — true statistic-class novelty, jump test is well-established academic literature, single statistic axis (Lesson #21 PASS).

## Final recommendation

**proceed with Path 4**: paradigm 125 candidate `alt_realized_quarticity_normalized_bipower_jump_event_alt_directional_2h`. Standard R-0 prescreen + Lesson #46 2nd-dogfood-CONFIRMED stratified protocol + Lesson #44 amendment 6th-dogfood graveyard xref vs paradigm 65/66/67/68/69/124.

User approval required before R-1 dispatch (R-0 only halt convention).
