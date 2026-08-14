# Graveyard: Paradigm 244 — premium_index_cusum_cp_bilateral_4h

- Date: 2026-08-04 KST
- Dispatch mode: autonomous SELF-RECOMMEND (post-231 escalation continuation)
- Phase halted: **R-0**
- Verdict: **R0_HALT_LESSON_39_SUB_CLASS_A_FEE_SYMMETRIC_BROAD_FALSIFIED**

## Hypothesis (as proposed)

Per-symbol Binance perpetual `premium_index` at 5m resolution shows structural
upward or downward mean level-shifts detected by an online Page-Hinkley CUSUM
(pure numpy). An UP shift is claimed to predict LONG continuation over 30m/1h/2h/4h,
a DOWN shift to predict SHORT continuation. Bilateral 4-quadrant SNT
(Lesson #19) mandatory: A_focus UP×LONG, A_mirror UP×SHORT, B_focus DOWN×SHORT,
B_mirror DOWN×LONG. Sensitivity λ ∈ {1.5σ, 2.0σ, 2.5σ}. Events within ±1h of
funding boundaries (00:00/08:00/16:00 UTC) excluded.

## Why this looked promising (motivation summary)

- Lesson #22 (paradigm 84) prescribed exactly this fix: stateful change-point
  detectors need frame-grade source frequency. Premium_5m *is* frame-grade,
  unlike the daily `book_depth` that killed paradigm 84.
- Q3 queue item #12 `change_point_detection_premium` remained untested through
  paradigm 243.
- Statistic class (Page-Hinkley online change-point) had not been used in the
  243-paradigm history at frame-grade frequency. DNA overlap with paradigm 84:
  2–3/6 dims, well below the 5/6 duplicate ceiling.
- Non-OHLCV substrate — Lesson #77 compliant.

## Substrate audit (Lesson #28)

| Dependency | Status |
|---|---|
| `runs/premium_index/{SYM}_premium_5m.joblib` (14 syms) | present, 2024-05-15 → 2026-05-13, 5min OHLC-shaped |
| `runs/ohlcv_cache/{SYM}_1m.joblib` (14 syms) | present |
| Frame-grade for CUSUM (Lesson #22) | **YES** (5m native, not daily like paradigm 84) |

## Sample density (Lesson #11)

Rolling-baseline Page-Hinkley at λ=2.0σ, 30d lookback, cooldown 36 bars:
- Pooled 14-sym: n_up ≈ 1,114 / n_dn ≈ 1,084 per hold
- Per-cell (4 quadrant × 4 quarter): ~70 pooled — PASS
- Per-symbol per-quarter at λ=2.5σ: ~15 — below 30, but pooling recovers

Sample density was *not* the killer. This paradigm reached the fee-symmetry
diagnostic on the strength of adequate events.

## Lesson #79 predictive-content pretest (1h fwd, λ=2.0σ)

Per-symbol signed t-stat (LONG on UP, SHORT on DOWN, funding-filtered):

| Symbol | signed_t | Symbol | signed_t |
|---|---|---|---|
| BTCUSDT | +1.37 | LINKUSDT | -0.79 |
| ETHUSDT | +1.21 | LTCUSDT  | -1.62 |
| SOLUSDT | -0.80 | NEARUSDT | -1.10 |
| ADAUSDT | -0.30 | WIFUSDT  | +0.26 |
| AVAXUSDT| -0.44 | XRPUSDT  | +3.69 |
| BCHUSDT | -0.27 | FILUSDT  | -0.77 |
| BNBUSDT | +0.47 | DOGEUSDT | +1.50 |

- Aggregate mean = **+0.17** (essentially zero)
- Only 1/14 syms with |t|>2 (XRP alone). This mirrors paradigm 237's
  universal-negative predictive content halt.

## Lesson #39 sub-class A confirmation (definitive kill)

Full 3λ × 4hold sweep of pooled 4-quadrant net edge after 8bp round-trip fee:

| λ | hold | A_focus (bp) | A_mirror (bp) | B_focus (bp) | B_mirror (bp) | sum_A | sum_B |
|---|---|---|---|---|---|---|---|
| 1.5 | 30m | -7.00 | -9.00 | -10.19 | -5.81 | **-16.00** | **-16.00** |
| 1.5 | 1h  | -3.60 | -12.40 | -13.37 | -2.63 | -16.00 | -16.00 |
| 1.5 | 2h  | -3.51 | -12.49 | -21.46 | +5.46 | -16.00 | -16.00 |
| 1.5 | 4h  | +2.52 | -18.52 | -14.15 | -1.85 | -16.00 | -16.00 |
| 2.0 | 30m | -7.65 | -8.35 | -6.38 | -9.62 | -16.00 | -16.00 |
| 2.0 | 1h  | -7.25 | -8.75 | -6.50 | -9.50 | -16.00 | -16.00 |
| 2.0 | 2h  | -7.94 | -8.06 | -11.39 | -4.61 | -16.00 | -16.00 |
| 2.0 | 4h  | -2.22 | -13.78 | -15.20 | -0.80 | -16.00 | -16.00 |
| 2.5 | 30m | -10.89 | -5.11 | -13.82 | -2.18 | -16.00 | -16.00 |
| 2.5 | 1h  | -13.65 | -2.35 | -15.96 | -0.04 | -16.00 | -16.00 |
| 2.5 | 2h  | -13.17 | -2.83 | -17.30 | +1.30 | -16.00 | -16.00 |
| 2.5 | 4h  | +0.94 | -16.94 | -20.94 | +4.94 | -16.00 | -16.00 |

**12/12 cells**: `sum_A = A_focus + A_mirror = -16.00 bp = -2 × fee`.
**12/12 cells**: `sum_B = B_focus + B_mirror = -16.00 bp = -2 × fee`.

Best positive cell across the entire grid: `B_mirror DN×LONG 2h λ=1.5 = +5.46 bp`
— **1/37th of the elite gate threshold** (+200 bp/trade).

## Root cause

Page-Hinkley successfully identifies statistical mean-shifts in the premium_5m
series (~200 events/sym/yr per side after cooldown). The mean-shifts are real
and detectable. But the **shift direction carries no information about
subsequent 30m–4h spot price direction.** In a 4-quadrant SNT, focus+mirror
sums to exactly −2× fee whenever the trigger is directionally uninformative;
this is the canonical Lesson #39 sub-class A fingerprint.

The Lesson #22 fix (frame-grade source substrate) works structurally — CUSUM
now emits events instead of being freq-mismatched — but the underlying economic
premise is wrong. Premium level-shifts on this substrate reflect *funding
regime transitions* and *inventory absorption*, both of which either mean-revert
or resolve at horizons much longer than 4h. The 5m detector on this data
generates events at the wrong horizon for what the events represent.

## Lessons dogfooded

- **#11** sample density — measured, passed (would not have killed)
- **#19** 4-quadrant SNT — enforced in pretest
- **#22** stateful CP frame-freq — satisfied (premium_5m IS frame-grade). Lesson
  #22 fix worked structurally but did not produce economic edge.
- **#28** substrate audit — passed
- **#39 sub-class A** — 10th confirmed dogfood, fee-symmetric broad-falsified
- **#40** structural threshold feasibility — passed (not a threshold-on-non-negative)
- **#61** slug uniqueness — new slug
- **#77** non-OHLCV substrate — premium_index is non-OHLCV
- **#79** predictive-content pretest — universal fail (13/14 syms |t|<2)

## New lesson candidate (L84 candidate)

**Name**: `frame_grade_stateful_cp_still_needs_economic_horizon_alignment`

**Prescription**: Lesson #22 (stateful CP requires frame-grade source frequency)
is a **necessary but not sufficient** condition. Even when the source substrate
is at the correct frequency for the detector, the economic mechanism the
change-points represent must have a *predictive* horizon overlapping the
proposed hold window. Premium_5m CUSUM detects funding-regime and inventory
transitions — those horizons are hours-to-days on the mean-reverting side and
have no directional information at 30m–4h holds. Before proposing a hold
window for a CUSUM/BOCPD/HMM paradigm, run Lesson #79 pretest at the target
hold to confirm |signed_t| ≥ 2 for ≥ 50% of the universe.

Confirmation status: 1st dogfood (needs 1 more independent kill via
frame-grade-satisfied-but-Lesson-#79-fail to confirm).

## Compute saved

- R-1 sweep avoided: 3 λ × 4 hold × 4 quadrant × 14 sym = **672 cells**
- Estimated compute: ~4h wall-clock at prior CUSUM R-1 pace
- All information needed for the kill was obtainable at R-0 pretest cost (~2 min)

## Files

- Script: `backend/scripts/research/paradigm_244_premium_index_cusum_cp_bilateral_4h_r0.py`
- Metrics: `backend/runs/research_track/paradigm_244_premium_index_cusum_cp_bilateral_4h/r0_prescreen__metrics.json`
- Graveyard: `backend/runs/research_track/graveyard__paradigm_244_premium_index_cusum_cp_bilateral_4h.md`

## Autonomous mode note

Paradigm 244 continues the SELF-RECOMMEND streak initiated after paradigm 231.
The proposed queue item (`change_point_detection_premium`, Q3 ⭐⭐) was
autonomously executed to R-0 halt. NEXT_PARADIGM_RUNBOOK §12 saturation
guidance remains active — future SELF-RECOMMEND proposals in this cluster
should apply the L84 candidate prescription (economic-horizon-alignment pretest
at target hold) before dispatching R-1.
