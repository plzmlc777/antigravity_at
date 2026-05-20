# Graveyard — paradigm 126 candidate `alt_5m_close_to_open_overnight_gap_z_normalized_atr_session_anchor_directional_4h`

- **Date**: 2026-05-20 21:18 KST
- **Phase reached**: R-0 (halt before R-1 compute)
- **Verdict**: `R0_HALT_FAMILY_DISTINCT_GATE_FAIL_SESSION_ANCHOR_MOMENTUM_CONJUNCTION_DUPLICATE`
- **Counter increment**: NO (inventory-halt, cumulative graveyard counter stays at 125)
- **Wall clock**: 0 min (no compute, statistic decomposition + graveyard cross-reference only)
- **Predecessor chain**: paradigm 113 `intraday_hour_of_day_anchor_alt_directional_2h` BROAD_FALSIFIED 2026-05-20 + paradigm 122 `intraday_session_open_alt_oi_acceleration_directional_30m` BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE 2026-05-20 + paradigm 125 R0_HALT_STRUCTURAL_THRESHOLD_INFEASIBLE_LESSON_40 2026-05-20

## 1. Proposed mechanism

8h funding-boundary anchored 5m close-to-open price gap, ATR-normalized, rolling 30d z-scored. Trigger `|gap_z| > 2.5` at UTC 00:00/08:00/16:00 5m bar boundary. Direction = gap sign continuation. Forward hold 4h directional. 13-alt universe.

## 2. R-0 family-distinct gate analysis

### 2.1 Mathematical decomposition

`gap_z` decomposes as:
```
raw_gap   = (open_t / close_{t-1bar}) - 1   # 1-bar 5m signed log-return
gap_norm  = raw_gap / ATR_24h               # sigma-rescaling (preserves sign)
gap_z     = (gap_norm - mu_30d) / sigma_30d # affine z (preserves sign)
```

**Trigger sign(`gap_z`) = sign(`raw_gap`)** because both ATR division and z-score affine transforms are monotone in sign. ATR normalization and rolling z-score are **scaling transforms**, not statistic-class changes.

Therefore paradigm 126's trigger is **(session anchor) AND (1-bar 5m signed return magnitude)** sign-matched directional hold.

### 2.2 Class equivalence to predecessor graveyards

| Predecessor | Trigger structure | Verdict |
|---|---|---|
| **paradigm 113** | hour anchor {00,07,13,21} × prior 1h signed |z|≥1 → 2h directional | BROAD_FALSIFIED (0/13 syms ci_pos all 4 quadrants, hour-ALONE -6.69bp, \|z\|-ALONE -7.35bp, joint -11.65bp Lesson #21 anti-synthesis) |
| **paradigm 122** | dual anchor {21,00,08,16} × OI velocity z top-decile → 30min directional | BROAD_FALSIFIED_BOTH_FOCUS (0/13 syms ci_pos all 4 quadrants, both focus arms broad-uniform-negative, Lesson #21 4th dogfood) |
| **paradigm 126 candidate** | funding-boundary anchor {00,08,16} × 5m signed gap_z>2.5 → 4h directional | **R-0 HALT** (decomposes to temporal anchor × signed return z, equivalent to paradigm 113 class) |

paradigm 113 graveyard explicitly states (lines 138-141): "Hour-of-day axis combined with **NON-momentum signals** (e.g., volume z, OI z, premium z at anchor hr) might retain hypothesis space but is paradigm-distinct. Hour-of-day axis combined with NON-momentum signals... Hour-of-day × |z| momentum is directionally falsified."

paradigm 126's `gap_z` IS a 1-bar momentum/return signal at anchor → **paradigm 113 explicit exclusion zone**.

### 2.3 Differentiator evaluation

Each claimed differentiator was evaluated and rejected as parameter-sweep (not class-change):

| Claimed differentiator | Evaluation | Verdict |
|---|---|---|
| 5m gap vs 1h signed z (return window length) | Both produce signed return z; granularity is parameter sweep | REJECTED |
| ATR-normalization vs rolling std z | Both are sigma-rescaling transforms (ATR vs std is estimator choice) | REJECTED |
| Funding-boundary {00,08,16} vs hour-of-day {00,07,13,21} | paradigm 122 already tested funding-boundary as Anchor 2; anchor narrowing within same class is parameter sweep | REJECTED |
| 4h hold vs 2h/30min | paradigm 113 hold sweep tested 4h; sigex +1.58 FAIL 3-gate; horizon is forward-window parameter | REJECTED |

**All 4 claimed differentiators rejected.** paradigm 126 is **statistic-class duplicate** of paradigm 113/122 session-anchor × signed-magnitude family.

## 3. Lesson #21 explicit antipattern materialization (predicted)

Component axes:
- **Temporal anchor (funding-boundary)** = NULL per paradigm 113 + 122 (2 dogfoods)
- **1-bar 5m signed return z** = NULL per paradigm 113 (|z|-axis-ALONE -7.35bp, joint -11.65bp)

Stacking two null axes = Lesson #21 explicit antipattern: "joint axis underperforms either subset alone." paradigm 113 graveyard line 79 verbatim: "Joint is WORSE than either axis alone. Stacking the two NULL axes compounds fee drag without synthesizing alpha. Lesson #21 antipattern confirmed."

**paradigm 126 R-0 halt prevents 5th dogfood of Lesson #21 anti-synthesis** — the prediction is sufficient without empirical re-confirmation.

## 4. Session-anchor family Tier 4 retire candidate status

| Sub-class | Verdict | Date |
|---|---|---|
| paradigm 113 (hour anchor × signed return z) | BROAD_FALSIFIED | 2026-05-20 |
| paradigm 122 (dual anchor × OI velocity z) | BROAD_FALSIFIED | 2026-05-20 |
| paradigm 126 (funding-boundary anchor × signed return z) | **R-0 HALT (no compute)** | 2026-05-20 |

**Status**: Advisory caution etage maintained at **2 sub-classes BROAD_FALSIFIED + 1 R-0 halt**.

**Tier 4 formal retire decision**: NOT YET. Formal Tier 4 retire requires **3 R-1-computed BROAD_FALSIFIED sub-classes**. R-0 halt does NOT count as falsification dispatch (no compute, no graveyard verdict — only DNA duplication detection).

**Future dispatch policy** (R-0 advisory amendment): Any future session-anchor family R-1 dispatch must establish family-distinct via **NON-return / NON-OI / NON-momentum** trigger at anchor:
- Allowed candidates (per paradigm 113 graveyard explicit allowance): volume z at anchor, premium z at anchor, basis z at anchor, funding-rate at anchor, book_depth imbalance at anchor.
- Excluded (per paradigm 113 falsification): any signed-return z, any magnitude z derived from price, any OI velocity z.

Return-class triggers at session anchor are **explicitly excluded** until external evidence reverses paradigm 113 verdict.

## 5. Lesson dogfoods at R-0 (no compute, decomposition only)

| Lesson | Dogfood # | Notes |
|---|---|---|
| #21 axis stacking | 5th R-0 detection (paradigm 83+113+119+122 R-1 + paradigm 126 R-0) | Predicted antipattern, halt-by-DNA |
| #43 statistic-class novelty trap | dogfood | ATR-normalization + 30d z-score claimed as novelty; both rejected as scaling transforms |
| #44 amendment graveyard cross-reference | 8th dogfood | paradigm 113+122 substrate keyword match (anchor / signed-z / 5m frame), CONFIRMED status preserved |
| #45 unsupervised block | PASS | Explicit threshold \|gap_z\|>2.5, not unsupervised |
| #46 amendment stratified n=50×4q | not invoked (halt before R-0 compute) | n/a |

## 6. Counter classification

- **Counter increment**: NO. Cumulative graveyard counter remains at **125**.
- **Halt class**: `inventory_halt_R0_pre_dispatch_no_compute` (parallels paradigm 97 candidate funding_dispersion 2026-05-19, paradigm 122 slot-1 liquidation duplicate 2026-05-20).
- **paradigm 126 slot**: retained for next family-distinct candidate.

## 7. Recommended next candidate (paradigm 126 slot retained)

`alt_5m_volume_cusum_change_point_persistence_directional_2h`

**Rationale** (sourced from paradigm 122 graveyard line 119 recommendation):
- **Family-distinct axes**: volume CUSUM (NOT magnitude z, NOT velocity z, NOT taker-side, NOT session-anchored). Avoids retired families: OI velocity (71/120/122 3-sub-class Tier 4 retire qualified), taker-side (23/60/72 Tier 4 retired), funding (8 sub-classes Tier 4 retired), book_depth (12/23/61/84 Tier 4 retired), session-anchor (113/122 + 126 R-0 advisory caution), HMM/unsupervised (Lesson #45 confirmed retire), higher-order moments (65/66/124/125 Tier 4 retired).
- **Mechanism**: per-symbol cumulative sum of normalized 5m volume deviation; CUSUM upper-threshold breach with prior 30d persistence > median; 2h forward directional drift hypothesis.
- **Lesson #22 frame-grade**: 5m volume frame verified abundant (paradigm 122 panel 2.66M bars). PASS expected.
- **Lesson #11/#23**: CUSUM is non-event-anchored continuous trigger (Lesson #23 explicit non-target). Sample density structurally safe.
- **Lesson #28**: 1m OHLCV (volume) DB resampled → 5m archive-direct (paradigm 122 substrate reuse). PASS.
- **Lesson #40**: CUSUM symmetric continuous, no z-trigger structural infeasibility. PASS.
- **Lesson #45**: explicit CUSUM threshold (e.g., > 5σ cumulative), not unsupervised. PASS.
- **Lesson #44**: graveyard cross-reference required at R-0 — no prior CUSUM volume paradigm in 125 graveyards.

## 8. Artifacts

- R-0 prescreen JSON: `backend/runs/research_track/alt_5m_close_to_open_overnight_gap_z_normalized_atr_session_anchor_directional_4h/r0_prescreen.json`
- Graveyard report: this file
- INDEX entry: NOT registered (inventory-halt, no counter increment)
- No script generated (R-0 halt before code dispatch)

## 9. Lessons referenced

- **Lesson #11** sample density — not measured (halt before compute)
- **Lesson #19** SNT 4-quadrant — not applied (halt before compute)
- **Lesson #21** axis stacking — predicted antipattern, R-0 halt-by-DNA (5th detection)
- **Lesson #28** substrate availability — PASS (5m klines archive-direct)
- **Lesson #30** data window ratio — not measured
- **Lesson #39** sub-class A — predicted (symmetric trigger by construction; not executed)
- **Lesson #40** structural threshold feasibility — PASS (signed empirical z, |z|>2.5 reachable)
- **Lesson #43** statistic-class novelty trap — dogfood (ATR + z-score normalization rejected as class novelty)
- **Lesson #44 amendment** graveyard cross-reference — 8th dogfood, CONFIRMED preserved
- **Lesson #45** unsupervised block — PASS (explicit threshold, not unsupervised)
- **Lesson #46 amendment** stratified n=50×4q — not invoked

## 10. Conclusion

paradigm 126 candidate is a **session-anchor × signed-return-z class duplicate** of paradigm 113 and paradigm 122. All 4 claimed differentiators (return window length, ATR-normalization, anchor specificity, hold horizon) are parameter sweeps within the same statistic class, not class-distinct. ATR-normalization + 30d z-score are mathematical scaling transforms that preserve directional sign — they do NOT constitute a new statistic class. paradigm 113 graveyard line 138-141 explicit prediction: momentum/return signals at session anchor are directionally falsified; only non-return triggers (volume, premium, basis, funding rate, book_depth) at anchor remain hypothesis-eligible.

**R-0 halt mandatory. Counter not incremented. Next dispatch use paradigm 126 slot with `alt_5m_volume_cusum_change_point_persistence_directional_2h` or equivalent family-distinct candidate.**
