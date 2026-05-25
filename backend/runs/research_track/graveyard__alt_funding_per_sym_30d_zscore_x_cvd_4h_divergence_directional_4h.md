# Graveyard — paradigm 139 alt_funding_per_sym_30d_zscore_x_cvd_4h_divergence_directional_4h

**Phase**: R-0 prescreen HALT (R-1 never dispatched)
**Verdict**: `R0_HALT_LESSON_40_PERSYM_ZSCORE_INHERITS_ASYMMETRY`
**Date (KST)**: 2026-05-21 12:05
**Cumulative graveyard count**: 139 (was 138 paradigm raw funding × CVD raw bp R-0 halt)
**Streak**: 11-streak non-PASS (129-139)

## Hypothesis (user-proposed, paradigm 138 reformulation via Lesson #40 path 1)

paradigm 138 R-0 halt @ 11:56 KST (raw ±50bp funding infeasible) → user proposed reformulation
using paradigm 22 R-5 SEED per-sym 30d z-score approach × CVD axis confluence.

- Axis 1 (funding per-sym 30d z-score): z ≤ -2.0 (extreme LONG-crowded normalized)
- Axis 2 (CVD ratio 4h): cvd ≤ -0.1 (sustained taker SELL)
- Joint trigger A: funding_z ≤ -2.0 AND CVD ≤ -0.1 → SHORT 4h (smart money exit)
- 4-quadrant SNT: A_focus/A_mirror (SHORT/LONG), B_focus/B_mirror (funding_z ≥ +2.0 × CVD ≥ +0.1 × LONG/SHORT)

## R-0 STEP 1 — Lesson #40 structural threshold attainability — FAIL

Per-sym 30d z-score distribution (10-sym cohort, 90-obs rolling at 8h funding cadence):

| sym | n | p1 | p5 | p50 | p95 | p99 | min | max | z≤-2 | z≥+2 |
|---|---|---|---|---|---|---|---|---|---|---|
| HBARUSDT | 1054 | -3.31 | -2.08 | 0.27 | 1.26 | 1.45 | -5.28 | 1.78 | **5.31%** | 0.00% |
| AXSUSDT  | 1549 | -4.29 | -2.02 | 0.35 | 1.29 | 1.67 | -9.25 | 2.00 | **5.04%** | 0.06% |
| COMPUSDT | 1054 | -4.79 | -1.89 | 0.28 | 0.75 | 0.96 | -9.21 | 1.44 | **4.36%** | 0.00% |
| AVAXUSDT | 1036 | -3.47 | -2.07 | 0.36 | 1.17 | 1.51 | -5.19 | 1.93 | **5.41%** | 0.00% |
| SOLUSDT  | 1058 | -3.29 | -1.92 | 0.19 | 1.27 | 1.47 | -9.23 | 3.12 | **4.44%** | 0.09% |
| DOGEUSDT | 1058 | -2.72 | -1.91 | 0.15 | 1.29 | 1.61 | -4.51 | 6.45 | **4.54%** | 0.09% |
| ETHUSDT  | 1036 | -3.07 | -1.91 | 0.01 | 1.41 | 1.73 | -4.84 | 2.19 | **4.05%** | 0.19% |
| LINKUSDT | 1036 | -3.17 | -2.13 | 0.34 | 1.06 | 1.26 | -5.05 | 1.41 | **5.60%** | 0.00% |
| LDOUSDT  | 1054 | -3.57 | -2.03 | 0.29 | 1.24 | 1.54 | -5.44 | 1.71 | **5.50%** | 0.00% |
| ETCUSDT  | 1054 | -3.48 | -2.09 | 0.35 | 1.07 | 1.31 | -7.73 | 1.52 | **5.60%** | 0.00% |

**A-side (z ≤ -2.0)**: 10/10 syms reach at rate 4.05-5.60% (healthy, density ≥ 1.5% threshold)
**B-side (z ≥ +2.0)**: **0/10 syms** reach at rate ≥ 1.5%
- 6/10 syms have ZERO observations z ≥ +2.0 (HBAR/COMP/AVAX/LINK/LDO/ETC)
- 4/10 syms have 1-2 observations only (AXS 0.06%, SOL 0.09%, DOGE 0.09%, ETH 0.19%)
- p95 across all 10 syms: 0.75-1.41 (never reaches +2.0)
- p99 across all 10 syms: 0.96-1.73 (never reaches +2.0)

**Root cause**: Binance funding rate hard-caps at +0.01% (+1 bp) on regular tier. Leveraged
liquidation episodes (AXS observed -200 bp, COMP -147 bp, SOL -30 bp) drive the negative
tail to extreme values. The rolling 30d std is dominated by the **negative tail**, so the
z-score scaling makes z ≥ +2.0 structurally rare — even when the raw funding hits its
positive cap of +1 bp.

**Verdict**: Symmetric ±2.0 z-score trigger structurally infeasible. **Per-sym z-score
normalization does NOT rescue symmetric threshold feasibility** when the underlying
scalar is asymmetrically exchange-bounded.

## STEP 2 — Lesson #28 substrate availability — PASS (informational)

- funding DB: 10/10 cohort syms with non-zero rows (paradigm 138 cohort 13 minus BCH/BNB/LTC = ZERO funding DB rows)
- funding DB span: 2025-05-04 to 2026-05-10 (~370 days)
- CVD via TBR joblib: 10/10 cohort syms available, 5m frequency, ~230k rows/sym, span 2024-02-24 to 2026-05-03 (~800 days)
- Intersection window: 2025-05-04 to 2026-05-03 ≈ 365 days

Substrate sufficient, but STEP 1 halt at funding axis precludes joint test.

## Lesson #40 4th dogfood instance — sub-amendment elevation candidate

| Instance | Paradigm | Statistic class | Symmetric trigger | Outcome |
|---|---|---|---|---|
| 1 | 109 | RV (non-negative aggregate) | z ≤ -T | INFEASIBLE (CONFIRMED) |
| 2 | 110 | std (non-negative aggregate) | z ≤ -T | INFEASIBLE (CONFIRMED) |
| 3 | 138 | funding raw bp (asymmetrically exchange-bounded) | ±50 bp | INFEASIBLE (3rd dogfood) |
| 4 | **139** | **funding per-sym 30d z-score (asymmetric bound inherited via std)** | **±2.0** | **INFEASIBLE (4th dogfood)** |

**Sub-amendment text expansion (4th dogfood proposed)**:
> Lesson #40 structural threshold feasibility prescreen applies to:
> (a) non-negative aggregate statistics (std/var/count/magnitude/ATR/|return|/drawdown/RV) — symmetric z ≤ -T infeasible
> (b) asymmetrically exchange-bounded scalars (funding rate hard-capped on one side) — symmetric ±T raw threshold infeasible
> (c) **per-sym z-score (or any per-sym standardization) of asymmetrically bounded scalars** — symmetric ±T z-threshold infeasible because rolling std is dominated by the uncapped tail
>
> Reformulation alternatives (all 3 sub-classes):
> - One-sided z-score (drop B-quadrant, paradigm 22 R-5 approach)
> - Cross-sectional percentile rank per-time-stamp (removes per-sym std bias, but inherits raw cap)
> - Absolute magnitude on log scale (compresses tail asymmetry)
> - Distinct mechanism (drop the bounded scalar entirely)

## Lesson #44 22nd amendment cross-reference

- **paradigm 22 funding_carry R-5 SEEDED** (HBAR/AXS/COMP): uses per-sym z-score on funding rate. **One-sided directional only** (LONG-crowded → SHORT mean-reversion). paradigm 22 succeeds precisely because it avoids the symmetric pretense paradigm 139 hits. **Direct guidance**: paradigm 22 is the existence proof for A-only z-score approach.
- **paradigm 138 raw bp R-0 halt** (2026-05-21 11:56 KST): immediate predecessor, motivated paradigm 139 z-score reformulation attempt. 3rd Lesson #40 dogfood.
- **paradigm 109+110 Lesson #40 CONFIRMED**: original 2-dogfood basis. paradigm 138+139 extend scope.
- **Funding family Tier 4 retire** (now 9 graveyards: 73/79*/96/97/98/99/103/132/138/139, *exceptions paradigm 22+79 R-5): funding axis sub-class space functionally exhausted. paradigm 139 is the 9th funding family graveyard.
- **paradigm 132 funding × OI × magnitude triple GRAVEYARD** (Lesson #21): 3-way axis stacking trap. paradigm 139 is 2-way (funding_z × CVD) so distinct, but funding axis structural failure precludes the test.
- **paradigm 72 taker_buy_volume_5m_zscore GRAVEYARD**: CVD ratio axis is DNA-distinct (ratio not volume magnitude) so axis can be reused in future paradigms, but paradigm 139 cannot reach it.
- **paradigm 127+128 R-5 LIVE Mint**: 1m volume burst directional. DNA-distinct.

## Reformulation paths offered to user (R-0 output)

| Path | Approach | Risk / next-step |
|---|---|---|
| **path 1 (RECOMMENDED)** | funding_z A-only (drop B-quadrant) × CVD A-only, 2-quadrant SNT | Lesson #19 SNT exception justified by Lesson #40 structural infeasibility (mirror infeasible substrate, not test failure). Recovers paradigm 22 R-5 alignment. CVD axis = NEW. **Lesson #21 6th dogfood individual-vs-joint sigex still required**. |
| path 2 | funding cross-sectional percentile rank per-time-stamp (bottom 10% / top 10%) | Top-decile would degenerate to ties at +1 bp cap. FAIL CANDIDATE. |
| path 3 | Drop funding entirely. CVD 4h alone directional. | paradigm 72 risk (5m taker volume z family Tier 4 retire) — but ratio ≠ volume magnitude, and 4h ≠ 5m. Needs separate R-0. |
| path 4 | funding velocity (Δfunding_z) | paradigm 99 NARROW_SCOPE_LIFE_CHANGING_FAIL precedent. **NOT RECOMMENDED**. |
| path 5 | funding sign-flip event | paradigm 96 sign-flip lagging marker. **NOT RECOMMENDED**. |

**Recommended next dispatch (paradigm 140 candidate)**: path 1 (funding_z A-only × CVD A-only 2-quadrant) OR path 3 (CVD 4h alone, separate R-0).

## Campaign state

- Cumulative graveyards: **139** (paradigm 138 raw bp + paradigm 139 z-score 2-step Lesson #40 dogfood)
- R-5 LIVE: 10 (paradigm 127+128 unchanged)
- 11-streak non-PASS (129-139)
- R-5 yield: 10/139 = 7.19%
- Lesson #40 instances: **4** (109+110+138+139, sub-amendment 4th dogfood elevation candidate)
- Funding family Tier 4 graveyards: **9** (73/79*/96/97/98/99/103/132/138/139, *exception paradigm 22+79 R-5)
- D-Day 2026-06-03: D-13
- paradigm 127+128 Day 7 baseline: D-7 (2026-05-28)

## Decision (paradigm-architect spec compliance)

R-1 NOT DISPATCHED. R-0 STEP 1 halt at Lesson #40 prescreen (FIRST per spec).

**Per spec failure protocol** (paradigm-architect.md):
> `Non-negative aggregate statistic + symmetric z≤−T trigger (Lesson #40 paradigm 109+110 CONFIRMED 자격) → SAMPLE_INSUFFICIENT_STRUCTURAL_THRESHOLD_INFEASIBLE R-0 halt — measure z.min() empirical, if > T reformulate (percentile rank / log-transform / ratio compression / absolute threshold)`

paradigm 139 extends the rule to asymmetrically-bounded scalars where z-score normalization
inherits the asymmetry via the std denominator. This is **mechanically identical** to the
Lesson #40 antipattern, just the threshold structure is "z ≥ +T infeasible" rather than
"z ≤ -T infeasible" on the same one-sided cap principle.
