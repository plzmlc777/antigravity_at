# paradigm 22 R-5 expansion screening — 10 deep syms verdict

**Slug**: `paradigm_22_r5_narrow_scope_expansion_screening_10_deep_syms`
**Dispatch**: 2026-05-21 KST
**Track**: R-5 expansion screening (paradigm counter NOT increased)

## Verdict: NO_R5_EXPANSION_ELIGIBLE_SYMS

0 / 10 deep syms pass both three-gate AND life-changing 4-dim using canonical paradigm 22 R-5 v4 spec on the paradigm 170 funding DB asset (2.25yr OOS).

## Per-sym screening table

| Symbol | n_trd | sigex | ci_lo bp | perm_p | 3-gate | trd/yr | edge% | util% | sharpe | 4-dim | ELIG |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT  | 41 | +0.05 | -37.4   | 0.542 | FAIL | 18.4 | +0.38 | 5.5 | +0.56 | FAIL | NO |
| ETHUSDT  | 48 | +0.04 | -123.7  | 0.899 | FAIL | 21.6 | +0.16 | 6.2 | +0.08 | FAIL | NO |
| SOLUSDT  | 45 | +0.10 | -117.3  | 0.883 | FAIL | 20.2 | +0.00 | 5.7 | -0.09 | FAIL | NO |
| LINKUSDT | 73 | -0.01 | -81.2   | 0.886 | FAIL | 32.8 | +0.14 | 6.7 | +0.08 | FAIL | NO |
| ADAUSDT  | 64 | +0.05 | -106.5  | 0.724 | FAIL | 28.8 | +0.30 | 6.8 | +0.22 | FAIL | NO |
| DOTUSDT  | 68 | +0.04 | -151.0  | 0.715 | FAIL | 30.6 | -0.15 | 7.4 | -0.25 | FAIL | NO |
| XRPUSDT  | 46 | -0.00 | -168.3  | 0.509 | FAIL | 20.7 | -0.63 | 4.5 | -0.95 | FAIL | NO |
| BNBUSDT  | 75 | -0.01 | -84.2   | 0.508 | FAIL | 33.7 | -0.22 | 8.4 | -0.74 | FAIL | NO |
| BCHUSDT  | 51 | +0.04 | -155.4  | 0.997 | FAIL | 22.9 | +0.07 | 6.5 | -0.00 | FAIL | NO |
| LTCUSDT  | 54 | +0.01 | -120.7  | 0.756 | FAIL | 24.3 | -0.08 | 6.0 | -0.20 | FAIL | NO |

Three-gate thresholds: sigex ≥ 2.0 AND ci_lower > 0 AND perm_p ≤ 0.10
Life-changing 4-dim: trd/yr ≥ 12 AND edge ≥ +2.0% AND util ≥ 30% AND sharpe ≥ 1.5

## Failure mode breakdown

### Three-gate FAIL — all 10
- All sigex ∈ [-0.01, +0.10] → effectively zero excess over fee-applied null (paradigm 22 R-5 v4 spec produces edge that does NOT survive 8 bp round-trip fee on 10 deep syms)
- All ci_lower < 0 (deep negative -37 bp to -168 bp) → 95% CI on net-return mean **strictly excludes positive territory**
- All perm_p ∈ [0.51, 0.997] → observed t-stat indistinguishable from random selection of same gross distribution with fee applied

### Life-changing 4-dim FAIL — all 10
- **edge per trade**: -0.63% to +0.38% (need ≥ +2.0%) — **all 10 fail by >5x margin**, this is the binding constraint
- **capital util**: 4.5% to 8.4% (need ≥ 30%) — **all 10 fail by ~4-7x margin** (median bars_held = 2-3 / max=7, so position duration short relative to 2466-period window)
- **trades/year**: 18-34 (PASS threshold 12) — 10/10 pass on this axis
- **sharpe**: -0.95 to +0.56 (need ≥ 1.5) — 10/10 fail

## Sub-class pattern in screening data

**Positive median bars_held + dominant `mean` exit reason**: most exits are `mean` (z drops back below 0.5) — this is the **intended carry-harvest mechanism**. Exit reasons split:
- BTCUSDT: 33 mean / 6 time / 2 sl (80.5% mean exit)
- LINKUSDT: 56 mean / 15 sl / 2 time (76.7% mean exit)
- BNBUSDT: 65 mean / 6 sl / 4 time (86.7% mean exit)

→ Mechanism IS firing as designed; the gross edge per trade is simply too small on these 10 deep syms.

## Why does paradigm 22 R-5 work on HBAR/AXS/COMP but not on deep syms?

This screening result confirms paradigm 22's **alpha is highly cohort-specific**:
- HBAR/AXS/COMP R-5 v4 spec: alpha 108-149%, sharpe 1.48-1.87, n_trades 19-38, OOS 355d
- 10 deep syms (BTC/ETH/SOL/LINK/ADA/DOT/XRP/BNB/BCH/LTC): alpha -161 to +69%, sharpe -0.95 to +0.56, edge 0.0-0.4% / trade
- **Pattern**: paradigm 22 alpha exists in **mid/small-cap funding-volatile alts** (HBAR/AXS/COMP funding regimes spike high & revert), but **major caps have funding rates that are too well-arbitraged** (efficient cross-exchange flow, deep liquidity) → funding z extremes lack the same reversion premium

This is consistent with the funding family Tier 4 retire 11-graveyard pattern: funding-axis paradigms struggle on liquid majors (paradigm 73 BTC/ETH-heavy / paradigm 96 broad univ / paradigm 99 broad univ) but the narrow paradigm 22 R-5 cohort exception worked because mid-cap funding crowdedness inefficiency is real (smaller capital, less arbitraged).

## Lesson candidate (NOT formal — single-instance dogfood, no prior counterexample)

**Lesson #70 candidate** (subject to second dogfood confirmation): *"R-5 LIVE survivor narrow-cohort alpha does NOT transfer to deep-liquid universe sym-by-sym at the same spec — cohort selection itself is part of the alpha. Expansion screening should test mid-cap funding-volatile cohorts (e.g., DOGE/LDO/UNI/ETC) rather than deep majors."*

This is a candidate, not formal — needs second R-5 expansion screening attempt on a different paradigm (e.g., paradigm 24 premium_index DOGE/SOL/LDO) on a deep universe to confirm pattern.

## R-5 expansion eligible candidates: **NONE**

No R-5 seed_proposal.md generated. No paper session config drafted. No paper trading deployment proposed.

## Recommended next-action

### Option α (preferred): mid-cap funding-volatile cohort R-5 expansion screening
Repeat paradigm 22 R-5 v4 screening on a **mid-cap funding-volatile universe**:
- Suggested screening cohort: DOGE/LDO/UNI/ETC/AVAX/NEAR/FIL/WLD/JUP/PYTH (i.e., funding_dispersion's 14-sym default universe minus HBAR/AXS/COMP/SOL already covered/large)
- Substrate requirement: backfill `binance_funding_rate` for these syms 2.25yr (paradigm 170 backfill pattern — re-use script)
- Expected outcome: discover 2-5 syms with HBAR/AXS/COMP-like funding crowdedness inefficiency
- **paradigm 174 dispatch candidate**

### Option β: paradigm 24 (premium_index z-score) deep-univ expansion screening
- paradigm 24 R-5 LIVE survivors: DOGE/SOL/LDO (5/5 strict cutoff, mode = follow momentum)
- Apply same screening pattern: paradigm 24 v? spec → 10 deep syms (BTC/ETH/SOL etc.)
- Tests whether the "narrow-cohort R-5 alpha doesn't transfer" pattern is funding-specific or general
- If confirmed → Lesson #70 candidate becomes confirmed (CONFIRMED 자격)

### Option γ: continue normal paradigm dispatch
- Move on to new paradigm hypothesis (paradigm 174 = new paradigm DNA, counter increases)

**1순위 권고**: Option α (mid-cap cohort screening), to maximize chance of discovering paradigm 22 R-5 expansion candidates while substrate is fresh and infrastructure ready.

## Cumulative campaign status (post-paradigm 173 R-5 expansion screening)
- Cumulative graveyards: **170** (unchanged — paradigm 173 is screening, not paradigm)
- Non-PASS streak: **40+** (paradigm 173 expansion-eligible 0/10 reinforces persistence-over-efficiency [[feedback_persistence_over_efficiency]])
- R-5 LIVE: **11** (unchanged)
- R-5 yield: **6.40%** (unchanged)
- New artifact: paradigm 173 R-5 expansion screening (paradigm 22 funding_carry v4 NO_EXPANSION_ELIGIBLE)
