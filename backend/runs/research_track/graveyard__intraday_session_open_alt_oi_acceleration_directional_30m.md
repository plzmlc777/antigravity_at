# Graveyard — paradigm 122 `intraday_session_open_alt_oi_acceleration_directional_30m`

- **Date**: 2026-05-20 KST 20:03
- **Phase reached**: R-1 (verdict at R-1, no R-2 dispatch per directive)
- **Verdict**: `BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE`
- **Predecessor history**: paradigm 113 hour-of-day anchor BROAD_FALSIFIED + paradigm 71 OI velocity single BROAD_FALSIFIED + paradigm 120 OI velocity × BTC regime decomp BROAD_FALSIFIED (combinatorial DNA already exhausted, Lesson #21 antipattern materialized)
- **Wall clock**: 2.85 min total (R-0 prescreen 78s + R-1 64s)
- **Script**: `backend/scripts/research/paradigm122_r1.py` + `paradigm122_r0_prescreen.py`
- **Metrics**: `backend/runs/research_track/intraday_session_open_alt_oi_acceleration_directional_30m/r1__metrics.json`
- **R-0 prescreen**: `backend/runs/research_track/intraday_session_open_alt_oi_acceleration_directional_30m/r0_prescreen.json`

## 1. Hypothesis

13 alt 5m OI velocity z-score top-decile (|z| ≥ per-symbol rolling 30d p90) at DUAL ANCHOR
- **Anchor 1 (CME close)**: 21:00 UTC ± 15 min (US equity close transition liquidity)
- **Anchor 2 (Funding-cycle clock)**: 00:00 / 08:00 / 16:00 UTC ± 5 min (funding cycle timing axis — NOT funding magnitude)

Forward 30 min sign-matched directional hold (positive OI velocity → LONG, negative → SHORT).

Mechanism: temporal-anchor liquidity transition coincident with OI acceleration → continuation extension.

## 2. R-0 prescreen results (Lesson #46 AMENDMENT — exact mechanism, no proxy)

| Lesson | Check | Result |
|---|---|---|
| #11 sample density | per-quadrant per-quarter ≥ 30 | **PASS** (pos 10/10 q, neg 10/10 q measurable) |
| #19 SNT mandatory | 4-quadrant in single batch | **APPLIED** |
| #20 narrow-scope | 0.56% effective trigger rate, top-decile by construction | **APPLIED** |
| #21 axis stacking | OI velocity + temporal anchor = 2 null axes (per paradigm 71 + 113) | **APPLIED — risk flagged ex ante** |
| #23 event-anchor density | dual anchor 5.43% time-coverage, 14,925 triggers across 783 days | **PASS** |
| #28 substrate availability | 5m OHLCV (DB resampled) + 5m OI (microstructure joblib) verified 13/13 | **PASS** |
| #30 data window ratio | 783 days vs 800-day proxy = 97.9% | **PASS** (no advisory) |
| #34 empirical distribution | \|OI vel z\| p50=0.19 p70=0.39 p90=1.00 p95=1.56 p99=3.64 | **PASS** |
| #40 structural threshold feasibility | per-sym top-decile by construction reachable | **PASS** |
| #44 amendment graveyard xref | paradigm 71 + 113 + 120 substrate keyword match | **APPLIED — DNA proximity flagged** |
| #46 amendment exact-mechanism R-0 | n=200 first-events exact filter measurement (NO proxy) | **APPLIED** (R-0 verdict `R0_PASS_PROCEED_TO_R1`, but bias warning: chronological subset n=200 ≠ full panel) |

R-0 exact-mechanism small-sample finding (n=200): A_focus gross −7.40bp / B_focus gross +16.10bp, suggesting sign-asymmetric mechanism. **R-1 full-panel measurement OVERTURNED this**: with full n=14,925, the sign-asymmetry vanished — both focus arms broad-uniform-negative net.

**Lesson #46 AMENDMENT dogfood meta-result**: exact-mechanism R-0 at n=200 (chronological first events) is **insufficient** to predict full-panel direction. The n=200 sample is dominated by 2024 early period (bear-pump aftermath), inducing direction artifact. **R-0 exact-mechanism prescreen avoids the 4.2x optimistic proxy bias (paradigm 121 trap) but introduces a NEW small-sample temporal-coherent direction artifact.** Recommend amendment refinement: R-0 n=200 sample should be **temporally-stratified** (e.g., 50 events × 4 quarters) rather than chronological first.

## 3. R-1 full 4-quadrant SNT results (primary hold = 30min, fee 16bp)

Panel: 2,663,459 5m bars / 783 days / 13 symbols / 14,925 triggers (pos 6,941 / neg 7,983) / trigger rate 0.560%.

| Quadrant | n | gross_bp | net_bp | obs_t | sigex | CI_lower_bp | perm_p | 3-gate | qpos_t | syms_ci_pos |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|---:|---:|
| **A_focus pos→LONG**  | 6941 | **+8.98** | −7.02 | −2.35 | +16.36 | −15.88 | 1.000 | FAIL | 3/10 | **0/13** |
| A_mirror pos→SHORT    | 6941 | −8.98     | −24.98 | −8.36 | +10.35 | −37.41 | 0.999 | FAIL | 0/10 | 0/13 |
| **B_focus neg→SHORT** | 7983 | **−1.47** | −17.47 | −8.07 | +11.92 | −25.32 | 1.000 | FAIL | 2/10 | **0/13** |
| B_mirror neg→LONG     | 7983 | +1.47     | −14.53 | −6.72 | +13.27 | −22.20 | 1.000 | FAIL | 1/10 | 0/13 |

**3-gate ALL FAIL** in all 4 quadrants (gate_ci FAIL all, gate_perm FAIL all). The sigex values are inflated artifacts of fee-aware perm null mean being very negative (null pool draws random directions → null t-mean ≈ −18σ to −20σ). Observed obs_t ranges −2.35 to −8.36 — all observed t-stats are **less negative** than the null but still negative. CI lower bound is **uniformly < 0** confirming net negative.

**Per-symbol concentration**: 0/13 syms ci_pos in ALL 4 quadrants — broad homogeneous negative (NOT cherry-pick artifact).

## 4. Lesson #39 sub-class manual detection

| Arm | sym_sum (focus + mirror gross_bp) | exact_symmetric | focus_broad_negative | mirror_real_concentration | sub-class |
|---|---:|:---:|:---:|:---:|:---:|
| **A-arm** | 8.98 + (−8.98) = 0 | TRUE | TRUE (net −7.02, 0/13 syms ci_pos) | FALSE (0/13 mirror syms) | **A (broad uniform negative)** |
| **B-arm** | −1.47 + 1.47 = 0 | TRUE | TRUE (net −17.47, 0/13 syms ci_pos) | FALSE (1/10 mirror q_pos_t, 0/13 syms) | **A (broad uniform negative)** |

Both arms = **Lesson #39 sub-class A signature** (exact-symmetric by construction since mirror = −focus on sign-matched paradigm; both broad-uniform-negative net after fee → trigger has zero directional info, joint signal is pure direction-bet + fee drag).

## 5. Life-changing 4-dim (Lesson #41 AMENDMENT — edge ≥ 2% gate FIRST)

| Quadrant | trades/yr | per_trade_edge_pct | sharpe_approx | edge_first_gate |
|---|---:|---:|---:|:---:|
| A_focus pos→LONG  | 3236 | **−0.0702%** | −1.60 | **FAIL** |
| A_mirror pos→SHORT| 3236 | −0.2498% | −5.71 | FAIL |
| B_focus neg→SHORT | 3721 | −0.1747% | −5.51 | FAIL |
| B_mirror neg→LONG | 3721 | −0.1453% | −4.59 | FAIL |

**ALL 4 quadrants fail Lesson #41 AMENDMENT edge-first gate** (need ≥ +2.0% per-trade edge). No life-changing pathway exists.

## 6. Lesson #44 AMENDMENT dogfood — graveyard substrate-keyword cross-reference

| Predecessor | Verdict | DNA overlap with paradigm 122 |
|---|---|---|
| paradigm 71 `btc_oi_velocity_*` | BROAD_FALSIFIED 2026-05-15 | **OI velocity axis** — single-trigger null direction (0/3 z thresholds 3-gate FAIL) |
| paradigm 113 `intraday_hour_of_day_anchor_alt_directional_2h` | BROAD_FALSIFIED 2026-05-20 | **temporal anchor axis** — anchor hours {00,07,13,21} × \|z\|≥1, 0/13 syms ci_pos all 4 quadrants; hour-anchor ALONE = −6.69bp |
| paradigm 120 `btc_oi_activity_regime_x_alt_oi_velocity_decomp_long_4h` | BROAD_FALSIFIED 2026-05-19 | **OI velocity axis** — joint with BTC OI activity regime, 0/13 alts × 4/4 clusters fail |

**Lesson #21 antipattern materialization**: paradigm 122 = OI velocity (null per paradigm 71) × temporal anchor (null per paradigm 113) = TWO NULL AXES stacked. Lesson #21 explicit antipattern: stacking null axes compounds fee drag without alpha synthesis. **Confirmed 4th dogfood** (paradigm 83 OI 5m k-means + paradigm 113 hour × \|z\| + paradigm 122 OI velocity × temporal anchor + earlier paradigm 119 axis stacking).

**Lesson #44 AMENDMENT dogfood verdict — partial success**: cross-reference scan correctly identified paradigm 71/113/120 DNA proximity at R-0, allowing ex ante Lesson #21 risk flagging. Dispatch proceeded under user directive; the prescreen FOUND the risk but did not enforce halt. **Recommend Lesson #44 amendment formal CONFIRMED status** (3rd dogfood after paradigms 119 + 120 graveyard cross-references).

## 7. Family-distinct verification result

**Original family-distinct claim** (R-0 prescreen): "dual-anchor + OI velocity temporal conjunction is paradigm-distinct via conjunction axis (cf. paradigm 113 graveyard explicit allowance for OI z at anchor hr)."

**R-1 empirical refutation**: while the conjunction IS paradigm-distinct in 5-axis novelty taxonomy (3/5 NOVEL ex ante), the **mechanism alpha is structurally absent** because:
1. Component axes (OI velocity, temporal anchor) are independently null;
2. Lesson #21 stacking compounds noise;
3. Per-sym broad uniform negative (0/13 syms ci_pos) confirms no symbol-cluster carve-out.

**Conclusion**: paradigm 122 IS family-distinct in novelty axis, but **mechanism-equivalent to paradigm 71/113/120 null** (different conjunction, same underlying null axes). This is the **classical Lesson #21 false-novelty trap** — novelty in conjunction does not synthesize alpha when component axes are independently null.

## 8. Cumulative counters update

- **122nd graveyard** (was 121, paradigm 122 slot-1 liquidation duplicate inventory-halt → slot-2 this dispatch)
- **9 family retires likely** (oi_velocity_directional_family Tier 4 retire CANDIDATE triggered):
  - paradigm 71 single-axis OI velocity BROAD_FALSIFIED
  - paradigm 120 OI velocity × BTC regime BROAD_FALSIFIED
  - paradigm 122 OI velocity × temporal-anchor BROAD_FALSIFIED
  - = **3 sub-classes falsified → Tier 4 formal retire qualified per Lesson #21 + paradigm 113 graveyard explicit prediction**
- **35 lessons confirmed + 1 amendment confirmed candidate** (Lesson #44 amendment 3rd dogfood reaches CONFIRMED 자격)
- **Lesson #21 4th dogfood** (paradigm 83 + 113 + 119 + 122) — already CONFIRMED, additional reinforcement
- **Lesson #39 sub-class A 4th dogfood** (paradigm 108 + 113 + 120 + 122)
- **Lesson #46 AMENDMENT first stress-test**: exact-mechanism R-0 at n=200 chronological subset is **insufficient** to predict full-panel direction (R-0 estimated B_focus +16.10bp, R-1 full-panel measured −1.47bp). **Recommend amendment refinement**: temporally-stratified R-0 sample (e.g., n=50 × 4 quarters)

## 9. Next action

**Halt at R-1 per directive (R-1 only halt, no R-2 dispatch).**

### Recommended next candidate (1 only)

`alt_volume_cusum_change_point_persistence_directional_2h`

**Rationale**:
- **Family-distinct axes**: volume CUSUM (NOT magnitude z, NOT velocity z) + statistical change-point detection + non-event-anchored continuous trigger. Avoids OI velocity family (paradigm 71/120/122 now 3 retired sub-classes), avoids temporal anchor family (paradigm 113 + 122 retired), avoids funding family (8 retired sub-classes), avoids HMM/unsupervised (Lesson #45 candidate retire).
- **Mechanism**: per-symbol cumulative sum of normalized 5m volume deviation; trigger at CUSUM upper-threshold breach with prior 30d persistence > median. Hypothesis: large traders accumulate positions detectable via volume regime persistence shift, predicting 2h directional drift.
- **Lesson #22 risk**: stateful CUSUM Page-Hinkley requires frame-grade source frequency. Volume 5m frame is abundant (paradigm 122 panel verified 2.66M bars). PASS.
- **Lesson #11/#23**: CUSUM is **non-event-anchored continuous trigger** (Lesson #23 explicit non-target). Sample density structurally safe.
- **Substrate**: 1m OHLCV (volume) DB resampled → 5m, archive-direct (paradigm 122 substrate reuse).
- **Lesson #28**: substrate exists. PASS.
- **Lesson #40**: CUSUM by construction symmetric continuous, no z-trigger structural infeasibility.
- **Lesson #46**: R-0 prescreen requires temporally-stratified n=200 exact mechanism (50 × 4 quarters per amendment refinement above).

**Avoid**: OI velocity any-variant (oi_velocity_directional_family Tier 4 retire qualified), any temporal-anchor + magnitude conjunction (Lesson #21 stacking risk), HMM/unsupervised decomposition (Lesson #45 candidate retire), funding-axis any variant.

## 10. Artifacts

- Scripts: `backend/scripts/research/paradigm122_r0_prescreen.py`, `paradigm122_r1.py`
- Metrics: `backend/runs/research_track/intraday_session_open_alt_oi_acceleration_directional_30m/r0_prescreen.json`, `r1__metrics.json`
- INDEX entry: registered + graveyarded 2026-05-20 20:03 KST
- Graveyard report: this file
