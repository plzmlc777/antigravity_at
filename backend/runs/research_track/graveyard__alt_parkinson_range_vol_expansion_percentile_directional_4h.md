# Graveyard — paradigm 129 `alt_parkinson_range_vol_expansion_percentile_directional_4h`

**Verdict**: `BROAD_FALSIFIED_FEE_FLOOR_LONG_DRIFT_ARTIFACT`
**Date**: 2026-05-21 09:28 KST
**Killed at**: R-1 PoC three-gate + Concentration Gate
**Counter**: 128 → 129

## Hypothesis recap

Parkinson range-based variance estimator at 4h frame, per-symbol 30-day rolling
percentile p90 threshold (range expansion regime), directional signal based on
sign of 4h log-return at trigger bar, 4h forward hold.

```
park = (1 / (4*ln(2))) * (ln(H/L))^2
trigger: park >= rolling_p90_30d (per-symbol)
direction: sign(log_ret_4h at trigger)
hold: 4h forward
debounce: 8h
universe: 12 alts (ADA/BTC excluded per Lesson #30 short-window)
```

## Lifecycle summary

| Phase | Verdict | Key metric |
|---|---|---|
| R-0 prescreen | R0_READY_FOR_R1 | n=4344 triggers, 10/10 quarters measurable, Lesson #46 sign-flip A_focus=3/B_focus=2 (advisory unstable) |
| R-1 PoC | **BROAD_FALSIFIED_FEE_FLOOR_LONG_DRIFT_ARTIFACT** | 0/4 quadrants three-gate PASS, 0/4 Concentration Gate PASS |

## R-1 results — 4-quadrant SNT (Lesson #19)

| Quadrant | n | gross_bp | net_bp | obs_t | null_t | sigex | ci_lower_bp | perm_p_above | 3-gate |
|---|---|---|---|---|---|---|---|---|---|
| A_focus park_p90 ∩ pos × **LONG** | 2008 | **+17.35** | +1.35 | +0.21 | -3.75 | **+3.96** | **-11.24** | 0.000 | FAIL (ci) |
| A_mirror park_p90 ∩ pos × SHORT | 2008 | -17.35 | -33.35 | -5.22 | -3.37 | -1.85 | -45.39 | 0.966 | FAIL all |
| B_focus park_p90 ∩ neg × **SHORT** | 2336 | -11.11 | -27.11 | -4.88 | -3.66 | -1.22 | -38.18 | 0.889 | FAIL all |
| B_mirror park_p90 ∩ neg × **LONG** | 2336 | **+11.11** | -4.89 | -0.88 | -4.04 | **+3.15** | **-15.95** | 0.001 | FAIL (ci) |

## Concentration Gate (Lesson #16) — all 4 quadrants FAIL

| Quadrant | q_pos_t / q_meas | quarter_ratio | n_ci_pos_syms / n_meas | symbol_ratio | gate |
|---|---|---|---|---|---|
| A_focus_LONG | 6/10 | 0.60 ✓ | **0/12** | 0.00 ✗ | FAIL |
| A_mirror_SHORT | 1/10 | 0.10 ✗ | 0/12 | 0.00 ✗ | FAIL |
| B_focus_SHORT | 3/10 | 0.30 ✗ | 0/12 | 0.00 ✗ | FAIL |
| B_mirror_LONG | 4/10 | 0.40 ✗ | 0/12 | 0.00 ✗ | FAIL |

**0/12 symbols had ci_lower>0 in ANY quadrant — pure systemic LONG drift artifact, NOT per-symbol mechanism.**

## Lesson #39 sub-class identification (manual detection per skill bug workaround)

Both LONG quadrants (A_focus pos×LONG, B_mirror neg×LONG) show:
- sigex ≥ 3 above fee-drift null
- gross_bp positive (+17.35 / +11.11)
- BUT ci_lower deeply negative (-11.24 / -15.95)
- BUT 0/12 syms ci_pos

Both SHORT quadrants (A_mirror pos×SHORT, B_focus neg×SHORT) show:
- sigex deeply negative
- gross_bp negative (-17.35 / -11.11)

**Sub-class detection: Lesson #8 amendment candidate** (universe LONG bias artifact)
- LONG-side wins regardless of trigger sign convention
- SHORT-side loses regardless of trigger sign convention
- Mathematical mirror property — by construction, if A_focus shows gross +X then A_mirror shows gross -X
- The +17.35bp / +11.11bp gross on LONG sides is fundamentally **universe upward drift over 2024Q1–2026Q2**, NOT range-expansion alpha

This is the SAME pattern documented in paradigm 99 (funding family per-sym velocity):
*"A focus + B mirror 모두 양수 = leverage shock magnitude → general upward bias"*

paradigm 129 is the **2nd dogfood** of Lesson #8 amendment candidate (LONG-drift artifact).

## Lesson #39 explicit sub-class antipattern

This paradigm exhibits:
- Sub-class A (broad-uniform-negative): NO (LONG side gross +)
- Sub-class B (mechanism-inverted with mirror real concentration): NO (0/12 syms ci_pos in mirror)
- **NEW sub-class candidate D: universe-level drift artifact masquerading as paradigm alpha**
  - LONG quadrant gross > 0 due to systemic upward drift, NOT trigger semantics
  - Per-symbol Concentration Gate 0/12 ci_pos confirms drift attribution
  - Both LONG quadrants would show identical "alpha" if trigger were RANDOM

## Primary failure mode

1. **Range expansion regime (Parkinson p90) does NOT carry directional information** — per-symbol per-trade edge near fee floor (1.35bp / -4.89bp net)
2. **0/12 syms Concentration Gate PASS** — no symbol-level mechanism alpha
3. **LONG-drift artifact**: both LONG quadrants show positive gross_bp due to universe upward drift, NOT range mechanism
4. **A_focus apparent +3.96 sigex is artifact of LONG-drift baseline** vs SHORT-fee-drift null

## Why range info (Parkinson) failed where return RV (paradigm 67/68/69) showed partial life

Hypothesis: Range estimator captures intra-bar volatility magnitude but **discards directional information** (H-L is symmetric). The directional component comes only from `sign(log_ret_4h at trigger)` which is a **noisy 4h close-to-close signal** at trigger bar — not informative for next 4h.

paradigm 69 (R-5 seeded BTC RV highvol) used:
- BTC systemic high-vol filter (regime conditional)
- 13 alt LONG (universe direction not from trigger)
- 240m hold

paradigm 129 used:
- per-symbol intrinsic range (NO regime filter)
- direction from trigger-bar sign (NOT robust)
- 4h hold

The directional signal source (trigger-bar 4h sign vs systemic BTC regime) is the critical missing piece. Per-symbol Parkinson + trigger-bar sign = pure noise.

## Lessons applied / dogfood'd

| Lesson | Applied | Outcome |
|---|---|---|
| #11 sample density | per-quarter ≥30, 10/10 quarters PASS | density not a barrier |
| #16 Concentration Gate | per-quarter t + per-sym CI | 0/12 syms PASS — drift attribution evident |
| #19 SNT 4-quadrant mandatory | Single R-1 batch all 4 quadrants | mathematical mirror property visible |
| #21 axis stacking | 1 trigger axis (no stacking) | no axis-stack confound |
| #28 substrate availability | 12/12 syms 755-799d 4h bars | substrate OK |
| #30 short-window | ADA/BTC excluded (143/142d local DB) | followed |
| #40 structural threshold | Percentile rank (NOT z-score on non-neg aggregate) | PASS |
| #44 amendment 10+1 dogfood xref | 11 paradigms xref'd in R-0 | dogfood #11 confirmed |
| #45 family-distinct HMM avoidance | Explicit p90 (not HMM) | PASS |
| #46 REFINEMENT temporal-stratified R-0 | 50×4q + sign-flip detection | A_focus 3 flips / B_focus 2 flips advisory caught instability |
| #50 first-burst-sign N/A | 4h frame > 5m scope | N/A |

## NEW Lesson candidate

**Lesson #51 candidate** (2nd dogfood of LONG-drift artifact, paradigm 99 1st):
- Title: *"Universe LONG drift artifact in 4-quadrant SNT — LONG-side both quadrants positive without per-symbol concentration = systemic drift, NOT paradigm alpha"*
- Detection rule: if quadrants {A_focus_LONG, B_mirror_LONG} both gross > 0 AND ci_lower < 0 in both AND symbol_ci_pos_ratio < 0.1 in both, attribute to LONG drift artifact (Lesson #8 amendment / paradigm 99 2nd dogfood = paradigm 129)
- Confirmed once Lesson #51 reaches 2+ dogfoods (currently 1: paradigm 129; paradigm 99 was funding-family which had only 1 LONG-side check)
- Mitigation: subtract universe-level LONG-drift mean from quadrant edge before three-gate evaluation, OR require BOTH LONG quadrants AND BOTH SHORT quadrants gross pass before promoting

## Family-distinct status post-graveyard

| Family | Status before | Status after | Change |
|---|---|---|---|
| Range estimator (Parkinson/Garman-Klass) | Untried (NEW) | **Single-pair NEGATIVE 1st dogfood** | New family-distinct cohort opened with negative outcome |
| Higher-order moment (RV cousins) | 3+1 retire CANDIDATE | unchanged | range vs RV are distinct families |
| LONG-drift artifact sub-class | Lesson #8 amendment candidate 1 dogfood | **2nd dogfood — promote to amendment confirmed** | paradigm 129 explicit dogfood |

## Recommendation for next paradigm 130

Path 1 (highest priority): **Different DIRECTIONAL signal source** — paradigm 129 failed because trigger-bar sign was noisy. Test paradigms that derive direction from external/systemic source:
- `alt_funding_rate_extreme_directional_signed_filter_4h` — funding rate sign (NOT magnitude) as DIRECTIONAL filter, hold direction-conditional 4h
- BUT funding family Tier 4 retired — declined

Path 2: **Drawdown PERSISTENCE** (NOT 24h spike paradigm 117) — 14d sustained drawdown ≤−20%, 5d hold, distinct timescale.
- Cohort 12 alts, ~30-65 events/sym at -15%, distinct from paradigm 117 (24h spike, 24h hold)
- WARNING: paradigm 117 graveyard caveat 6 (cohort survivorship -3.86%/trade) raises concern about drawdown-family generalization. R-3 cohort extension may fail.

Path 3 (recommended): **Realized correlation breakdown per-pair (ETH-alt, NOT BTC due to short-window)** — per-pair 4h rolling 30d correlation drops below per-pair p10, direction = sign of alt log-return at break, 4h hold.
- Uses ETH as benchmark (795d available, vs BTC 142d sub-30%)
- Per-pair (NOT cohort aggregate paradigm 75/81)
- Different mechanism: correlation breakdown ≠ range expansion
- Family-distinct from all current paradigms

## Artifacts

- `backend/scripts/research/paradigm129_r0_prescreen.py`
- `backend/scripts/research/paradigm129_r1.py`
- `backend/runs/research_track/alt_parkinson_range_vol_expansion_percentile_directional_4h/r0_prescreen.json`
- `backend/runs/research_track/alt_parkinson_range_vol_expansion_percentile_directional_4h/r1__metrics.json`
- This graveyard report

## Counter

128 → **129** (formal graveyard, candidate counter incremented).

## Continuous-parallel campaign status post-129

- Cumulative paradigms: 129
- R-5 seeded: 10 (paradigm 127+128 Mint deploy 2026-05-21, unchanged)
- Lessons: 31 confirmed + 5 candidates + **NEW Lesson #51 candidate** (LONG-drift artifact 2nd dogfood with paradigm 99)
- Family retire: 8 formal + 2 advisory caution + 4 retire CANDIDATE (unchanged; range-estimator family 1 dogfood not enough to retire)
- Continuous-parallel R-4 PASS streak (127+128) broken by R-1 BROAD_FALSIFIED (129); 1-streak non-PASS
- Lesson #46 REFINEMENT 4th dogfood (sign-flip detected R-0 instability → R-1 graveyard confirmed)
- Lesson #44 amendment 11th dogfood (paradigm 67/68/69/81/116/121/123/124/125/126/127/128 xref'd in R-0)
