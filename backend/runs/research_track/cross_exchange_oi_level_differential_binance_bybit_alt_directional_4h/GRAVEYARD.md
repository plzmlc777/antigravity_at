# Paradigm 104 — `cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h` GRAVEYARD

**Verdict**: `BROAD_FALSIFIED_PRIMARY_HOLD` (R-1 PoC, fee-aware perm gate FAIL at primary 240m)
**Date**: 2026-05-19 KST 17:36
**Phase**: R-1
**Sequence**: 104

## TL;DR
Cross-exchange OI **level differential** (Binance USDS-M perp OI − Bybit linear perp OI, per-exchange 30d-median-normalized then 30d z-score on 1h frame) **structurally validates path #3** premise vs paradigm 103 (gross |signal| 25.7bp at primary horizon ≫ paradigm 103 rate-diff ceiling 14bp), but **primary 240m hold fails three-gate on fee-aware perm_p (0.988)** due to upward-bias trap: candidate pool 240m long-direction returns already include 2024-2026 bull-market drift mean, so the perm null mean t ≈ obs t. Mechanism shows monotonic improvement at longer holds (480m 3-gate + Concentration BOTH PASS, 1440m strong), but **life-changing 4-dim FAIL at 480m** (edge 0.26%/trade < 2.0%). Asymmetric — B side (negative z, Bybit accumulating) does not mirror — paradigm exhibits same crypto-market LONG-bias pattern as paradigm 69 / 95 / 99.

## Substrate (Lesson #28)
- **Binance OI**: data.binance.vision 5min archive resampled to 1h close, n=20,847 bars/sym × 7 syms × 2024-01-01..2026-05-19 (869d, ratio=1.000)
- **Bybit OI**: V5 REST `/v5/market/open-interest` intervalTime=1h cursor pagination, n=20,857 bars/sym × 7 syms, native 1h
- **OHLCV**: 1m joblib cache, n=1,241,280 rows/sym
- **Backfill wall-clock**: 325.5s (deep-7 universe)
- **Data window ratio (Lesson #30)**: 1.000 (full overlap window)

## Lesson #34 candidate prescreen (z_diff empirical distribution BEFORE threshold sweep)
| metric | value |
|---|---|
| n | 142,583 |
| median \|z\| | 0.900 |
| p90 \|z\| | 1.992 |
| p95 \|z\| | 2.411 |
| p99 \|z\| | 3.416 |
| max \|z\| | 18.841 |
| frac \|z\|≥1.5 | 22.36% |
| frac \|z\|≥2.0 | 9.86% |
| frac \|z\|≥2.5 | 4.38% |
| signed +/− | 0.498 / 0.502 (symmetric) |

**Outcome**: chosen z=2.5 has non-zero trigger mass (4.38% = 3,425 A-side / 2,774 B-side at 240m). Distribution well-behaved, no recalibration needed. **Lesson #34 candidate dogfood 1 (paradigm 104) — prescreen prevented a paradigm 103-style 50bp-yields-zero-events compute waste**. Confirms lesson #34 candidate (carry forward to confirmation status).

## Lesson #11 sample density (per quadrant per quarter)
| z threshold | A_focus n (q≥30 / total q) | B_focus n (q≥30 / total q) |
|---|---|---|
| 1.5 | 15,808 (10/10) | 15,747 (10/10) |
| 2.0 | 7,174 (10/10) | 6,763 (10/10) |
| 2.5 | 3,425 (10/10) | 2,774 (10/10) |

All thresholds PASS density (10/10 quarters ≥ 30 per cell). Chosen focus = **z=2.5** (largest threshold meeting density).

## 4-quadrant Symmetric Negative Test (Lesson #19) — focus z=2.5 / hold 240m
| Quadrant | n | net (bp) | gross (bp) | sigex | perm_p | ci_lower (bp) | 3-gate |
|---|---|---|---|---|---|---|---|
| A_focus  (Binance↑ + LONG)  | 3,425 | **+9.70** | **+25.70** | **+7.09** | **0.988** | +2.05 | **FAIL** (perm_p) |
| A_mirror (Binance↑ + SHORT) | 3,425 | −41.70 | −25.70 | −5.96 | 0.000 | −49.21 | FAIL |
| B_focus  (Bybit↑ + SHORT)   | 2,774 | −21.12 | −5.12 | −0.83 | 0.206 | −29.12 | FAIL |
| B_mirror (Bybit↑ + LONG)    | 2,774 | −10.88 | +5.12 | +1.63 | 0.952 | −18.85 | FAIL |

**Quadrant pair signature** (Lesson #8): `[+, −, −, −]`. A-side and B-side are **structurally asymmetric** — A_focus → A_mirror sign-flip (continuation real on positive z) but B_focus and B_mirror are both negative (no symmetric continuation on negative z). Same antipattern as paradigm 69 mirror SHORT graveyard 13σ asymmetry (memory snapshot §paradigm 70).

**Lesson #8 upward bias flag**: False (B_mirror is negative, not the +/+/−/− symmetric LONG bias pattern of paradigm 99).

## Concentration Gate (Lesson #16) — focus z=2.5 / hold 240m

**A_focus**: 2/7 syms ci_pos = 0.286 (FAIL ≥0.30), 7/10 quarters pos_t = 0.700 (PASS ≥0.50). **Overall FAIL** (symbol ratio + n_syms < 3 — only 2 ci_pos).

Per-symbol:
- BCHUSDT: +28.58bp ci=[+12.37, +45.97] ci_pos ✓
- DOGEUSDT: +25.32bp ci=[+10.06, +41.71] ci_pos ✓
- LINKUSDT: +14.42bp ci=[−1.72, +30.07] borderline
- XRPUSDT: +20.26bp ci=[−2.43, +44.49] borderline
- AVAXUSDT: **−31.57bp** ci_pos ✗
- BNBUSDT: **−30.25bp** ci_pos ✗
- SOLUSDT: **−57.55bp** ci_pos ✗

3/7 syms show strong NEGATIVE alpha at A_focus — concentration not just sparse but **directionally heterogeneous**.

Per-quarter:
| Q | n | mean (bp) | t | pos_t |
|---|---|---|---|---|
| 2024Q1 | 451 | +24.21 | +1.87 | ✓ |
| 2024Q2 | 199 | +0.36  | +0.03 | ✓ |
| 2024Q3 | 356 | +3.76  | +0.45 | ✓ |
| **2024Q4** | 378 | **+69.73** | **+3.96** | ✓ (large) |
| **2025Q1** | 573 | **−30.97** | **−3.44** | ✗ (large) |
| 2025Q2 | 184 | +20.17 | +1.64 | ✓ |
| 2025Q3 | 296 | +39.21 | +3.04 | ✓ |
| 2025Q4 | 318 | −4.84 | −0.40 | ✗ |
| 2026Q1 | 533 | −3.75 | −0.43 | ✗ |
| 2026Q2 | 137 | +3.68 | +0.38 | ✓ |

7/10 pos_t but **2024Q4 single-quarter +69.73bp carries 36% of cumulative mean**, balanced by 2025Q1 −30.97bp reversal. Same single-quarter-driven pattern as paradigm 87 R-2 walk-forward FAIL (lesson #26 amendment territory).

## Hold sweep diagnostic — focus z=2.5

| Hold | A_focus net | A_focus gross | sigex | perm_p | ci_lower | 3-gate | Concentration |
|---|---|---|---|---|---|---|---|
| 60m | −6.04 | +9.96 | +7.21 | 1.000 | −10.01 | FAIL | n/a |
| **240m (primary)** | **+9.70** | **+25.70** | **+7.09** | **0.988** | **+2.05** | **FAIL (perm_p)** | **FAIL** |
| **480m** | **+26.11** | **+42.11** | **+7.59** | **0.045** | **+15.45** | **PASS** | **PASS** (4/7 syms, 8/10 q) |
| **1440m** | **+76.78** | **+92.78** | **+8.93** | **0.000** | **+58.45** | **PASS** | **PASS** (4/7 syms, 8/10 q) |

**Monotonic improvement** through hold horizon (similar to paradigm 103 but stronger gross magnitudes). 480m and 1440m **both clear three-gate + Concentration**. Primary 240m (paradigm name `_4h`) fails on perm_p only — the upward-bias trap: 142,583 candidate-pool 240m forward returns have positive bull-market drift mean, so the perm null t-mean is high; observed +25.7bp gross is a real signal but lost in the null distribution at that horizon.

A_mirror at all holds is strongly negative (matched sign-flip), B_focus and B_mirror both negative (no B-side continuation).

## Cross-paradigm 103 comparison — **path #3 structurally validated**
| metric | paradigm 103 (rate diff) | paradigm 104 (OI diff) |
|---|---|---|
| Focus gross at primary hold | ~14bp ceiling | **+25.70bp** (1.84× stronger) |
| 1440m gross | +24bp drift | **+92.78bp** (3.87× stronger) |
| Three-gate at primary | FAIL (fee floor) | FAIL (upward-bias trap) |
| 480m gross | n/a | **+42.11bp** 3-gate + Concentration PASS |
| Fail mechanism | round-trip fee 16bp ≥ gross signal | candidate-pool drift mean ≥ obs t |

**Path #3 separation from path #2 is structurally validated** — OI level differential carries materially stronger signal than rate differential, breaking through paradigm 103's fee-floor ceiling. But the alternative trap mechanism (upward-bias / pool drift at primary horizon) replaces fee-floor as the failure mode.

## Lesson #32 universe-baseline-coherent check
- Universe-wide 240m no-trigger forward return mean: **+1.67bp**
- Per-sym: AVAX −0.85 / BCH +2.52 / BNB +2.14 / DOGE +2.45 / LINK +1.01 / SOL +1.30 / XRP +3.13

A_focus selects on `oi_diff_z > +2.5` which positively correlates with crypto bull regime (Binance OI accumulating during rallies). Universe mean is +1.67bp; A_focus mean is +25.70bp (net +9.70 = +25.70 gross − 16 fee). Selection is real (+24bp lift above baseline gross), but the candidate-pool perm null also lifts. **Lesson #32 trap variant — universe baseline-coherent at gross but perm null lifts proportionally**.

## Life-changing 4-dim (Lesson #20 amendment)
At 480m hold (the variant that PASSES three-gate + Concentration):
- trades/yr: 1,439 (PASS ≥12)
- edge per trade: **0.26%** (**FAIL** ≥2.0%)
- capital util: 131% — overlap artifact, normalize to ~30-40% with position sizing
- sharpe proxy: 3.01 (PASS ≥3.0)

**Life-changing 4-dim FAIL on edge dimension**. Even the longer-hold variant cannot achieve +2.0%/trade. At 1440m: edge 0.77%/trade still FAIL.

## Verdict

**`BROAD_FALSIFIED_PRIMARY_HOLD` at paradigm-spec primary 240m hold** (per orchestration verdict tree, halts here):
1. A_focus three-gate at primary 240m FAIL on perm_p=0.988 (upward-bias trap)
2. B_focus three-gate FAIL with gross −5.12bp (no B-side continuation, asymmetric)
3. Concentration FAIL at primary (2/7 syms ci_pos = 0.286 < 0.30)
4. A_mirror at all holds strongly negative — sign-direction asymmetry confirmed (matches paradigm 69/70 antipattern: market structural LONG bias)

**Substantive nuance worth documenting** (NOT promoting paradigm 104):
- 480m + 1440m hold variants PASS three-gate + Concentration, but **fail life-changing 4-dim edge/trade**
- OI level differential **does** carry stronger signal than rate differential (path #3 premise validated)
- Mechanism real on A-side only; symmetric path #3 falsified

## Lessons confirmed/newly observed in this R-1

1. **Lesson #34 candidate confirmed (2nd dogfood, paradigm 103 + 104)** — empirical |z| distribution prescreen BEFORE threshold sweep prevented compute waste. Distribution-driven threshold sweep more efficient than fixed-grid. **Recommend promote to confirmed Lesson #34**.

2. **NEW lesson candidate #35 — Primary-hold-fee-trap vs upward-bias-pool-drift distinction**: paradigm 103 graveyard was BROAD_FALSIFIED_FEE_FLOOR (gross < fee). Paradigm 104 is structurally different — gross >> fee but perm_p FAILs at primary hold due to candidate-pool drift mean. Both fail three-gate at primary horizon but for different mechanisms. Need to flag this in eval_research_gate output for orchestrator triage.

3. **Lesson #19 + #8 confirmation (dogfood 3 cumulative paradigm 99 + 104)** — A-side three-gate FAIL when mirror sign-flips correctly but B-side absent → structural LONG-bias antipattern. Single-side path #3 admits no symmetric continuation. Should be combined as Lesson #8 amendment Q3 §6.

4. **Cross-exchange family-distinct path #3 status update**: paradigm 103 (path #2 lead-lag rejected by fee-floor) + paradigm 104 (path #3 OI level rejected by primary-hold upward-bias trap) — **2/3 cross-exchange paradigm 103-family paths now graveyard at primary horizon**. Remaining path #1 (illiquid venue arbitrage) untouched but tier-4 advisory caution should be raised given 2 consecutive primary-horizon falsifications.

## Resources committed
- **OI cache (permanent)**: backend/runs/ohlcv_cache/binance_oi/{SYM}_1h.joblib + bybit_oi/{SYM}_1h.joblib (7 syms × 2 venues, ~5MB total compressed)
- **Daily archive cache**: backend/runs/ohlcv_cache/binance_metrics_daily/{SYM}__YYYY-MM-DD.joblib (6,090 files)
- **R-1 script (permanent)**: backend/scripts/research/p104_r1.py
- **Backfill script (permanent)**: backend/scripts/research/p104_backfill_oi.py
- **R-1 metrics**: backend/runs/research_track/cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h/r1/r1__metrics.json (174 KB)
- **R-1 log**: /tmp/p104_r1.log
- **Wall-clock**: 29.9s R-1 + 325.5s backfill = ~356s total

## Next-action recommendation
1. **Halt at R-1**. No R-2 spawn — life-changing 4-dim FAIL even at PASSING longer holds rules out paradigm 104 advancement.
2. **Re-classify path #3 as 'partial-mechanism with horizon constraint'**: log finding that cross-exchange OI level differential validates path #3 premise at 480m+ but fails life-changing edge per trade.
3. **Confirm Lesson #34 candidate**: promote to confirmed lesson (2nd dogfood paradigm 103 + 104 both prevented compute waste).
4. **Add Lesson #35 candidate**: primary-hold-fee-trap vs upward-bias-pool-drift dual failure mode classification.
5. **Cross-exchange family Tier 4 retire decision deferred**: paths #1 + #2 + #3 → 2/3 graveyard. Path #1 (illiquid venue) still untouched. Recommend explicit advisory caution flag for cross-exchange family in agent prescreens.
6. **OI infrastructure now permanent asset**: Bybit OI cache + Binance archive cache available for any future paradigm needing OI substrate (paradigm 71 btc_oi_velocity universe expansion candidate, OI-Premium joint paradigm 24 re-test on extended window etc).
