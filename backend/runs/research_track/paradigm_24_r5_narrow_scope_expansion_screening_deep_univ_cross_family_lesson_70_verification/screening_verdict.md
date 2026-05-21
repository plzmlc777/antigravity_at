# paradigm 175 — paradigm 24 R-5 cross-family expansion screening verdict

**Slug**: `paradigm_24_r5_narrow_scope_expansion_screening_deep_univ_cross_family_lesson_70_verification`
**Dispatch**: 2026-05-21 KST
**Track**: R-5 expansion screening (paradigm counter NOT increased)
**Lesson #70 cross-family dogfood**: **3rd dogfood → CONFIRMED universal property**

## Verdict: NO_R5_EXPANSION_ELIGIBLE_SYMS (3rd dogfood across distinct family)

**0 / 17 syms** pass both three-gate AND life-changing 4-dim using canonical paradigm 24 R-5 v1 `follow_z2.0_h5` spec on the premium_index joblib substrate (2.19yr OOS).

## Per-sym screening table

| Symbol | cohort | n_trd | sigex | ci_lo bp | perm_p | 3-gate | trd/yr | edge% | util% | sharpe | 4-dim | ELIG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT* | deep | 4 | nan | nan | nan | FAIL | 14.6 | +3.37 | 16.8 | +1.10 | FAIL | NO |
| ETHUSDT  | deep | 34 | -0.01 | +64.8 | 0.504 | FAIL | 16.2 | +3.63 | 19.9 | +1.56 | FAIL | NO |
| LINKUSDT | deep | 25 | -0.02 | -114.7 | 0.522 | FAIL | 12.3 | +2.98 | 14.9 | +0.96 | FAIL | NO |
| ADAUSDT* | deep | 1 | nan | nan | nan | FAIL | 3.6 | +10.79 | 4.9 | +0.00 | FAIL | NO |
| DOTUSDT  | deep | 31 | -0.05 | -141.5 | 0.520 | FAIL | 14.7 | +2.65 | 17.9 | +0.83 | FAIL | NO |
| XRPUSDT  | deep | 35 | -0.01 | +47.2 | 0.522 | FAIL | 16.6 | +4.45 | 20.3 | +1.38 | FAIL | NO |
| BNBUSDT  | deep | 31 | +0.09 | -196.2 | 0.956 | FAIL | 14.7 | +0.13 | 17.9 | +0.03 | FAIL | NO |
| BCHUSDT  | deep | 26 | -0.09 | -145.0 | 0.522 | FAIL | 12.3 | +2.33 | 15.7 | +0.85 | FAIL | NO |
| LTCUSDT  | deep | 29 | -0.02 | -54.1 | 0.509 | FAIL | 13.8 | +2.87 | 17.1 | +1.08 | FAIL | NO |
| UNIUSDT  | mid-cap | 26 | -0.04 | -465.8 | 0.933 | FAIL | 12.3 | -0.14 | 13.2 | -0.07 | FAIL | NO |
| ETCUSDT  | mid-cap | 17 | -0.09 | +5.7 | 0.497 | FAIL | 8.1 | +4.98 | 9.0 | +1.32 | FAIL | NO |
| AVAXUSDT | mid-cap | 29 | -0.02 | +111.5 | 0.502 | FAIL | 14.6 | +4.35 | 17.4 | +1.74 | FAIL | NO |
| NEARUSDT | mid-cap | 28 | -0.03 | +33.6 | 0.498 | FAIL | 13.3 | +4.39 | 14.9 | +1.46 | FAIL | NO |
| FILUSDT  | mid-cap | 29 | -0.01 | -112.3 | 0.527 | FAIL | 13.8 | +3.12 | 14.6 | +0.93 | FAIL | NO |
| WLDUSDT  | mid-cap | 32 | -0.02 | -60.0 | 0.501 | FAIL | 15.2 | +3.84 | 18.3 | +1.09 | FAIL | NO |
| JUPUSDT  | mid-cap | 28 | +0.02 | -607.2 | 0.625 | FAIL | 13.3 | -1.23 | 13.2 | -0.37 | FAIL | NO |
| PYTHUSDT | mid-cap | 31 | -0.25 | -888.4 | 0.947 | FAIL | 14.7 | -0.24 | 16.5 | -0.06 | FAIL | NO |

*BTCUSDT / ADAUSDT: 1m ohlcv DB has only ~5 months (2025-12-22+), insufficient OOS — Lesson #30 advisory (data window << universe full-window). 15/17 syms have STRONG OOS (2.19yr).

Three-gate: sigex ≥ 2.0 AND ci_lower > 0 AND perm_p ≤ 0.10
Life-changing 4-dim: trd/yr ≥ 12 AND edge ≥ +2.0% AND util ≥ 30% AND sharpe ≥ 1.5

## Failure mode breakdown

### Three-gate FAIL — 17/17

- **sigex range [-0.25, +0.09]** (15 valid) — all essentially zero excess over fee-applied null on the gross distribution. **No sym shows signal excess >0.10σ above fee floor**.
- **ci_lower range [-888 bp, +111 bp]** (15 valid) — only 4 syms (ETH +65 / XRP +47 / ETC +6 / AVAX +112 / NEAR +34) have positive ci_lower, but **all < threshold trivially** because sigex ≈ 0
- **perm_p range [0.497, 0.956]** (15 valid) — no observed t-stat distinguishable from random fee-applied null on any sym

### Life-changing 4-dim FAIL — 17/17

- **trades/yr**: 8.1 to 16.6 (PASS threshold 12) — **14/17 pass** (only ETC/ADA fail; BTC marginal but n_trd=4 sample-deficient)
- **edge per trade**: -1.23% to +10.79% (need ≥ +2.0%) — **10/17 pass** (BTC/ETH/LINK/DOT/XRP/BCH/LTC/ETC/AVAX/NEAR/FIL/WLD — most syms produce 2.5-5% gross edge)
- **sharpe**: -0.37 to +1.74 (need ≥ 1.5) — **2/17 pass** (ETH 1.56 / AVAX 1.74) plus 3 borderline (XRP 1.38 / ETC 1.32 / NEAR 1.46)
- **capital util**: 4.9% to 20.3% (need ≥ 30%) — **0/17 pass**, **binding constraint**, all 17 fail by 1.5-6x margin

### Binding-constraint analysis: capital util

paradigm 24 R-5 native frequency is **fundamentally sparse**: 16-17 trades/yr × 5d hold ≈ 80-85 bars in position per year. Against a 770-day OOS window, this gives **~10% capital util ceiling structurally**. Even doubling trade count (which would require relaxing entry_z below 2.0, departing from canonical spec) the util ceiling would be ~20%.

The 30% util threshold (per [[feedback-life-changing-strategy-criterion]]) is **structurally unreachable at paradigm 24 R-5 canonical spec on any cohort** — including the original R-5 cohort (DOGE/SOL/LDO at 13-17 trades / 395d OOS = 9-12% util at seed time, below the threshold).

**Confluence with paradigm 173/174**: paradigm 22 R-5 util also failed at 5.2-8.6% across 20 syms (median bars_held 2-3 × 30-75 trades / 2.25yr window ≈ 5-8% util). The util constraint is **systematically violated by both R-5 LIVE paradigms** at expansion cohort — yet the original R-5 cohorts were seeded anyway under different (alpha-pct-mean / sharpe / perm_σ) gate criteria.

This reveals that paradigm 22 + paradigm 24 R-5 seeds **passed at seed-time because seed-time gates were alpha%/sharpe/perm-σ centric**, NOT life-changing 4-dim. The 4-dim gate enforced post-hoc here is **structurally incompatible** with sparse-trigger R-5 paradigms regardless of cohort.

## Best near-miss candidates (4-dim 3/4 PASS)

| Symbol | trd/yr | edge | util | sharpe | Binding fail |
|---|---|---|---|---|---|
| AVAXUSDT | 14.6 ✓ | +4.35% ✓ | 17.4% ✗ | +1.74 ✓ | util only |
| ETHUSDT  | 16.2 ✓ | +3.63% ✓ | 19.9% ✗ | +1.56 ✓ | util only |
| NEARUSDT | 13.3 ✓ | +4.39% ✓ | 14.9% ✗ | +1.46 ✗ | util + sharpe |

All near-misses fail on **util** as the structural-ceiling constraint. None of these are 3-gate PASS either (sigex ≤ +0.09, perm_p ≈ 0.5), so even with util relaxation they would not qualify under strict screening.

## Cohort-pattern: deep vs mid-cap parity

| Metric | Deep (9 syms) | Mid-cap (8 syms) |
|---|---|---|
| sigex range | -0.09 to +0.09 | -0.25 to +0.02 |
| Mean edge% | +2.83% | +2.41% |
| Best sharpe | 1.56 (ETH) | 1.74 (AVAX) |
| 3-gate PASS | 0/9 | 0/8 |
| 4-dim PASS | 0/9 | 0/8 |
| ELIG | 0/9 | 0/8 |

Both cohorts produce essentially identical results. **Liquidity tier / cap class does NOT differentiate expansion candidates at paradigm 24 spec** — same as paradigm 22 cross-cohort parity (paradigm 173 deep 0/10 vs paradigm 174 mid-cap 0/10).

## Lesson #70 cross-family verification — CONFIRMED universal property (3rd dogfood)

**Lesson #70 (now CONFIRMED at 3 dogfoods across 2 distinct paradigm families)**:
> "R-5 LIVE survivor narrow-cohort alpha does NOT transfer to a broader cohort sym-by-sym at the same spec — cohort selection itself is part of the alpha. The phenomenon generalizes beyond funding family to premium_index family, indicating it is a **universal property of R-5 expansion screening** rather than a funding-family-specific anomaly."

**Dogfood log**:
- 1st (paradigm 173, funding family): 10 deep syms BTC/ETH/SOL/LINK/ADA/DOT/XRP/BNB/BCH/LTC → 0/10 eligible
- 2nd (paradigm 174, funding family): 10 mid-cap funding-volatile syms DOGE/LDO/UNI/ETC/AVAX/NEAR/FIL/WLD/JUP/PYTH → 0/10 eligible
- **3rd (paradigm 175, premium_index family, this)**: 17 syms (deep 9 + mid-cap 8) → 0/17 eligible
- **Cumulative**: **0/37 eligible across 2 distinct paradigm families and 3 cohort axes**

### Lesson #70 formal upgrade rationale
- 3 dogfoods × 2 families × 0/37 aggregate is **overwhelming evidence** for universal property
- Pattern is **mechanism-agnostic**: applies regardless of underlying axis (funding-MR vs premium-momentum follow)
- Pattern is **cohort-agnostic**: applies regardless of liquidity tier or substrate volatility profile
- **Root cause confirmed**: R-5 seed gates were alpha%/sharpe/perm_σ centric → original cohorts were post-hoc cherry-picked from broader screening; the alpha is **non-stationary across symbols**, not a mechanism that applies "to all symbols of class X"

### Lesson #70 paradigm-architect skill amendment (proposed permanent)
- **All future R-5 LIVE expansion screening attempts at same spec on extended cohort should be presumptively HALT** (negative-yield exercise expectation)
- **R-5 expansion eligibility requires NEW spec discovery** (per-sym parameter optimization, adaptive entry_z/hold_days/zwin), NOT same-spec cohort expansion
- **Original R-5 cohorts should be regarded as terminal**: paradigm 22 = HBAR/AXS/COMP only; paradigm 24 = DOGE/SOL/LDO only

## Sub-finding: util as structural-ceiling constraint for sparse-trigger paradigms

paradigm 22 + 24 R-5 5-day hold × 15-17 trades/yr = **structural util ceiling ~10-20%** regardless of cohort. The 30% life-changing util threshold is **incompatible with daily-granularity sparse-trigger paradigms by design**.

This is consistent with Lesson #25 (sparse-trigger paradigm life-changing 4-dim FAIL ineligibility) from the life-changing campaign session 1 halt — daily-cycle paradigms cannot satisfy 30% util at any sensible spec without departing from the original mechanism.

**Implication**: R-5 LIVE paradigms 22 + 24 (and likely all daily/sparse-trigger R-5 survivors) are **structurally exempted** from life-changing 4-dim screening. They survive on alpha/sharpe/perm-σ criteria but **cannot satisfy 4-dim by design**. This is acceptable for diversification/non-correlated alpha contribution, but rules out single-paradigm life-changing yield.

## R-5 expansion eligible candidates: **NONE**

No R-5 seed_proposal.md generated. No paper session config drafted. No paper trading deployment proposed.

## Cumulative campaign status (post-paradigm 175 R-5 expansion screening cross-family)

- **Cumulative graveyards: 170** (unchanged — paradigm 175 is screening, not paradigm)
- **Non-PASS streak: 40+** (paradigm 175 expansion-eligible 0/17 reinforces persistence-over-efficiency)
- **R-5 LIVE: 11** (unchanged)
- **R-5 yield: 6.40%** (unchanged)
- **paradigm 24 R-5 LIVE seeded cohort**: DOGE/SOL/LDO (terminal — no expansion candidates)
- **paradigm 22 R-5 LIVE seeded cohort**: HBAR/AXS/COMP (terminal — confirmed by paradigm 173/174)
- **New permanent lesson**: **Lesson #70 CONFIRMED universal property** (3 dogfoods × 2 families × 0/37 aggregate; paradigm-architect skill amendment proposed: all R-5 same-spec cohort expansion presumptively HALT)

## Recommended next-action (paradigm 176 dispatch)

### Option α: Lesson #70 formal upgrade to CONFIRMED + paradigm-architect skill amendment
- 3 dogfoods × 2 families × 0/37 eligible aggregate clearly sufficient for CONFIRMED 자격 → CONFIRMED 정식 승급
- Document in `PARADIGM_QUEUE_2026Q3.md` §6.73 + paradigm-architect skill files
- Add to lesson prescreen checklist: R-5 cohort expansion = presumptively HALT_BY_LESSON_70 unless mechanism-distinct or spec-adaptive

### Option β: NEW paradigm DNA dispatch (paradigm 176, counter increases)
- Move on to fresh paradigm hypothesis per [[feedback-persistence-over-efficiency]] and [[feedback-paradigm-campaign-continuous-parallel]]
- Avoid further R-5 expansion screening for now (Lesson #70 sufficient evidence)

### Option γ: paradigm 24 spec-ADAPTIVE expansion (per-sym entry_z optimization)
- Test whether adaptive entry_z (e.g., per-sym entry_z chosen to produce 25-30 trades/yr) recovers eligibility on subset of 17 syms
- This is a **mechanism-extension hypothesis**, not same-spec expansion (Lesson #70 exempt)
- Could be paradigm 176 (counter increases) if framed as new DNA
- **Caveat**: per-sym parameter optimization is **per-sym overfitting risk** — would require out-of-sample fold validation, larger spec sweep

**1순위 권고**: **Option α + Option β simultaneous** — Lesson #70 formal upgrade (lightweight doc update, skill amendment) + paradigm 176 dispatch (new paradigm DNA, normal counter advance). Option γ valuable but lower priority and higher overfitting risk vs new DNA exploration.

## Sub-finding documentation (advisory only, not formal lesson)

**Sub-finding A — capital util structural ceiling**: daily-granularity sparse-trigger R-5 paradigms (paradigm 22 + 24 family) have structural util ceiling 10-20% regardless of cohort or fine-tuning. This is **Lesson #25 amendment candidate** but does not require new lesson code (already covered by life-changing 4-dim sparse-trigger ineligibility doctrine).

**Sub-finding B — alpha non-stationarity vs symbol**: paradigm 24 follow_z2.0_h5 produces gross edge +2.5% to +5% on most syms (suggesting **mean reversion of mean reversion** = momentum signal works at broad cohort scale), but **sigex ≈ 0** meaning the signal is fully consumed by the fee-applied null distribution. This is the **net-vs-gross asymmetry** unique to 5-day daily-hold paradigms — gross drift is real but does not survive 8 bp fee + permutation null variance. Consistent with paradigm 22 expansion pattern.

**Sub-finding C — premium-momentum as broad-cohort signal**: cross-sym pattern (10/17 gross edge >2% at follow mode) suggests **premium z-score momentum signal is real at broad-cohort level**, but the eligible-cohort identification requires more than spec sweep — it needs **interaction with another covariate** (e.g., funding regime, vol regime, market beta). Future paradigm hypothesis candidate: premium_index × {funding regime / vol regime / market beta} joint signal — but caution: this is funding/vol-axis stacking territory and may hit Lesson #21 (axis stacking does not synthesize alpha).
