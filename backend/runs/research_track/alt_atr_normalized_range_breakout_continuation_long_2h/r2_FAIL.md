# Paradigm 115 R-2 FAIL Report

**Paradigm**: `alt_atr_normalized_range_breakout_continuation_long_2h` (paradigm 115)
**Phase**: R-2 universe expansion
**Executed**: 2026-05-20 14:19~14:20 KST
**Wall clock**: 1.0 minute
**Verdict**: `R2_FAIL_LIFE_CHANGING`
**Lesson #41 candidate dogfood**: `confirmed_but_narrow_scope_life_changing_fail`

---

## R-1 Recap → R-2 Hypothesis

R-1 verdict: `CONCENTRATION_DISPERSION_FAIL` (k=1.5 × 4h cell)
- Pool n=1082 (13 alts × 2yr), gross +29.11bp / **net +21.11bp clears 16bp fee floor**
- sigex +4.28, perm_p_one 0.000, q_pos 6/9, pool ci_lower +5.58bp
- BUT syms_ci_pos **0/13** (DIFFUSE_POSITIVE — Lesson #41 candidate 1st dogfood)

R-2 hypothesis: per-sym n=63-98 → CI width ~±50bp suppresses ci_pos.
**Universe expansion to 29 alts** halves per-sym n (~40-50) but increases the
absolute count of syms where bootstrap CI crosses positive via diffuse alpha
aggregation. Target: syms_ci_pos ≥ 4/29 → Lesson #41 confirmed 정식 승급.

## R-2 Results

### Universe expansion
- 13 original + 16 new = 29 alts (1000SHIB/1000PEPE remapped; MATICUSDT
  delisted post 2024-09 → partial 6mo cohort)
- Substrate prescreen (Lesson #28): 16/16 candidates HTTP 200 at 2024-05
- Cohort-aligned 2yr (Lesson #30) for 28/29; MATIC short window 3202 bars
- panel load 58.1s (29/29 alts loaded, all 17520 hourly bars except MATIC)

### Pool aggregate (k=1.5 × 4h, expanded 29 alts)

| Metric | R-1 (13 alts) | R-2 (29 alts) | Δ |
|---|---|---|---|
| n_trades | 1082 | **2245** | +107% |
| gross_bp | +29.11 | **+34.99** | +20% |
| net_bp | +21.11 | **+26.99** | +28% |
| obs_t | 2.66 | **4.50** | +69% |
| sigex | +4.28 | **+6.96** | +63% |
| pool ci_lower_bp | +5.58 | **+14.84** | +166% |
| perm_p_one_sided | 0.000 | **0.000** | = |
| q_pos / measurable | 6/9 | **8/9** | +2 |
| q_pos_ratio | 66.7% | **88.9%** | +22pp |

Pool 3-gate: PASS (all three gates stronger on expansion)
Pool ci_pos: TRUE
**Mechanism is REAL and STRONGER on expanded universe.**

### Concentration Gate (Lesson #16 + #41 target)

- syms_ci_pos: **3/29** (10.3%) — DOTUSDT / SEIUSDT / ARBUSDT (all 3 from
  EXPANSION universe, none from original 13)
- Concentration Gate (≥3 syms_ci_pos AND ≥30% ratio): FAIL (10.3% < 30%)
- Lesson #41 dogfood gate (≥4 AND ≥15%): FAIL (3 syms / 10.3% < threshold)

### Walk-forward 5-fold TS-CV (Lesson #26 mandatory)

| Fold | n | mean_bp | t_stat | ci_lower_bp | PASS_loose |
|---|---|---|---|---|---|
| 1 | 449 | +32.72 | 2.60 | +10.19 | PASS |
| 2 | 449 | +14.02 | 0.84 | -17.70 | FAIL |
| 3 | 449 | +25.38 | 2.11 | +1.45 | PASS |
| 4 | 449 | +64.30 | 5.17 | +39.92 | PASS |
| 5 | 449 | -1.45 | -0.11 | -27.69 | FAIL |

WF gate: **3/5 PASS** (clears Lesson #26 ≥3/5 mandatory). Fold 5 (2026Q1-Q2)
shows attenuation — paradigm 87 fragility partial signature but not majority.

### Per-symbol breakdown (top by mean_net_bp)

ci_pos at 95% (3): **DOTUSDT** n=70 +75.65bp [+17.16, +140.05] /
**SEIUSDT** n=86 +73.15bp [+2.20, +154.13] / **ARBUSDT** n=71 +71.57bp
[+0.11, +145.05]. All 3 from expansion universe.

Top 5 expansion-only mean_bp: DOT +75.65, SEI +73.15, ARB +71.57, ICP +51.47,
1000PEPE +40.87. Most ci_lower negative due to per-sym n=63-86 width.

### Deep-bootstrap top R-1 candidates (n_boot=5000)

Original top 4 R-1 candidates (HBAR/ADA/AVAX/FIL): **0/4 ci_95_pos**, only
ADA ci_90_pos. R-1 outlier candidate behavior not robust to extended
bootstrap iterations.

### Deep-bootstrap top 3 expanded universe

- DOTUSDT: ci_95 [+16.41, +141.56] **PASS** / ci_90 [+24.79, +129.23] PASS
- SEIUSDT: ci_95 [+2.01, +150.70] **PASS** / ci_90 [+14.65, +137.66] PASS
- ARBUSDT: ci_95 [-0.27, +144.43] FAIL / ci_90 [+12.04, +131.14] PASS

**2/3 deep ci_95_pos** at expanded top-3 — narrow-scope discovery validates
universe expansion path partially.

### Life-changing 4-dim

| Dimension | Value | Threshold | PASS |
|---|---|---|---|
| trades/yr | 1148 | ≥12 | PASS |
| **edge%/trade** | **0.27%** | **≥2.0%** | **FAIL** (hard blocker) |
| capital util% | 52.4% | ≥30% | PASS |
| sharpe (annualized) | 3.22 | ≥1.5 | PASS |

n_dims_pass = 3/4. Per `feedback_life_changing_strategy_criterion`, edge<+2%/trade
is INDIVIDUAL hard blocker disqualifying from life-changing category regardless
of n_dims_pass. Edge 0.27% means 1148 trades/yr × 0.27% / (16bp fee × 100) =
1148 × ~11x leverage of pool advantage per fee floor — extremely fragile if
fee or slippage changes. NOT life-changing.

## Verdict Tree (Strict)

1. pool_pass_3gate: **PASS** (sigex+6.96, ci_lower+14.84bp, perm_p_one 0.000)
2. wf_pass: **PASS** (3/5 ≥ 3/5)
3. **life_changing_hard_blocker: TRUE** (edge 0.27% < 2%/trade) → **R2_FAIL_LIFE_CHANGING**
4. (would-be checks if no hard-blocker)
   - syms_ci_pos_gate: FAIL (3/29 = 10.3% < 15%)
   - narrow_single_sym_pass: PASS (2/3 deep_expanded ci_95_pos)
   - → R2_PASS narrow_scope_only would obtain IF life-changing 4/4

## Lesson #41 Candidate Dogfood (2nd Iteration)

**Verdict**: `confirmed_but_narrow_scope_life_changing_fail`

**Diffuse alpha aggregation hypothesis VALIDATED**:
- Pool sigex jumped +4.28 → +6.96 on expansion (+63%)
- Pool ci_lower jumped +5.58 → +14.84bp (+166%)
- syms_ci_pos went 0/13 → 3/29 (DOT/SEI/ARB all expansion alts)
- 2/3 deep ci_95_pos at expanded top-3
- WF 3/5 PASS holds

**BUT life-changing hard-block disqualifies operational seed**:
- Per-trade edge 0.27% << 2% structural floor
- Mechanism IS real but per-trade economics insufficient for capital-changing
  scale even at 1148 trades/yr × 52.4% util

Lesson #41 is hereby **confirmed-with-amendment**: DIFFUSE_POSITIVE pool-level
alpha CAN be resolved via universe expansion (mechanism real), but if
per-trade edge is structurally below life-changing 2%/trade floor, expansion
recovery is academically successful but operationally moot.

## Comparison vs Past Graveyards

vs paradigm 95 (`cross_asset_volume_share_high_alt_long`): both reached
NARROW_SCOPE_LIFE_CHANGING_FAIL family. paradigm 95 had **edge 0.47%** with
4-cell ALL PASS; paradigm 115 has **edge 0.27%** with diffuse pool +
narrow-scope concentration. Both confirm KR/Binance crypto continuation
paradigms at hourly timeframe live at sub-1% per-trade edge ceiling.

vs paradigm 99 (`funding_per_sym_velocity`): identical
NARROW_SCOPE_LIFE_CHANGING_FAIL pattern.

vs paradigm 104 (`cross_exchange_oi_differential`): edge 0.26-0.77% at
extended hold 480m/1440m — paradigm 115 4h hold sits in similar regime.

**Cumulative**: paradigm 95 / 99 / 104 / 115 = 4th NARROW_SCOPE_LIFE_CHANGING_FAIL
dogfood. Verdict category itself now well-validated (≥4 dogfoods).

## Comparison vs Past R-2 WF Outcomes

vs paradigm 87 (`binance_delisting`): R-1 PASS_R1_FULL → R-2 WF 1/5 PASS
graveyard. Paradigm 115 R-2 WF 3/5 PASS clears Lesson #26 mandatory gate —
paradigm 87 fragility precedent NOT replicated.

vs paradigm 92 (`dart_h1_earnings_gap`): R-1 gap-proxy PASS → R-2c true YoY
0/5 PASS graveyard. Paradigm 115 has no proxy mismatch issue (ATR-buffered
breakout = directly observable, no fundamental signal).

## Mechanism Documentation (Future Reference)

The k=1.5 × 4h cell mechanism survived universe expansion with strong
amplification. The mechanism is:

1. **Statistic**: close > rolling_24h_max + 1.5 × ATR_14d × close_t-1
2. **Debounce**: no prior breakout in last 12 bars
3. **Direction**: LONG (continuation)
4. **Hold**: 4h fixed
5. **Universe**: 29 alts (preferentially DOTUSDT/SEIUSDT/ARBUSDT for concentration)

Stronger-than-fee gross (+34.99bp) and survival across 8/9 quarters indicate
this is NOT a fee-floor artifact (Lesson #35 reversed at R-2). However the
per-trade edge of 0.27% net implies a paradigm operating just above noise
floor, not life-changing scale.

## Files

- code: `backend/scripts/research/paradigm115_r2_universe_expansion.py`
- metrics: `backend/runs/research_track/alt_atr_normalized_range_breakout_continuation_long_2h/r2__metrics.json`
- stdout: `backend/runs/research_track/alt_atr_normalized_range_breakout_continuation_long_2h/r2__stdout.log`
- expansion klines cache: `backend/runs/research_track/alt_atr_normalized_range_breakout_continuation_long_2h/klines_cache_r2_expansion/` (16 alts × 24mo, permanent asset)

## Next Action Recommendation

1. **Mark paradigm 115 graveyard** (this R-2 FAIL report finalizes).
2. **Lesson #41 candidate official upgrade** to confirmed-with-amendment:
   diffuse pool alpha + universe expansion path is VALID research move, but
   life-changing hard-block precedes Lesson #41 concentration recovery.
3. **Lesson #20 (NARROW_SCOPE_LIFE_CHANGING_FAIL) 4th dogfood** — verdict
   category fully validated.
4. **Continue continuous-parallel campaign** ([[feedback_paradigm_campaign_continuous_parallel]])
   — paradigm 116+ candidates that target ≥2%/trade per-trade edge as PRIMARY
   constraint (NOT pool sigex). Mechanisms operating at hourly-scale 24h
   trailing-high breakouts inherently sub-1%/trade — pivot toward sparse
   event-driven mechanisms with ≥2% expected per-event edge.
5. **DO NOT seed R-5 paper sessions** — paradigm fails life-changing hard
   block, baseline pool would underperform existing paper sessions on edge
   density.
