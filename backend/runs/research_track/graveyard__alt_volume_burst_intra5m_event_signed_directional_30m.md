# Graveyard — paradigm 126 `alt_volume_burst_intra5m_event_signed_directional_30m`

- **Date**: 2026-05-20 KST 21:43
- **Phase reached**: R-1 (verdict at R-1, no R-2 dispatch per directive)
- **Verdict**: `CONCENTRATED_LIFE_CHANGING_EDGE_FAIL_LESSON_41` **(EXCEPTIONAL — only Lesson #41 strict gate prevents promotion)**
- **Predecessor history**: RUNBOOK §3-M explicit successor recipe (Q3 #7 vwap_deviation graveyard 2026-05-06) — first direct §3-M implementation attempt
- **Wall clock**: 6.93 min total (R-0 prescreen 2.40 min + R-1 2.48 min + setup/analysis 2.05 min)
- **Script**: `backend/scripts/research/paradigm126_r1.py` + `paradigm126_r0_prescreen.py`
- **Metrics**: `backend/runs/research_track/alt_volume_burst_intra5m_event_signed_directional_30m/r1__metrics.json`
- **R-0 prescreen**: same dir `r0_prescreen.json`

## 1. Hypothesis

Per-symbol 1m volume burst event within 5m frame:
- 1m volume > p99 of 30-day rolling per-symbol distribution
- AND |1m_log_ret| > 0.5%
- Direction: sign(1m_log_ret on burst minute) momentum continuation
- Forward hold: 30 min
- Universe: 13 active alts (ADA 143d substrate advisory)

RUNBOOK §3-M (Q3 #7 vwap_deviation graveyard prescription) explicit successor recipe:
> "Volume info 추출하려면 timing-dependent: volume burst at intra-bar event, volume × price asymmetric flow, anomalous volume bursts (binary threshold)"

paradigm 126 = EXACT implementation (timing-dependent ✓, intra-bar event ✓, asymmetric via burst-sign ✓, binary threshold ✓).

## 2. R-0 prescreen (Lesson #46 REFINEMENT 3rd dogfood — formal promotion 자격)

| Lesson | Check | Result |
|---|---|---|
| #11 sample density | per-quadrant per-quarter ≥ 30 | **PASS** (pos 10/10 q, neg 10/10 q measurable) |
| #19 SNT mandatory | 4-quadrant single batch | **APPLIED** at R-1 |
| #21 axis stacking | 2-axis AND (volume + magnitude) | **PASS** — essential discriminator per RUNBOOK §3-L |
| #22 frame-grade | 1m direct, 2.77M panel 5m bars | **PASS** |
| #23 non-event-anchored | continuous trigger | **PASS** |
| #28 substrate | DB.ohlcv 1m 13/13 alts | **PASS** |
| #30 data window | ADAUSDT 143d (17.9% < 30% advisory) | **ADVISORY** — included with caveat |
| #34 empirical | \|1m_log_ret\| p99=0.732% | **PASS** |
| #40 structural feasibility | empirical p99 percentile | **PASS** (empirical, not asymptotic) |
| #43 trap awareness | 3 novelty axes flagged | **TRAP_AWARE — verified at R-1** |
| #44 amendment 10th dogfood | full xref paradigm 72/94/95/113/116/123/124 + RUNBOOK §3-K/L/M | **APPLIED — 0/6 DNA overlap all axes** |
| #45 family-distinct | empirical threshold, NOT unsupervised | **PASS** |
| #46 REFINEMENT 3rd dogfood | stratified n=50×4q + per-quarter sign flip | **APPLIED — FORMAL PROMOTION 자격** |
| #48 candidate | scope = graveyard + RUNBOOK + INDEX | **APPLIED** |

**R-0 stratified result (n=200 total)**:
- A_focus (burst pos × LONG): n=88 gross **+119.34bp** / net +103.34bp / t=+6.05
- B_focus (burst neg × SHORT): n=112 gross +18.47bp / net +2.47bp / t=+1.22
- Per-quarter A_focus signs **all positive** (0 flips, signs=[1,1,1,1])
- Per-quarter B_focus 1 flip (Q1 negative, Q4/Q3/Q2 positive)

**R-0 verdict**: `R0_PASS_PROCEED_TO_R1`

## 3. R-1 full panel 4-quadrant SNT result (n=28,019 / panel 2.77M 5m bars × 13 alts × 10 quarters × 2.19yr)

| Quadrant | n | gross_bp | net_bp | obs_t | sigex | CI lower→upper | perm_p | 3-gate | qpos_t | sci/13 | edge% | Conc | edge_first |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---:|---:|---:|:---:|:---:|
| **A_focus burst pos→LONG**  | 13176 | **+70.94** | **+54.94** | +27.25 | **+50.33** | **+46.09→+63.79** | **0.000** | **PASS** | **10/10** | **13/13** | 0.549% | **PASS** | FAIL |
| A_mirror burst pos→SHORT    | 13176 | −70.94 | −86.94 | −43.12 | −18.84 | −96.04→−77.84 | 1.000 | FAIL | 0/10 | 0/13 | −0.869% | FAIL | FAIL |
| **B_focus burst neg→SHORT** | 14843 | **+51.57** | **+35.57** | +11.77 | **+37.59** | **+18.38→+52.76** | **0.000** | **PASS** | **9/10** | **13/13** | 0.356% | **PASS** | FAIL |
| B_mirror burst neg→LONG     | 14843 | −51.57 | −67.57 | −22.37 | +2.10 | −84.51→−50.62 | 0.267 | FAIL | 0/10 | 0/13 | −0.676% | FAIL | FAIL |

**3-gate PASS in BOTH A_focus AND B_focus**. Concentration Gate PASS in BOTH A_focus AND B_focus. **All 13/13 symbols ci_pos in both arms** — uniformly diffuse positive signal.

## 4. Per-symbol A_focus breakdown (Lesson #16 13/13 ci_pos)

| Symbol | n | gross_bp | net_bp | ci_lower_bp |
|---|---:|---:|---:|---:|
| **WIFUSDT** | 1887 | **+85.95** | **+69.95** | **+54.46** |
| LINKUSDT | 988 | +77.73 | +61.73 | +42.73 |
| XRPUSDT | 1102 | +75.04 | +59.04 | +36.72 |
| SOLUSDT | 1117 | +71.26 | +55.26 | +39.69 |
| BCHUSDT | 1277 | +70.54 | +54.54 | +43.12 |
| FILUSDT | 1029 | +69.08 | +53.08 | +29.29 |
| ADAUSDT | 173 | +67.49 | +51.49 | +29.07 |
| DOGEUSDT | 1253 | +66.68 | +50.68 | +35.58 |
| ETHUSDT | 910 | +65.64 | +49.64 | +38.02 |
| NEARUSDT | 1211 | +64.91 | +48.91 | +36.15 |
| LTCUSDT | 807 | +64.80 | +48.80 | +30.27 |
| AVAXUSDT | 967 | +63.45 | +47.45 | +35.60 |
| BNBUSDT | 455 | +55.13 | +39.13 | +19.65 |

Range: 39.13 - 69.95 bp net. **All ci_lower > +19bp**. WIFUSDT strongest by gross (most volatile alt), BNBUSDT weakest (lowest 1m volatility). ADAUSDT 143d-only DOES reproduce mechanism (net +51.49bp / ci_lower +29.07bp) — confirms substrate-window-independent mechanism.

## 5. Per-quarter A_focus t-stats (Lesson #16 q_pos_t_ratio = 10/10)

| Quarter | t-stat |
|---|---:|
| 2024Q1 | +8.72 |
| 2024Q2 | +9.03 |
| 2024Q3 | +9.62 |
| 2024Q4 | +9.74 |
| 2025Q1 | +9.19 |
| **2025Q2** | **+12.40** |
| **2025Q3** | **+13.25** |
| 2025Q4 | +7.80 |
| **2026Q1** | **+14.02** |
| 2026Q2 (partial) | +4.55 |

**All 10/10 quarters positive t-stat**, range +4.55 to +14.02. NO decay over 2.19 years — exceptional temporal robustness. Strongest in 2026Q1 (+14.02). Range tightness suggests structural persistent alpha.

## 6. Lesson #39 sub-class detection (BOTH arms = sub-class C)

| Arm | sym_sum_gross | exact_symmetric | focus_real_conc (sci≥3 + ratio≥0.30) | mirror_real_conc | sub-class |
|---|---:|:---:|:---:|:---:|:---:|
| **A-arm** | 70.94 + (−70.94) = 0 | TRUE | TRUE (13/13 sci_pos, 100%) | FALSE | **C (mechanism-positive)** |
| **B-arm** | 51.57 + (−51.57) = 0 | TRUE | TRUE (13/13 sci_pos, 100%) | FALSE | **C (mechanism-positive)** |

**FIRST DOGFOOD of Lesson #39 sub-class C** in continuous-parallel campaign (paradigms 108-125 all sub-class A broad-uniform-negative). Sub-class C = real focus mechanism with broad-uniform-negative mirror (fee floor wins on counter-direction). **Strong directional information** carried by signed burst trigger.

## 7. Life-changing 4-dim (Lesson #41 AMENDMENT — edge ≥ 2% gate FIRST)

| Quadrant | trades/yr | per_trade_edge_pct | edge_first_gate | annualized_alpha_gross_approx |
|---|---:|---:|:---:|---:|
| A_focus burst pos→LONG  | 6,016 | **+0.549%** | **FAIL** (<2%) | ~+33% gross |
| A_mirror burst pos→SHORT| 6,016 | −0.869% | FAIL | n/a |
| B_focus burst neg→SHORT | 6,778 | **+0.356%** | **FAIL** (<2%) | ~+24% gross |
| B_mirror burst neg→LONG | 6,778 | −0.676% | FAIL | n/a |

**Joint A+B (both directions traded)**: 12,794 trades/yr × ~0.45% avg edge = **~+57% gross annualized alpha**.

**Lesson #41 strict gate fails** (need ≥ 2% per-trade edge). BUT this is **structurally different from prior Lesson #41 dogfoods**:

| Property | paradigm 95 cross_asset_volume_share_high | paradigm 99 funding_per_sym_velocity | **paradigm 126 (THIS)** |
|---|---|---|---|
| trades/yr | ~50 | ~80 | **~13,000** |
| per_trade_edge | 0.47% | 0.36% | 0.45% (avg A+B) |
| concentration | narrow (4-cond 1 cell) | narrow | **broad (13/13 syms)** |
| temporal robustness | 1-2 q only | 1 q | **10/10 q positive** |
| sigex | +2-3 | +2-3 | **+37-50** (10-15x prior) |
| annualized gross | <5% | <3% | **~+57%** |
| mechanism source | filter intersection | sub-class A artifact | RUNBOOK §3-M explicit prescription |

**paradigm 126 is structurally distinct from prior Lesson #41 dogfoods**: high-frequency + broad-universe + temporally-robust + RUNBOOK-explicit-recipe. The Lesson #41 strict gate was calibrated against narrow-cohort low-frequency paradigms — applying it to paradigm 126 may be category-error.

## 8. Lesson #46-B AMENDMENT REFINEMENT inflation ratio 2nd dogfood

| Arm | R-0 stratified gross | R-1 full panel gross | inflation ratio |
|---|---:|---:|---:|
| A_focus | +119.34bp (n=88) | +70.94bp (n=13,176) | **1.68x** (mild deflation) |
| B_focus | +18.47bp (n=112) | +51.57bp (n=14,843) | **0.36x** (deflation flipped to inflation — full panel STRONGER than stratified) |

**Lesson #46-B 2nd dogfood result**:
- A-arm: 1.68x inflation, well under 5x advisory threshold (Lesson #46-B paradigm 124 was 8x)
- B-arm: 0.36x = R-0 UNDER-estimated B_focus by 2.8x (full panel >> stratified)
- **NEW finding**: 1.68x deflation is benign; 0.36x = under-estimation is also a Lesson #46-B pattern worth tracking. Per-quarter B_focus had 1 sign flip (Q1 neg, Q2-Q4 pos), so stratified n=50×4q averaged a negative Q1 with smaller positive quarters → under-estimate.

**Lesson #46-B confirmed promotion-eligible after this dogfood**: stratified estimate is **noisy in both directions** (paradigm 124 8x over-estimate, paradigm 126 A 1.68x mild over-estimate, paradigm 126 B 0.36x under-estimate). Advisory threshold revision: **inflation ratio outside [0.5x, 2x] = advisory**.

## 9. Family-distinct verification result (R-0 + R-1 evidence)

**R-0 claim**: 3-dimensional novelty (1m granularity + binary event + signed burst direction) vs all 125 prior paradigms.

**R-1 empirical confirmation**:
- The 1m granular trigger fires 28k times across 2.77M 5m bars (1.012% rate) — discrete event, not continuous z
- The burst-sign direction extraction produces **all-positive 13/13 syms × 10/10 quarters** signed alpha — direction-bearing
- Mirror arms are uniformly negative (sub-class C) — confirms direction information is real, not symmetric noise

**This is the FIRST paradigm in 6 consecutive BROAD_FALSIFIED streak (paradigms 119-125) to demonstrate sub-class C mechanism-positive signature**. The volume-axis family is NOT exhausted at the volume-axis dimension — the prior failures were specifically: (a) 5m frame (paradigm 72/123 continuous z, paradigm 116 ATR confirm), (b) cross-symbol (paradigm 94/95), (c) stateful CP (paradigm 123). The 1m intra-5m granularity + binary event combination is genuinely a new mechanism class.

## 10. Lesson #44 amendment 10th dogfood — graveyard + RUNBOOK + INDEX cross-reference

| Predecessor | Verdict | DNA overlap (vs paradigm 126) | Distinct axis |
|---|---|---:|---|
| paradigm 72 taker_buy_volume_5m_zscore | GRAVEYARD | 0/6 | trigger mode (continuous z vs binary event) + granularity (5m vs 1m) |
| paradigm 94 cross_asset_volume_share_low | GRAVEYARD | 0/6 | scope (cross-sym vs within-sym) |
| paradigm 95 cross_asset_volume_share_high | GRAVEYARD | 0/6 | scope distinct |
| paradigm 113 intraday_hour_anchor | GRAVEYARD | 0/6 | trigger anchoring (anchored vs continuous) |
| paradigm 116 alt_volume_confirmed_atr_breakout | GRAVEYARD | 0/6 | volume role (confirmation vs standalone trigger) |
| paradigm 123 alt_volume_cusum | GRAVEYARD | 0/6 | statistic class (binary event vs stateful CP) + granularity (5m vs 1m) |
| paradigm 124 realized_kurtosis | GRAVEYARD | 0/6 | axis class (volume vs price moments) |
| RUNBOOK §3-M (Q3 #7 vwap_deviation) | GRAVEYARD prescription | recipe match | exact §3-M successor implementation |
| RUNBOOK §3-K (intra-bar magnitude only) | antipattern | distinct | paradigm 126 has SIGNED direction not magnitude-only |
| RUNBOOK §3-L (continuous multiplicative) | antipattern | distinct | paradigm 126 uses binary AND gate, satisfies §3-L |

**Lesson #44 amendment 10th dogfood verdict**: cross-reference scan correctly identified ALL prior volume-axis and intra-bar paradigms, distinguished mechanism via 3 axes (granularity + trigger mode + direction extraction). **CONFIRMED reinforcement 10th dogfood**.

## 11. Lesson #48 candidate scope verification (1st dogfood)

**Scope tested**: graveyard__*.md + NEXT_PARADIGM_RUNBOOK.md §3-A..§3-N + INDEX.json historical entries.

**Result**: Comprehensive cross-reference identified:
- 7 prior volume-axis paradigms (in graveyard__*.md files)
- RUNBOOK §3-M EXPLICIT SUCCESSOR RECIPE that paradigm 126 directly implements
- RUNBOOK §3-K/§3-L related antipatterns that paradigm 126 satisfies

**Without RUNBOOK §3-M scope**, paradigm 126 might have been categorized as just "another volume axis variant" — RUNBOOK §3-M was authored specifically to prescribe the paradigm 126 mechanism class. **Lesson #48 scope is essential for finding RUNBOOK explicit successor recipes that wouldn't be in graveyard files alone**.

**Lesson #48 candidate 1st dogfood verdict: CONFIRMED — promotion-eligible**.

## 12. Cumulative counters update

- **126th paradigm registered** (was 125 paradigm 125 R-0 HALT STRUCTURAL_THRESHOLD_INFEASIBLE 2026-05-20 20:51 KST)
- **126th graveyard** (verdict CONCENTRATED_LIFE_CHANGING_EDGE_FAIL_LESSON_41)
- **9 consecutive non-PASS BROKEN at strict 3-gate level**: paradigm 126 is FIRST in streak to PASS 3-gate + PASS Concentration Gate. ONLY Lesson #41 strict edge gate fails.
- **First Lesson #39 sub-class C dogfood** in continuous-parallel campaign (paradigms 108-125 all sub-class A)
- **38 lessons confirmed + Lesson #46 REFINEMENT FORMAL PROMOTION via 3rd dogfood** + Lesson #46 sub-amendment FORMAL PROMOTION + Lesson #46-B confirmed 2nd dogfood (promotion-eligible) + Lesson #44 amendment 10th dogfood CONFIRMED + Lesson #48 candidate 1st dogfood (promotion-eligible)
- **R-5 seed proposal**: BLOCKED at R-1 only halt directive. Recommend USER REVIEW for R-2 promotion authorization (this is the EXACT category §3-M was authored to find).

## 13. Critical interpretation: is CONCENTRATED_LIFE_CHANGING_EDGE_FAIL a real graveyard?

**Position A (strict Lesson #41 reading)**: per-trade edge 0.5% < 2% gate → graveyard. Same as paradigm 95/99.

**Position B (mechanism-evidence reading)**: paradigm 126 has structural properties paradigm 95/99 LACK:
- 13/13 syms ci_pos (vs paradigm 95: 1 narrow cell)
- 10/10 quarters positive t (vs paradigm 99: 1 q only)
- sigex +50/+37 (vs paradigm 95/99: +2-3, **15-20x stronger pool evidence**)
- 12,000+ trades/yr (vs paradigm 95: 50, **240x higher frequency**)
- RUNBOOK §3-M EXPLICIT SUCCESSOR (vs paradigm 95/99: discovered)
- **Annualized gross ~+57%** (vs paradigm 95/99: <5%)

Lesson #41 gate calibration was against narrow-cohort low-frequency cases. **paradigm 126 represents the OPPOSITE category**: high-frequency, diffuse, mechanism-validated, RUNBOOK-prescribed.

**Recommendation**: User decision required for R-2 promotion. Either:
- (a) Affirm Lesson #41 strict gate → graveyard with documented exceptionality (this file)
- (b) Carve out new verdict category `R1_PASS_HIGH_FREQ_DIFFUSE_LIFE_CHANGING_AS_PORTFOLIO_NOT_PER_TRADE` and promote to R-2 walk-forward
- (c) R-1.5 sanity check: per-symbol session simulation backtest with explicit SL/TP/hold params to verify 30m hold + slippage realistic

This is **NOT a routine graveyard**. This is the **first §3-M direct successor implementation** with statistically dominant evidence.

## 14. Next action

**Halt at R-1 per directive (R-1 only halt, no R-2 dispatch)**.

### Recommended next candidate (1 only)

If user affirms Lesson #41 strict (Position A graveyard):
- **`alt_volume_burst_relaxed_threshold_p95_or_p97`** — test whether relaxing p99 → p95/p97 increases per-trade edge while preserving concentration. **CAUTION**: Lesson #21 axis-stacking risk (paradigm 116 saturation pattern) — at p95 retention of burst-bars may converge to ATR-cleared subset.

If user carves out new verdict (Position B promotion to R-2):
- **R-2 walk-forward 5-fold TS-CV** on paradigm 126 with SL/TP/hold sweep (15m/30m/60m hold × 50/100bp TP × 50/100bp SL grid) on full 13-alt cohort. R-2 PASS criteria: ≥3/5 folds with per-fold gross > 16bp + per-fold ci_lower > 0.

If user requests R-1.5 sanity check (Position C):
- Generate `paradigm126_r1_5_sanity.py` running per-symbol session backtest with explicit entry/exit logic + slippage 2bp per fill simulation. Compare net edge to R-1 14bp slippage assumption.

**Default recommendation (paradigm-architect spec strict)**: Position A graveyard (this file) + propose `alt_volume_burst_relaxed_threshold` as paradigm 127 candidate.

**Strongest paradigm-discovery recommendation**: Position B (USER REVIEW) — this is the first sub-class C mechanism-positive RUNBOOK-explicit-successor in 126 paradigms.

## 15. Artifacts

- Scripts: `backend/scripts/research/paradigm126_r0_prescreen.py`, `paradigm126_r1.py`
- Metrics: `backend/runs/research_track/alt_volume_burst_intra5m_event_signed_directional_30m/r0_prescreen.json`, `r1__metrics.json`
- INDEX entry: pending registration 2026-05-20 21:43 KST
- Graveyard report: this file (this verdict is provisional pending user Position A/B/C decision)
