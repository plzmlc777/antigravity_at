# paradigm 212 R-1 GRAVEYARD

- **slug**: `alt_cross_sym_funding_correlation_matrix_eigenvalue_1_dominance_ratio_30d_rolling_z_spike_directional_4h`
- **phase**: R-1 GRAVEYARD
- **verdict**: `BROAD_FALSIFIED_PRIMARY_DIRECTION_PATTERN_P1_6TH_CONSECUTIVE_B_MIRROR_PASS_AS_ARTIFACT_LESSON_42_18TH_NEGATIVE`
- **date_kst**: 2026-05-22

## Hypothesis

10 deep syms × 8h funding rate cycle → rolling 30d cross-sym funding rate correlation matrix → eigenvalue-1 dominance ratio (PC1 explained variance = lambda_1 / sum(lambda_i)) → 90d rolling z-score → |z|>=2 spike trigger × bar direction signed × 4-quadrant SNT.

Mechanism: HIGH PC1 dominance = funding rates 동조화 = systemic stress regime / LOW PC1 dominance = idiosyncratic decoupling.

## Lesson #69 8-item template result

| Item | Check | Result |
|------|-------|--------|
| 1 | INDEX.json DNA grep (correlation_matrix/eigenvalue/pca/dominance) | PASS — zero overlap, matrix-class fresh |
| 2 | Substrate 10 syms × 821d × 24,660 funding records | PASS, substrate_maturity 2.25yr verified |
| 3 | Sample density per-cell ≥30 (Lesson #11) | PASS — primary cell A_focus n=566, per-era ~88-298 |
| 4 | DNA family-distinct 5/5 strict (vs funding family 13 graveyards + paradigm 22/dispersion R-5) | PASS 5/5 — matrix decomposition statistic class structurally distinct from all scalar z-score variants |
| 5 | family-proxy axis class fresh | PASS — eigenvalue decomposition NOT prior scalar axes |
| 6 | Alpha decay 5-pattern audit (era stratify) | **Pattern P1 monotonic decay 6th consecutive** (paradigm 87+136+202+210+211+212) |
| 7 | SNT structural integrity + cross-set |A| vs |B| asymmetry | PASS — disjoint trigger sets, ratio 1.143x (n_A=566 / n_B=495) |
| 8 | Concentration + Temporal Independence (A_focus continuation) | A_focus sym_ci_pos 0/10 → FAIL on continuation. temporal_cluster_ratio 0.557 ≥0.5 PASS |

## family-distinct 5/5 strict verdict (CRITICAL)

vs funding family Tier 4 retire 13 graveyards:
- funding_boundary_revertion / pre_funding_window_divergence_5m / funding_velocity_cross_section_dispersion / funding_regime_stratify_dispersion / funding_cycle_8h_differential_velocity_per_sym / funding_boundary_x_oi_direction_x_funding_magnitude_triple / funding_rate_x_cvd_4h_divergence / funding_per_sym_30d_zscore variants / funding_carry_x_oi_decoupling / cross_exchange_funding_spread / per_sym_5d_30d_short_long_ratio

vs R-5 LIVE / R-5 seeded exceptions:
- paradigm 22 (per-sym 30d z MR) → per-sym scalar z
- funding_dispersion ETCUSDT → cross-section scalar z

**Statistic class**: matrix decomposition (eigenvalue ratio) **vs** all 13+2 scalar z/dispersion/velocity → DISTINCT 5/5 strict PASS. R-1 dispatch greenlit.

## R-1 Primary cell (|z|>=2.0, hold=4h) 4-quadrant verdict

| Cell | Label | n | sigex | ci_lower_bp | ci_upper_bp | obs_mean_bp | perm_p_above | prob_pos | sym_ci_pos | 3-gate |
|------|-------|---|-------|-------------|-------------|-------------|--------------|----------|------------|--------|
| A_focus | HIGHstress × barUP × LONG | 566 | **+2.085** | -20.24 | +52.51 | +9.80 | 0.021 | 0.779 | **0/10** | **FAIL** (ci_lower<0) |
| A_mirror | HIGHstress × barUP × SHORT | 566 | -1.674 | -68.51 | +4.24 | -25.80 | 0.948 | 0.049 | 0/10 | FAIL |
| B_same | LOWidio × barDOWN × SHORT | 495 | -5.738 | -100.79 | -24.48 | -57.50 | 1.000 | 0.001 | 0/10 | FAIL |
| **B_mirror** | **LOWidio × barDOWN × LONG** | **495** | **+5.876** | **+8.48** | +84.79 | +41.50 | 0.000 | 0.995 | **6/10** | **PASS** |

## Lesson #37 full hold×threshold sweep verdict scan (의무)

| Cell | A_focus 3-gate | B_mirror 3-gate | B_mirror sigex | B_mirror ci_lower_bp |
|------|---------------|------------------|----------------|----------------------|
| z_1.5_hold_4h | FAIL | (skip) | — | — |
| z_2.0_hold_4h | FAIL | **PASS** | +5.88 | +8.48 |
| z_2.0_hold_8h | FAIL | **PASS** | +6.75 | +25.28 |
| z_2.0_hold_12h | FAIL | **PASS** | +7.46 | +29.88 |
| z_2.0_hold_24h | FAIL | **PASS** | +7.83 | +41.77 |
| z_2.5_hold_4h | FAIL | (skip) | — | — |

**A_focus FAIL across all 12 cells. B_mirror PASS in all 4 z=2.0 cells (longer hold → stronger).**

## Lesson #39 sub-class B avoidance verification (B_mirror PASS validation)

Unconditional baselines (no funding trigger):
- barUP_LONG_4h: n=24523 mean_bp = -5.41 t=-5.03
- barDOWN_SHORT_4h: n=24457 mean_bp = -6.97 t=-6.04
- barUP_SHORT_4h: n=24523 mean_bp = -10.59 t=-9.86
- **barDOWN_LONG_4h: n=24457 mean_bp = -9.03 t=-7.82**

B_mirror conditioned (z=2.0, hold=4h): +41.50 bp obs_mean_bp
**Differential signal contribution: +41.50 - (-9.03) = +50.53 bp clean trigger alpha**

Sub-class B (mechanism inversion fee-floor) would require unconditional ≈ B_mirror. Here +50.53 bp differential → **NOT sub-class B fee-floor artifact, real reversal alpha exists in LOW idiosyncratic regime**.

## Item 7 cross-set asymmetric magnitude verdict

- n_A_focus = 566, n_B_same = 495, ratio = **1.143x**
- paradigm reference: 206=1.83x / 207=2.79x / 210=3.36x / 211=0.86x sub-1.0 / **212=1.143x**
- Within normal asymmetric range (>1.0, < 2x). Disjoint trigger sets confirmed (z_sign +1 HIGH vs -1 LOW × bar_dir +1 vs -1).

## Item 8 Concentration + Temporal Independence (A_focus continuation only)

- temporal_cluster_ratio (A_focus z+ × bar UP, 24h min gap): **0.557 ≥0.5 PASS**
- temporal_cluster_ratio (B_same z- × bar DOWN): 0.564 ≥0.5 PASS
- A_focus sym_ci_pos_ratio: **0/10 = 0.000 < 0.30 FAIL** (no sym sustains ci_lower>0 on continuation)
- B_mirror sym_ci_pos_ratio: 6/10 = 0.600 ≥0.30 PASS (would-PASS on reversal direction)

**Item 8 A_focus continuation FAIL** — 0/10 syms with ci_pos confirms diffuse signal collapse on primary direction.

## Pattern P1 monotonic decay (Item 6 8th operational dogfood — 6th consecutive)

A_focus per-era mean_bp:
- **2024: n=257 mean_bp=+42.81 t=+2.44** (positive era)
- **2025: n=298 mean_bp=-15.97 t=-1.48** (sign-flip)
- **2026: n=11 mean_bp=-63.21 t=-4.12** (deeply negative)

Rolling 6m window per-cell t-stat (Lesson candidate market maturity decay paradigm 211 amendment):
- 2024-11-10 → 2025-05-12: n=257 mean_bp=+42.81 t=+2.44
- 2025-05-12 → 2025-11-11: n=256 mean_bp=-12.29 t=-1.48
- 2025-11-11 → 2026-05-13: n=53 mean_bp=-43.57 t=-4.12

**Sign-flip count: 1, flip_ratio: 0.50** (boundary at threshold), but **monotonic decay direction t +2.44 → -1.48 → -4.12 = consistent deterioration**.

**Pattern P1 monotonic decay 6th consecutive instance documented**: paradigm 87 (delisting) + 136 (RV intraday cross-family) + 202 (RV) + 210 + 211 + 212 → **broad cross-class alpha decay hypothesis 강화** (vol-axis + funding-axis 모두 동일 패턴, market maturity decay 2024→2025 inflection point).

## Lesson #42 18th dogfood classification (B_mirror cell)

paradigm 117/158/162/179/193/194/195/196/197/198/204/205/206/207/208/210/211/212 chain.

paradigm 211 17th = PASS_AS_ARTIFACT annotation.

paradigm 212 18th classification:
- B_mirror three-gate PASS (sigex +5.88 / ci_lower_bp +8.48 / perm_p 0.000)
- B_mirror sym_ci_pos_ratio 0.60 ≥ 0.30 PASS
- B_mirror obs_mean_bp +41.50 net (gross +49.50, after 8bp fee)
- Differential vs unconditional barDOWN_LONG_4h baseline: +50.53 bp (clean signal)
- **per-trade edge: 0.42% (z=2.0 hold=4h)** to **1.51% (z=2.0 hold=24h)** — sub-2% life-changing threshold
- capital util estimate: 10 syms × 4h-24h bilateral × ~5% pos size ≈ 10-15% — sub-30% threshold
- **Lesson #42 18th: NEGATIVE — B_mirror reversal alpha real and statistically robust, but per-trade edge sub-2% + capital util sub-30% → life-changing 4-dim FAIL**

paradigm 212 B_mirror is **structurally analogous to paradigm 95 NARROW_SCOPE_LIFE_CHANGING_FAIL** (statistically PASS, life-changing FAIL).

## Final verdict

**BROAD_FALSIFIED_PRIMARY_DIRECTION**: A_focus continuation FAIL all 12 sweep cells (sigex 0.117-4.43, ci_lower_bp always <0, 0/10 sym_ci_pos).

**PATTERN_P1_6TH_CONSECUTIVE**: 2024-2026 monotonic alpha decay 6th instance + rolling 6m strict deterioration t-stat +2.44 → -1.48 → -4.12.

**B_MIRROR_PASS_AS_ARTIFACT_NARROW_SCOPE_LIFE_CHANGING_FAIL**: B_mirror reversal robust (sigex +5.88 / ci +8.48bp / 6/10 syms / Lesson #39 sub-class B avoidance verified +50.53bp differential) but per-trade edge 0.42-1.51% < 2% + capital util 10-15% < 30%. Lesson #42 18th NEGATIVE.

**R-2 진행 절대 금지** (사용자 명시 R-1 only STRICT).

## paradigm 213 next-action 권고

1. **Pattern P1 monotonic decay 6th consecutive formal escalation** — vol-axis + funding-axis broad cross-class alpha decay hypothesis 강화. paradigm 213+에서 2026-only sub-cohort era stratify mandatory + structural-cause investigation (market maturity, retail participation, microstructure efficiency 향상)
2. **Lesson candidate market maturity decay → CONFIRMED 승급 권고** (paradigm 211 CONFIRMED-자격 + 212 6th consecutive = 정식 CONFIRMED)
3. **Funding family Tier 4 retire 강화** — 8 sub-class + matrix-class (paradigm 212) 도합 9 sub-class graveyard. paradigm 22 R-5 LIVE exception + funding_dispersion ETCUSDT exception 2건만 활성. **Funding axis "axis-class exhaustion" formal verdict 권고**
4. **B_mirror reversal mechanism 학습 자산** — LOW PC1 dominance × bar DOWN × LONG = 50.53bp clean trigger alpha. 별도 paradigm 213 candidate으로 reversal-direction primary hypothesis 재공식화 가능 (but 4-dim life-changing edge 2%+ scoping 필요)
5. **next dispatch family-class**: funding-family + vol-axis 광역 retire 상태 강화. NEW axis class fresh candidate (orderbook microstructure / liquidation cascade / cross-asset macro / session-boundary 등) 우선
6. **Lesson #69 8-item template Item 7 5th dogfood**: 1.143x asymmetric ratio (paradigm 206/207/210/211/212 표준 분포 0.86-3.36x), 정상 작동 확인

---

## 종료 메시지 형식 — paradigm-architect 보고

### 가설 분해
- 데이터 차원: 10 deep syms × 8h funding rate × 2.25yr (24,660 records)
- 의사결정 모드: rolling 30d corr matrix → eigenvalue-1 dominance ratio → 90d z → |z|>=2 spike
- 시간 척도: 4h-24h forward hold sweep
- Sub-hypotheses: HIGH PC1 → 동조화 systemic stress / LOW PC1 → idiosyncratic decoupling, bar-dir signed continuation

### 진행 결과
- **R-1: BROAD_FALSIFIED_PRIMARY_DIRECTION_PATTERN_P1_6TH_CONSECUTIVE_B_MIRROR_PASS_AS_ARTIFACT**
- A_focus n=566 sigex +2.085 ci_lower_bp **-20.24** perm_p 0.021 (sigex PASS but ci FAIL = three-gate FAIL)
- A_mirror n=566 sigex -1.67 ci_lower_bp -68.51 FAIL
- B_same n=495 sigex -5.74 ci_lower_bp -100.79 FAIL (구조적 anti-alpha)
- B_mirror n=495 **sigex +5.88 ci_lower_bp +8.48 perm_p 0.000** PASS_R1 (cross-set Lesson #42 18th NEGATIVE)
- diversity: A_focus 0/10 / B_mirror 6/10 sym_ci_pos

### Symmetric Negative Test (Lesson #19 의무)
4-quadrant disjoint trigger 측정 완료. A_focus FAIL (continuation primary) + B_mirror PASS (reversal mirror) — primary direction broad-falsified, mirror direction sub-grade life-changing.

### Concentration Diagnostics (Lesson #16, Item 8 paradigm 208 amendment)
- A_focus sym_ci_pos_ratio: **0.000 (0/10) FAIL** (continuation collapse)
- B_mirror sym_ci_pos_ratio: 0.600 (6/10) PASS
- temporal_cluster_ratio A_focus 0.557 / B_same 0.564 PASS

### 최종 판정
**❌ BROAD_FALSIFIED + PATTERN_P1_6TH_CONSECUTIVE + B_MIRROR_PASS_AS_ARTIFACT_NARROW_SCOPE_LIFE_CHANGING_FAIL**

### 산출물
- code: `backend/scripts/research/paradigm_212_r1.py`
- metrics: `backend/runs/research_track/paradigm_212_funding_corr_eigenvalue_dominance/r1__metrics.json`
- z_series: `backend/runs/research_track/paradigm_212_funding_corr_eigenvalue_dominance/z_series.csv`
- graveyard: `backend/runs/research_track/paradigm_212_funding_corr_eigenvalue_dominance/GRAVEYARD.md` (this file)

### 다음 단계 권장
1. Lesson candidate **market maturity decay → CONFIRMED 정식 승급** (212에서 6th consecutive 확정)
2. Funding family Tier 4 retire 강화 (matrix-class 추가, 9 sub-class graveyard)
3. paradigm 213: NEW axis class fresh (vol/funding 광역 retire 상태) — orderbook microstructure / liquidation cascade / cross-asset macro 우선
4. B_mirror reversal alpha 학습 자산 보존 — LOW PC1 × barDOWN × LONG +50.53bp differential alpha (별도 R-1 재공식화 가능, but 4-dim life-changing edge 2%+ scoping 필요)
