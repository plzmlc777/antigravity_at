# Graveyard — paradigm 153 `alt_range_volume_divergence_percentile_rank_directional_4h`

**Date**: 2026-05-21 14:53 KST
**Phase halt**: R-1 (4-quadrant SNT executed)
**Verdict**: `BROAD_FALSIFIED` (Lesson #40 reformulate structural fix SUCCESS + mechanism alpha 부재)
**Counter**: 152 → **153**, non-PASS streak 23 → **24**

## Hypothesis

- **Mechanism**: range_z − vol_z divergence (paradigm 152 identical) as thin/consolidation regime classifier
- **Statistic class**: percentile rank of divergence over 30d rolling window (paradigm 152 z-score 분포 negatively-skewed 구조적 asymmetry → distribution-agnostic [0,1] bounded reformulate)
- **Trigger**: pct_rank > 0.95 (top 5%) OR < 0.05 (bottom 5%)
- **Direction story**:
  - rank > 0.95 (HIGH divergence, thin spike) → 4h **MR** of trigger-bar close direction
  - rank < 0.05 (LOW divergence, consolidation) → 4h **CONTINUATION** of trigger-bar close direction
- **Family-distinct vs paradigm 152**: trigger formulation only (pct rank vs z), same underlying mechanism story

## R-0 prescreen — Lesson #40 reformulate structural fix VERIFIED

- pct_rank bounded [0, 1] by construction → both sides structurally attainable
- **paradigm 152 (z-score)**: per_cell_pos=28.7 (FAIL) / per_cell_neg=62.1 / asymmetric p99<2.0 13/13 syms
- **paradigm 153 (pct rank)**: total_top=3282 / total_bot=3322 / ratio=**0.99 perfect symmetry** / per_cell top=365 bot=369 (≫30)
- 13/13 syms with both top and bottom triggers
- **Lesson #40 reformulate first STRUCTURED dogfood SUCCESS at the structural layer** (paradigm 110 was 1st natural reformulate precedent)
- prescreen wall clock: ~12s

## R-1 4-quadrant SNT (Lesson #19 mandatory)

```
Quadrant              n      mean_bp  sig_t_ex  perm_p   ci_lo_bp  ci_up_bp  3gate
A_focus_top_MR       3343    -8.87    0.302     0.643    -17.32    -0.51     False
A_mirror_top_CONT    3343    -7.13    0.714     0.786    -15.49     1.32     False
B_focus_bot_CONT     3358    -0.11    2.190     1.000     -8.20     7.98     False
B_mirror_bot_MR      3358   -15.89   -1.461     0.065    -23.98    -7.80     False
```

### Critical reading — sigex paradox on B_focus

- B_focus_bot_CONT sigex=**+2.190** appears to clear 3-gate threshold, BUT:
  - `obs_t = -0.026` (essentially zero, mean is ≈0)
  - `null_mean_t = -2.216` (fee-drift null is strongly negative as expected for 8bp/4h hold)
  - `signal_t_excess = obs_t - null_mean_t = -0.026 - (-2.216) = +2.19`
- Interpretation: observed return is "above the fee-drift floor" but is itself ≈ zero → **alpha is exactly fee** (8bp net-zero), CI lower=-8.20 (negative), perm_p=1.0 (saturated against null draws because obs is at the upper edge)
- Three-gate fails because CI lower not > 0 AND perm_p not ≤ 0.10
- Classic "above-fee-drift but at-fee-floor" pattern — no usable alpha despite passing the sigex sub-gate

### Lesson #39 sub-class detection — neither A nor B triggered

- sub_class_A (broad-uniform-negative ≤ -2 sigex all 4): **False** (B_focus +2.19 lifts threshold)
- sub_class_B (mechanism inverted, mirror dominates focus by ≥1.5σ): **False**
  - A side: mirror=+0.71 vs focus=+0.30, delta=+0.41 (no inversion)
  - B side: mirror=-1.46 vs focus=+2.19, delta=-3.65 (focus is correct direction; mechanism direction VERIFIED ≠ paradigm 110 inversion antipattern)

### paradigm 110 mechanism direction inversion check — SAFE

- paradigm 110 precedent (funding neg z → pct rank ≤0.10) was 1st natural reformulate that achieved structural fix but flipped direction (mechanism inverted graveyard)
- paradigm 153 explicit Lesson #44 37th xref check executed: both A_mirror and B_mirror did NOT dominate corresponding focus by ≥1.5σ → direction is correct
- **Lesson #44 amendment 37th xref dogfood**: paradigm 110 inversion antipattern check 정상 작동 + NEGATIVE result (paradigm 153 direction not inverted; failure mode different = mechanism doesn't carry alpha at all)

## Hold sweep (Lesson #37 full scan)

```
Hold   A_focus_MR (mean_bp / sigex)      B_focus_CONT (mean_bp / sigex)
4h     -8.87 / 0.302  3gate=False        -0.11 / 2.190  3gate=False
8h     -9.47 / -0.414 3gate=False        -5.41 / 0.320  3gate=False
12h     0.95 / 1.216  3gate=False         1.74 / 1.323  3gate=False
```

- 0/6 off-primary cells PASS three-gate
- 12h shows marginal mean_bp positive but sigex < 2.0 — fee floor sub-dominance
- No hidden cell PASS escapes primary inspection

## Concentration diagnostics — B_focus (closest cell)

- per_quarter: q_pos_t_ratio = 0.40 (4/10) — FAIL (cutoff 0.50)
- per_symbol: sym_ci_pos_ratio = **0.00** (0/13) — FAIL CATEGORICALLY (cutoff 0.30)
- **Zero symbols** have CI lower > 0 — no per-symbol alpha concentration
- Wide per-sym mean_bp dispersion: XRPUSDT -29.78 / DOGEUSDT +19.58 (random noise, not alpha)

## Life-changing 4-dim — both focus sides FAIL EDGE

- A_focus_MR: trades/yr=1489, edge=**-0.089%**, util=68.0%, sharpe=-1.34 → 4/4 dim fail (edge negative)
- B_focus_CONT: trades/yr=1496, edge=**-0.001%**, util=68.3%, sharpe=-0.02 → 4/4 dim fail (edge ≈0, fee saturated)
- High trigger frequency (≈1490/yr per side) inherent to top/bottom 5% × 13 syms × 4h, but the alpha-per-trade vanishes against the fee floor

## Lesson #46 stratified + sign-flip diagnostics

- A_focus_MR: q_meas=10 pos_q=3 neg_q=7 flips=3/9 strong_alternating=False
- B_focus_CONT: q_meas=10 pos_q=4 neg_q=6 flips=5/9 strong_alternating=False
- Neither side shows persistent positive quarters → no robust regime
- Sign-flip warning not triggered (≤ max possible), but balance leans negative

## Structural diagnosis — Lesson #40 sub-class C verification (mechanism agnostic alpha-loss)

paradigm 110 = sub-class C (mechanism inversion): structural fix worked + direction flipped
paradigm 152 = sub-class D (asymmetric distribution): structural threshold infeasible
paradigm 153 = NEW pattern: structural fix worked, direction stayed correct, **but underlying mechanism itself carries no alpha**

This is a clean separation result:
- **Layer 1 (R-0)**: pct rank reformulate fixes the asymmetry → succeeded
- **Layer 2 (R-1 direction)**: mirror does NOT dominate focus → paradigm 110 inversion antipattern avoided
- **Layer 3 (R-1 alpha)**: focus mean_bp ≈ fee floor → no alpha exists in the mechanism story regardless of trigger form

This is **honest negative evidence** that the "range-volume divergence = thin/consolidation regime classifier" mechanism itself does not produce 4h directional alpha at the 14-alt panel scale, independent of statistic class (z-score or pct rank).

## NEW Lesson #63 CANDIDATE — Reformulate structural fix ≠ mechanism alpha resurrection

> **Lesson #63 candidate (1st dogfood paradigm 153)**:
> A successful Lesson #40 reformulate (e.g., z → pct rank) that fixes structural threshold infeasibility may still produce a BROAD_FALSIFIED R-1 if the underlying mechanism itself carries no alpha. The reformulate is necessary for sample density / threshold attainability but is insufficient to grant alpha. R-0 PASS on reformulate axis does NOT predict R-1 PASS on mechanism axis. Future Lesson #40 reformulate candidates must explicitly distinguish "structural feasibility" (R-0) from "mechanism alpha" (R-1) in dispatch rationale.

Promotion path: 2nd dogfood (future Lesson #40 reformulate candidate that BROAD_FALSIFIED) → CONFIRMED 자격.

## Lesson #40 sub-pattern catalog update (3 sub-classes + sub-class D from p152 → reformulate outcomes mapped)

| Sub-class | Origin | Trigger Pattern | Reformulate Result |
|---|---|---|---|
| A (p109+110+152 base) | non-negative aggregate stat + symmetric z ≤ -T | structurally infeasible | reformulate via pct rank required |
| B (p110 natural) | funding neg z + pct rank reformulate | structural fix SUCCESS | mechanism direction inverted → graveyard |
| C (p152 structured detection) | z subtraction asymmetric distribution | structural fix needed | reformulate path opened |
| **D (p153 structured outcome) NEW** | pct rank reformulate of subtraction divergence | **structural fix SUCCESS** | **mechanism alpha 부재** → graveyard |

paradigm 153 = sub-class D = "reformulate structurally succeeded but mechanism is alpha-empty"

## Family-distinct verification (Lesson #44 amendment 37th xref)

- paradigm 152 (z-score subtraction) GRAVEYARD: distinct via pct rank trigger formulation
- paradigm 110 (funding pct rank precedent) GRAVEYARD: structural fix precedent; paradigm 153 explicit direction inversion check executed → did NOT invert (paradigm 110 antipattern AVOIDED)
- paradigm 116/129/137/142/144 range/volume family: all distinct
- DNA overlap: substrate (12-col klines 4h) + same divergence statistic shared with p152; **trigger statistic class (pct rank) is the genuinely new axis**

## Lessons applied & dogfooded

- **Lesson #11** sample density — R-0 + R-1 both PASS (per-cell ≥ 350)
- **Lesson #16** concentration gate STRICT — B_focus sym_ci_pos 0/13 CATEGORICAL FAIL
- **Lesson #19** 4-quadrant SNT mandatory — executed
- **Lesson #30** data_window_ratio — 1.00 uniform
- **Lesson #37** full sweep verdict scan — 0/6 off-primary PASS
- **Lesson #39** sub-class A/B detection — neither triggered (NEW outcome pattern for paradigm 153)
- **Lesson #40** structural threshold feasibility — REFORMULATE VERIFIED + 1st structured dogfood SUCCESS at structural layer
- **Lesson #40 sub-class D NEW** — reformulate structural success + mechanism alpha 부재 (sub-class catalog amendment)
- **Lesson #44 amendment 37th xref** — paradigm 110 direction inversion antipattern check executed + AVOIDED
- **Lesson #46** stratified n=50×4q + sign-flip — strong_alternating False both sides
- **Lesson #54** same-bar subtraction (not ratio) — identical to p152, no degeneracy
- **Lesson #58 candidate** range-vol corr healthy zone — xref p152 PASS confirmed
- **NARROW_SCOPE_LIFE_CHANGING_FAIL** verdict layer — not reached (3gate fail upstream)
- **NEW Lesson #63 candidate** reformulate structural fix ≠ mechanism alpha resurrection — 1st dogfood

## Artifacts

- `backend/scripts/research/paradigm153_r0_prescreen.py` (compile clean, executed 2026-05-21 14:50 KST)
- `backend/scripts/research/paradigm153_r1.py` (compile clean, executed 2026-05-21 14:53 KST, wall clock 2.5s)
- `backend/runs/research_track/alt_range_volume_divergence_percentile_rank_directional_4h/r0_prescreen.json`
- `backend/runs/research_track/alt_range_volume_divergence_percentile_rank_directional_4h/r1__metrics.json`

## Counter

- Graveyards: 152 → **153**
- R-5 LIVE: 10 (unchanged)
- Non-PASS streak: 23 → **24**
- R-5 yield: 10/153 = **6.54%**
- Lessons: 34 confirmed + 16 candidates → 34 confirmed + **17 candidates** (NEW Lesson #63 candidate)
- Q3 §6.50 next entry

## Next paradigm recommendation

Family axis options:
1. **Different mechanism family** — range-volume divergence axis has now exhausted (p152 z fail + p153 pct rank fix verified but no alpha). Pivot away from "range-volume joint regime classifier" mechanism story.
2. **Cross-timeframe regime layer** — e.g., 1d divergence regime × 4h entry trigger (MTF dual confirmation), to test whether higher-TF regime context resurrects alpha
3. **OI×range or OI×volume joint** (avoiding range-volume since exhausted) — paradigm 142v2 already covered taker_buy quote_vol; OI dimension axis underutilized
4. **Funding microstructure axis** — funding family Tier 4 retired (6 graveyards) so this is closed
5. **Listing/event boundary family** — Tier 4 retired
6. **Lifecycle live mode dispatch** — 2026-05-29+ when WS recorder accumulates 60+d (per [[project-life-changing-campaign-session1-halt]])

**권고 1순위**: option 2 (MTF dual confirmation regime × entry) — directly addresses paradigm 153's negative finding by adding a regime layer the bar-level mechanism lacks. Frame: 1d range-percentile rank regime gate + 4h trigger within regime.
