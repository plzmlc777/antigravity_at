# Graveyard — paradigm 243 · alt_funding_rate_30d_rolling_skewness_bilateral_1d_to_4d

- **Paradigm number**: 243
- **Slug**: `funding_skewness_bilateral`
- **Registered**: 2026-08-02 (autonomous self-recommend dispatch)
- **Verdict phase**: R-1
- **Final verdict**: `BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED` (Lesson #39 sub-class B) + `CONCENTRATED_R1_FAIL_TEMPORAL_FRAGILE` (Lesson #16 + Lesson #13)

---

## Hypothesis

Per-symbol Binance Futures perp 8h funding rate 30d rolling skewness at extremes predicts directional alpha:
- `A_focus`: skew ≥ +T → SHORT (fragile bullish leverage)
- `B_focus`: skew ≤ −T → LONG (fragile bearish leverage)
- `A_mirror` / `B_mirror`: opposite side (bilateral SNT)

Thresholds T ∈ {0.5, 1.0, 1.5}, holds ∈ {1d, 3d, 4d}, universe = 14 syms (funding DB ∩ ohlcv cache), fee 8bp round-trip.

## Substrate

- `binance_funding_rate` DB (Lesson #77 non-OHLCV compliant), 2023-11-15 → 2026-08, 8h cadence
- 14 syms × ~858 daily obs each after 90-period skew warmup + fwd-return dropna
- Skew computed via `scipy.stats.skew` over rolling 90 funding periods

## R-0 lesson prescreen

- Lesson #61 slug grep: no direct "funding_skewness" prior. PASS.
- Lesson #62 DNA 5/6: closest priors (funding window-ratio z, eigenvalue dominance, per-sym z-score MR) share substrate + trigger-type but not `distribution-shape` statistic. Novel 4/6 max overlap. PASS.
- Lesson #56 outcome-family: funding_carry (level MR) vs funding_dispersion (cross-sym var) vs funding_skewness (per-sym shape) — distinct mechanisms. PASS.
- Lesson #77 non-OHLCV: PASS.
- Lesson #11 sample density: 858 daily obs × 14 sym × ~45% trigger rate at T=1.0 → ~5.4k triggers per quadrant. PASS.
- Lesson #19 4-quadrant SNT: implemented.
- Lesson #40 structural threshold: |skew| ≥ {0.5, 1.0, 1.5} achievable (SOL: 79%/45%/25% rates). PASS.
- Lesson #79 predictive corr pretest (crypto extension): SOL max |corr(skew, fwd_Xd)| = 0.086 at h=4d; BTC/ETH/DOGE mostly <0.03 — advisory only, proceeded.

## R-1 results (36 cells: 4 quadrants × 3 thresholds × 3 holds)

**Three-gate pass count**: 5/30 measurable — ALL are A_mirror direction (i.e., "positive skew → LONG", the **INVERTED** mechanism relative to the hypothesized "positive skew → SHORT").

**No focus quadrant passes three-gate.** No cell passes concentration gate.

Top-5 three-gate-pass cells (all A_mirror; hypothesis-inverted):

| quadrant | T | h | n | mean_bp | t_ex | ci_lo_bp | perm_p | sym_ci_pos | q_pos_t | conc_gate |
|---|---|---|---|---|---|---|---|---|---|---|
| A_mirror | 1.5 | 4d | 1104 | +202.7 | +6.40 | +136.4 | 0.000 | 0.50 | 0.44 | FAIL |
| A_mirror | 1.5 | 3d | 1104 | +151.5 | +5.65 | +94.8 | 0.000 | 0.36 | 0.44 | FAIL |
| A_mirror | 1.5 | 1d | 1104 | +53.4 | +4.06 | +22.5 | 0.005 | 0.07 | 0.67 | FAIL |
| A_mirror | 1.0 | 4d | 1864 | +79.4 | +3.64 | +29.6 | 0.007 | 0.14 | 0.56 | FAIL |
| A_mirror | 1.0 | 3d | 1864 | +49.9 | +2.86 | +5.1 | 0.062 | 0.14 | 0.56 | FAIL |

## Lesson #39 exact-symmetric mirror antipattern — CONFIRMED (sub-class B: mechanism-inverted)

Every focus/mirror pair sums to **exactly -16.0 bp = -2 × fee**:

| T | h | A_focus (bp) | A_mirror (bp) | sum | B_focus (bp) | B_mirror (bp) | sum |
|---|---|---|---|---|---|---|---|
| 1.0 | 1d | -26.4 | +10.4 | -16.0 | -17.2 | +1.2 | -16.0 |
| 1.0 | 3d | -65.9 | +49.9 | -16.0 | -32.1 | +16.1 | -16.0 |
| 1.0 | 4d | -95.4 | +79.4 | -16.0 | -38.5 | +22.5 | -16.0 |
| 1.5 | 1d | -69.4 | +53.4 | -16.0 | -18.7 | +2.7 | -16.0 |
| 1.5 | 3d | -167.5 | +151.5 | -16.0 | -31.0 | +15.0 | -16.0 |
| 1.5 | 4d | -218.7 | +202.7 | -16.0 | -33.9 | +17.9 | -16.0 |

This mathematical identity (focus + mirror = -2 × fee) proves the trigger contains **zero directional information** — every trigger corresponds to a single gross-return realization, and the "focus vs mirror" split is just `−r − fee` vs `+r − fee`. All observed asymmetry is inherited from the underlying gross-return distribution's mean (long-drift), NOT from any mechanism the skew statistic captures.

## Lesson #16 + #13 concentration + temporal fragility (best cell A_mirror T=1.5 h=4d)

Per-symbol (14 measurable, 7 ci_pos = 50%):
```
BTC   n=  96  +78.4bp  ci_lo=  -17.1bp  ci_pos=False
ETH   n=  84 +162.7bp  ci_lo=  +38.5bp  ci_pos=True
SOL   n=  68  +32.0bp  ci_lo= -147.9bp  ci_pos=False
DOGE  n=  65 +434.1bp  ci_lo= +112.0bp  ci_pos=True
ADA   n=  96 +232.8bp  ci_lo=  +33.1bp  ci_pos=True
XRP   n= 108 +454.6bp  ci_lo= +213.3bp  ci_pos=True
BNB   n= 184   +0.4bp  ci_lo=  -76.3bp  ci_pos=False
BCH   n=  29 +211.5bp  ci_lo= -398.7bp  ci_pos=False
LTC   n= 125 +187.6bp  ci_lo=  +22.5bp  ci_pos=True
LINK  n=  61 +209.2bp  ci_lo=  -28.0bp  ci_pos=False
AVAX  n=  48  +37.2bp  ci_lo= -216.8bp  ci_pos=False
FIL   n=  34 +640.0bp  ci_lo= +246.8bp  ci_pos=True
NEAR  n=  43 -297.3bp  ci_lo= -658.3bp  ci_pos=False
WIF   n=  63 +754.8bp  ci_lo= +125.5bp  ci_pos=True
```

Per-quarter (9 measurable, 4 pos t = 44% < 50% gate):
```
2024Q1  n=377  +479.8bp  t=+6.98
2024Q2  n=165  -282.0bp  t=-4.66
2024Q3  n= 36  -135.1bp  t=-1.06
2024Q4  n=302  +379.9bp  t=+5.45
2025Q1  n= 53  -437.3bp  t=-3.15
2025Q3  n= 65  +129.5bp  t=+2.28
2025Q4  n= 67   -32.8bp  t=-0.35
2026Q1  n= 22  -203.1bp  t=-1.64
2026Q2  n= 17   +56.3bp  t=+0.93
```

The aggregate is driven almost entirely by **2024Q1 + 2024Q4** (crypto bull episodes). Every non-bull quarter is either flat or reversed. This is **exactly the regime-artifact temporal fragility** Lesson #13 targets.

## Root cause

The rolling-30d skewness statistic on 8h funding rates does not measure "fragility of leverage buildup". In practice, positive-skew regimes correspond to periods where funding intermittently spikes positive — i.e., episodic bull-flow bursts. During bull markets, going LONG during such regimes captures the bull drift itself; during bear markets, going LONG loses. The trigger has no direction-predictive content beyond selecting elevated-volatility windows that coincide with bull episodes in the 2024-2026 sample.

## Verdict

**R-1 GRAVEYARD — `BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED` + `CONCENTRATED_R1_FAIL_TEMPORAL_FRAGILE`.**

No R-2 warranted. No follow-up. Do not narrow-scope (Lesson #20 blocked by 4-cond fail: focus fails ubiquitously; the mirror pass is not a valid alternative direction because the ±16bp identity proves zero directional information in the trigger).

## Lesson-referenced action items

- **Lesson #39 sub-class B** confirmed for 2nd time this quarter (paradigm 110 was 1st; 243 is 2nd). Statute of Lesson #39 promotion from "2 dogfood CONFIRMED 자격" to **CONFIRMED** should be reviewed by lesson index maintainer.
- **Lesson #79 crypto extension** recorded: skew-magnitude class predictive corr max ~0.086 → still enough to trigger 3-gate pass in mirror direction due to bull drift; corr-based prescreen is insufficient to block Lesson #39 sub-class B failures.
- Future funding-shape statistics (kurtosis, skew-of-skew, etc.) should incorporate a **pre-R-1 direction-info test**: compute `E[fwd | trigger] − E[fwd | ¬trigger]` (gross, no fee, no direction) and require |Δ| ≥ 20bp before dispatching a bilateral R-1. If Δ ~ 0, only the sign asymmetry of drift produces the mirror-pass artifact.

## Artifacts

- Script: `backend/scripts/research/paradigm_243_funding_skewness_bilateral_r1.py`
- Metrics: `backend/runs/research_track/paradigm_243_funding_skewness_bilateral/r1__metrics.json`
- This graveyard: `backend/runs/research_track/graveyard__paradigm_243_alt_funding_rate_30d_rolling_skewness_bilateral_1d_to_4d.md`
