# R-1 Gate Evaluation — paradigm 131 `alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h`

**Executed**: 2026-05-21 09:56:37 KST · Host: hcp_local · Phase killed: R-1
**Verdict**: `BROAD_FALSIFIED_LESSON_52A_LONG_DRIFT_ARTIFACT`
**Sub-class**: Lesson #52a 2nd explicit dogfood (paradigm 129 1st) → **promotion to CONFIRMED** + Lesson #21 axis stacking trap 4th dogfood

## Hypothesis recap

Dual-axis liquidity stress conjunction at 4h frame:
- Axis 1: mark-index basis pct rolling-30d z-score, |basis_z| > 1.5
- Axis 2: (high-low)/close 4h rolling-30d z-score, range_close_z > +1.5
- Joint trigger: BOTH axes extreme in same 4h bar
- Direction: MEAN-REVERSION via sign(basis_z) — A_focus pos×SHORT / B_focus neg×LONG
- Universe: 6 alts (SOL/HBAR/AVAX/DOGE/ETH/LINK) × 12 months 2025-05..2026-04
- Forward hold: 4h directional · Debounce: 8h · Fee: 16bp round-trip

## R-0 prescreen status

- Triggers n=209 (A_pos_basis=118, B_neg_basis=91)
- per-quarter measurable: A 1/5, B 1/5 (Lesson #11 floor 30/quarter)
- Verdict: `R0_HALT_INSUFFICIENT_DENSITY` — **R-1 dispatched anyway with caveat**
  for Lesson #21 individual-vs-joint comparison + Lesson #52 dual detection

## R-1 4-quadrant SNT (Lesson #19)

| Quadrant | n | gross_bp | net_bp | obs_t | sigex | ci_lower_bp | perm_p_above | gate3 | gate_conc |
|---|---|---|---|---|---|---|---|---|---|
| **A_focus pos × SHORT_MR** | 118 | **-15.41** | -23.41 | -1.02 | -0.60 | -50.77 | 0.730 | FAIL | FAIL |
| **A_mirror pos × LONG** | 118 | **+15.41** | +7.41 | +0.32 | +1.01 | -35.21 | 0.168 | FAIL | FAIL |
| **B_focus neg × LONG_MR** | 91 | +8.18 | +0.18 | +0.01 | +0.59 | -31.37 | 0.271 | FAIL | FAIL |
| **B_mirror neg × SHORT** | 91 | -8.18 | -16.18 | -0.70 | -0.30 | -59.73 | 0.641 | FAIL | FAIL |

**0/4 quadrants pass 3-gate. 0/4 quadrants pass Concentration Gate.**

## Concentration Gate (Lesson #16)

| Quadrant | q_pos_t_ratio | syms_ci_pos_ratio | n_syms_ci_pos | gate_conc |
|---|---|---|---|---|
| A_focus | 1.00 (3/3) | 0.00 | 0/6 | FAIL (no sym ci_pos) |
| A_mirror | 0.67 (2/3) | 0.00 | 0/6 | FAIL (no sym ci_pos) |
| B_focus | 0.67 (2/3) | 0.00 | 0/6 | FAIL (no sym ci_pos) |
| B_mirror | 1.00 (3/3) | 0.00 | 0/6 | FAIL (no sym ci_pos) |

**0/6 sym ci_pos in ALL 4 quadrants** — universal universe-wide low-power.

## Lesson #21 INDIVIDUAL-vs-JOINT sigex comparison (MANDATORY dogfood)

| Trigger | n | gross_bp | sigex | ci_lower_bp |
|---|---|---|---|---|
| **Joint A_focus** (basis>+1.5 AND range>+1.5) × SHORT | 118 | -15.41 | -0.60 | -50.77 |
| Individual basis_only (basis>+1.5) × SHORT | 658 | +0.76 | -0.17 | -20.51 |
| **Joint B_focus** (basis<-1.5 AND range>+1.5) × LONG | 91 | +8.18 | +0.59 | -31.37 |
| Individual basis_only (basis<-1.5) × LONG | 623 | +1.13 | +0.55 | -19.77 |
| Individual range_close_only (range>+1.5) × LONG | 703 | -4.42 | +0.14 | -30.30 |

**Lesson #21 verdict**: **axis_stacking_trap_detected = TRUE**
- Joint A_focus sigex (-0.60) WORSE than individual basis_only (-0.17) by delta -0.43
- Joint B_focus sigex (+0.59) essentially equal to individual basis_only (+0.55) delta +0.04
- The range_close axis adds NOISE not signal. Conjunction reduces n 5x without sigex gain.

This is **4th dogfood** of Lesson #21 "axis stacking does not synthesize alpha"
(precedents: paradigm 83 oi_5m_latent_regime 1st, paradigm 122 dual-anchor 2nd,
paradigm 124 kurtosis confluence 3rd, **paradigm 131 4th**).

## Lesson #52 a/b dual detection (paradigm 130 INVERSE 1st precedent)

| Detection rule | Triggered? |
|---|---|
| **52a Universe LONG drift artifact** (A_mirror_LONG +15.41, B_focus_LONG +8.18, both gross>0, both ci_lower<0, 0/6 sym_ci_pos) | **TRUE** |
| **52b SHORT-bias INVERSE artifact** (A_focus_SHORT>0 + B_mirror_SHORT>0 + LONG quadrants<0) | FALSE |

**Lesson #52a 2nd EXPLICIT dogfood** (paradigm 129 was 1st explicit, paradigm 99 was 1st implicit funding family). With 2 explicit dogfoods, **Lesson #52a promotion-eligible CONFIRMED**.

The 6-alt universe over 2025-05..2026-04 exhibits unconditional bull-market drift:
any subset of LONG-direction trades on filter triggers gains ~+8-15bp gross
regardless of trigger mechanism. SHORT direction symmetrically loses. No per-pair
mechanism (0/6 sym ci_pos confirms).

## Mechanism failure analysis

1. **paradigm 111 single-axis basis percentile already broad-falsified** (2026-05-20):
   A_focus pLOW LONG gross -0.37bp essentially zero alpha at single-axis basis.
   paradigm 131 attempted to rescue via range_close conjunction — failed.

2. **Lesson #21 axis stacking trap**: range_close_z is non-negative aggregate
   (Lesson #40 acknowledged upper-tail only used). Combining non-negative volatility
   proxy with signed basis-z does NOT synthesize directional alpha — range_close
   is direction-blind by construction.

3. **Sample density loss**: from 658 (basis-only) to 118 (joint) = 5.6x reduction
   in n_trades while sigex degraded from -0.17 to -0.60. Axis conjunction filtering
   discards 82% of basis-only events without compensating signal density.

4. **Lesson #52a artifact**: bull-drift universe-wide bias dominates conditional
   sample. A_mirror_LONG +15.41bp gross is mathematical mirror of A_focus_SHORT
   -15.41bp — same data, opposite direction. ci_lower<0 in BOTH directions confirms
   no real mechanism, only universe drift artifact.

## Liquidity-microstructure family family-distinct claim status

| paradigm | mechanism | status |
|---|---|---|
| 105 (~111 implementation) | mark-index basis percentile single-axis | GRAVEYARD |
| 121 | HMM realized-vol state × markPrice basis filter | GRAVEYARD (Lesson #45) |
| 131 | basis_z × range_close_z joint conjunction MR | GRAVEYARD (this) |

**3 liquidity-microstructure single-domain graveyards**. Advisory caution.
NOT yet Tier 4 retire (need 1-2 more distinct sub-mechanism fails to confirm
substantive vs notational distinctness across the family).

## Lessons dogfood at R-1

- **Lesson #11** R-0 halt density per-quarter 1/5 → R-1 dispatched with caveat (informative quadrant aggregate)
- **Lesson #16** 0/6 sym ci_pos ALL 4 quadrants (4-quadrant universal zero concentration)
- **Lesson #19** SNT 4-quadrant single batch
- **Lesson #21** **4th dogfood** axis stacking trap CONFIRMED (joint sigex ≤ individual axis sigex)
- **Lesson #28** substrate 6/6 paradigm 111 cache reuse PASS
- **Lesson #30** 12mo / 12mo full window = 1.0 PASS
- **Lesson #34** basis_z + range_close_z empirical percentiles measured
- **Lesson #40** axis 2 upper-tail-only acknowledged (PASS)
- **Lesson #44** **13th xref dogfood** (10 paradigm xrefs + RUNBOOK)
- **Lesson #45** explicit empirical z-thresholds (no HMM) PASS
- **Lesson #46** REFINEMENT 6th dogfood — sub-amendment 6th (stratified n=137 weak negative caught by full R-1 broad-falsified)
- **Lesson #52a** **2nd EXPLICIT dogfood → CONFIRMED-eligible** (paradigm 129 1st explicit + 99 1st implicit + paradigm 131 2nd explicit)

## Verdict

```
verdict: BROAD_FALSIFIED_LESSON_52A_LONG_DRIFT_ARTIFACT
sub_class:
  - Lesson #52a universe LONG drift artifact 2nd explicit dogfood
    (promotion to CONFIRMED eligible)
  - Lesson #21 axis stacking trap 4th dogfood
    (joint sigex ≤ individual axis sigex)
  - Lesson #44 amendment 13th xref dogfood (10 paradigm xrefs)
  - Lesson #46 REFINEMENT 6th dogfood + sub-amendment 6th
```

**Continuous-parallel 3-streak non-PASS**: paradigm 129 + 130 + **131**. 3-streak axis pivot threshold reached.

## Next-paradigm recommendation

**PIVOT AWAY** from:
- Cross-asset correlation/beta (paradigm 130 + 4 retired)
- Per-symbol range/RV/quarticity (paradigm 129)
- **Liquidity-microstructure single-domain** (paradigm 111/121/131 — 3 graveyards, advisory)
- Magnitude-only or magnitude+magnitude conjunction (Lesson #21 4 dogfoods)
- Conditional-overextension event detection on bull-drift universe (Lesson #52a)

**Recommended pivots (3-streak axis family-distinct pivots)**:

1. **Event-anchored funding boundary refinement** — funding sign × magnitude × OI direction triple-confirm at funding boundary (paradigm 22 R-5 family but boundary-restricted slice). Distinct via event-anchoring + 3-way confirm instead of pure conjunction.

2. **Cross-venue ARBITRAGE refinement** — paradigm 103 cross-exchange spread caution-class extension to OI divergence (Bybit V5 substrate verified). Distinct via cross-venue mechanism not single-venue conjunction.

3. **Lifecycle-event refinement** — listing-day forced-buyer flow specific window (paradigm 87 entry-side mechanism, paradigm 88/90 sub-mechanism distinct). May require lifecycle live mode (2026-05-29+).

4. **Inventory-halt option** — 3-streak non-PASS threshold reached, consider paradigm-architect halt + meta-review until paradigm 127+128 Day 7 baseline (2026-05-28) and Day 30 D-Day (2026-06-03).

## Artifacts

- `backend/scripts/research/paradigm131_r0_prescreen.py`
- `backend/scripts/research/paradigm131_r1.py`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/r0_prescreen.json`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/r1__metrics.json`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/sym_4h_panel.joblib`
- `backend/runs/research_track/alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/trig_panel.joblib`
- `backend/runs/research_track/graveyard__alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h.md`
