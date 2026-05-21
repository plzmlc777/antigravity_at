# paradigm 22 R-5 expansion screening — 10 mid-cap funding-volatile syms verdict

**Slug**: `paradigm_22_r5_narrow_scope_expansion_screening_10_midcap_funding_volatile_syms`
**Dispatch**: 2026-05-21 KST
**Track**: R-5 expansion screening (paradigm counter NOT increased)
**Lesson #70 candidate**: **2nd dogfood — CONFIRMED 자격**

## Verdict: NO_R5_EXPANSION_ELIGIBLE_SYMS (2nd cohort)

**0 / 10 mid-cap funding-volatile syms** pass both three-gate AND life-changing 4-dim using canonical paradigm 22 R-5 v4 spec on the freshly-backfilled 2.25yr funding asset.

## Per-sym screening table

| Symbol | cycle | n_trd | sigex | ci_lo bp | perm_p | 3-gate | trd/yr | edge% | util% | sharpe | 4-dim | ELIG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DOGEUSDT | 8h | 46  | +0.00 | -126.0 | 0.968 | FAIL | 20.7 | +0.06 | 5.2 | -0.03 | FAIL | NO |
| LDOUSDT  | 8h | 71  | +0.02 | -38.0  | 0.516 | FAIL | 31.9 | +0.60 | 7.5 | +0.75 | FAIL | NO |
| UNIUSDT  | 8h | 75  | +0.07 | -103.0 | 0.676 | FAIL | 33.7 | -0.10 | 8.0 | -0.27 | FAIL | NO |
| ETCUSDT  | 8h | 66  | +0.04 | -66.9  | 0.561 | FAIL | 29.7 | +0.51 | 7.0 | +0.50 | FAIL | NO |
| AVAXUSDT | 8h | 58  | +0.02 | -95.2  | 0.686 | FAIL | 26.1 | +0.36 | 7.1 | +0.29 | FAIL | NO |
| NEARUSDT | 8h | 75  | +0.13 | -141.2 | 0.785 | FAIL | 33.7 | -0.09 | 7.5 | -0.17 | FAIL | NO |
| FILUSDT  | 8h | 75  | +0.38 | -133.0 | 0.780 | FAIL | 33.7 | +0.43 | 8.5 | +0.21 | FAIL | NO |
| WLDUSDT  | 8h | 74  | +0.00 | -227.6 | 0.485 | FAIL | 33.3 | -1.07 | 6.8 | -1.31 | FAIL | NO |
| JUPUSDT  | 4h | 137 | +0.20 | -104.4 | 0.610 | FAIL | 61.2 | -0.18 | 8.6 | -0.38 | FAIL | NO |
| PYTHUSDT | 4h | 140 | +0.02 | -141.0 | 0.495 | FAIL | 62.5 | -0.73 | 7.9 | -1.72 | FAIL | NO |

Three-gate: sigex >= 2.0 AND ci_lower > 0 AND perm_p <= 0.10
Life-changing 4-dim: trd/yr >= 12 AND edge >= +2.0% AND util >= 30% AND sharpe >= 1.5

## Failure mode breakdown

### Three-gate FAIL — 10/10
- sigex range [+0.00, +0.38] → all essentially zero excess over fee-applied null on the gross distribution
- ci_lower range [-227.6 bp, -38.0 bp] → 95% CI on net-return mean **strictly excludes positive territory** for every sym (worst: WLD -227 bp; best: LDO -38 bp)
- perm_p range [0.485, 0.968] → no observed t-stat distinguishable from random fee-applied null

### Life-changing 4-dim FAIL — 10/10
- **edge/trade**: -1.07% to +0.60% (need ≥ +2.0%) — **all 10 fail by 3-10x margin**, binding constraint
- **capital util**: 5.2% to 8.6% (need ≥ 30%) — **all 10 fail by ~4-6x margin** (median bars_held = 2-3, position duration short vs 2466- or 4932-period window)
- **trades/year**: 20.7 to 62.5 (PASS threshold 12) — 10/10 pass on this axis (4h-cycle JUP/PYTH naturally 2x)
- **sharpe**: -1.72 to +0.75 (need ≥ 1.5) — 10/10 fail

### Best mid-cap sym (LDOUSDT):
- alpha indicative-positive (gross_mean +0.68%, net +0.52% — but ci_lo still -38 bp, perm_p 0.516)
- 71 trades, sharpe 0.75, edge 0.60% net → mechanism marginally better than deep majors, but still **3.3x below life-changing edge threshold** and **7.5% util vs 30% needed**
- NO eligibility upgrade possible at v4 spec on LDOUSDT alone

## Exit-reason composition (mechanism integrity check)

Exit reasons split (mean / sl / time) — most exits via "mean" (z drops back below 0.5) = intended carry-harvest mechanism:
- DOGEUSDT: 36 mean / 8 sl / 2 time (78.3% mean)
- LDOUSDT: 56 mean / 11 sl / 4 time (78.9% mean)
- ETCUSDT: 49 mean / 11 sl / 6 time (74.2% mean)
- NEARUSDT: 60 mean / 12 sl / 3 time (80.0% mean)
- JUPUSDT: 109 mean / 21 sl / 7 time (79.6% mean)

→ Mechanism **IS firing as designed**; the gross edge per trade is simply too small on mid-cap funding-volatile syms as well.

## Lesson #70 candidate — 2nd dogfood CONFIRMED 자격

**Lesson #70 statement (CONFIRMED 자격, 2 cohort dogfoods)**:
> "R-5 LIVE survivor narrow-cohort alpha does NOT transfer to a broader cohort sym-by-sym at the same spec — cohort selection itself is part of the alpha. The original paradigm 22 R-5 cohort (HBAR/AXS/COMP) was discovered via post-hoc selection from a wider initial screening, NOT via mechanism-universal applicability. Expansion screening at the same spec on either deep-liquid (paradigm 173) or mid-cap funding-volatile (paradigm 174) cohort produces 0 eligible candidates."

**Dogfood log**:
- 1st (paradigm 173): 10 deep syms BTC/ETH/SOL/LINK/ADA/DOT/XRP/BNB/BCH/LTC → 0/10 eligible
- 2nd (paradigm 174, this): 10 mid-cap funding-volatile syms DOGE/LDO/UNI/ETC/AVAX/NEAR/FIL/WLD/JUP/PYTH → 0/10 eligible
- **Outcome**: cohort axis (liquidity tier, funding volatility profile) is NOT the distinguishing factor — paradigm 22 R-5 alpha is **specific to the HBAR/AXS/COMP cohort by post-hoc cherry-pick**, NOT a property of "mid-cap funding-volatile syms" as a class

### Lesson #70 corollary
- Narrow-cohort R-5 LIVE survivor expansion is a **negative-yield exercise at same spec** on any extended cohort.
- Future paradigm cohort expansion attempts at fixed spec should be **deprioritized** vs new paradigm DNA discovery or spec-adaptive expansion (per-sym parameter optimization).
- The pattern is consistent across both paradigm 22 (funding family Tier 4 retire exception) → suggests funding family Tier 4 retire decision remains **decisively correct**, with paradigm 22 being a true single-cohort outlier rather than mechanism head of a broader subfamily.

## Comparison vs paradigm 173 (deep cohort)

| Metric | paradigm 173 deep | paradigm 174 mid-cap | Mid-cap edge? |
|---|---|---|---|
| Mean edge%/trade range | -0.63 to +0.38 | -1.07 to +0.60 | similar (slightly wider on both ends) |
| Best sigex | +0.10 (SOL) | +0.38 (FIL) | +0.28 better but still ≪ 2.0 |
| Best ci_lower bp | -37.4 (BTC) | -38.0 (LDO) | tie |
| n_trades range | 41-75 | 46-140 | mid-cap higher (volatile funding ↑ events; 4h cycle ↑) |
| 4h-cycle outliers | none | JUP/PYTH (4-hr cycle) | distinct sub-tier |
| Eligible count | 0/10 | 0/10 | identical |

**Pattern**: more volatile funding ↑ trade count, but **edge/trade does not improve correspondingly** — fee floor + reversion noise dominates regardless of base funding distribution.

## R-5 expansion eligible candidates: **NONE**

No R-5 seed_proposal.md generated. No paper session config drafted. No paper trading deployment proposed.

## Cumulative campaign status (post-paradigm 174 R-5 expansion screening)

- Cumulative graveyards: **170** (unchanged — paradigm 174 is screening, not paradigm)
- Non-PASS streak: **40+** (paradigm 174 expansion-eligible 0/10 reinforces persistence-over-efficiency)
- R-5 LIVE: **11** (unchanged)
- R-5 yield: **6.40%** (unchanged)
- New permanent asset: 10 mid-cap funding-volatile syms × 2.25yr funding DB (DOGE/LDO/UNI/ETC/AVAX/NEAR/FIL/WLD/JUP/PYTH; 4h-cycle distinct JUP/PYTH)
- New permanent lesson: **Lesson #70 CONFIRMED 자격** — narrow-cohort R-5 alpha non-transferable to ANY broader cohort at same spec (2 dogfoods, 2 cohorts, 0/20 eligible aggregate)

## Recommended next-action (paradigm 175 dispatch)

### Option α: Lesson #70 formal upgrade to CONFIRMED (no new dogfood needed)
- 2 dogfoods (paradigm 173 + paradigm 174) on 2 distinct cohort axes (liquidity tier vs funding volatility)
- 0/20 aggregate eligible
- Material clearly sufficient for **CONFIRMED 자격 → CONFIRMED 정식 승급** without further dogfood
- Document in PARADIGM_QUEUE_2026Q3.md §6.72 + paradigm_index/agent skills

### Option β: paradigm 24 (premium_index z-score) deep-univ expansion screening — alternative dogfood track
- Test whether Lesson #70 pattern holds for a NON-funding R-5 LIVE survivor (paradigm 24 = premium index z-score, DOGE/SOL/LDO seeded)
- If confirmed → Lesson #70 generalizes beyond funding family
- If refuted → Lesson #70 is funding-specific (narrower scope)

### Option γ: continue normal paradigm dispatch (new paradigm DNA, counter increases)
- Move on to paradigm 175 (new paradigm hypothesis, full R-1 protocol)
- Per [[feedback-persistence-over-efficiency]] and [[feedback-paradigm-campaign-continuous-parallel]]

**1순위 권고**: **Option α + γ simultaneous** — Lesson #70 formal upgrade (lightweight doc update) + paradigm 175 dispatch (new DNA, normal counter advance). Option β is valuable but lower priority vs new paradigm exploration since Lesson #70 already CONFIRMED 자격 at strong evidence.
