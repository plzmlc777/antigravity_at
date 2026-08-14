# Paradigm 239 — alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h — GRAVEYARD (R-1)

**Date**: 2026-07-28
**Phase reached**: R-1 (PoC on SOLUSDT, single-symbol full sweep 324 cells)
**Verdict**: `R1_GRAVEYARD_FEE_SYMMETRIC_BROAD_FALSIFIED`
**Lessons applied**: #11, #28, #37, #39, #40, #61, #77, #79

## Hypothesis

BTC market dominance undergoes slow regime shifts that predict alt rotation. Signal:
`dom_z = 90d rolling z-score of (btc_7d_ret − alt_basket_7d_ret)` triggers bilateral
entries on 14 alts at 1-3d holds. Universe = BTCUSDT + 13 alts (cache-restricted:
ADA/AVAX/BCH/BNB/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP).

## R-0 Prescreen — 9/9 PASS

| Item | Test | Result |
|---|---|---|
| 1 | Lesson #61 slug grep | No prior paradigm uses this slug; only mentioned in NEXT_PARADIGM_RUNBOOK.md queue |
| 2 | Lesson #79 predictive-content pretest | **max \|corr\| = 0.10113 (DOGE h=3, OOS half)**; PASS (>0.02) |
| 3 | Lesson #62 DNA 5-dim | ≤ 2/5 overlap vs prior paradigms (cross-asset macro spread substrate = novel) |
| 4 | Lesson #56 family proxy | Distinct from cross_sectional_momentum (within-alt ranking) |
| 5 | Lesson #28 substrate audit | BTC + 13 alts, 846 aligned daily closes (2024-01-16 → 2026-05-12) |
| 6 | Lesson #11 sample density | \|z\|≥1.0: 202/750 days (26.9%, ~98/yr); \|z\|≥1.5: 88 (11.7%, ~42/yr); \|z\|≥2.0: 36 (4.8%, ~17/yr) |
| 7 | Lesson #40 structural feasibility | z.min=-4.12, z.max=+2.67; all thresholds achievable in both directions |
| 8 | Lesson #39 direction axis | sign(dom_z) is cross-asset spread sign, non-bar_direction |
| 9 | Lesson #77 substrate class | Cross-asset macro regime (partial compliance per §239 dispatch brief) |

R-0 output: `r0_prescreen__metrics.json`

## R-0 KEY WARNING — Correlation direction INVERTED vs hypothesis

Lesson #79 OOS half correlations all POSITIVE across (sym × hold):

```
SOLUSDT_h1  +0.008  |  SOLUSDT_h2  +0.036  |  SOLUSDT_h3  +0.049
AVAXUSDT_h1 +0.045  |  AVAXUSDT_h2 +0.074  |  AVAXUSDT_h3 +0.089
DOGEUSDT_h1 +0.048  |  DOGEUSDT_h2 +0.084  |  DOGEUSDT_h3 +0.101
```

Positive corr(dom_z, fwd_ret) means "when BTC outperforms alts (dom_z ↑), alts continue
to underperform NEXT" — i.e. cross-asset momentum CONTINUATION, opposite to the paradigm's
proposed rotation-reversal mechanism. R-1 tested both directions via 4-quadrant SNT, so
the correct direction (B_mirror = dom_z ≥ T → LONG alts, which is the momentum-continuation-
opposite interpretation) was included, and it still failed the fee-aware 3-gate.

## R-1 PoC — SOL sweep 324 cells

Grid: window ∈ {60,90,120} × spread_days ∈ {5,7,14} × threshold T ∈ {1.0,1.5,2.0} ×
hold ∈ {1d,2d,3d} × quadrant ∈ {A_focus, A_mirror, B_focus, B_mirror} = 324 cells.

- **72 / 324** cells pass weak concentration gate (mean_bp>0, t>0, sharpe>0, n≥30)
- Passing distribution skewed: B_mirror 12 / A_focus 4 / A_mirror 3 / B_focus 1 (of top 20)

### Top-4 cells fee-aware perm + bootstrap CI (Lesson #37 verify)

| w | sp | T | h | quadrant | n | signal_t_excess | ci_lower_bp | perm_p_2s | perm_p_1a | obs_t | null_mean_t | gate3 |
|---|----|---|---|----------|---|----|----|----|----|----|----|------|
| 120| 5 |2.0|1|A_focus  |35 |1.487|-20.94|0.194|0.071|1.333|-0.154|FAIL|
| 90 | 7 |1.0|2|B_mirror |59 |1.336|+46.23|0.191|0.088|1.276|-0.060|FAIL|
| 90 | 7 |1.0|1|B_mirror |89 |1.256|-13.26|0.228|0.094|1.158|-0.098|FAIL|
| 120| 7 |1.0|3|B_mirror |43 |1.158|-13.71|0.282|0.121|1.069|-0.089|FAIL|

3-gate criteria: `signal_t_excess ≥ 2.0` AND `ci_lower > 0` AND `perm_p_two_sided ≤ 0.10`.
**0 / 4 cells pass**. Best signal_t_excess = 1.49 (< 2.0). Best ci_lower is +46bp but that cell fails perm_p (0.19).

### Lesson #39 sub-class A verdict — BROAD_FALSIFIED

`subclass_A_all_pairs_broad_fee_symmetric = True` — for every (w, sp, T, h) tuple in the
sweep, the pair `A_focus + A_mirror` sums to **exactly -16.00 bp** (= -2 × FEE_RT floor).

Sample (top 10 by sum_bp, all identical to fee floor):

```
w=60 sp=5 T=1.0 h=1  af=+14.02  am=-30.02  sum=-16.00
w=60 sp=5 T=1.0 h=2  af=+19.67  am=-35.67  sum=-16.00
w=60 sp=5 T=1.5 h=2  af= -4.61  am=-11.39  sum=-16.00
w=60 sp=5 T=2.0 h=3  af=-74.66  am=+58.66  sum=-16.00
```

This is the classical **Lesson #39 sub-class A pattern**: any apparent per-quadrant edge is
exactly cancelled by its mirror. The trigger `|dom_z| ≥ T` produces zero directional
information; the joint signal is a pure direction-bet dominated by fee drag.

## Root cause

1. **Trigger has structural zero-info**: cross-asset return spread mean-reverts perfectly over
   the 1-3d hold horizon. `A_focus + A_mirror = -2×fee` for ALL 27 (w, sp, T, h) tuples means
   the direction axis `sign(dom_z)` carries no useable predictive edge over fees.
2. **Weak positive correlation (0.05-0.10) is INSUFFICIENT for fee-aware t-stat**: Lesson #79
   pretest correctly flagged predictive content above the 0.02 threshold, but the mechanism's
   raw predictive strength (corr ~0.05-0.10) translates to obs_t ~1.0-1.3, well below the
   2σ signal_t_excess required to clear the fee-drift null (which itself has null_mean_t ~
   -0.1 due to fee floor).
3. **Momentum-continuation direction (B_mirror) has weak signs** but the empirical corr is
   insufficient to justify 8bp round-trip fees at 1-3d hold horizons. To pass at these fees
   would require |corr| > ~0.15 or hold extension beyond 3d (out of paradigm scope).

## Lesson candidacy

**Candidate Lesson #79-follow-up**: *"Lesson #79 predictive-content pretest at corr threshold
0.02 is a NECESSARY but NOT SUFFICIENT gate for cross-asset regime paradigms at daily holds
+ 8bp fees. Cross-asset spread paradigms with corr ∈ [0.05, 0.15] on 1-3d holds will
Lesson #39 sub-class A fee-symmetric BROAD_FALSIFIED at R-1 because the effect size is
below the fee floor. Prescription: for cross-asset spread paradigms, either (a) extend hold
to ≥ 7d, (b) require |corr| ≥ 0.15 on OOS half, or (c) use a fee-reduced strategy (limit
orders / longer holds with fewer trigger events)."*

Recommend elevating to CONFIRMED-자격 after one more cross-asset paradigm hits identical
fail mode (this is 1st dogfood; paradigm 239 established the pattern).

## Artifacts

- code: `backend/scripts/research/alt_btc_dominance_regime_shift_r0_prescreen.py`
- code: `backend/scripts/research/alt_btc_dominance_regime_shift_r1.py`
- code: `backend/scripts/research/alt_btc_dominance_regime_shift_r1_top3_verify.py`
- metrics: `backend/runs/research_track/alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h/r0_prescreen__metrics.json`
- metrics: `backend/runs/research_track/alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h/r1__metrics.json`
- metrics: `backend/runs/research_track/alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h/r1__top_cells_verify.json`

## Next paradigm recommendation

Cross-asset macro-substrate family is now 1× dogfood (Lesson #39 sub-A at daily holds).
Do NOT immediately retry with variant window/spread — the Lesson #79 corr ceiling at ~0.10
predicts identical fail. If a future cross-asset paradigm is proposed, R-0 MUST include:

1. Lesson #79 pretest EXTENDED: require |corr| ≥ 0.15 for 1-3d hold paradigms at 8bp fees.
2. OR shift to ≥ 7d hold windows (paradigm 239 was scope-restricted to 1-3d per dispatch brief).
3. OR pivot to non-fee-symmetric structural triggers (e.g., unlock cliffs, listings, delistings).

Immediate next candidate from NEXT_PARADIGM_RUNBOOK.md queue — pick one not in cross-asset
spread family.
