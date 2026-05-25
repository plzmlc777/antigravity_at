# Graveyard — paradigm 130 `alt_realized_corr_breakdown_eth_per_pair_directional_4h`

**Verdict**: `BROAD_FALSIFIED_A_FOCUS_NEGATIVE` (with NEW Lesson #52 amendment candidate: **SHORT-side gross-positive inverse drift artifact**)
**Date**: 2026-05-21 09:42 KST
**Killed at**: R-1 PoC three-gate + Concentration Gate + Lesson #52 detection
**Counter**: 129 → 130

## Hypothesis recap

Per-pair (alt, ETHUSDT) realized correlation breakdown at 4h frame.

```
benchmark: ETHUSDT (NOT BTC, BTC local DB 142d Lesson #30 short-window)
statistic: rho_30d = corr(log_ret_4h_alt, log_ret_4h_ETH) on 30-day rolling
trigger: rho_30d <= per-pair empirical p10 (per-pair threshold 0.49 - 0.70)
direction: sign(log_ret_4h alt at trigger bar)
hold: 4h forward
debounce: 8h
universe: 11 alts (paradigm 129 cohort minus ETH benchmark)
```

## Lifecycle summary

| Phase | Verdict | Key metric |
|---|---|---|
| R-0 prescreen | R0_READY_FOR_R1 | n=2592, 11 alts × 755-799d, per-pair p10 0.49-0.70, stratified A_focus +31.73bp t=1.06 |
| R-1 PoC | **BROAD_FALSIFIED_A_FOCUS_NEGATIVE** | 0/4 quadrants three-gate PASS, 0/4 Concentration Gate PASS, **SHORT-side gross-positive inversion** |

## R-1 results — 4-quadrant SNT (Lesson #19)

| Quadrant | n | gross_bp | net_bp | obs_t | null_t | sigex | ci_lower_bp | perm_p_above | 3-gate |
|---|---|---|---|---|---|---|---|---|---|
| A_focus rho<p10 ∩ pos × **LONG** | 1266 | **-8.77** | -24.77 | -3.76 | -2.92 | -0.84 | -37.51 | 0.808 | FAIL all |
| A_mirror rho<p10 ∩ pos × **SHORT** | 1266 | **+8.77** | -7.23 | -1.10 | -2.64 | +1.54 | -20.45 | 0.059 | FAIL (excess+ci) |
| B_focus rho<p10 ∩ neg × **SHORT** | 1326 | **+18.59** | +2.59 | +0.33 | -2.75 | **+3.08** | -12.84 | 0.000 | FAIL (ci) |
| B_mirror rho<p10 ∩ neg × **LONG** | 1326 | **-18.59** | -34.59 | -4.41 | -2.95 | -1.46 | -50.61 | 0.939 | FAIL all |

## Concentration Gate (Lesson #16) — all 4 quadrants FAIL

| Quadrant | q_pos_t / q_meas | quarter_ratio | n_ci_pos_syms / n_meas | symbol_ratio | gate |
|---|---|---|---|---|---|
| A_focus_LONG | 1/9 | 0.11 ✗ | **0/11** | 0.00 ✗ | FAIL |
| A_mirror_SHORT | 5/9 | 0.56 ✓ | **0/11** | 0.00 ✗ | FAIL |
| B_focus_SHORT | 5/9 | 0.56 ✓ | **0/11** | 0.00 ✗ | FAIL |
| B_mirror_LONG | 0/9 | 0.00 ✗ | **0/11** | 0.00 ✗ | FAIL |

**0/11 symbols had ci_lower>0 in ANY quadrant — pure systemic artifact, NOT per-pair mechanism.**

## Lesson #52 CANDIDATE — NEW INVERSE PATTERN DISCOVERY

Original Lesson #52 candidate (paradigm 99/129 precedent): "universe LONG drift artifact"
where A focus LONG + B mirror LONG both gross > 0.

paradigm 130 exhibits **OPPOSITE pattern** — `is_long_drift_artifact = False` but:
- Both LONG quadrants gross **negative** (-8.77 / -18.59)
- Both SHORT quadrants gross **positive** (+8.77 / +18.59)
- Mathematical mirror property preserved (A_focus gross = -A_mirror gross by construction)

### Lesson #52 amendment candidate (1st dogfood of inverse direction)

**NEW sub-class E candidate: Trigger-conditional SHORT-bias artifact**
- During correlation breakdown events (rho<p10), the underlying alts have **already moved sufficiently** that mean-reversion is the dominant systemic effect
- LONG continuation FAILS regardless of trigger sign → trigger captures **overextension** not **directional info**
- SHORT positions gain gross BUT 0/11 syms ci_pos → SHORT gain is **universe-level mean-reversion drift during decoupling events**, NOT per-pair mechanism alpha

This is **structurally DIFFERENT from paradigm 129's LONG-drift bull-market artifact**:
- paradigm 129: bull market 2024 lifts all alts → LONG gross+ regardless of trigger
- paradigm 130: correlation breakdown events ARE overextension events → SHORT gross+ regardless of trigger sign within the conditional sample

### Detection signature for Lesson #52 amendment

```
both_long_gross_neg AND both_short_gross_pos AND
all_per_sym_ci_pos < 3 in EVERY quadrant AND
trigger uses conditional-overextension event detection (correlation/vol/RV percentile)
→ SHORT-side conditional-mean-reversion-drift artifact
```

This is now the **3rd accumulated dogfood of Lesson #52** but with **2 distinct sub-patterns**:
- 99/129: LONG-drift (bull market regime artifact, unconditional)
- 130: SHORT-drift (conditional-overextension trigger artifact)

**Lesson #52 should likely split into:**
- Lesson #52a: unconditional universe-LONG-drift artifact (paradigm 99/129)
- Lesson #52b: conditional-trigger SHORT-bias artifact (paradigm 130) ← NEW candidate

## Lesson #46 REFINEMENT 5th dogfood — sign-flip detection

R-0 stratified n=50×4q sign flips:
- A_focus: [1, 1, -1] flips=1 (Q1 2024 +113bp → Q4 2024 +16bp → Q3 2025 -19bp → 2026Q2 NA)
- B_focus: [1, 1, -1, 1] flips=2

Progressive decay in 2024-2025 was visible in R-0 stratified estimate. Full R-1 showed both A_focus and B_mirror negative — R-0 stratified estimate was **misleading positive** because it weighted 2024Q1 +113bp heavily (bull market regime artifact).

**Sub-amendment dogfood: R-0 stratified estimate alone insufficient**, full R-1 confirmation always required. Lesson #46 stratified is **necessary but not sufficient** prescreen.

## Lesson #44 amendment 12th dogfood — graveyard cross-reference

| Reference paradigm | Status | Distinct claim |
|---|---|---|
| paradigm 62 cross_sec_weekly_mr | GRAVEYARD | DISTINCT: per-pair vs cross-section rank rotation ✓ |
| paradigm 75 cross_symbol_lead_lag | GRAVEYARD | DISTINCT: per-pair Pearson vs cohort-aggregate lag ✓ |
| paradigm 81 rolling_beta_regime | GRAVEYARD | DISTINCT: Pearson rho vs beta coefficient, ETH vs BTC ✓ |
| paradigm 118 realized_correlation_regime_universe | GRAVEYARD | DISTINCT: per-pair vs universe-aggregate ✓ |
| paradigm 99 funding per-sym velocity | GRAVEYARD | PRECEDENT: Lesson #52 detection ✓ |
| paradigm 129 alt_parkinson_range | GRAVEYARD | PRECEDENT: Lesson #52 detection ✓ |
| RUNBOOK_3M_volume_extraction | ANTIPATTERN avoided | No volume axis ✓ |

All distinct claims verified — no DNA duplication.

## Mechanism failure analysis

1. **Correlation breakdown ≠ directional information**: rho<p10 indicates decoupling magnitude but not direction
2. **Conditional sample is post-event overextension pool**: by the time rho_30d drops to p10, the alt has already moved enough to register the decorrelation → trigger is *lagging* indicator of extension
3. **Per-trade gross magnitudes ±8-18bp ≪ 16bp fee floor** in both directions
4. **0/11 Concentration ci_pos in ANY quadrant** confirms NO per-pair mechanism — alpha apparent in SHORT quadrants is systemic mean-reversion drift during conditional sample

## Why correlation paradigms keep failing

Correlation/lead-lag/beta family accumulated graveyards: paradigm 75 + 81 + 118 + 130 (+ 62 cross-sec). The structural issue:

- **Cross-asset correlation statistics are second-moment derivatives** that **inherit lag from rolling windows**
- 30d × 4h rolling = 180-bar lookback → trigger fires AFTER divergence has accumulated
- Decoupling events captured AFTER the fact carry **no forward directional information**
- This is structurally similar to paradigm 129 Parkinson range — both are **magnitude/structural statistics that don't carry directional info**

## Family advisory escalation recommendation

Correlation-based cross-asset signal family (paradigm 75/81/118/130) is at:
- 4 graveyards across 4 distinct sub-mechanisms (lead-lag / beta / universe-aggregate / per-pair breakdown)
- Advisory caution → **Tier 4 candidate retire** at next correlation paradigm graveyard

## Recommendations

1. **NO further correlation-axis paradigm dispatch** without explicit Lesson #52a/52b separation framework
2. **Lesson #52 split formalization**: 52a (unconditional bull-drift) vs 52b (conditional-overextension SHORT-bias) — promote to confirmed when 1 more dogfood of either subtype occurs
3. **Paradigm 130 SHORT-side B_focus partial signal** (sigex +3.08 perm_p 0.000) is **not** mechanism-confirmable due to 0/11 ci_pos — DO NOT chase as narrow-scope candidate
4. **Continuous-parallel policy maintained**: next paradigm 131 dispatch should pivot AWAY from correlation/range/structural-second-moment family entirely
5. **2-streak non-PASS** approaches 3-streak — review next-candidate selection rigorously
