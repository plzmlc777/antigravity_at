# Graveyard — paradigm 233 `alt_toptrader_position_lsr_velocity_z_bilateral_4h`

**Verdict**: `R1_FAIL_LESSON_39_SUB_CLASS_A_PERFECT_FEE_SYMMETRIC_ALL_27_CELLS`
**Phase halted**: R-1 PoC (SOLUSDT single-symbol sweep)
**Date**: 2026-07-22 (KST 12:58)
**Mode**: SELF_RECOMMEND autonomous daily dispatch (11th consecutive graveyard)

---

## Hypothesis

The Binance Futures `toptrader_position_ls_ratio` (POSITION-notional-value weighted long/short ratio of top traders) captures WHERE LARGE CAPITAL is deployed. This is fundamentally distinct from `toptrader_account_ls_ratio` (account-count based, used in graveyard `smart_money_lsr_contrarian`) — empirically corr(SOL) = 0.189, confirming column distinction.

The **VELOCITY** (1st derivative, rolling z-score over 12h/24h/48h windows on 5m bars) of this position-ratio was hypothesized to detect **rapid smart-money net-notional repositioning**. Direction was FOLLOW (rising position-LSR velocity → LONG signal, mirroring the smart money's rising net-long notional bias).

**DNA novelty vs prior art**:
1. vs `smart_money_lsr_contrarian` (GRAVEYARD): DIFFERENT column (position vs account), DIFFERENT statistic (velocity vs level), DIFFERENT direction (follow vs contrarian). 3/3 axes distinct.
2. vs `premium_velocity_zscore` (SEEDED R-5): same velocity class but ENTIRELY different substrate (position LSR vs premium/basis).
3. vs `oi_price_decoupling` (SEEDED R-5): different mechanism (position notional flow vs OI/price divergence).

---

## R-0 Prescreen — ALL 9 items PASS

| # | Item | Result |
|---|------|--------|
| 1 | Lesson #61 slug grep | PASS — zero prior slug hits for `toptrader_position_lsr_velocity` |
| 2 | Substrate audit (#28) | PASS — column exists in SOLUSDT_full_metrics.joblib, 253358 rows, 2024-02-21 to 2026-07-19; corr vs account_lsr = 0.189 confirms distinct column |
| 3 | Sample density (#11) | PASS — empirical vel_z>1.5 n=11062, vel_z<-1.5 n=9510 at vw=288; post-decimation to 4h hold >> 30 trades per cell |
| 4 | DNA 5-dim novelty (#62) | PASS — vs graveyard `smart_money_lsr_contrarian`: 3/3 differentiators (column, statistic, direction) |
| 5 | Family proxy outcome (#56) | PASS — position-notional-weight fundamentally different from account-count for smart-money detection |
| 6 | Alpha decay (#55) | N/A — no prior paradigm on this column+transform |
| 7 | Structural threshold feasibility (#40) | PASS — vel_z bilateral range -21.9 to +21.3 observed, easily supports |z|>2 |
| 8 | Lesson #77 non-OHLCV | PASS — signal and direction both microstructure-derived; direction axis = sign(vel_z), NOT bar_direction |
| 9 | Backfill scope | PASS — 0 bytes, existing joblib used |

**R-0 verdict**: PROCEED to R-1.

---

## R-1 Protocol Executed

- Symbol: SOLUSDT (single)
- Grid: `velocity_window` in {144, 288, 576} × `entry_z` in {1.0, 1.5, 2.0} × `hold_bars` in {12, 48, 96} × 4 quadrants = **108 sub-runs / 27 (vw,ez,hold) cells**
- OOS: last 50% of 253358 bars ≈ 2025-05-05 to 2026-07-19 (~440 days)
- Fee: 8bp round-trip (4bp/side × 2)
- Fixed-hold sim, non-overlapping, no SL, no exit-signal (pure signal test)
- Lesson #37 compliance: full sweep verdict scan across ALL cells

---

## Findings

### Full sweep result: 0/54 focus cells pass 3-gate

- n_focus_passing (alpha>0 AND sharpe>0 AND mean_net_bp>0 AND n>=30): **0/54**
- n_mirror_passing: **0/54**
- Best A_focus: `vw288_ez2.0_h48_A_focus` alpha=+0.37% sharpe=-0.69 mean_net_bp=-3.6 n=1284 (nominal alpha crossing zero from fee drag, NOT a real edge)
- Best B_focus: `vw576_ez2.0_h96_B_focus` alpha=+0.65% sharpe=-0.59 mean_net_bp=-5.7 n=763 (same — nominal only)
- 52/54 focus cells: alpha < 0 AND sharpe < 0 (unambiguously fee-drag-losing)

### Lesson #39 sub-class A: PERFECT signature in 27/27 cells

For every (vw, ez, hold) cell:
- **A_focus + A_mirror mean_net_ret_bp = EXACTLY -16.00 bp = -2×fee(round-trip)**
- **B_focus + B_mirror mean_net_ret_bp = EXACTLY -16.00 bp = -2×fee(round-trip)**

This is the definitive mathematical fingerprint of Lesson #39 sub-class A: the vel_z sign carries **zero directional information** about the forward N-bar price move. When you take opposite directions on the same trigger, the gross returns exactly cancel and the net sum equals -2 × fee_round_trip.

Sample of 10 (vw, ez, hold) cells (all 27 identical to 2 decimals):

| Cell | A_sum_bp | B_sum_bp | A_focus α% | B_focus α% |
|------|----------|----------|------------|------------|
| vw144_ez1.0_h12 | -16.00 | -16.00 | -51.58 | -50.37 |
| vw144_ez1.0_h48 | -16.00 | -16.00 | -34.47 | -42.98 |
| vw144_ez1.0_h96 | -16.00 | -16.00 | -29.44 | -24.54 |
| vw144_ez1.5_h12 | -16.00 | -16.00 | -47.44 | -43.14 |
| vw144_ez2.0_h48 | -16.00 | -16.00 | -16.43 | -36.08 |
| vw288_ez1.0_h12 | -16.00 | -16.00 | -48.90 | -48.50 |
| vw288_ez2.0_h48 | -16.00 | -16.00 | +0.37 | -34.55 |
| vw576_ez1.5_h96 | -16.00 | -16.00 | -31.94 | -13.46 |
| vw576_ez2.0_h48 | -16.00 | -16.00 | +0.30 | -25.80 |
| vw576_ez2.0_h96 | -16.00 | -16.00 | -12.27 | +0.65 |

### Root cause

The direction axis was correctly non-OHLCV (`sign(vel_z)` from microstructure position-LSR column, not bar_direction). Yet **Lesson #39 sub-class A still triggered perfectly**. This proves that vel_z of position LSR has **zero measurable predictive content** for 1h/4h/8h forward returns on SOL over 2025-05 to 2026-07.

**Mechanistic hypothesis** (to feed Lesson #79 candidate): top-trader position LSR is a **REACTIVE** signal (mirrors price move — when price rises, top traders' net long positions become larger in NOTIONAL terms), not a **PREDICTIVE** one. Its velocity captures the SPEED of that reaction, not the smart money's INTENT. So vel_z at time t contains only information about price at t (already priced in), not price at t+N.

---

## NEW LESSON CANDIDATE #79 (1st dogfood)

**Title**: `microstructure_direction_axis_necessary_but_not_sufficient_for_lesson_39_escape`

**Statement**: Using a non-OHLCV microstructure-derived direction axis (e.g. sign of vel_z of position LSR) is **necessary** but **not sufficient** to escape Lesson #39 sub-class A. If the microstructure signal itself lacks predictive content over the forward hold horizon, the 4-quadrant Symmetric Negative Test collapses to pure -2×fee fee-symmetric mirror EXACTLY as with bar_direction. Lesson #39 sub-class A is fundamentally a **signal-quality diagnostic**, NOT merely a direction-axis-source antipattern.

**Diagnostic decision procedure** (for R-0 amendments):
1. Before R-1, measure `corr(signal, forward_return_at_target_hold)` on OOS window for target symbol.
2. If |corr| < 0.02 (below noise floor for hourly holds) → HALT_BY_ZERO_PREDICTIVE_CONTENT and reformulate signal.
3. Applies especially to REACTIVE microstructure signals (position ratios, OI, taker flows) whose velocity may capture reaction speed but not intent.

**Precedents**: 
- Paradigm 108 (bar_direction × event): sub-class A originally identified
- Paradigm 110 (bar_direction × event): sub-class A confirmed 2nd dogfood
- Paradigm 232 (regime × direction): sub-class A confirmed 3rd dogfood — regime axis orthogonal to direction
- **Paradigm 233 (this) — 4th dogfood**: microstructure vel_z axis in position LSR — proves even microstructure axes fall to sub-class A when signal lacks predictive content

**Confirmed-자격** upgrade candidate after 1 more dogfood. Add to `lesson_prescreen_checklist.md` §Lesson#79 candidate section.

---

## Next Paradigm Recommendation

Given 11 consecutive SELF_RECOMMEND graveyards (paradigms 222-233), the agent has now saturated several substrate families:
1. Premium/basis/funding derivatives (Q2 §5)
2. Position/account LSR (level and velocity, contrarian and follow, both column variants)
3. OI composition/share (z, pct-rank, HHI)
4. Fear&Greed, launchpool events, cross-sym OI shift

**Suggestions for paradigm 234** (following the SELF-RECOMMEND 5-consecutive-fail rule at position 5, we are well past — the runbook note "5 consecutive non-PASS → mode-switch to user-provided hypothesis" is triggered):

Per handoff guidance, since agent SELF-RECOMMEND has been consecutively failing on smart-money microstructure family, the mode should switch:

**RECOMMENDATION**: Halt agent SELF-RECOMMEND for paradigm 234. Request user-provided hypothesis for next dispatch. Handoff note: "agent SELF-RECOMMEND saturated on microstructure velocity family (paradigms 225-233 all graveyard). Position LSR, account LSR, premium, funding, OI-composition, and Fear&Greed all exhausted. User-provided hypothesis or non-microstructure substrate (e.g., on-chain, exchange announcement calendar filtered by class exclusions, orderbook depth snapshots, or cross-exchange arbitrage residuals) recommended."

If continuing SELF-RECOMMEND anyway (per persistence-over-efficiency directive), the next candidate MUST include an R-0 amendment step: **predictive-content pretest** (compute `corr(signal, forward_return)` on OOS half; halt if |corr| < 0.02) before dispatching R-1. This directly encodes Lesson #79 candidate.

---

## Artifacts

- Code: `backend/scripts/research/paradigm_233_toptrader_position_lsr_velocity_z_r1.py`
- Metrics: `backend/runs/research_track/paradigm_233_alt_toptrader_position_lsr_velocity_z_bilateral_4h/r1__metrics.json`
- INDEX entry updated with `current_phase: graveyard`
- Runbook appended (paradigm 233 section)
