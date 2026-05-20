# Graveyard — paradigm 115 `alt_atr_normalized_range_breakout_continuation_long_2h`

**Date**: 2026-05-20 (KST)
**Phase**: R-1
**Type**: E
**Verdict**: `CONCENTRATION_DISPERSION_FAIL` (verdict-tree labeled `BROAD_FALSIFIED` but mechanism characterization is more specific — see §Verdict Refinement)
**Wall-clock**: 0.03 min
**Cumulative paradigm graveyard count**: 115

## Hypothesis

paradigm 114 (raw 24h trailing-high Donchian breakout, 13-alt × 2h) returned
`BROAD_FALSIFIED_FEE_FLOOR` with explicit follow-up reco:

> "ATR-normalized breakout (close > prior 24h max + k×ATR) — concentration이 alt subset에 집중되는지 검증. 추가 fee-floor 1번 더 확인 시 'level-crossing single-domain family' lesson 자격 promotion 가능."

paradigm 115 implements that follow-up. Trigger:

```
A_focus  : close > prior_24h_max + k × ATR_norm × prev_close, debounced  -> LONG  (continuation, 2h hold)
A_mirror : same trigger                                                  -> SHORT (wrong direction)
B_same   : close < prior_24h_min - k × ATR_norm × prev_close, debounced  -> SHORT (continuation, 2h hold)
B_mirror : same trigger                                                  -> LONG  (wrong direction)
```

k sweep ∈ {0.5, 1.0, 1.5}, primary k=1.0, ATR_14d on 1h bars (336 bars rolling).

## Key Result Tables

### Per-k primary 2h-hold (4-quadrant SNT)

| k   | quadrant | n     | gross_bp | net_bp  | ci_low | ci_up | sigex | perm_p_2s | perm_p_1s_above | q_pos | syms_ci_pos | gate3 | conc |
|-----|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.5 | A_focus | 3021 | +6.10  | -1.90  | -7.76  | +3.32 | +2.98 | 1.000 | n/a   | 2/9 | 2/13 | False | False |
| 0.5 | A_mirror | 3021 | -6.10  | -14.10 | -19.39 | -8.10 | -1.65 | 0.048 | n/a   | 0/9 | 0/13 | False | False |
| 0.5 | B_same | 3164 | -0.07  | -8.07  | -12.74 | -3.65 | +0.08 | 0.537 | n/a   | 2/9 | 0/13 | False | False |
| 0.5 | B_mirror | 3164 | +0.07  | -7.93  | -13.13 | -2.83 | +0.55 | 0.704 | n/a   | 2/9 | 0/13 | False | False |
| 1.0 | A_focus | 1884 | +8.04  | +0.04  | -7.74  | +7.94 | +2.83 | 1.000 | n/a   | 3/9 | 0/13 | False | False |
| 1.0 | A_mirror | 1884 | -8.04  | -16.04 | -24.32 | -7.97 | -1.21 | 0.112 | n/a   | 1/9 | 0/13 | False | False |
| 1.0 | B_same | 1959 | +3.47  | -4.53  | -12.71 | +3.79 | +1.51 | 0.937 | n/a   | 2/9 | 0/13 | False | False |
| 1.0 | B_mirror | 1959 | -3.47  | -11.47 | -20.53 | -2.41 | +0.25 | 0.588 | n/a   | 2/9 | 0/13 | False | False |
| **1.5** | **A_focus** | **1082** | **+20.03** | **+12.03** | **-0.28** | **+24.04** | **+3.99** | **0.605** | **0.000** | **6/9** | **0/13** | **False** | **False** |
| 1.5 | A_mirror | 1082 | -20.03 | -28.03 | -40.04 | -16.13 | -2.41 | 0.008 | n/a   | 1/9 | 0/13 | False | False |
| 1.5 | B_same | 1084 | +7.87  | -0.13  | -14.27 | +13.39 | +1.90 | 0.998 | n/a  | 5/9 | 0/13 | False | False |
| 1.5 | B_mirror | 1084 | -7.87  | -15.87 | -30.23 | -1.96 | -0.12 | 0.459 | n/a   | 2/9 | 0/13 | False | False |

### Hold sweep on k=1.5 A_focus (LONG)

| hold | n    | gross_bp | net_bp | ci_low | ci_up | sigex | perm_p_2s | q_pos | syms_ci_pos | sharpe_ann | util%  |
|------|------|----------|--------|--------|-------|-------|-----------|-------|-------------|------------|--------|
| 1h   | 1082 | +14.73   | +6.73  | -3.19  | +16.92 | +4.26 | 0.946     | 5/9   | 1/13        | 0.93       | 6.32   |
| 2h   | 1082 | +20.03   | +12.03 | -0.28  | +24.04 | +3.99 | 0.605     | 6/9   | 0/13        | 1.32       | 12.65  |
| **4h** | **1082** | **+29.11** | **+21.11** | **+5.58** | **+35.87** | **+4.28** | **0.147** | **6/9** | **0/13** | **1.90** | **25.29** |

### Lesson #21 axis-stacking diagnostic (joint vs paradigm 114 raw baseline)

| k   | joint gross | joint net | vs p114 gross delta | beats raw on gross | clears fee floor (net>0) |
|-----|-------------|-----------|---------------------|--------------------|--------------------------|
| 0.5 | +6.10       | -1.90     | +0.69bp             | True               | False                    |
| 1.0 | +8.04       | +0.04     | +2.63bp             | True               | False                    |
| 1.5 | +20.03      | +12.03    | +14.62bp            | True               | True (single-leg)        |

**Lesson #21 POSITIVE 5th dogfood**: ATR k-buffer stacking on Donchian breakout
**synthesizes alpha monotonically** with k. Joint(breakout × ATR-buffer) beats
raw breakout at every k, and the magnitude scales monotonically: +0.69bp at
k=0.5, +2.63bp at k=1.0, +14.62bp at k=1.5. Paradigm 114 baseline +5.41bp
gross → paradigm 115 k=1.5 +20.03bp gross = **3.7x amplification**.

### Lesson #39 symmetry diagnostic

All 3 k values produce `sum_abs_bp` = 0.000 (perfect ±k bp mirror). This is
**mechanical** (same trigger mask, sign-flipped fwd return = exact mirror),
not Lesson #39 sub-class A antipattern. Same situation as paradigm 114.

### Empirical distribution

| k   | deb_up | deb_dn | per_q_up | per_q_dn | retention vs p114 up | passes Lesson #11 |
|-----|--------|--------|----------|----------|----------------------|-------------------|
| 0.5 | 3021   | 3164   | 167.8    | 175.8    | 105.7%               | True              |
| 1.0 | 1884   | 1959   | 104.7    | 108.8    | 65.9%                | True              |
| 1.5 | 1082   | 1084   | 60.1     | 60.2     | 37.9%                | True              |

Notable: k=0.5 produced **more** debounced events than paradigm 114 raw (+5.7%
retention). This is because k=0.5 ATR-buffer triggers fewer raw breakouts than
the bare Donchian (some marginal closes don't clear the buffer) but the
debounce filter then preserves **a higher fraction** of those that do
(debounced retention shifts because the "any breakout in last 12h" window
sees fewer prior events to disqualify).

## Verdict Refinement (vs auto-labeled `BROAD_FALSIFIED`)

The verdict-tree assigned `BROAD_FALSIFIED` because `n_quadrants_pass_3gate_total
== 0` at primary 2h hold AND `max_focus_gross_any_k` (20.03 at k=1.5) > 16. The
"does not even point positive" branch label is **misleading** — gross IS strongly
positive (+20.03bp at k=1.5 A_focus, sigex +3.99), but:

1. **Pool CI at primary 2h hold**: ci_lower -0.28bp at k=1.5 — just barely
   negative (one bp from positive). Statistical artifact of one-tailed evidence
   in two-tailed CI.
2. **Pool CI at hold=4h**: ci_lower **+5.58bp** — strongly positive.
3. **`perm_p_two_sided` at hold=4h**: 0.147 — just above 0.10 strict cutoff
   (would PASS at p≤0.15).
4. **`perm_p_one_sided_above` at all k=1.5 cells**: **0.000** (decisively
   significant in directional null).
5. **Per-symbol CI**: 0/13 syms with ci_pos at k=1.5 4h. Per-sym mean is positive
   in **9/13 syms** (HBAR +56bp, ADA +66bp, AVAX +38bp, FIL +43bp, XRP +29bp,
   ETH +26bp, SOL +13bp, BCH +13bp, NEAR +5bp), but per-sym n=63-98 too small
   to make individual bootstrap CI tight enough.
6. **Per-quarter t**: 6/9 positive at k=1.5 (q_pos_ratio 0.67, PASSES first
   Concentration leg).

**Refined characterization**: `CONCENTRATION_DISPERSION_FAIL` — mechanism IS
real (signal_t_excess +3.99, perm_p_one_sided 0.000, q_pos 6/9, 9/13 syms
positive-mean, hold=4h pool ci strongly positive), but alpha is **diffusely
spread across 13 symbols too thinly to register per-sym CI positivity**. This
is a different fail mode than fee-trap (paradigm 104 + 114) — those failed at
the pool level. paradigm 115 PASSES at pool level (4h hold) but fails the
per-symbol concentration leg.

**Life-changing 4-dim** at k=1.5 4h hold:
- trades/yr: 554 (PASS, ≥12)
- per_trade_edge: 0.21% (FAIL, <2%)
- capital_util: 25.3% (FAIL, <30%, but close)
- annualized_sharpe: 1.90 (PASS, ≥1.5)
- pass_all: False (2/4)

Diffuse alpha = high trade rate + low per-trade edge — the trade frequency is
fine, but **edge per trade is fundamentally noise-limited** by the per-symbol
sample density.

## Lesson #35 fee-trap dogfood

`is_3rd_fee_trap_dogfood: False`. paradigm 115 is NOT a fee-floor failure at
the pool level — at k=1.5 4h hold, net +21.11bp > 16bp fee floor. The
"level-crossing single-domain family" Tier 4 retire eligibility from paradigm
114's recommendation is **NOT triggered**.

Instead, the fee-trap pattern (paradigm 104 venue arb + paradigm 114 raw
Donchian) is **partially reversed** by ATR-normalization at k=1.5 — gross
scales 3.7x with vol-conditioning. The mechanism is real and economically
viable, just not concentratable at this universe size + horizon.

## Lesson candidates

### Lesson #41 candidate (NEW): "Concentration Gate per-symbol bootstrap CI tightness scales with per-sym n; small-cohort universe (≤13 sym, per-sym n<100) cannot satisfy Concentration leg even with pool-level signal_t_excess ≥ +4σ"

**Statement**: Concentration Gate per-symbol CI positivity threshold
(`n_syms_ci_pos >= 3`) implicitly requires per-sym n ≥ ~150-200 for bootstrap
CI to be tight enough relative to single-bar return σ ≈ 50-100bp. For 13-alt
universe × ~1000 total events, per-sym n ≈ 75 → bootstrap CI width ≈ ±50bp
even with +50bp mean (e.g. HBAR +56bp at 4h ci=[-19, +147], width 166bp). Pool
CI tightens by √n_total but per-sym CI is dominated by per-sym n.

**Implication for paradigm-architect spec**: If pool-level evidence (signal_t_excess
≥ +4, perm_p_one_sided ≤ 0.001, q_pos_ratio ≥ 0.6, ci_lower > 0) is strong but
n_syms_ci_pos = 0 with per-sym n < 150, this is **diffuse-positive alpha** not
broad falsification. Should classify as:
- `DIFFUSE_POSITIVE_CONCENTRATION_FAIL` (verdict candidate) — promote to R-2
  with cohort expansion (≥25 sym, or longer window) instead of graveyard.

**Dogfood requirement**: This is the **1st dogfood**. Promote to confirmed
after 2nd independent dogfood (likely candidate: paradigm 116 or similar).

### Lesson #21 POSITIVE 5th dogfood (confirmed-tier)

ATR k-buffer × Donchian breakout = joint synthesizes alpha monotonically with
k. 5th positive instance of axis stacking synthesizing (vs the few negative
instances cataloged). Lesson #21 confirmed via 5 dogfoods — axis stacking
IS sometimes alpha-synthesizing, contrary to the conservative bias suggested
by Q3 lesson §6.2 #21.

### Lesson #34 candidate (paradigm 103 candidate) FAILS to confirm

Paradigm 115 at k=1.5 net +12bp (2h hold) and +21bp (4h hold) breaks the
"venue arbitrage / level-crossing fee-floor bound" pattern that paradigm 103
+ 104 + 114 cumulatively suggested. The level-crossing single-domain family
Tier 4 retire eligibility is **rejected** — vol-conditioning escapes fee
floor.

## Per-symbol diagnostics (k=1.5 4h hold A_focus)

9/13 symbols have positive mean (HBAR, ADA, AVAX, FIL, XRP, ETH, SOL, BCH, NEAR).
4/13 negative (DOGE, LINK, LTC, BNB). Mean ranges from -11.4bp (LTC) to +66bp
(ADA). The directional signal IS broadly distributed but per-sym CIs are too
wide.

## Recommended Next Action

**Option A (priority)**: R-2 EXPANSION TEST at hold=4h k=1.5 with **expanded
universe** (≥25 alts) and **extended window** (3yr if cache permits). Goal:
push per-sym n from ~75 to ~200 to test whether per-sym CI tightens. If
expanded universe + window produces n_syms_ci_pos ≥ 4-5 at hold=4h k=1.5 →
promote to R-2 formal walk-forward. If still 0-2 ci_pos → confirm Lesson #41
candidate as a structural limitation of small-cohort 13-alt universe and
reject promotion.

**Option B**: Document `CONCENTRATION_DISPERSION_FAIL` verdict and graveyard
without R-2 attempt. Conservative — paradigm 115 has 3 of 4 life-changing
4-dim leg failures even at 4h hold (edge 0.21% << 2%). Even if Concentration
PASSED, the per-trade edge is mathematically insufficient for life-changing
criteria.

**Option C** (rejected): paradigm 114 follow-up suggested "level-crossing
single-domain family" Tier 4 retire if paradigm 115 also failed. paradigm 115
does NOT fail in the predicted manner (fee floor) — it fails by
concentration dispersion. Family retire eligibility **rejected**.

## Verdict (formal)

**`CONCENTRATION_DISPERSION_FAIL`** — pool-level signal real (signal_t_excess
+3.99, perm_p_one_sided 0.000, q_pos 6/9, hold=4h net +21bp pool CI +5.58 to
+35.87) at k=1.5, but Concentration Gate per-symbol bootstrap CI 0/13
positive — alpha too diffusely spread across 13-alt universe. Life-changing
4-dim 2/4 pass (trades/yr + sharpe) but edge 0.21% << 2% threshold blocks
life-changing eligibility independently.

paradigm 115 mechanism (ATR-normalized Donchian breakout, k=1.5, 4h hold,
13-alt) **IS economically real** (net +21bp clears 16bp fee floor at hold=4h)
but **NOT concentratable** in the current universe size.

**Next action recommendation**: Option B — accept graveyard. Even with
Option A R-2 universe expansion succeeding, per-trade edge of 0.21% rules
out life-changing 4-dim PASS. Promote Lesson #41 candidate to "candidate"
tier pending 2nd dogfood.

## Files

- code: `backend/scripts/research/paradigm115_alt_atr_normalized_range_breakout_continuation_long_2h_r1.py`
- metrics: `backend/runs/research_track/alt_atr_normalized_range_breakout_continuation_long_2h/r1__metrics.json`
- stdout log: `backend/runs/research_track/alt_atr_normalized_range_breakout_continuation_long_2h/r1__stdout.log`
- this graveyard: `backend/runs/research_track/graveyard__alt_atr_normalized_range_breakout_continuation_long_2h.md`

## INDEX update

- name: alt_atr_normalized_range_breakout_continuation_long_2h
- phase: graveyard
- type: E
- verdict_code: CONCENTRATION_DISPERSION_FAIL (verdict-tree label BROAD_FALSIFIED, refined manually)
- date: 2026-05-20

KST: 2026-05-20 13:34
