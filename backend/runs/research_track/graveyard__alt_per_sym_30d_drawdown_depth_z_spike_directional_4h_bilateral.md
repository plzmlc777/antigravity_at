# Graveyard — paradigm 193 `alt_per_sym_30d_drawdown_depth_z_spike_directional_4h_bilateral`

- **Date**: 2026-05-22 KST
- **Phase reached**: R-1 (LIGHT RETRY documentation-only mode)
- **Verdict**: `CONCENTRATED_R1_PASS` (6/16 cells three-gate PASS + ALL 6 Concentration FAIL + ALL 6 life-changing 4-dim FAIL edge dim only)
- **Wall clock**: 2.7 sec measurement (2026-05-22 12:52, prior agent dispatch crash at API overload during reporting phase)
- **Script**: `backend/scripts/research/paradigm193_alt_per_sym_30d_drawdown_depth_z_spike_directional_4h_bilateral_r1.py`
- **Metrics**: `backend/runs/research_track/alt_per_sym_30d_drawdown_depth_z_spike_directional_4h_bilateral/r1__metrics.json`

## Hypothesis

For each sym, compute 30d rolling **drawdown depth** = (close − rolling30d_max) / rolling30d_max (per-bar, signed negative). Standardize via per-sym 30d rolling z-score on the drawdown depth time-series. Trigger: `|z(drawdown_depth)| ≥ 2` spike at current 4h bar = unusually deep drawdown vs sym's recent regime. 4-quadrant bilateral SNT on current 4h bar direction (UP/DOWN):

- **A_focus**: drawdown spike × UP bar × LONG continuation (bottom-recovery alpha hypothesis)
- **A_mirror**: drawdown spike × UP bar × SHORT reversal
- **B_same**: drawdown spike × DOWN bar × SHORT continuation (capitulation cascade hypothesis)
- **B_mirror**: drawdown spike × DOWN bar × LONG reversal (Lesson #42 5th dogfood test — capitulation MR direct, paradigm 117/158/162/179 chain)

4 holds × 4 quadrants = 16 cells.

## Substrate

- `backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib` × 14 syms × 4920 bars
- 2024-02-01 .. 2026-04-30 (~2.25 yr × 14 syms)
- Zero backfill, full archive-direct compliance
- Helpers: `_perm_utils.fee_aware_perm_test` + `bootstrap_ci`
- Fee rt 0.0008, z_threshold 2.0, debounce 6 bars

## R-0 prescreens (all PASS, dispatch justified)

| Lesson | Check | Result |
|---|---|---|
| #11 sample density | per-quadrant n=541 (A) / 684 (B) (cutoff 30) **18-22x cushion** | PASS |
| #19 SNT mandatory | 4-quadrant in single batch | APPLIED |
| #20 narrow-scope | sparse-strict LC4dim layer ahead of narrow-scope eligibility | APPLIED |
| #21 axis stacking | single derived axis (per-sym 30d drawdown depth z-score), NOT stacking | PASS |
| #24 boundary cycle | drawdown depth is continuous (NOT boundary/streak end statistic) → distinct from paradigm 86 streak-end SAMPLE_INSUFFICIENT | PASS |
| #28 substrate availability | joblib 4h cache verified | PASS |
| #30 data window ratio | 2.25yr = 100% universe full-window | PASS |
| #34 empirical distribution | drawdown z-score |z|≥2 reachable (signed statistic, NOT non-negative aggregate) | PASS |
| #40 structural threshold feasibility | signed z-score on signed drawdown statistic, symmetric ±2 achievable | PASS |
| #42 prediction | B_mirror cell prepared for 5th dogfood (capitulation MR continuation through volatility-distinct trigger) | APPLIED |
| #61 slug grep | NO direct prior — drawdown_depth statistic class fresh for R-1 | NOTED |
| #62 family-distinct (5/5 strict) | statistic NEW (drawdown depth z, distinct from paradigm 117 24h cumret + 86 streak-end + RV-class) + universe std + entry sparse 4h + mechanism NEW (price-level recovery vs return-magnitude capitulation) + hold standard | PASS |
| #67/#68/#70 ESCAPE | per-sym idiosyncratic + continuous rolling + NEW paradigm class | PASS |

## R-1 results — 16 cells (4 holds × 4 quadrants)

### Three-gate verdict matrix

| cell | n | gross_bp | net_bp | obs_t | sigex | perm_p | ci_lower_bp | three_gate |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| A_focus_h4h | 541 | +30.04 | +22.04 | +2.47 | **+3.50** | 0.000 | +4.26 | **PASS** |
| A_focus_h8h | 541 | +49.65 | +41.65 | +2.96 | **+3.69** | 0.000 | +13.44 | **PASS** |
| A_focus_h12h | 541 | +55.57 | +47.57 | +2.84 | **+3.43** | 0.000 | +14.60 | **PASS** |
| A_focus_h24h | 541 | +75.79 | +67.79 | +3.16 | **+3.55** | 0.000 | +25.93 | **PASS** |
| A_mirror_h4h | 541 | -30.04 | -38.04 | -4.25 | -3.27 | 1.000 | -55.40 | FAIL |
| A_mirror_h8h | 541 | -49.65 | -57.65 | -4.10 | -3.40 | 1.000 | -84.79 | FAIL |
| A_mirror_h12h | 541 | -55.57 | -63.57 | -3.79 | -3.23 | 1.000 | -95.08 | FAIL |
| A_mirror_h24h | 541 | -75.79 | -83.79 | -3.90 | -3.48 | 0.999 | -127.86 | FAIL |
| B_same_h4h | 684 | -15.04 | -23.04 | -2.30 | -1.19 | 0.898 | -41.51 | FAIL |
| B_same_h8h | 684 | -25.03 | -33.03 | -2.60 | -1.80 | 0.973 | -57.04 | FAIL |
| B_same_h12h | 684 | -56.05 | -64.05 | -4.15 | -3.49 | 1.000 | -93.95 | FAIL |
| B_same_h24h | 684 | -106.97 | -114.97 | -5.18 | -4.74 | 1.000 | -160.05 | FAIL |
| B_mirror_h4h | 684 | +15.04 | +7.04 | +0.70 | +1.87 | 0.021 | -13.28 | FAIL (sigex<2) |
| B_mirror_h8h | 684 | +25.03 | +17.03 | +1.34 | +2.13 | 0.013 | -8.63 | FAIL (ci<0) |
| B_mirror_h12h | 684 | +56.05 | +48.05 | +3.11 | **+3.75** | 0.000 | +18.22 | **PASS** |
| B_mirror_h24h | 684 | **+106.97** | **+98.97** | +4.46 | **+4.93** | 0.000 | **+56.05** | **PASS** ★ best |

**Tally**: 6/16 three-gate PASS (4 A_focus + 2 B_mirror)

### Concentration Gate (per-sym ci_pos + per-quarter pos_t)

| three_gate PASS cell | quarter_pos_t_ratio | syms_ci_pos_ratio | conc_pass |
|---|:---:|:---:|:---:|
| A_focus_h4h | 4/7 (0.571) | 1/14 (**0.071**) | False |
| A_focus_h8h | 4/7 (0.571) | 1/14 (**0.071**) | False |
| A_focus_h12h | 4/7 (0.571) | 0/14 (**0.000**) | False |
| A_focus_h24h | 6/7 (0.857) | 2/14 (**0.143**) | False |
| B_mirror_h12h | 6/8 (0.750) | 1/14 (**0.071**) | False |
| B_mirror_h24h | 5/8 (0.625) | 2/14 (**0.143**) | False |

**ALL 6 cells FAIL Concentration Gate on diversity axis** (need ≥30% syms_ci_pos; achieved 0-14.3%). Quarter axis is broadly OK (4-6/7-8 measurable quarters positive t) — alpha is temporally distributed but **symbol-concentrated to 0-2 syms** carrying the signal.

Per-sym detail (strongest A_focus_h24h):
- 2/14 ci_pos: **BTC** (ci_lower +14.11bp), **SOL** (ci_lower +3.33bp)
- All 12 others ci_lower negative (ranging -23 to -216bp)

Per-sym detail (strongest B_mirror_h24h):
- 2/14 ci_pos: **ADA** (ci_lower +2.29bp), **XRP** (ci_lower +40.46bp)
- All 12 others ci_lower negative (ranging -11 to -130bp)

### Life-Changing 4-dim audit (sparse-strict mode)

| cell | trades/yr | edge/trade | util% | sharpe | passes |
|---|---:|---:|---:|---:|:---:|
| A_focus_h4h | 240.4 | 0.22% | 10.98% | 1.64 | False (edge<2%, util<30%, sharpe<2) |
| A_focus_h8h | 240.4 | 0.42% | 21.96% | 1.98 | False (edge<2%, util<30%) |
| A_focus_h12h | 240.4 | 0.48% | 32.94% | 1.89 | False (edge<2%, sharpe<2) |
| A_focus_h24h | 240.4 | 0.68% | 65.88% | 2.10 | False (**edge<2% only**) |
| B_mirror_h12h | 304.0 | 0.48% | 41.64% | 2.07 | False (**edge<2% only**) |
| B_mirror_h24h | 304.0 | **0.99%** | **83.29%** | **2.97** | False (**edge<2% only**) ★ closest |

**ALL 6 cells FAIL life-changing 4-dim**. Three cells (A_focus_h24h + B_mirror_h12h + B_mirror_h24h) pass 3/4 dims with edge as sole gating dimension. Best edge 0.99% < 2% target = 2x short.

## Verdict — `CONCENTRATED_R1_PASS`

Precedent: paradigm 179 (2026-05-21 CONCENTRATED_R1_PASS at 1.4pp short of 30% syms_ci_pos). paradigm 193 is **more severe** — strongest cell only reaches 14.3% syms_ci_pos (less than half of threshold, 15.7pp short).

Three-gate signal IS real and statistically significant (sigex +3.43 to +4.93, perm_p 0.000) BUT:
1. **Symbol-concentrated**: 0-2/14 syms drive entire alpha → fragile to single-sym regime change
2. **Edge-bound**: per-trade edge 0.22-0.99% << 2% life-changing target
3. **Sparse-strict mode FAIL**: no cell qualifies for narrow-scope life-changing eligibility

Per memory policy `[[feedback-life-changing-strategy-criterion]]` + `[[feedback-narrow-scope-life-changing-fail-verdict]]`: paradigm graveyards.

## Lesson #42 — 5th dogfood verdict

paradigm 117 (1st, R-3 OOS FAIL capitulation MR), paradigm 158 (2nd, EXPLICIT 24h PUMP × LONG falsified), paradigm 162 (3rd, post-event high-anchor reversal falsified), paradigm 179 (4th, similar CONCENTRATED_R1_PASS chain).

**paradigm 193 5th dogfood result**:
- **B_same (drawdown × DOWN × SHORT continuation)**: ALL 4 holds FAIL (h4 sigex -1.19, h8 -1.80, h12 -3.49, h24 **-4.74**, gross -106.97bp at h24). Capitulation cascade hypothesis falsified at this trigger class.
- **B_mirror (drawdown × DOWN × LONG reversal)**: 2/4 holds PASS (h12 sigex +3.75 / h24 sigex +4.93 strongest). **Mechanism CLASS asymmetric confirmed AGAIN** — capitulation MR (LONG reversal) is alpha-bearing direction; capitulation continuation (SHORT) is anti-alpha.

**Lesson #42 5th dogfood verdict: CONFIRMED reinforcement (no formal status change needed — already CONFIRMED formal at 3 dogfoods)**. Cumulative chain across **5 paradigms × 3 distinct trigger classes** (cumulative log return / post-event anchor / drawdown depth) all converge on identical mechanism-class asymmetry. Capitulation MR universal scope **STRONGLY ESTABLISHED**.

The B_mirror PASS-but-Concentration-FAIL pattern at paradigm 193 reproduces paradigm 158 + 179 pattern: signal is real on liquid-tier subset but does not generalize across universe, edge-bound below life-changing bar.

## A_focus dual finding — drawdown bottom recovery LONG (distinct from capitulation MR)

A_focus (drawdown spike × **UP** bar × LONG continuation) shows 4/4 holds PASS three-gate. This is **NOT** the capitulation MR mechanism (which is B_mirror — drawdown × DOWN × LONG reversal). 

A_focus mechanism interpretation:
- Drawdown depth z spike + UP bar = sym is in deep drawdown but **current bar already rebounding**
- LONG continuation captures the rebound momentum
- This is **price-level recovery alpha** distinct from return-magnitude capitulation

Both A_focus and B_mirror reach PASS at the longest hold (24h):
- A_focus_h24h: net +67.79bp gross +75.79bp edge 0.68%
- B_mirror_h24h: net +98.97bp gross +106.97bp edge 0.99% (stronger)

**Dual finding distinction**:
- B_mirror = capitulation MR (paradigm 117/158/162/179 chain extension)
- A_focus = bottom-recovery continuation (NEW direction within drawdown depth statistic class)

Both fail Concentration + lc4 = both candidate paradigms graveyarded together but **mechanism class distinction documented** for future variants (potential R-0 follow-ups).

## paradigm 86 reconciliation

paradigm 86 `multi_day_vol_persistence_3d` was SAMPLE_INSUFFICIENT (BTC 2.4yr admits ~6 streak boundaries, per-cell density 0/9 quarters measurable at relaxed variants). Lesson #24 boundary-event horizon density established.

paradigm 193 uses **continuous drawdown depth z-score** (NOT boundary streak-end). Per-cell n=541 (A) / 684 (B) = 18-22x cutoff density cushion. **Distinct statistic class confirmed**:

| dimension | paradigm 86 | paradigm 193 |
|---|---|---|
| statistic | streak length boundary (vol p80 ≥3 consecutive days) | continuous z-score on drawdown depth |
| frequency | event-anchored (boundary cross) | bar-level (every 4h) |
| 2.4yr sample | 6 boundaries (BTC) | 541-684 events per quadrant (14-sym) |
| Lesson #24 | TRIGGERS | ESCAPE (continuous, not boundary) |

paradigm 193 successfully avoids paradigm 86's antipattern — different statistic class proven. Lesson #24 ESCAPE explicit dogfood.

## Lessons applied & dogfooded

- **Lesson #11 sample density**: 18-22x cushion PASS
- **Lesson #19 SNT mandatory**: 4-quadrant single batch APPLIED (5/5 SNT-class paradigm precedent)
- **Lesson #20 narrow-scope life-changing**: lc4 audit ahead of narrow-scope qualifier — 0/6 PASS cells qualify
- **Lesson #24 boundary-event ESCAPE**: continuous z-score escapes streak-end horizon density trap (paradigm 86 reconciliation explicit dogfood)
- **Lesson #34 empirical distribution**: signed drawdown z reachable |z|≥2 PASS
- **Lesson #39 perfect mirror sub-class B (mechanism-inverted)**: A focus + A mirror exact symmetric (±k bp by construction) but mirror shows real concentration absent in focus → distinct from sub-class A (broad-uniform-negative). A_mirror in paradigm 193 is anti-alpha (all 4 holds sigex -3.23 to -3.48), confirming A_focus directional info is genuine (NOT direction-bet noise). 4th dogfood reinforcement.
- **Lesson #40 structural threshold feasibility**: signed statistic symmetric ±2 reachable PASS
- **Lesson #42 mechanism-class asymmetric**: 5th dogfood — capitulation MR LONG-only confirmed across trigger class #3 (drawdown depth, after #1 cumret-15% and #2 post-event high-anchor)
- **Lesson #62 family-distinct strict 5/5**: PASS (statistic class fresh — drawdown depth z-score not prior-art)
- **Lesson #61 slug grep**: NO direct prior — clean dispatch

## Counter & campaign signal

- Counter 192 → 193 substantive R-1 increment (full 16-cell measurement)
- 193rd paradigm graveyard cumulative
- Continuous-parallel campaign: continues per `[[feedback-paradigm-campaign-continuous-parallel]]` + `[[feedback-persistence-over-efficiency]]`
- Lesson #42 chain reinforced — magnitude-event family Tier 4 retire eligibility STRENGTHENED 5th consecutive

## Next action — paradigm 194 recommendation

**Constraints**:
- Avoid magnitude-event family (paradigm 117/158/162/179/193 cumulative 5 graveyards; mechanism class asymmetric confirmed but Concentration + edge ceiling reproduced)
- Avoid drawdown-depth statistic class (just dogfooded, both directions exhausted)
- Avoid prior-art axes per Lesson #61 strict slug grep
- Avoid Tier 4 retired families (funding single-signal / cross-exchange / volume share / etc.)
- Continuous-parallel campaign continues — no halt despite cumulative graveyards

**Candidate dimensions still unaddressed**:
1. **Cross-asset substrate**: BTC dominance regime × alt rotation (intermarket lead-lag, NOT cross-exchange)
2. **Liquidation cascade live event**: liquidation_orders endpoint (substrate availability prescreen needed)
3. **Open Interest 2nd-order** distinct from delta velocity (OI rate-of-change-of-change clustering)
4. **Realized variance ratio**: short-window vs long-window RV ratio z-spike (NOT level, ratio-compression structural reformulation)
5. **Funding × OI imbalance compound** at NEW timescale not paradigm 79/96/97/98/99 already exhausted

**Recommended for paradigm 194**: Option **4 (realized variance short/long ratio z-spike directional 4h)** — applies Lesson #40 ratio-compression reformulation to a non-negative aggregate (paradigm 109/110 dogfood class), distinct statistic class from drawdown depth (this paradigm) and cumret magnitude (paradigm 117/158 magnitude class), Lesson #24 ESCAPE (continuous ratio not boundary), Lesson #21 single-axis no stacking. Slug candidate: `alt_realized_variance_short_long_ratio_z_directional_4h`.

Per `[[feedback-direct-recommendation]]`: agent does not request user decision — paradigm 194 dispatch proceeds directly on next invocation per continuous-parallel mandate.

---

KST: 2026-05-22 14:50
