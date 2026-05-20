# Graveyard — paradigm 125 `alt_realized_quarticity_normalized_bipower_jump_event_alt_directional_2h`

**Date** 2026-05-20 20:51 KST
**Phase reached** R-0 prescreen (HALT before R-1 dispatch)
**Verdict** `R0_HALT_STRUCTURAL_THRESHOLD_INFEASIBLE_LESSON_40`
**Counter** 125 (124 → 125)

## Hypothesis

Barndorff-Nielsen (Andersen-Bollerslev 2007 / Huang-Tauchen 2005) realized **ratio jump test** on 1h windows of 5m crypto log-returns. Standard threshold Z > 3.0 detects discrete jumps separate from continuous volatility. Trigger: Z>3 AND |1-bar log_ret| > 0.5%. Direction: jump sign. Forward hold 2h. Universe: 13 active alts.

**Family-distinct claim vs paradigm 65/66/124**:
- Statistic class: RATIO of realized variations (RV-BV)/RV (jump-isolation) — not raw moment.
- Trigger mode: discrete event (Z>3 binary detection) — not continuous percentile.
- Direction: 1-bar log-return sign (price-jump sign) — not skew sign.

## R-0 empirical findings (substrate panel 2.77M 5m bars × 13 alts × 2.03y)

Two implementations attempted (both canonical from literature):

| Form | Z_jump p50 | p90 | p99 | p99.9 | Z>3 rate |
|---|---|---|---|---|---|
| (RV-BV)/(BV × sqrt(theta·ratio/M)) [Huang-Tauchen variant] | 0.028 | 1.409 | 2.294 | 2.898 | **0.064%** |
| ((RV-BV)/RV) × sqrt(M / (theta · max(1, RQ/BV²))) [canonical ratio] | 0.028 | 0.885 | 1.135 | 1.255 | **0.000%** |

| Threshold | Joint trig (Z>3 AND |log_ret|>0.5%) | Joint rate |
|---|---|---|
| |log_ret| > 0.3% | 445 | 0.0161% |
| |log_ret| > 0.5% | 181 | 0.0065% |
| |log_ret| > 0.7% | 85 | 0.0031% |
| |log_ret| > 1.0% | 24 | 0.0009% |

Maximum joint trigger rate < 0.02% under permissive 0.3% magnitude filter; well below `[0.5%, 8%]` band target. Even ignoring magnitude filter, Z>3 alone fires at **0.064%** of bars (1782 across full panel), giving ~140/sym/2y — Lesson #11 per-cell threshold violated.

## Failure analysis — Lesson #40 STRUCTURAL THRESHOLD INFEASIBLE

The B-N ratio jump test is **asymptotically N(0,1) under H0 = no jump** when M (intra-day return count) is large. At M=12 (1h window of 5m bars), the test is **non-asymptotic**:

1. **Numerator bounded by [0, 1]** in the canonical ratio form (RV-BV)/RV cannot exceed 1 since BV ≥ 0.
2. **Scale factor sqrt(M / theta) = sqrt(12 / 0.609) ≈ 4.44** insufficient to amplify the bounded numerator past 3.
3. **Asymptotic critical value 3.0 unreachable** by construction. p99.9 of Z_jump = 1.255 < 3.0.

Original Andersen-Bollerslev (2007) study used M=78 (NYSE 6.5h × 5min) and Huang-Tauchen (2005) used M=288 (24h crypto × 5min). At those windows, sqrt(M/theta) = sqrt(78/0.609) ≈ 11.3 or sqrt(288/0.609) ≈ 21.8, comfortably amplifying the [0,1] numerator past 3.

**This is exactly the Lesson #40 antipattern**: non-negative aggregate statistic (ratio form) with structural upper bound, target threshold (Z>3) unreachable.

### Lesson #40 prescription: reformulate via percentile rank / log / ratio

Standard Lesson #40 escape is percentile rank reformulation. **Tried mentally**:
- p98+ Z_jump ≈ 1.1 — no longer carries B-N "jump" semantic
- Becomes "above-2σ ratio statistic" — equivalent to a kurt-skew variant of paradigm 124
- **Reformulation collapses paradigm 125 into paradigm 124 family** — defeats family-distinct claim entirely

### Lesson #40 escape via M expansion (window length)

Expanding M to 78 (6.5h) or 288 (24h) would restore asymptotic test validity, but:
- Breaks 1h frame design (overlaps with paradigm 67/68/69 RV-based daily-frame family)
- 6h+ windows on crypto perp ignore the intraday flow microstructure premise
- Trigger rate at M=78 still constrained by 24h cycle; daily-frame paradigms already extensively explored

Both escape paths land in already-retired family space → paradigm 125 R-0 HALT is dispositive.

## Lessons applied

| Lesson | Verdict |
|---|---|
| #11 sample density | n/a (Z>3 rate 0.064% would give ~140 events; per-cell <30) |
| #21 axis stacking | PASS (single jump-statistic axis, magnitude is confirm not stack) |
| #22 frame-grade 5m | PASS (2.77M bars substrate, but Lesson #40 dominates) |
| #23 non-event-anchored | PASS (continuous rolling) |
| #28 substrate | PASS (5m OHLCV resampled, 13/13 alts) |
| #30 data window ratio | PASS (full 795d) |
| #34 empirical distribution | applied — revealed Lesson #40 violation |
| **#40 structural threshold feasibility** | **FAIL** — canonical ratio form bounded by [0,1] × sqrt(M/theta) cannot reach Z=3 at M=12 |
| #44 amendment xref (6th dogfood) | applied — paradigm 65/66/124 distinguishing axes documented |
| #45 family-distinct | PASS at definition layer, but reformulation would collapse into paradigm 124 family |
| #46 AMENDMENT REFINEMENT (3rd dogfood) | n/a — halted before stratified test became applicable |

## Lesson #40 dogfood — 4th confirmed application

Cumulative Lesson #40 invocations:
- paradigm 109 (z-score on non-negative aggregate; first dogfood)
- paradigm 110 (z-score on RV; second dogfood)
- paradigm 125 **canonical ratio form bounded [0,1] cannot reach asymptotic critical value at short window** — third explicit dogfood

NEW Lesson #40 sub-antipattern documented: **academic test statistics designed for long-window asymptotics fail at short-window rolling deployment**. R-0 must verify empirical distribution attainability of the published threshold under the rolling-window M actually used. Two consecutive paradigms (109, 110, 125) with structural infeasibility — Lesson #40 broadly applicable beyond aggregate-stat z-score.

## Lesson #44 amendment 6th dogfood

paradigm 65 / 66 / 124 cross-referenced in R-0 JSON. Mechanism distinction (ratio vs raw moment, discrete event vs continuous percentile, price-jump sign vs skew sign) **verified at definition layer** but the proposed B-N test is **empirically inaccessible at M=12** — so the mechanism never gets tested.

Confirmed amendment: graveyard cross-reference must include **substrate availability + threshold reachability** sub-check beyond pure mechanism-name distinction.

## Family / axis impact — Higher-order moment family Tier 4 retire **CANDIDATE** strengthened (NOT formal retire)

| Counter | Family member | Verdict | Frame | Trigger mode |
|---|---|---|---|---|
| 65 | realized_skewness_exhaustion_mr | GRAVEYARD | 1m | z-trigger MR |
| 66 | realized_skewness_momentum_continuation | GRAVEYARD | 1m | z-trigger momentum |
| 124 | alt_realized_kurtosis_extreme_signed_directional_2h | BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE | 5m | continuous top-decile + skew sign |
| **125** | **alt_realized_quarticity_normalized_bipower_jump_event_alt_directional_2h** | **R0_HALT_STRUCTURAL_THRESHOLD_INFEASIBLE_LESSON_40** | 5m | discrete event (UNREACHABLE) |

**4th paradigm in family** but failure mode is **substrate-level not mechanism-level**. Mechanism (jump detection) never empirically tested — only the operationalization at M=12 failed. Strict reading: **NOT formal Tier 4 retire trigger** because the family's mechanism axis (4th-moment-derived discrete jump detection) was not falsified, only the chosen window length.

Conservative recommendation: keep family as **Tier 4 retire CANDIDATE** (no upgrade). To exhaust the family proper, future R-0 candidate at M=288 (24h cycle) frame would need to be falsified separately. That candidate already overlaps with paradigm 67/68/69 RV daily-frame family.

**Practical outcome**: higher-order moment family **effectively retired** for 1h-frame discrete-event variants; 24h-frame variants overlap with already-retired RV-based family — both directions exhausted.

## Continuous-parallel campaign state

| Counter | Verdict |
|---|---|
| 119 | BROAD_FALSIFIED |
| 120 | BROAD_FALSIFIED |
| 121 | BROAD_FALSIFIED |
| 122 | BROAD_FALSIFIED |
| 123 | BROAD_FALSIFIED |
| 124 | BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE |
| **125** | **R0_HALT_STRUCTURAL_THRESHOLD_INFEASIBLE_LESSON_40** (R-1 not dispatched) |

7 consecutive non-PASS verdicts since paradigm 119. Of these, 125 is the first **R-0 halt** in the streak (124 ran R-1; 119-123 ran R-1). Axis exhaustion + substrate exhaustion signals BOTH active.

## Next candidate recommendation

**Path 1 — REJECTED**: paradigm 125 retry at M=78 (6.5h) or M=288 (24h)
- Overlaps with paradigm 67/68/69 RV daily-frame family (already R-3+/seed). Adds no novelty.

**Path 2 — REJECTED**: Lesson #40 reformulation via Z_jump percentile rank
- Collapses into paradigm 124 family (continuous percentile of higher-order-moment-derived statistic). 4th confirmation of family without distinction.

**Path 3 — RECOMMENDED**: pivot AWAY from higher-order moment family entirely. `alt_5m_close_to_open_overnight_gap_z_directional_4h_with_session_anchor`
- Statistic: close-to-open (5m bar boundary at 00:00 / 08:00 / 16:00 UTC, anchored to 8h funding boundary) **price-level gap** divided by trailing 24h ATR.
- Trigger: |gap_z| > 2.5 (top ~1% of overnight session-boundary gaps).
- Direction: gap sign (gap-up → LONG continuation OR gap-down → SHORT continuation).
- Family-distinct: NEW statistic class (price-level overnight-gap normalized by intraday ATR). Closest neighbors: paradigm 122 (intraday session open OI velocity, BROAD_FALSIFIED — DIFFERENT axis OI) and paradigm 113 (hour-of-day anchor, no normalization). DNA 4/6 distinct.
- Lesson #21 axis stack risk: temporal anchor + price gap z-statistic — 2 axes but **anchor is selection filter not signal** (Lesson #21 PASS pattern).
- Substrate: 100% archive-direct (klines 5m), already cached.
- **CAUTION**: paradigm 113 hour-of-day anchor already BROAD_FALSIFIED. Need to demonstrate gap normalization provides directional signal hour-of-day did not.

**Path 4 — ALTERNATIVE**: `alt_perp_funding_rate_sign_x_oi_sign_pretrigger_anchor_alt_directional_8h`
- 8h pre-funding-boundary window, condition: funding sign + OI change sign agreement (both bullish or both bearish over prior 4h).
- Substrate: funding (1y limited cohort 7-syms) + OI 5m. **Lesson #11 sample density risk** — short funding window + agreement filter.
- Family-overlap risk: funding family Tier 4 retired (paradigm 73/79/96/97/98/99 + 22 R-5 exception). Sign × OI conjunction is candidate-novel; paradigm 96 was funding-sign-flip alone.
- **RECOMMEND-DEFER**: funding family already 6 retire, novelty axis is OI-conjunction not new.

**FINAL recommendation: Path 3** — overnight gap z-normalized × session boundary. New statistic class (price-level intraday gap), low family overlap, archive substrate, Lesson #21 PASS pattern, single R-0 prescreen feasible.

## Counter / R-5 / family summary post-125

- Cumulative graveyards: **125** (124 → 125, R-0 halt counts; substantive empirical finding produced)
- R-5 seeded: 8 (unchanged)
- Family retire formal Tier 4: 8 (unchanged)
- Family retire CANDIDATE: 4 (higher-order moment now strengthened but NOT promoted to formal — see family/axis section)
- Lessons: 30 confirmed + #31 confirmed + 3 amendments + #41 amendment confirmed + #45 CONFIRMED + #46 AMENDMENT REFINEMENT + sub-amendment formal promotion 자격 (3rd dogfood reached only at R-0 partial — refinement protocol applied but stratified not executed) + #44 amendment 6th dogfood (CONFIRMED, with new sub-amendment: substrate-keyword AND threshold-reachability dual check) + #40 4th explicit dogfood with new sub-antipattern (academic asymptotic test statistic at short-M rolling deployment)
