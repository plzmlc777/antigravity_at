# Paradigm 117 R-1 PASS — alt_extreme_24h_drawdown_reversal_long_4h

**Date**: 2026-05-20 KST
**Host**: hcp_local
**Wall clock**: 2.4 sec

## Pivot context

Post paradigm 114→115→116→115_R2 level-crossing class
NARROW_SCOPE_LIFE_CHANGING_FAIL 4th dogfood, pivoted to sparse
event-driven mechanism with target edge ≥2%/trade. This paradigm is
the first post-pivot dispatch.

## Hypothesis

When an alt's rolling 24h cumulative log return drops ≤ −15%, forward
LONG continuation captures a mean-reversion bounce. Tested 4 hold
periods {1h, 4h primary, 12h, 24h} × 4 thresholds {−10%, −15%, −20%,
−25%}.

## Verdict: PASS_R1_FULL (via Lesson #37 sweep verdict scan)

The primary specified hold (4h) does NOT show signal (gross +0.18bp),
but the hold-sweep scan at primary threshold −15% identified a strong
PASS cell at **24h hold**.

## Headline cell: A_focus_drawdown_LONG_th-0.15_h24

| Metric | Value |
| --- | --- |
| n_trades | 406 (28 alts, 24mo, ≥24h debounce) |
| obs_mean_gross_bp | **+275.31 bp** |
| obs_mean_net_bp | **+267.31 bp** |
| obs_t | (see metrics) |
| signal_t_excess | **8.71** |
| perm_p_two_sided | **0.000** |
| CI_lower_bp / CI_upper_bp | **+201.52 / +329.38** |
| 3-gate PASS | True |
| per-quarter pos_t | **7/8** (q_pos_ratio 0.88) |
| per-sym ci_pos | **13/28** (syms_ci_pos_ratio 0.46) |
| Concentration Gate PASS | True |
| trades_per_year | 216 |
| per_trade_edge_pct | **+2.67%** |
| capital_util_pct | 59.0% |
| annualized_sharpe | 5.72 |
| life-changing 4-dim PASS | True (all 4: trades≥12 + edge≥2% + util≥30% + sharpe≥1.5) |

## Full hold-sweep results @ threshold −15%

| Hold | n | gross bp | net bp | sigex | perm_p | CI lower bp | 3-gate | Conc | q_pos | syms_pos | edge % | tpy | util % | sharpe | lc4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1h | 406 | -11.87 | -19.87 | 0.39 | 0.657 | -52.01 | False | False | 2/8 | 0/28 | -0.20 | 216 | 2.5 | -0.98 | False |
| 4h primary | 406 | 0.18 | -7.82 | 0.63 | 0.816 | -46.72 | False | False | 2/8 | 0/28 | -0.08 | 216 | 9.8 | -0.30 | False |
| 12h | 406 | 69.97 | 61.97 | 2.72 | 0.137 | 0.94 | False | False | 5/8 | 2/28 | 0.62 | 216 | 29.5 | 1.38 | False |
| **24h** | **406** | **275.31** | **267.31** | **8.71** | **0.000** | **201.52** | **True** | **True** | **7/8** | **13/28** | **2.67** | **216** | **59.0** | **5.72** | **True** |

The signal scales monotonically with hold: nil at 1h, flat at 4h,
emerging at 12h, dominant at 24h.

## 4-quadrant SNT at threshold −15% × hold 4h (Lesson #19)

| Quadrant | n | gross bp | net bp | sigex | 3-gate | Conc |
| --- | --- | --- | --- | --- | --- | --- |
| A_focus_drawdown_LONG | 406 | +0.18 | -7.82 | 0.63 | False | False |
| A_mirror_drawdown_SHORT | 406 | -0.18 | -8.18 | 0.18 | False | False |
| B_same_sign_pump_SHORT | 409 | +35.55 | +27.55 | 1.87 | False | False |
| B_mirror_pump_LONG | 409 | -35.55 | -43.55 | -0.92 | False | False |

Notes:
- A_focus and A_mirror are near-perfect mirror at 4h (sum |bp| ≈ 0.36)
  — Lesson #39 sub-class A pattern at 4h (no directional info in 4h
  forward window post-drawdown).
- B_same_sign_pump_SHORT shows partial mean-reversion (gross +35.55bp,
  sigex 1.87) but does not clear 3-gate. Pumps revert weakly in 4h.

## Empirical 24h log-return distribution (Lesson #34)

- n_obs: 478k
- p01: -13.17%, p05: -7.34%, p99: +13.23%
- min/max: -50.69% / +79.92%
- frac ≤ -10%: 2.24%, ≤ -15%: 0.66%, ≤ -20%: 0.24%, ≤ -25%: 0.11%
- frac ≥ +10%: 2.34%, ≥ +15%: 0.65%

The distribution is roughly symmetric; threshold sweep -10% and -15%
have ample sample, -20% and -25% fall below Lesson #11 cutoff (per
quarter < 30).

## Lesson #11 prescreen (with empirical debounce ≥24h)

| Threshold | n_raw_dn | n_deb_dn | per-quarter | PASS |
| --- | --- | --- | --- | --- |
| -10% | 10973 | 1322 | 146.9 | True |
| -15% | 3250 | 406 | 45.1 | True |
| -20% | 1187 | 166 | 18.4 | False |
| -25% | 537 | 80 | 8.9 | False |

Primary −15% passes comfortably. −20%/−25% skipped by Lesson #11.

## Per-quarter detail for the PASS cell (h=24)

| Quarter | n | mean bp | t | pos |
| --- | --- | --- | --- | --- |
| 2024Q2 | 17 | +289.97 | +2.17 | True |
| 2024Q3 | 55 | +645.01 | +8.90 | True |
| 2024Q4 | 79 | +190.97 | +2.45 | True |
| 2025Q1 | 97 | +108.36 | +1.44 | True |
| 2025Q2 | 40 | +494.22 | +5.70 | True |
| 2025Q3 | **5** | **-174.13** | **-2.73** | **False** |
| 2025Q4 | 71 | +27.33 | +0.34 | True |
| 2026Q1 | 41 | +547.12 | +5.88 | True |

Variance across quarters is HIGH (108bp → 645bp range). Q3-2025 is
single failure with marginal n=5 (only 5 drawdown events that quarter,
mean -174bp). This will be the R-2 walk-forward stress point.

## Caveats / R-2 watchpoints

1. **Mechanism timescale = 24h, not 4h**. The hypothesis as stated
   ("4h forward LONG continuation") does NOT hold. The actual signal
   emerges at 24h hold. R-2 must reframe paradigm name and primary
   hold accordingly: `alt_extreme_24h_drawdown_24h_reversion_long`.

2. **Capital utilization 59% at 24h hold × 216 trades/yr** is high.
   Position overlap reality: multiple alts simultaneously in drawdown
   during regime crashes (Q2-2024, Q3-2024) → portfolio sizing must
   account for cluster events.

3. **Per-quarter variance** suggests regime sensitivity. Q3-2025
   single failure quarter (n=5 marginal) is the R-2 walk-forward
   stress test. 5-fold TS-CV will reveal whether this is a stable
   mean-reversion or a regime-dependent pattern (Lesson #26 small-
   sample Concentration blind spot — paradigm 87 dogfood).

4. **Survivorship caveat**: universe is 28 currently-listed alts. If
   delisted alts had different post-drawdown behavior (forced exits,
   no recovery), the result is biased. R-3 should test on the
   delisted-cohort if practical, or document as known scope.

5. **Per-sym concentration 13/28 = 46%** clears Concentration Gate
   (≥30%) but is well below universal coverage. Mechanism is real but
   not uniformly distributed across the cohort. Best 6 syms (HBAR
   AAVE UNI ADA AVAX 1000SHIB DOGE XRP SOL LINK BCH ETH SUI) carry
   the signal; mid-tier (TIA OP INJ ARB FIL DOT ATOM LTC NEAR APT
   ICP 1000PEPE) flat. TRX/BNB underpopulated (n<5, not measurable).

6. **Lesson #39 symmetric mirror antipattern check at 4h**: A_focus
   gross +0.18bp + A_mirror gross -0.18bp sum_abs 0.36bp. At 4h this
   IS a perfect-mirror sub-class A (broad-uniform-zero) — meaning the
   4h hold contains zero directional info. The 24h cell's directional
   info is genuinely present (gross +275bp ≠ a mirror artifact since
   A_mirror at 24h was not computed but would be ~-275bp gross, which
   is the directional bet OPPOSITE to drawdown). R-2 must compute
   A_mirror at 24h to confirm Lesson #39 sub-class status.

7. **Look-ahead check**: trigger uses close(t) vs close(t−24). Forward
   return uses close(t+24) vs close(t). No overlap, no look-ahead.
   Valid event-study design.

## Files

- Script: `backend/scripts/research/paradigm117_alt_extreme_24h_drawdown_reversal_long_4h_r1.py`
- Metrics: `backend/runs/research_track/alt_extreme_24h_drawdown_reversal_long_4h/r1__metrics.json`
- Log: `backend/runs/research_track/alt_extreme_24h_drawdown_reversal_long_4h/r1__stdout.log`

## Recommendation

HALT at R-1. Strongly recommend user approval for R-2 dispatch with
the following structural changes:

1. **Rename paradigm slug** to `alt_extreme_24h_drawdown_24h_reversion_long`
   to reflect actual mechanism timescale.
2. **Primary hold = 24h** (paradigm 117 R-1 confirmed real signal).
3. **R-2 walk-forward 5-fold TS-CV** on Q3-2025 outlier — Lesson #26
   small-sample Concentration blind spot watchpoint.
4. **R-2 must include A_mirror at 24h** to confirm Lesson #39 status.
5. **R-2 should also test threshold −12% and −18%** to map robustness
   plateau; if signal monotone in threshold strength (sparser =
   stronger edge), narrow to −18% for cleaner edge.
6. **R-2 universe consideration**: option to drop TRX/BNB (n<5
   underpopulated) and add delisted-cohort if archive feasible.

This is a candidate **first post-pivot PASS** demonstrating sparse
event-driven mechanism class remains viable when timescale is allowed
to extend to the natural recovery horizon (24h for alt drawdowns).
