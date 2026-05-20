# Graveyard: paradigm 120 `btc_oi_activity_regime_x_alt_oi_velocity_decomp_long_4h`

- **Date**: 2026-05-20 17:07 KST
- **Phase reached**: R-1 (single batch 4-quadrant Symmetric Negative Test)
- **Verdict**: `BROAD_FALSIFIED_FEE_FLOOR_SUB_THRESHOLD`
- **Counter**: 119 → **120**
- **Wall-clock**: 5.5 s (archive-direct, no DB load)

## Hypothesis

BTC derivatives market activity regime (BTC 5m OI velocity rolling 24h std,
percentile p70+ HIGH_DERIV) provides exogenous orthogonal macro state to per-alt
endogenous OI velocity z-score. Joint trigger:

- alt 5m OI velocity z (rolling 24h, 288 bars) × `|z|>1.0` × BTC HIGH_DERIV → forward 4h directional
- 4 quadrants (Lesson #19 mandatory single-batch):
  - A_focus  : z>+1.0 × HIGH × LONG  (leveraged longs piling on under macro stress → contagion squeeze setup)
  - A_mirror : z>+1.0 × HIGH × SHORT (mechanism inverted)
  - B_focus  : z<-1.0 × HIGH × SHORT (symmetric short-pile)
  - B_mirror : z<-1.0 × HIGH × LONG  (mechanism inverted)

## Family-distinct claim (R-0 audit)

- paradigm 69 R-5 seeded `btc_rv_spike_highvol_filter_alt_long_240m` — BTC **price-based** RV. Here BTC **OI activity** = derivatives market intensity, different statistic family.
- paradigm 71 `btc_oi_velocity` graveyard — single OI z trigger. Here joint with BTC regime (conditioning axis added).
- Lesson #45 candidate (paradigm 83+119 HMM/k-means endogenous decomposition w/o orthogonal mechanism). Percentile-threshold regime classification is structured statistical filter, NOT unsupervised model. Out of Lesson #45 scope. (Note: Lesson #45 우회 path 유효성은 본 paradigm BROAD_FALSIFIED로 입증 미달 — alpha 부재로 mechanism level test 불가.)
- DNA 5/6 distinct vs paradigm 69 (only universe overlap), 5/6 distinct vs paradigm 71 (regime axis added).

## Substrate

- Microstructure 5m joblib `backend/runs/microstructure/{SYM}_full_metrics.joblib`
- Universe: 13 alts (paradigm 119 substitution) + BTCUSDT
- Window: 2024-11-07 ~ 2026-05-02 (~1.55yr, ~155K bars/sym × 14 syms)
- Total events per direction × pool: ~37K post-dedup (4h non-overlapping)

## R-1 results (4-quadrant)

| Quadrant | n | mean_bp | obs_t | sigex | ci_lower_bp | perm_p | 3-gate | conc | edge% | life-chg |
|---|---|---|---|---|---|---|---|---|---|---|
| A_focus z>+1 × HIGH × LONG | 9337 | +2.16 | +0.84 | **+4.07** | -1.94 | 0.000 | ✗ | ✗ (0/13 ci_pos) | +0.022% | ✗ |
| A_mirror z>+1 × HIGH × SHORT | 9337 | -18.16 | -7.09 | -3.86 | -22.57 | 0.000 | ✗ | ✗ | -0.182% | ✗ |
| B_focus z<-1 × HIGH × SHORT | 9499 | -19.95 | -8.09 | -4.87 | -24.24 | 0.000 | ✗ | ✗ | -0.199% | ✗ |
| B_mirror z<-1 × HIGH × LONG | 9499 | +3.95 | +1.60 | **+4.82** | -0.49 | 0.000 | ✗ | ✗ (0/13 ci_pos) | +0.039% | ✗ |

### Lesson #39 symmetry check

- A focus + A mirror sum = **-16.00 bp = exactly -2×fee** (8 bp × 2)
- B focus + B mirror sum = **-16.00 bp = exactly -2×fee**
- A sym diff |abs(+2.16) - abs(-18.16)| = 16.00 bp (= 2×fee)
- B sym diff = 16.00 bp

**Mirror exact-fee-symmetric** verified — gross direction is fully captured by focus quadrants (z>+1 × HIGH gross LONG drift ≈ +10 bp, z<-1 × HIGH gross LONG drift ≈ +12 bp). However, **fee floor 16 bp 2×fee 우월** → focus net positive ≈ +2~+4 bp insufficient.

This is **NOT** Lesson #39 sub-class A (broad-uniform-negative) — gross drift exists, just sub-fee.
This is **NOT** Lesson #39 sub-class B (mechanism-inverted) — focus direction is correct, fee binding.

### Diffuse positive sub-fee (BROAD_FALSIFIED_FEE_FLOOR_SUB_THRESHOLD)

Both A focus and B mirror show:
- `signal_t_excess > +4σ` (3-gate sigex PASS)
- `perm_p = 0.000` (3-gate perm PASS)
- `ci_lower < 0` (3-gate ci FAIL)
- `quarter_pos_t_ratio = 4/7 = 57%` (Concentration quarter PASS marginal)
- `n_syms_ci_pos = 0/13` (Concentration symbol FAIL universal)

→ Weak positive drift suppressed by fee floor + universally diffuse across symbols.

### Per-quarter t evolution (A focus)

| Quarter | n | mean_bp | t |
|---|---|---|---|
| 2024Q4 | 1128 | +23.14 | +2.43 |
| 2025Q1 | 1802 | -5.41 | -0.80 |
| 2025Q2 | 1965 | +10.91 | +2.11 |
| 2025Q3 | 802 | +6.43 | +0.95 |
| 2025Q4 | 1233 | +7.40 | +0.95 |
| **2026Q1** | **1912** | **-14.92** | **-3.33** |
| 2026Q2 | 495 | -6.89 | -1.21 |

**2026Q1 reversal** — strong negative quarter eliminates aggregate edge. Same pattern observed in B mirror (2026Q1 t=-2.78). Lesson #32 universe-baseline-coherent check: 2026Q1 alt universe broad-negative (BTC bear regime confirmed by BTC OI activity remaining high while alt prices fell), so trigger z>+1 in alts during BTC stress 2026Q1 captures **bag-holding longs at peak** → drawdown.

## Verdict rationale

`BROAD_FALSIFIED_FEE_FLOOR_SUB_THRESHOLD`:
- 3-gate sigex + perm PASS, but ci_lower FAIL — `weak positive sub-fee` signature
- Concentration symbol gate universally FAIL (0/13 ci_pos in both positive quadrants)
- Per-trade edge 0.022% × 100 = ~2.2 bp ≪ 200 bp (2%) life-changing threshold
- Lesson #41 amendment applied: per-trade edge gate FIRST eliminates this regardless
- Lesson #19 4-quadrant single-batch executed (no time wasted on mirror-only re-run)

## Lesson dogfood

- **Lesson #11 (sample density)**: prescreen target ≥30/cell, achieved ~9300/cell per quadrant. PASS structural.
- **Lesson #19 (Symmetric Negative Test 4-quadrant joint-trigger mandatory)**: single R-1 batch satisfied — 6th dogfood (paradigm 82, 96-99, 118, 120 cumulative).
- **Lesson #23 (event-anchored cycle horizon density)**: continuous-trigger paradigm (not cycle-anchored), N/A.
- **Lesson #30 candidate (data window ratio)**: 100% archive-direct microstructure joblib (no DB), no advisory caution. Local agent context compliance ([[feedback_paradigm_architect_local_context]]).
- **Lesson #32 (universe-baseline-coherent A vs B drift artifact)**: A focus 2026Q1 -14.92bp + B mirror 2026Q1 -12.17bp confirms drift coherent (not artifact), broad bear-quarter cohort drag — mechanism genuinely failed in 2026Q1 not artifact.
- **Lesson #34 (empirical distribution prescreen)**: |OI velocity z| p50=0.33 p70=0.60 p90=1.35 p99=4.17, |z|>1.0 = 15.9% rate. PASS structural.
- **Lesson #39 (symmetric perfect mirror antipattern)**: A focus + mirror sum exactly -2×fee, sym diff exactly 2×fee. **NOT sub-class A or B** (gross drift exists, mechanism direction correct, but fee floor binds). NEW finding — Lesson #39 sub-class C candidate: `weak_positive_drift_fee_floor_bound_with_mechanism_correct`.
- **Lesson #41 amendment (per-trade edge ≥ 2% gate FIRST)**: applied — edge 0.022% / 0.039% would FAIL even if 3-gate PASSed. PASS dogfood structural.
- **Lesson #45 candidate (unsupervised endogenous decomposition w/o orthogonal mechanism)**: 본 paradigm percentile-threshold filter ≠ unsupervised model, Lesson #45 적용 X. Lesson #45 우회 path 유효성 별도 검증 필요 (HMM × external axis paradigm 필요).

## NEW Lesson #46 candidate (1st dogfood)

**"Weak positive drift × strict fee floor binding × no concentration synthesis ≠ alpha — fee floor as binding constraint not just gate"**

paradigm 120 본 dogfood: gross direction correct (+10~12 bp focus LONG), fee 8 bp consumes 80% of edge, ci_lower < 0 (Bootstrap fails), 0/13 syms ci_pos (homogeneous diffuse).

Practical implication: paradigm-architect r0_inventory_check에 **gross drift estimate prescreen** 추가 — if expected gross direction < 2×fee (16 bp), advisory caution before R-1 dispatch (similar to Lesson #34 empirical distribution prescreen).

1 more dogfood (different paradigm class, same fee-floor-binding fail mode) = Lesson #46 candidate confirmed.

## Family classification

- **Not a new family retire** — paradigm 71 (single OI trigger) + paradigm 120 (OI joint × BTC regime) = 2 OI-axis triggers fail. Tier 4 retire requires 3+ sub-class.
- **OI velocity axis sub-classes 누적**: paradigm 71 single + paradigm 120 joint × macro regime = 2 sub-classes both falsified. 1 more (e.g., OI × event-anchored, OI × cross-section dispersion) → potential `oi_velocity_directional_family` Tier 4 retire.

## Artifacts

- Script: `backend/scripts/research/paradigm120_btc_oi_activity_regime_x_alt_oi_velocity_decomp_long_4h_r1.py`
- Metrics: `backend/runs/research_track/btc_oi_activity_regime_x_alt_oi_velocity_decomp_long_4h/r1__metrics.json`
- Graveyard: `backend/runs/research_track/graveyard__btc_oi_activity_regime_x_alt_oi_velocity_decomp_long_4h.md` (this file)

## Next candidate recommendation

Continuous-parallel policy + HMM × exogenous axis 우선 권장 (Lesson #45 uphold path):
- **#A `hmm_realized_vol_x_funding_sign_conditioning_alt_directional_4h`** — paradigm 119 HMM 인프라 reuse + funding sign as conditioning filter (not trigger) → funding family retire 우회 (funding as filter, not signal). 단 funding family-distinct path는 graveyard 96 §family-distinct에서 보수적 정의 — risk.
- **#B `markprice_index_basis_extreme_x_oi_velocity_alt_directional_4h`** — paradigm 105 (`binance_perp_mark_index_basis_extreme`) graveyard prior, BUT joint with OI velocity (z>+1) as filter not trigger. archive-direct markPrice substrate.
- **#C `aggtrade_imbalance_x_btc_regime_alt_directional_4h`** — aggTrades 5m imbalance (taker vol diff / total vol) × BTC OI activity HIGH regime. archive-direct aggTrades cache 보유 시.
