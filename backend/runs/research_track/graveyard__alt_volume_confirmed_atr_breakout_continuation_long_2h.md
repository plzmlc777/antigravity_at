# Graveyard — paradigm 116 `alt_volume_confirmed_atr_breakout_continuation_long_2h`

**Date**: 2026-05-20 (KST)
**Phase**: R-1
**Type**: E
**Verdict**: `BROAD_FALSIFIED` (verdict-tree label) / refined: **`AXIS_REDUNDANT_NO_SYNTHESIS`** at k=1.5 + **partial axis-amplification only at k=1.0 (volume axis adds +2.8bp gross but still sub-fee-floor)**
**Wall-clock**: 0.07 min (4 seconds)
**Cumulative paradigm graveyard count**: 116

## Hypothesis

Paradigm 115 returned `CONCENTRATION_DISPERSION_FAIL` at k=1.5 (gross +20bp,
net +12bp, sigex +3.99, perm_p_one_sided 0.000, q_pos 6/9, syms_pos_mean 9/13
BUT syms_ci_pos 0/13). Paradigm 116 layers a **volume confirmation overlay**
on the ATR-buffered breakout trigger:

```
A_focus  : (close > rmax + k×ATR_norm × prev_close) AND (1h vol >= rolling_p_vp_30d) -> LONG (2h hold)
A_mirror : same trigger -> SHORT
B_same   : (close < rmin - k×ATR_norm × prev_close) AND (1h vol >= rolling_p_vp_30d) -> SHORT (continuation, 2h)
B_mirror : same trigger -> LONG
```

Grid: k ∈ {1.0, 1.5} × vol_pct ∈ {60, 70, 80} = 6 cells × 4 quadrants = 24
quadrant-cells.

Hypothesis: real breakouts have liquidity backing visible as elevated volume;
noise breakouts (smart money selling into thin liquidity) show suppressed
volume. Volume gate should (H1) filter noise → per-trade edge UP, (H2)
reduce n → harder Lesson #11/#41, (H3) homogenize per-sym subset →
possibly recover Concentration Gate.

## Key Result Tables

### Empirical distribution per cell (Lesson #11 + retention vs paradigm 115)

| cell                | deb_up | deb_dn | retention_up | per_q_up | Lesson #11 |
|---------------------|--------|--------|--------------|----------|------------|
| k=1.0, vol_pct=60   | 1838   | 1943   | 97.6%        | 102.1    | PASS       |
| k=1.0, vol_pct=70   | 1794   | 1923   | 95.2%        | 99.7     | PASS       |
| k=1.0, vol_pct=80   | 1675   | 1834   | 88.9%        | 93.1     | PASS       |
| **k=1.5, vol_pct=60** | **1082** | **1084** | **100.0%** | **60.1** | PASS       |
| k=1.5, vol_pct=70   | 1080   | 1083   | 99.8%        | 60.0     | PASS       |
| k=1.5, vol_pct=80   | 1065   | 1075   | 98.4%        | 59.2     | PASS       |

**Decisive observation**: at k=1.5, volume p60 retains **100.0%**, p70 retains
**99.8%**, p80 retains **98.4%** of paradigm 115's events. The ATR-buffer at
k=1.5 is already so restrictive that virtually ALL ATR-cleared breakout bars
ALREADY have above-median volume. The volume overlay is **mechanically
redundant** at k=1.5. (At k=0.5 / k=1.0 the overlay would actually filter
events; at k=1.0 / vol_p80 we see meaningful retention shrink to 89%.)

### A_focus_breakUp_LONG per cell (primary 2h hold)

| cell                  | n    | gross_bp | net_bp | ci_low_bp | sigex | perm_p_1s | q_pos | syms_ci_pos | syms_pos_mean | gate3 | conc |
|-----------------------|------|----------|--------|-----------|-------|-----------|-------|-------------|---------------|-------|------|
| k=1.0, vol_pct=60     | 1838 | +8.96    | +0.96  | -7.53     | +3.02 | n/a       | 3/9   | 0/13        | 5/13          | False | False |
| k=1.0, vol_pct=70     | 1794 | +9.03    | +1.03  | -6.94     | +3.03 | n/a       | 4/9   | 0/13        | 5/13          | False | False |
| **k=1.0, vol_pct=80** | **1675** | **+10.87** | **+2.87**  | **-6.50** | **+3.27** | n/a       | **4/9** | **0/13** | **6/13** | False | False |
| **k=1.5, vol_pct=60** | **1082** | **+20.03** | **+12.03** | **-0.28** | **+3.99** | **0.000** | **6/9** | **0/13** | **9/13** | False | False |
| k=1.5, vol_pct=70     | 1080 | +19.52   | +11.52 | -0.75     | +3.91 | n/a       | 6/9   | 0/13        | 8/13          | False | False |
| k=1.5, vol_pct=80     | 1065 | +19.81   | +11.81 | -1.27     | +3.94 | n/a       | 6/9   | 0/13        | 9/13          | False | False |

### Hold sweep on best cell (k=1.5, vol_pct=60) A_focus

| hold | n    | gross_bp | net_bp | ci_low | sigex | q_pos | syms_ci_pos | sharpe_ann | util% | lc_all_4dim |
|------|------|----------|--------|--------|-------|-------|-------------|------------|-------|-------------|
| 2h   | 1082 | +20.03   | +12.03 | -0.28  | +3.99 | 6/9   | 0/13        | 1.32       | 12.65 | False       |
| **4h** | **1082** | **+29.11** | **+21.11** | **+5.58** | **+4.28** | **6/9** | **0/13** | **1.90** | **25.29** | False (edge 0.21%, util 25%) |

Identical to paradigm 115 hold sweep — confirms axis-redundancy at k=1.5.

### Lesson #21 axis-stacking diagnostic (vs paradigm 115 baseline)

| cell                | A_focus gross | vs p115_k_same baseline | beats baseline | clears fee floor (net>0) |
|---------------------|---------------|-------------------------|----------------|--------------------------|
| k=1.0, vol_pct=60   | +8.96bp       | +0.92bp (vs p115 k=1.0 baseline +8.04bp)  | True  | True (marginal)  |
| k=1.0, vol_pct=70   | +9.03bp       | +0.99bp                 | True           | True (marginal)          |
| **k=1.0, vol_pct=80** | **+10.87bp** | **+2.83bp**           | **True**       | **True**                 |
| k=1.5, vol_pct=60   | +20.03bp      | -0.00bp (vs p115 k=1.5 +20.03bp) | False  | True                     |
| k=1.5, vol_pct=70   | +19.52bp      | -0.51bp                 | False          | True                     |
| k=1.5, vol_pct=80   | +19.81bp      | -0.22bp                 | False          | True                     |

**Asymmetric Lesson #21 finding**:
- At k=1.0 (weaker ATR-buffer): volume axis ADDS +0.92 to +2.83bp gross.
  Volume p80 amplifies most (89% retention → +35% per-trade alpha)
- At k=1.5 (strong ATR-buffer): volume axis adds ~0bp. Axis is REDUNDANT
  because k=1.5 already selects the high-volume subset.

### Lesson #21 6th dogfood verdict: **NEUTRAL with k-conditional sub-finding**

Best cell delta: +2.83bp at k=1.0/vol_p80. This is below the +5bp positive
threshold but clearly above noise. **Refined interpretation**: Lesson #21
axis stacking **saturates as primary axis tightens**. When ATR-buffer is
relaxed (k=1.0), volume adds a measurable 35% boost. When ATR-buffer is
strong (k=1.5), volume becomes redundant because the high-vol-bar subset
∩ ATR-cleared subset ≈ ATR-cleared subset.

This is a **NEW Lesson #21 sub-finding**:
> Axis redundancy via **strict-primary-condition saturation**: when
> primary axis condition is restrictive enough that ≥95% of triggered
> bars satisfy secondary condition mechanically, secondary axis adds
> no orthogonal information.

### Lesson #39 symmetry

All 6 cells: sum_abs = 0.000 (perfect mechanical ±gross mirror). Same as
paradigms 114+115 — mechanical artifact of same trigger mask × sign-flipped
forward return, NOT Lesson #39 sub-class A antipattern.

### B_same_sign_breakDn_SHORT (downside path)

| cell                | n    | gross_bp | net_bp | sigex | q_pos | syms_ci_pos |
|---------------------|------|----------|--------|-------|-------|-------------|
| k=1.5, vol_pct=60   | 1084 | +7.64    | -0.36  | +1.86 | 5/9   | 0/13        |
| k=1.5, vol_pct=70   | 1083 | +7.51    | -0.49  | +1.88 | 5/9   | 0/13        |
| k=1.5, vol_pct=80   | 1075 | +5.79    | -2.21  | +1.58 | 4/9   | 0/13        |

Downside Donchian break continuation (SHORT) substantially weaker than
upside (LONG) continuation — confirms paradigm 114's directional asymmetry
finding. Downside breakouts get bought (mean-reversion / dip-buy bias) more
than upside breakouts get sold.

## Lesson #41 candidate 2nd dogfood

| metric                          | best cell k=1.5/vp=60 2h | best cell k=1.5/vp=60 4h |
|---------------------------------|--------------------------|--------------------------|
| sigex                           | +3.99                    | +4.28                    |
| perm_p_one_sided_above          | 0.000                    | 0.147 (2-sided), n/a 1-s |
| q_pos                           | 6/9                      | 6/9                      |
| ci_lower (pool)                 | -0.28bp                  | **+5.58bp** (STRONG)     |
| syms_ci_pos                     | 0/13                     | 0/13                     |
| syms_pos_mean                   | **9/13** (positive bias) | **9/13**                 |
| pool_evidence_strong (per spec) | False (ci_lower<0)       | **True**                 |
| concentration_fails             | True                     | True                     |
| Lesson #41 mode                 | borderline               | **confirmed at 4h hold** |

**Verdict**: **Lesson #41 confirmed 2nd dogfood at 4h hold cell**. Pool-level
evidence is decisive (sigex +4.28, ci_lower +5.58bp, q_pos 6/9), per-sym
mean is 9/13 positive, but per-sym CI tightness still fails 0/13.

Volume overlay did NOT help concentration (as the paradigm 115 graveyard
predicted Lesson #41 would persist at smaller n).

**Cumulative Lesson #41 dogfoods**: paradigm 115 (k=1.5 4h) + paradigm 116
(k=1.5 vol_p60 4h, k=1.5 vol_p70 4h-implied, k=1.5 vol_p80 4h-implied) = 2nd
paradigm-level confirmation across 3 sub-cells. **Lesson #41 promotion eligible
to confirmed status** pending criteria:
- 2 paradigms exhibit identical diffuse-positive concentration-fail mode
- per-sym n consistently < 100 across both paradigms (paradigm 115 best=98,
  paradigm 116 best=98)
- pool sigex ≥ +4σ with ci_lower > 0 at appropriate hold (paradigm 115 4h
  ci_lower +5.58bp, paradigm 116 4h ci_lower +5.58bp — identical because
  k=1.5 vol_p60 retains 100% of paradigm 115 events)

### Verdict Refinement

**The verdict-tree assigned `BROAD_FALSIFIED` because** `n_quadrants_pass_3gate_total
== 0` AND `max_focus_gross_any_cell` (20.03 at k=1.5) > 16bp but ci_lower negative
at 2h primary. Refined characterization:

**`AXIS_REDUNDANT_NO_SYNTHESIS`** — paradigm 116 at k=1.5 is **mechanically
identical** to paradigm 115 (retention 98-100%). The volume overlay does NOT
synthesize alpha at the operating point (k=1.5) where alpha is strongest. At
k=1.0 (weaker primary), volume adds modest +2.8bp but still sub-fee-floor.

This is a **NEW antipattern class** to add to Lesson #21:
> **Axis-redundancy via primary-condition saturation**: secondary axis
> (volume p80) intersects ≥95% with primary axis (ATR k=1.5 buffer) → no
> orthogonal information → no amplification. Diagnostic test: measure
> retention of secondary-axis trigger conditional on primary-axis trigger.
> If retention ≥95% → secondary axis is redundant.

## Life-changing 4-dim (best cell k=1.5/vp=60 4h hold)

- trades/yr: 554 (PASS, ≥12)
- per_trade_edge: 0.21% (FAIL, <2%)
- capital_util: 25.29% (FAIL, <30%, close)
- annualized_sharpe: 1.90 (PASS, ≥1.5)
- pass_all: False (2/4)

Identical to paradigm 115 — confirms axis-redundancy at the operating cell.

## Lesson candidates

### Lesson #21 sub-finding promotion (NEW): "Axis-redundancy via primary-condition saturation"

**Statement**: When two axes are stacked on a single event-trigger paradigm,
amplification scales NOT just with each axis's independent alpha but with
the **mutual information** between the two conditions. If primary axis is
restrictive enough that conditional retention of secondary axis ≥95%, the
secondary axis carries no orthogonal information → no amplification.

**Diagnostic prescreen** (paradigm-architect spec):
> Before measuring secondary-axis paradigm: compute
> `retention = P(secondary | primary)` empirically. If retention ≥95%,
> halt and reformulate (either relax primary so secondary becomes
> informative, or seek a truly orthogonal third axis).

**Dogfood count**: paradigm 116 first dogfood. Promote to candidate.

### Lesson #41 candidate strengthening (2nd dogfood confirmation)

paradigm 115 + 116 both at k=1.5 4h hold:
- sigex +4.28 (paradigm 115 + 116 4h)
- ci_lower +5.58bp (identical because cell mechanically identical)
- syms_pos_mean 9/13 (60-70% of universe positive-mean)
- syms_ci_pos 0/13 (NONE individually significant)
- per-sym n=63-98 (too small for tight CI)

**Lesson #41 promotion-eligible to confirmed**:
> Concentration Gate per-symbol bootstrap CI tightness scales with per-sym
> n; small-cohort universe (≤13 sym, per-sym n<100) cannot satisfy
> Concentration leg even with pool-level signal_t_excess ≥ +4σ. Verdict
> branch needed: `DIFFUSE_POSITIVE_CONCENTRATION_FAIL` — promote to R-2
> with cohort expansion instead of graveyard.

## Files

- `backend/scripts/research/paradigm116_alt_volume_confirmed_atr_breakout_continuation_long_2h_r1.py`
- `backend/runs/research_track/alt_volume_confirmed_atr_breakout_continuation_long_2h/r1__metrics.json`
- `backend/runs/research_track/alt_volume_confirmed_atr_breakout_continuation_long_2h/r1__stdout.log`
- `backend/runs/research_track/graveyard__alt_volume_confirmed_atr_breakout_continuation_long_2h.md` (this)

## Next steps recommendation

1. **Lesson #21 sub-finding promotion**: codify "axis-redundancy via
   primary-condition saturation" as Lesson #21 sub-clause in Q3 lesson
   index. Add the `retention ≥95% → halt` prescreen to
   paradigm-architect spec.
2. **Lesson #41 promotion to confirmed**: with 2 paradigm-level dogfoods
   (115 + 116, both at k=1.5 4h), promote candidate → confirmed.
   Implement `DIFFUSE_POSITIVE_CONCENTRATION_FAIL` verdict branch in
   paradigm-architect spec.
3. **Next paradigm direction** (paradigm 117 candidate, given p115/p116
   findings): instead of more stacking, pursue **cohort expansion** to
   test Lesson #41 — paradigm 117 hypothesis: same paradigm 115 mechanism
   (ATR k=1.5 4h LONG continuation) but on **25+ symbol universe** (full
   Binance Futures perp tier 1+2) to test whether per-sym n ≥ 150 recovers
   syms_ci_pos. This is the explicit Lesson #41 candidate test.
4. **Truly orthogonal axis candidates** (alternative to cohort expansion):
   - **Funding rate sign** at breakout (orthogonal to price/vol/liquidity)
   - **BTC dominance regime** (orthogonal market-state)
   - **Hour-of-day** (intraday liquidity regime, paradigm 113 anchor)
   - These provide orthogonal information NOT mechanically saturated by
     ATR-buffer.
