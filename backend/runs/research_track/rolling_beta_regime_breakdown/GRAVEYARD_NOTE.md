# paradigm 81 — rolling_beta_regime_breakdown R-1 GRAVEYARD

**Date**: 2026-05-15
**Paradigm #**: 81 (R-1 graveyard)
**Author**: paradigm-architect agent

## TL;DR

13 alts × BTCUSDT rolling 30d beta z-score breakdown, 4-cell sign-conditional
(beta_z extreme × BTC 1d direction × LONG/SHORT). Focus cell 1 (high-beta-amp
× BTC up × LONG) **falsified inverse** — focus mean −196.5bp / sigex −3.83 /
ci_lower −350.8bp / perm_p 0.0000 three-gate ALL FAIL. R-1 verdict
`R1_FAIL`.

However the 4-cell symmetric layout exposed a **sub-quadrant alpha**: cell 4
(low-beta-z × BTC down × LONG) +165.27bp, separate three-gate ALL PASS
(sigex +2.52 / ci_lower +3.19bp / perm_p 0.003). Despite this, cell 4 also
fails the **Concentration Gate** (symbol_ci_pos_ratio = 3/13 = 0.23 < 0.30
floor — alpha concentrated in AVAX/BCH/BNB only) and **Lesson #15 non-focus
PASS 4-cond** (Bonferroni adj_p ≈ 0.18 > 0.10, diversity 3/13 < 7/13).
Cell 4 not promoted as separate paradigm.

## Hypothesis

Beta = rolling 30d regression slope of alt daily return on BTC daily return.
Beta z-score = 60d rolling z on the beta series. Trigger: |beta_z| ≥ 2.0
combined with BTC 1d direction. Hold: 5d focus, 1/3/5/10/20 sweep.

4-cell layout:
- **Cell 1** (focus): beta_z > +2.0 × BTC up_1d → alt LONG (amplification +
  momentum). Hypothesized strong positive.
- Cell 2: beta_z > +2.0 × BTC dn_1d → alt SHORT (amplification + reversal).
- Cell 3: beta_z < −2.0 × BTC up_1d → alt SHORT (decoupling, undershoot).
- Cell 4: beta_z < −2.0 × BTC dn_1d → alt LONG (decoupling, outperform
  drawdown).

## Sample density (Lesson #11 prescreen)

- Daily panel: 14 syms × 862 days = 12,068 daily obs (2024-01-02 → 2026-05-12)
- Triggers at |beta_z| ≥ 2.0, hold 5d, valid BTC dir: **1,106 total**
- Per-cell n: cell 1 = 289, cell 2 = 275, cell 3 = 280, cell 4 = 262
- All four cells > 30 floor by ≥ 8x. Prescreen PASS.

Mint host BTCUSDT 1m count = 1,241,280 (Lesson #6 verification PASS).

## Focus cell 1 (R-1 verdict)

| Metric | Value |
|---|---|
| n_trades | 289 |
| mean_bp (net) | **−196.50** |
| signal_t_excess | **−3.83** (gate A FAIL: < +2.0) |
| ci_lower_bp | **−350.83** (gate B FAIL: < 0) |
| perm_p_two_sided | 0.0000 (gate C technically PASS but observation is on the wrong side) |
| three_gate.all_pass | **False** |

**Verdict: R1_FAIL** — focus hypothesis falsified, observed mean strongly
opposite of prediction. Beta amplification × BTC up does **not** translate
into alt LONG continuation alpha; instead the 5d forward shows mean reversion.

### Hold sweep (focus z=2.0, cell 1)

| hold_d | n | mean_bp | t-stat |
|---|---|---|---|
| 1 | 289 | −7.4 | −0.25 |
| 3 | 289 | −21.0 | −0.45 |
| 5 | 289 | **−196.5** | −3.30 |
| 10 | 289 | **−272.7** | −3.73 |
| 20 | 289 | **−318.3** | −3.28 |

Monotonic worsening — the longer the hold after a high-beta-amplification +
BTC-up trigger, the worse alt LONG performs. This is anti-momentum and the
opposite of the hypothesis (Carhart-style amplification follow-through).

## Symmetric variant breakdown (Lesson #19 mandatory)

| Cell | Trigger | Direction | n | mean_bp |
|---|---|---|---|---|
| 1 (focus) | high-beta-z × BTC up | LONG | 289 | **−196.5** |
| 2 | high-beta-z × BTC dn | SHORT | 275 | **−104.9** |
| 3 | low-beta-z × BTC up | SHORT | 280 | +11.5 |
| 4 | low-beta-z × BTC dn | LONG | 262 | **+165.3** |

**Not broad-falsified**: cell 3 ≈ zero, cell 4 strongly positive. Cells 1 +
2 are both strongly negative — this **rules out** the "broad mechanism dud"
case (Lesson #19's 80-paradigm precedent where all 4 cells were negative).
Instead the asymmetry suggests:

- **High-beta-z (cells 1, 2)** = momentum exhaustion — after a 30d window
  where the alt was unusually sensitive to BTC, the next 5d sees alt
  decouple/mean-revert in BOTH BTC up and BTC down regimes. Both LONG (cell 1)
  and SHORT (cell 2) directional bets lose.
- **Low-beta-z (cells 3, 4)** = decoupling regime; cell 4 (BTC down) shows
  alt outperforms BTC drawdown materially (+165bp 5d), while cell 3
  (BTC up) is near-zero (+11bp).

The asymmetry between cell 1 (−196bp) and cell 4 (+165bp) is **361bp**.
Stronger than 76-paradigm SHORT-vs-LONG 0.95σ but weaker than 70-paradigm
BTC-RV mirror 13σ. The mechanism asymmetry is real but not catastrophic
mirror antipattern level.

## Cell 4 sub-finding evaluation (separate three-gate)

Computed separately (cell 4 LONG net returns vs full daily candidate pool):

| Metric | Value | Gate |
|---|---|---|
| n_trades | 262 | — |
| mean_bp (net) | +165.27 | — |
| obs_t | +2.998 | — |
| null_mean_t | +0.475 | — |
| signal_t_excess | **+2.523** | A: PASS (≥ 2.0) |
| ci_lower_bp | +3.19 | B: PASS (> 0) |
| ci_upper_bp | +318.16 | — |
| perm_p_two_sided | 0.0030 | C: PASS (≤ 0.10) |
| **three_gate.all_pass** | **True** | — |

Three-gate PASS in isolation. Hold sweep also fully consistent:

| hold_d | cell 4 mean_bp | t-stat |
|---|---|---|
| 1 | +44.5 | +1.41 |
| 3 | +129.5 | +2.72 |
| 5 | +165.3 | +3.00 |
| 10 | +248.4 | +2.82 |
| 20 | +368.1 | +2.29 |

Monotonic increasing — alpha grows with horizon (cell 4 = decoupling +
BTC-down rebound). Z-threshold sweep also consistent (z=1.5: +134, z=2.0:
+165, z=2.5: +199 — deeper decoupling = stronger LONG alpha).

### Concentration Gate (Lesson #16)

| Dimension | Value | Floor | Result |
|---|---|---|---|
| quarter_pos_t_ratio | 6/8 = 0.75 | 0.50 | **PASS** |
| symbol_ci_pos_ratio | 3/13 = 0.23 | 0.30 | **FAIL** |
| n_symbols_ci_pos | 3 | 3 (absolute) | borderline |

Per-symbol bootstrap CI:

| Symbol | n | mean_bp | ci_lower_bp | ci_pos |
|---|---|---|---|---|
| ADAUSDT | 18 | +197.8 | −68.3 | False |
| **AVAXUSDT** | 11 | +327.9 | **+134.4** | **True** |
| **BCHUSDT** | 19 | +679.7 | **+385.3** | **True** |
| **BNBUSDT** | 21 | +144.8 | **+13.1** | **True** |
| DOGEUSDT | 21 | +239.4 | −90.4 | False |
| ETHUSDT | 14 | +271.2 | −19.4 | False |
| FILUSDT | 16 | +51.0 | −548.7 | False |
| LINKUSDT | 30 | +152.0 | −103.7 | False |
| **LTCUSDT** | 27 | **−408.5** | **−674.0** | **False (strongly negative)** |
| NEARUSDT | 31 | −15.2 | −401.0 | False |
| SOLUSDT | 20 | +198.0 | −187.5 | False |
| WIFUSDT | 19 | +293.9 | −147.4 | False |
| XRPUSDT | 15 | +528.9 | −155.7 | False |

Alpha is **concentrated in AVAX + BCH + BNB only**. LTC has strongly negative
ci (paradoxically negative under the same trigger). This is genuine
heterogeneity — not a universal cross-symbol mechanism.

### Lesson #15 non-focus PASS 4-cond promotion test

| Condition | Status |
|---|---|
| (a) all 4 R-1 gates pass (3-gate + diversity ≥ 7/13) | **FAIL** — diversity 3/13 = 0.23 |
| (b) separate R-1 replication ±10% | Not executed (gated by (a) failure) |
| (c) Bonferroni adj_p ≤ 0.10 (sweep tests count: 4 cells × 3 z × 5 hold = 60) | **FAIL** — 0.003 × 60 = 0.18 |
| (d) hold sweep sign consistency | **PASS** — monotonic positive 1d/3d/5d/10d/20d |

Cell 4 fails (a) and (c) of the 4-cond. **Not eligible for separate
paradigm promotion** despite isolated three-gate PASS.

## Distinct-from-retired analysis (Step 1 confirmation)

| Retired family | Why this paradigm is distinct |
|---|---|
| `btc_eth_5m_corr_breakdown_family` (74-77) | Correlation ρ is scale-free association [-1,1]; beta is regression slope (scale-dependent directional sensitivity, unbounded). Different statistic. |
| `geometric_path_metrics_family` (78) | Path tortuosity/fractality; beta is cross-asset regression coefficient. Different domain. |
| `funding_oi_joint_squeeze_family` (73, 79) | Funding × OI joint event detection; no OHLCV regression component. |
| `oi_premium_5m_decoupling` (80, broad-falsified) | 5m joint level z-event; beta is daily derived regression coefficient, sign-conditional 4-cell. |
| `cross_sec_30d_mom` (64), `cross_sec_weekly_mr` (63) | Cross-sectional ranking across 14 syms; beta paradigm is per-alt asynchronous pairwise event with BTC, not rank rotation. |

Confirmed: rolling-beta paradigm occupies a distinct statistical dimension
not covered by any retired family.

## Lessons extracted

### Lesson #20 candidate — Sign-conditional 4-cell exposes hypothesized
mechanism asymmetry but trigger does not generalize as a universal paradigm

The 4-cell symmetric layout (Lesson #19) successfully:
1. Eliminated broad-falsified case (cells 3, 4 not negative).
2. Surfaced a sub-quadrant alpha (cell 4 separate three-gate PASS).
3. Diagnosed per-symbol concentration (3/13 alts carry alpha, 1 alt
   actively contradicts).

But the cell 4 alpha is **heterogeneous, not universal**: AVAX/BCH/BNB
specifically. This is consistent with paradigm 77's lesson (per-alt
ci_lower 2/10) — aggregate three-gate PASS with concentrated symbol set
should be halted at R-1 (Concentration Gate) per Lesson #16.

**Lesson #15 (d) hold sweep sign consistency** held strongly (monotonic
+44 → +368 bp). Hold consistency alone is **insufficient** to override
diversity + Bonferroni failure (consistent with original 4-cond design).

### Cell-1 anti-momentum sub-finding

Cell 1 mean −196.5bp / hold sweep monotonic worsening (−7 → −318 bp) is a
genuine and statistically strong **anti-momentum signal**: high-beta-z
amplification + BTC-up direction does NOT produce alt LONG continuation;
it produces alt MEAN REVERSION (alt SHORT would profit). However a mirror
SHORT trial is exactly the antipattern blocked by Lesson #8 (paradigm 70
mirror antipattern) — separate R-1 required if pursued.

Note also that cell 2 (high-beta-z × BTC dn × SHORT) is **also negative**
(−105 bp). The mean-reversion is bidirectional: after high-beta-z, both
LONG-with-BTC-up and SHORT-with-BTC-dn lose. This argues against a clean
"high-beta = mean revert" mirror hypothesis — both directional bets after
high-beta-z lose, suggesting **trade-the-decoupling** (cell 3/cell 4)
is the actionable insight, not trade-the-amplification.

## Tier 4 retire recommendation

**Do NOT retire** `rolling_beta_breakdown_family`. Reasons:
1. Cell 4 isolated three-gate PASS demonstrates the statistic carries
   directional information.
2. Concentration on AVAX/BCH/BNB could potentially be repackaged as a
   narrow-scope paradigm with explicit per-symbol restriction (e.g.,
   "rolling-beta decoupling + BTC down + LONG for AVAX/BCH/BNB only,
   hold 10-20d").
3. The asymmetry between cells 1 and 4 (361 bp gap) is informative for
   future beta-related hypotheses.

However:
- Do **not** dispatch a mirror cell 1 SHORT R-1 (Lesson #8 antipattern).
- Do **not** dispatch a cell 4 universal-alts retry without explicit
  per-symbol scope (Lesson #16 + Lesson #15 4-cond).
- A narrow `rolling_beta_decoupling_btcdn_3sym_long` variant could be a
  separate R-1 candidate if user wants to pursue.

## Files

- Script: `backend/scripts/research/rolling_beta_regime_breakdown_r1.py`
- Metrics: `r1__metrics.json`
- Per-symbol: `r1__per_symbol.csv` (cell 1 breakdown)
- Hold sweep: `r1__hold_sweep.csv` (4 cells × 5 holds = 20 rows)
- Z threshold sweep: `r1__z_sweep.csv` (4 cells × 3 z = 12 rows)
- This note: `GRAVEYARD_NOTE.md`

## R-2 recommendation

**STOP**. R-1 FAIL on focus, sub-finding fails Lesson #15 4-cond. No R-2.

If user wants to pursue cell 4 as a narrow-scope paradigm with explicit
per-symbol restriction (AVAX/BCH/BNB), that requires a separate paradigm
registration (e.g., `rolling_beta_decoupling_btcdn_avax_bch_bnb_long_10d`)
with its own R-1 — not an extension of paradigm 81.
