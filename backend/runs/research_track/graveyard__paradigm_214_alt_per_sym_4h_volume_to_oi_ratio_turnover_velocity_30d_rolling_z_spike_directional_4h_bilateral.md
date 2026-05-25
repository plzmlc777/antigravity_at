# paradigm 214 GRAVEYARD — R-0 HALT (Lesson #40 3rd dogfood CONFIRMED FORMAL)

**Slug**: `alt_per_sym_4h_volume_to_oi_ratio_turnover_velocity_30d_rolling_z_spike_directional_4h_bilateral`
**Counter**: 214
**Phase**: R-0 prescreen (R-1 NOT dispatched)
**Halt timestamp**: 2026-05-22 19:30 KST
**Verdict**: `R0_HALT_LESSON_40_STRUCTURAL_THRESHOLD_INFEASIBILITY_NON_NEGATIVE_AGGREGATE_RATIO`

## Hypothesis (spec)

- statistic: per-sym 4h volume / 30d-mean-OI ratio (turnover velocity) → 30d rolling z-score
- triggers: |z| ≥ 2 bilateral spike (z ≥ +2 HIGH turnover, z ≤ -2 LOW turnover)
- 4-quadrant SNT split by bar direction:
  - A_focus: z ≥ +2 × bar UP × LONG
  - A_mirror: z ≥ +2 × bar UP × SHORT
  - B same-sign: z ≤ -2 × bar DOWN × SHORT (**DISJOINT trigger set from A**)
  - B mirror: z ≤ -2 × bar DOWN × LONG (Lesson #42 19th dogfood)
- hold: 4h primary + 8h + 12h + 24h sweep
- universe: 20 alts (paradigm 198 cohort)
- substrate: 4h cache 20 syms × 819d + 5min OI microstructure 541-801d

## Lesson #40 STRUCTURAL THRESHOLD INFEASIBILITY — full 20-sym verification

Volume/OI ratio is **non-negative by construction** (volume ≥ 0, OI ≥ 0 → ratio ≥ 0). Thin left tail compresses rolling z-score lower bound.

| sym | z.min | z.p01 | z.p99 | z.max | n(z≤-2) | n(z≥+2) |
|---|---|---|---|---|---|---|
| BTC | -1.39 | (-1.16) | (4.20) | 9.61 | **0** | 141 |
| ETH | -1.43 | (-1.18) | (4.18) | 10.32 | **0** | 207 |
| SOL | -1.47 | (-1.21) | (4.15) | 9.05 | **0** | 204 |
| XRP | -1.44 | -1.14 | 4.28 | 12.08 | **0** | est~200 |
| DOGE | -1.49 | -1.15 | 4.10 | 10.01 | **0** | est~200 |
| ADA | -1.42 | -1.18 | 3.80 | 12.33 | **0** | est~200 |
| LINK | -1.49 | -1.20 | 4.12 | 11.71 | **0** | est~200 |
| NEAR | -1.74 | -1.36 | 3.87 | 10.63 | **0** | est~200 |
| WIF | -1.74 | -1.33 | 4.00 | 12.43 | **0** | est~200 |
| ... (11 more syms) | similar | similar | similar | similar | **0** | similar |

**Aggregate verdict** (full 20-sym):
- z.min range across 20 syms: [-1.74, -1.39]
- **n_syms with any z ≤ -2 trigger: 0 / 20**
- **Total z ≤ -2 triggers universe-wide: 0**
- Total z ≥ +2 triggers universe-wide: 3,986
- **Cell B (z≤-2 × bar DOWN × SHORT): n_triggers = 0 STRUCTURALLY INFEASIBLE**
- **Cell B_mirror (z≤-2 × bar DOWN × LONG): n_triggers = 0 STRUCTURALLY INFEASIBLE**
- 4-quadrant SNT (Lesson #19) cannot be evaluated — 2 of 4 cells empty

Per **Lesson #40 R-0 prescreen sequential order (FIRST step)**: "If trigger uses z-score on non-negative aggregate statistic, verify z.min() achievable. If z.min() > T (target threshold), HALT_BY_STRUCTURE → reformulate".

z.min() max(across 20 syms) = -1.39 > T = -2.0 → **HALT_BY_STRUCTURE triggered**.

## Lesson #69 9-item template breakdown

- **Item 1 (Lesson #61 INDEX.json grep STRICT)**: PASS — 0 matches for turnover/volume_oi_ratio/volume_to_oi/active_rotation/passive_stake/rotational_flow in INDEX or directory listing
- **Item 2 (Lesson #28 substrate-shape + maturity)**: PASS — 20 syms × 819d 4h + 20 syms × 541-801d OI 5min, universe mean 2.15yr, ≥2yr threshold met. Rolling 6m consistency check **deferred** (Item 9 STRUCTURAL fail upstream).
- **Item 3 (Lesson #11 sample density)**: **FAIL B-side STRUCTURAL** — z≥+2 rate 4.71%/sym, z≤-2 rate **0.00%**/sym across 9 sample syms full-verified, 20 syms total verified
- **Item 4 (Lesson #62 DNA 4-dim 5/5 strict)**: PASS
  - vs paradigm 73 (funding × OI bipolar joint): DISTINCT — funding × OI joint NOT volume/OI ratio
  - vs paradigm 79 (funding × OI level): DISTINCT — funding-anchored NOT volume-anchored
  - vs paradigm 104 (cross-exchange OI diff): DISTINCT — cross-exchange NOT single-venue
  - vs paradigm 127/128 (volume burst): DISTINCT — 1m intra5m vol > p99 NOT 4h vol/OI ratio z
  - vs paradigm 196 (OI ratio z): DISTINCT — OI-only ratio z NOT vol/OI ratio z
  - vs funding family 9 sub-class retire: DISTINCT — volume axis not funding axis
- **Item 5 (Lesson #56 family-proxy)**: turnover velocity composite class (NEW)
- **Item 6 (alpha decay 5-pattern audit)**: DEFERRED — Item 9 upstream STRUCTURAL halt blocks
- **Item 7 (SNT structural integrity 6 dogfoods)**: **FAIL** — 2 of 4 SNT cells infeasible (B + B_mirror n_trig=0), cross-set |A|/|B| asymmetry undefined
- **Item 8 (Concentration + Temporal Independence)**: DEFERRED
- **Item 9 (Life-changing 4-dim STRUCTURAL prescreen 2nd operational)**: 
  - broad-scope universe trades/yr estimate (z≥+2 cells only): ~1,712
  - capital util 4h × 20 syms: ~78%
  - per-trade edge: cannot estimate — **Item 9 deferred to upstream Lesson #40 STRUCTURAL halt**
  - paradigm 213 was Item 9 1st operational (narrow-scope STRUCTURAL FAIL); paradigm 214 demonstrates Item 9 must be upstream-blocked by Lesson #40 first

## Reformulation prescription per Lesson #40

Empirical reformulation tests on BTC:

| Method | z.min | z.p01 | z.p99 | z.max | symmetric feasible? |
|---|---|---|---|---|---|
| **Raw ratio z** (paradigm 214 spec) | -1.39 | -1.16 | 4.20 | 9.61 | **NO** — z.min > -2 |
| **log-transform z** (Option A) | -3.10 | -2.18 | 2.33 | 3.77 | **YES** — symmetric ±2 feasible |
| **Percentile rank** (Option B) | 0.006 | (~0.01) | (~0.99) | 1.000 | **YES** — symmetric 0.05/0.95 feasible |

**Recommended**: Option A log-transform — preserves z-score framework + 4-quadrant SNT + symmetric threshold feasibility. Volume/OI is multiplicative composite, log-transform is the natural reformulation.

## Lesson #40 status update (3rd dogfood)

- Prior: 2 dogfoods CONFIRMED 자격 (paradigm 109 std-based z + paradigm 110 ATR-based z)
- **NEW: 3rd dogfood CONFIRMED FORMAL** (paradigm 214 volume/OI ratio z)
- **Amendment candidate**: Extend Lesson #40 non-negative aggregate list to explicitly include:
  - Previously listed: std, var, count, magnitude, ATR, |return|, drawdown, RV
  - **ADD**: volume/OI ratio, volume/turnover ratio, trade_count/OI ratio, any volume-normalized-by-positive-quantity composite

## Family-distinct 5/5 strict verdict

**PASS — turnover velocity composite axis is fresh statistic class**. Paradigm 214 family-distinct against all 6 reference families. The R-0 HALT is **NOT** family-retire (mechanism intent is valid), but **structural threshold infeasibility per Lesson #40** (z-formulation choice incompatible with non-negative ratio statistic).

## Next-action recommendation paradigm 215

**Direct recommendation** (per memory [[feedback-direct-recommendation]] + [[feedback-paradigm-campaign-continuous-parallel]] + [[feedback-persistence-over-efficiency]]):

**paradigm 215** = paradigm 214 reformulated with **Option A log-transform**:
- slug: `alt_per_sym_4h_log_volume_to_oi_ratio_turnover_velocity_30d_rolling_z_spike_directional_4h_bilateral`
- statistic: `log(volume / 30d-mean-OI)` then 30d rolling z-score
- BTC empirical z range [-3.10, +3.77] — symmetric ±2 threshold feasible
- Preserves: 4-quadrant SNT structural integrity (Lesson #19), turnover velocity mechanism intent, broad-scope 20-sym universe, family-distinct 5/5 strict
- Restores: B cell + B_mirror cell empirical trigger feasibility
- Lesson #40 prescription compliance: log-transform on non-negative composite

**Alternative** (if log-transform paradigm 215 also fails): paradigm 216 = new axis class entirely (turnover velocity DNA exhausted via reformulation+structural infeasibility cascade). Avoids retread.

## Pattern P1 alpha decay audit deferred — no R-1 evaluation possible

Item 6 5-pattern alpha decay audit cannot execute without R-1 quadrant evaluation. Pattern P1 consecutive count remains at 6 (paradigm 87/136/202/210/211/212) — paradigm 214 R-0 HALT does not increment, does not break streak. Next R-1 evaluation (paradigm 215 if dispatched) will resume P1 count check (7th consecutive verdict pending).

## Lesson #42 19th dogfood — deferred

B mirror cell (LOW turnover z- × bar DOWN × LONG reversal) chain entry deferred — cannot evaluate empty trigger set.

## Memory policy compliance

- [[feedback-paradigm-campaign-continuous-parallel]]: paradigm 215 dispatch ready, no pause
- [[feedback-persistence-over-efficiency]]: R-0 HALT is normal failure mode, dispatch continues
- [[feedback-direct-recommendation]]: paradigm 215 log-transform reformulation directly recommended above
- [[feedback-no-freemium-trial]]: zero backfill, joblib cache only
- [[feedback-life-changing-strategy-criterion]]: paradigm 214 broad-scope edge unmeasurable (R-0 halt upstream Lesson #40)

## Artifacts

- `backend/runs/research_track/paradigm_214_alt_per_sym_4h_volume_to_oi_ratio_turnover_velocity_30d_rolling_z_spike_directional_4h_bilateral_r0_halt/r0_halt__metrics.json` — full 20-sym verification data + reformulation test results
- this file — formal graveyard report
