# GRAVEYARD — paradigm 121 `hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h`

**Verdict**: `BROAD_FALSIFIED_LESSON39_SYMMETRIC_NO_AXIS_SYNTHESIS_HMM_FILTER_INEFFECTIVE`
**Date**: 2026-05-20 KST 17:21
**Counter**: 121 (paradigm 120 BROAD_FALSIFIED_FEE_FLOOR_SUB_THRESHOLD → **121 본 그레이브야드**)
**Wall clock**: 1.3 min (78.3s — R-0 prescreen 0.4s + R-1 78s incl. 6×HMM walk-forward fits)
**Host**: hcp local (paradigm 105 markPrice cache + paradigm 119 hmmlearn 0.3.3 install)

---

## 1. Hypothesis

HMM (3-state Gaussian, per-symbol, weekly walk-forward refit on 1h log-returns)
as **conditioning filter** + markPrice basis 1h z-score (rolling 30d, |z|>2) as
**trigger** = unsupervised endogenous vol decomposition × external orthogonal axis.

Joint 4-quadrant SNT:
- A_focus: HMM HIGH-vol (state==2, posterior>=0.8) × basis z>+2 × SHORT 4h
- A_mirror: HMM HIGH × basis z>+2 × LONG 4h
- B_focus: HMM HIGH × basis z<-2 × LONG 4h
- B_mirror: HMM HIGH × basis z<-2 × SHORT 4h

**Lesson #45 candidate UMBRELLA-PATH verification target** — paradigm 119 endogenous-only
HMM state-identity trigger was BROAD_FALSIFIED. paradigm 121 places HMM as filter
conditioning + exogenous axis as trigger, testing whether HMM-based mechanisms have
**any** viable architecture.

## 2. R-0 prescreen 2026-05-20 17:17 KST — **PASS**

| Check | Result | Verdict |
|---|---|---|
| Lesson #28 substrate | paradigm 105 cache 6 alts × 1y × 5m mark+index PASS | PASS |
| Lesson #11 sample density | 4.86% |basis z|>2 × ~30% high-vol proxy (rolling 30d std top tercile) × 6 alts × 1y = ~200/quadrant | PASS marginal |
| Lesson #34 empirical dist | basis_pct median -4.77~-5.91 bp (negative basis confirmed for all 6 alts), \|z\|>2 rate 4.17~5.54% by sym | PASS |
| Lesson #46 candidate (2nd dogfood) | **A_focus pool n=202 gross +43.46bp (CI 95% +16.3~+70.6bp) > 16bp fee floor** | **R-0 PASS, proceed to R-1** |

**R-0 verdict: `R0_PASS_PROCEED_R1`** based on Lesson #46 candidate strict-PASS signal.

## 3. R-1 result — 4-quadrant Symmetric Negative Test

**Frame**: 1h basis z-score × HMM HIGH-conf (state==2 ∧ posterior>=0.8) × 4h hold

### HMM HIGH-conf state rate (CRITICAL)
| Symbol | HMM HIGH-conf rate | R-0 proxy rate | Sample reduction |
|---|---|---|---|
| SOLUSDT | 1.79% | ~30% | **16.8x sparse** |
| HBARUSDT | 1.61% | ~30% | 18.6x sparse |
| AVAXUSDT | 1.63% | ~30% | 18.4x sparse |
| DOGEUSDT | 2.68% | ~30% | 11.2x sparse |
| ETHUSDT | 2.39% | ~30% | 12.6x sparse |
| LINKUSDT | 2.22% | ~30% | 13.5x sparse |
| **Median** | **2.05%** | ~30% | **~14.6x sparser than R-0 proxy** |

HMM HIGH-state with posterior>=0.8 high-confidence filter produces **~2% bars** vs
R-0 proxy (rolling 30d std rank top tercile) ~30%. The HMM is much more selective
on what counts as "high-vol regime".

### Per-quadrant results

| Quadrant | n | mean bp | obs_t | sigex | ci_lower bp | perm_p | 3-gate | conc q_pos_t | syms_ci_pos | life_changing |
|---|---|---|---|---|---|---|---|---|---|---|
| **A_focus** z>+2 × HIGH × SHORT | 70 | **+10.36** | +0.32 | +0.68 | -36.81 | 0.762 | FAIL | 0.50 (2q) | 0/0 | 0.10% (need 2%) |
| **A_mirror** z>+2 × HIGH × LONG | 70 | -26.36 | -0.81 | -0.45 | -83.43 | 0.678 | FAIL | 0.50 (2q) | 0/0 | -0.26% |
| **B_focus** z<-2 × HIGH × LONG | 78 | **-51.39** | -1.18 | -0.83 | -122.62 | 0.779 | FAIL | 0.00 (2q) | 0/0 | -0.51% |
| **B_mirror** z<-2 × HIGH × SHORT | 78 | +35.39 | +0.81 | +1.16 | -41.37 | 0.874 | FAIL | 1.00 (2q) | 0/0 | 0.35% |

**0/4 quadrants 3-gate PASS. Concentration FAIL universally (0 measurable syms — all
per-sym n < 20 after HMM filter).**

### Lesson #39 sub-class A symmetric exact 2×fee pattern

- A_focus +10.36 bp / A_mirror -26.36 bp → **diff = 16 bp = 2 × fee_per_trade (8bp)**
- B_focus -51.39 bp / B_mirror +35.39 bp → diff = -16 bp = -2 × fee
- **Both sides exact ±16bp mirror-symmetric** → Lesson #39 sub-class A confirmed:
  trigger carries ZERO directional information; observed mean = (gross_long − fee) vs
  (gross_short − fee), with gross_long ≈ -gross_short ≈ 0. Both directions = pure direction-bet + fee drag.

## 4. Mechanism diagnosis

### 4.1 HMM-as-filter does NOT enhance signal — only thins sample

- R-0 proxy (rolling 30d std top tercile) → A_focus gross +43.46 bp, n=202
- R-1 HMM proper (3-state Gaussian, posterior>=0.8) → A_focus gross +18.36 bp (net +10.36 + 8 fee), n=70
- **HMM HIGH-conf selection halved gross drift AND thinned sample 3x**. Sample-quality
  trade-off resulted in NET loss of statistical power. Per-trade edge collapsed from
  0.43% (R-0 sufficient) → 0.10% (R-1 way below 2% life-changing floor).

### 4.2 paradigm 119 vs 121 — HMM mechanism BROKEN across architectures

- paradigm 119 (graveyard): HMM state-identity as direct trigger (endogenous-only) → BROAD_FALSIFIED
- paradigm 121 (this): HMM as conditioning filter + exogenous axis (basis) → BROAD_FALSIFIED
- **Lesson #45 candidate STRENGTHENED** — HMM-based mechanism architecture broadly broken across both
  endogenous-only and exogenous-conditioned variants (2 dogfoods CONFIRMED 자격 자격 reached).

### 4.3 paradigm 105 vs 121 — markPrice basis as joint axis BROKEN

- paradigm 105 (graveyard): basis signed percentile rank at 5m × 4h hold single-axis → BROAD_FALSIFIED
- paradigm 121 (this): basis 1h z-score |z|>2 × HMM HIGH joint conditioning → BROAD_FALSIFIED
- markPrice basis directional alpha **continuously arbitraged via funding 8h cycle**, no
  amount of conditioning saves it (consistent with paradigm 105 §8 family analysis).

### 4.4 Lesson #46 candidate 2nd dogfood DECLINE — proxy/realized格差

- **R-0 prescreen signal +43.46 bp ≠ R-1 realized +10.36 bp** (4.2x optimistic bias)
- Root cause: R-0 used **rolling 30d std rank top tercile** as HIGH-vol proxy (~30% of bars)
  but R-1 uses HMM HIGH-conf state (posterior>=0.8, ~2% of bars)
- The cohort of "high-vol bars" in R-0 vs R-1 is structurally different — R-0 includes
  borderline elevated-vol bars where basis extreme is more frequent and resolves quickly;
  R-1 selects only deep-HIGH HMM-discriminated bars where mechanism is shorter-lived
- **Lesson #46 candidate REFINEMENT REQUIRED**: R-0 prescreen must use **exact R-1 mechanism**
  (HMM walk-forward), not faster proxy. Proxy-based gross drift estimates can overestimate
  by 4x — the gating decision must use the mechanism's own filter.
- **2 dogfood VERDICT diverge** (paradigm 120 R-0 NOT executed cleanly, paradigm 121 R-0 PASS but R-1 FAIL).
  Lesson #46 candidate retained but with mandatory amendment.

## 5. Verdict tree classification

`BROAD_FALSIFIED_LESSON39_SYMMETRIC_NO_AXIS_SYNTHESIS_HMM_FILTER_INEFFECTIVE`

This is a **compound verdict** capturing two simultaneous diagnoses:
1. **Lesson #39 sub-class A "no axis synthesis"** — A_focus / A_mirror exact ±2×fee
   symmetric, B_focus / B_mirror same. Joint trigger carries no directional info.
2. **HMM filter ineffective** — HMM HIGH-conf selection thins sample 14x while
   reducing gross drift 50%, net-effect harmful.

Verdict code in metrics.json was caught as `BROAD_FALSIFIED_FEE_FLOOR_GROSS_INSUFFICIENT`
(fee_floor branch) but the deeper diagnosis is Lesson #39 sub-class A (which the verdict
tree should have caught — script bug: `symmetric_diff_bp 16.0` matches `< 5.0` threshold
when threshold should compare diff to fee_per_trade × 2; the 16.0 == 2×fee was missed).

Recommended verdict-tree code amendment: Lesson #39 symmetric check should compare
`abs(focus_mean) + abs(mirror_mean)` to expected `2 × fee_per_trade × 1e4` window (within ±2bp), not the `abs(abs(focus) - abs(mirror))` difference. Filing as paradigm-architect skill bug.

## 6. Lessons dogfood

| Lesson | Dogfood action | Result |
|---|---|---|
| **#11** sample density | per-quadrant R-0 ~200 PASS, R-1 70-78 actual borderline | PASS (R-0) / borderline (R-1) |
| **#16** Concentration Gate | applied 4 quadrants, all FAIL (0/0 syms measurable per-cell) | dogfood OK |
| **#19** Symmetric Negative Test | 4-quadrant in single R-1 batch — broad-falsified diagnosis explicit | dogfood OK |
| **#28** substrate availability | paradigm 105 cache 6 alts verified pre-execution, hmmlearn 0.3.3 installed | dogfood OK |
| **#34** empirical distribution | basis_pct median ~-5bp (negative basis), |z|>2 rate ~4.86% measured | dogfood OK |
| **#39 sub-class A "no axis synthesis"** | A_focus +10.36 / A_mirror -26.36 exact 2×fee symmetric, B_focus / B_mirror same. Direction-bet + fee drag, joint trigger zero directional info | **3rd dogfood CONFIRMED 자격 reinforced** |
| **#45 candidate STRENGTHENED** | HMM as filter + exogenous axis BROAD_FALSIFIED → HMM-based mechanism broken across architectures (paradigm 119 endogenous-only + paradigm 121 conditioning filter) | **2 dogfoods CONFIRMED 자격 reached, promote to confirmed** |
| **#46 candidate DECLINE / AMENDMENT** | R-0 proxy +43.46bp vs R-1 realized +10.36bp = 4.2x optimistic bias. Proxy ≠ mechanism for gating | **2nd dogfood AMENDMENT REQUIRED: R-0 must use exact R-1 filter, not faster proxy** |

## 7. Family impact

### 7.1 Lesson #45 candidate → confirmed promotion criteria reached

Two independent HMM-based paradigm graveyards (119 endogenous-only + 121 exogenous-conditioned)
both BROAD_FALSIFIED. The umbrella-path verification was the explicit goal of paradigm 121,
and the result is structural failure. Recommend formal promotion of Lesson #45 candidate to
**confirmed** in PARADIGM_QUEUE_2026Q3 next §6.x update.

### 7.2 HMM-based unsupervised decomposition family Tier 4 retire candidate

With paradigm 119 + 121 dual BROAD_FALSIFIED, plus the larger unsupervised decomposition family
graveyards (paradigm 83 k-means latent regime, paradigm 84 CUSUM Page-Hinkley sample-insufficient,
paradigm 86 multi-day vol persistence sample-insufficient), the family is approaching **5 fail mode
graveyards**. With paradigm 121 explicitly testing the "HMM as filter not trigger" escape path and
failing, the family lacks any remaining viable architecture.

Recommend **Tier 4 formal retire of HMM unsupervised decomposition family** at next §6.x update.

### 7.3 markPrice basis × any conditioning family — diminishing returns

paradigm 105 (basis percentile rank single-axis) + paradigm 121 (basis × HMM joint) both fail. The
basis-axis-as-trigger paradigm space appears similarly exhausted. paradigm 22 (premium index daily
follow momentum) remains the only seeded paradigm using related substrate, operating at completely
different scale (daily, not 5m/1h).

## 8. Recommendations to user

1. **Update PARADIGM_QUEUE_2026Q3.md §6.x** with the following:
   - Lesson #45 candidate → **CONFIRMED 자격 reached** (2 dogfoods: paradigm 119 + paradigm 121)
   - Lesson #46 candidate → **AMENDMENT REQUIRED** (R-0 prescreen must use exact R-1 mechanism, not faster proxy)
   - HMM unsupervised decomposition family → **Tier 4 formal retire CANDIDATE** (will become formal after one more confirmation dogfood)
   - paradigm-architect skill **bug filing**: Lesson #39 verdict-tree code threshold should be `≈ 2 × fee_per_trade ± 2bp`, not `< 5bp absolute difference`
2. **Do NOT retry** HMM-based paradigms with current archive substrate. The mechanism architecture is broken.
3. **Continue continuous-parallel policy** with paradigm 122 candidate selection from non-HMM, non-basis axes.

## 9. Artifacts

- R-0 script: `backend/scripts/research/paradigm121_r0_prescreen.py` (152 lines)
- R-0 metrics: `backend/runs/research_track/hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h/r0_prescreen.json`
- R-1 script: `backend/scripts/research/paradigm121_hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h_r1.py` (390 lines)
- R-1 metrics: `backend/runs/research_track/hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h/r1__metrics.json`
- Substrate reused: paradigm 105 mark_index_cache (no net new substrate)
- New install: hmmlearn 0.3.3 (local venv, Mint compatibility confirmed)

**Total cost**: 1.3 min wall clock + 0 MB new disk (paradigm 105 cache reused).

## 10. Counter update

- paradigm 120 BROAD_FALSIFIED_FEE_FLOOR_SUB_THRESHOLD (2026-05-20 17:00)
- **paradigm 121 BROAD_FALSIFIED_LESSON39_SYMMETRIC_NO_AXIS_SYNTHESIS_HMM_FILTER_INEFFECTIVE (2026-05-20 17:21)**
- Cumulative graveyards: **121**
