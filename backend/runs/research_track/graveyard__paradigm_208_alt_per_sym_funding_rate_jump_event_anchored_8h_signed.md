# paradigm 208 graveyard — alt_per_sym_funding_rate_jump_event_anchored_8h_signed

**Verdict**: `BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED` (Lesson #39 sub-class B mirror-inverted antipattern + Lesson #69 Item 6 5th pattern "monotonic decay")

**Phase**: R-1 (R-2 absolutely NOT progressed per dispatch directive)

**Date**: 2026-05-22 KST

**Family**: funding-axis (7th sub-class graveyard, +73/79/96/97/98/99/103 + paradigm 22 R-5 LIVE exception + funding_dispersion ETCUSDT exception)

---

## Hypothesis

Per-symbol 8h funding rate **Δ jump magnitude** (sequential 8h diff |Δ| ≥ T) is family-distinct from prior funding axes (level / sign flip / cs velocity / dispersion / per-sym velocity / cross-exchange spread). Event-anchored at 8h funding settlement boundary, bar direction signed, 4-quadrant SNT with DISJOINT trigger sets.

## Lesson #69 7-item + Item 8 candidate prescreen results

| Item | Check | Result |
|---|---|---|
| 1 | Lesson #61 slug grep `funding_jump|funding_delta|funding_rate_jump|funding_event_anchor` | **PASS** (no slug overlap, only `funding_rate_sign_flip_event` distinct axis) |
| 2 | Lesson #28 substrate-shape (funding DB 20 syms × 2.25yr) | **PASS** (45,996 records, 19 deep syms × 2024-02-19 → 2026-05-21) |
| 3 | Lesson #11 sample density | **FORCED THRESHOLD RELAXATION** — spec ±0.05% gives 158+172=330 events with **52% in AXSUSDT alone** (18/20 syms n<20 ex ante Lesson #16 FAIL). Relaxed to ±0.02% primary (n=1972, 14/20 syms n≥30 both dirs); ±0.05% retained as sweep cell. |
| 4 | Lesson #62 family DNA 4-dim 5/5 strict (funding family Tier 4 retire 충돌) | **5/5 distinct PASS** (statistic class=jump magnitude vs level/sign/velocity/dispersion/cross-ex; mechanism=event-anchored boundary jump vs continuous regime; entry=sparse 8h boundary class). Family-distinct 자격 verified. |
| 5 | Lesson #56 family-proxy | **PASS** (jump axis distinct, family Tier 4 retire 회피 자격) |
| 6 | Item 6 alpha decay 5-pattern audit | **5th pattern "monotonic decay" CONFIRMED** (see §Era stratify) |
| 7 | SNT structural integrity (paradigm 206 1.83x / paradigm 207 2.79x reference) | **DISJOINT verified** by construction (jump_sign +1 ⊥ -1, bar_dir +1 ⊥ -1). Cross-set asym ratio = **1.03–1.09x** (symmetric, NOT 2-3x like 206/207 — structurally expected for symmetric Δ distribution). |
| 8 candidate | Concentration + Temporal Independence 3rd dogfood | **PARTIAL CONFIRM** — temporal_cluster_ratio 0.929–0.978 (well > 0.5 PASS, hypothesis verified for event-anchored sparse triggers). sym_ci_pos_ratio recovery PARTIAL (mirror cells only, sparse cells have small n_measurable=3-5). |

---

## R-1 sweep results (Lesson #37 full sweep verdict scan)

3 thresholds × 3 hold periods × 4 quadrants = **36 cells**, **5 PASS** — all are MIRROR cells:

| cell | quadrant | n | sigex | ci_lower_bp | syms_ci+ | verdict |
|---|---|---|---|---|---|---|
| thr_0.030_hold_8h | A_mirror | 185 | +5.41 | +78.6 | 12/14 | PASS |
| thr_0.030_hold_24h | A_mirror | 185 | +2.07 | +19.8 | 7/14 | PASS |
| thr_0.050_hold_4h | B_mirror | 50 | +5.50 | +77.4 | 5/5 | PASS |
| thr_0.050_hold_8h | A_mirror | 46 | +3.65 | +78.5 | 2/3 | PASS |
| thr_0.050_hold_8h | B_mirror | 50 | +5.16 | +76.9 | 5/5 | PASS |

**Primary cell ±0.02% × 4h**: A_focus FAIL (sigex −0.14), B_same FAIL (sigex −3.68), both mirrors FAIL three-gate (B_mirror sigex +4.39 but ci_lower −13bp).

**Spec cell ±0.05% × 4h**: A_focus / A_mirror / B_same FAIL; **B_mirror PASS** (n=50, sigex +5.50, ci_lower +77.4, 5/5 syms ci+).

---

## Lesson #39 mirror-inversion antipattern CONFIRMED (3rd dogfood)

**Mathematical mirror identity**: For all 9 sweep cells (3 thresholds × 3 holds):

```
A_focus_mean_bp + A_mirror_mean_bp + 2 × fee_bp = 0.00 ± 0.00 bp
B_same_mean_bp  + B_mirror_mean_bp  + 2 × fee_bp = 0.00 ± 0.00 bp
```

This is **perfect ±k bp symmetric mirror** with deviation EXACTLY 0.00bp in 9/9 cells. A_mirror is mathematically `−A_focus − 16bp fee` — i.e., the funding Δ jump trigger contains **zero directional information** beyond the bar direction itself.

**Sub-class classification**: **Lesson #39 sub-class B (mechanism-inverted)**. A_focus broad-uniform-negative + A_mirror shows real concentration (5/5 syms ci+ at ±0.05% × 8h, 12/14 at ±0.03% × 8h). The mirror's "alpha" is just the inversion of A_focus's loss — fee-bound mean-reversion with high-vol bar selection, NOT funding-jump directional information.

**Unconditional baseline comparison** (no funding jump filter, 18 syms × 88k bars × hold=4h):
- focus (bar_dir continuation): mean = **−5.78bp / t = −8.86** (fee-bound)
- mirror (−bar_dir reversal):   mean = **−10.22bp / t = −15.66** (strongly negative)

Without the funding filter, mirror alpha does NOT exist. With ±0.05% jump filter, conditional bar magnitude is only **1.24x unconditional median** — modest high-vol selection, insufficient to explain the +302bp B_mirror PASS unless **regime decay** is the driver.

---

## Era stratification (Item 6 alpha decay 5th pattern "monotonic decay" CONFIRMED)

| cell | quadrant | 2024 (n, mean_bp, ci_lo) | 2025 | 2026 | pattern |
|---|---|---|---|---|---|
| ±0.05% × 4h | B_mirror | n=27, +517, +316 | n=13, +104, +30 | n=10, **−21, −21** | **monotonic decay** |
| ±0.05% × 8h | B_mirror | n=27, +530, +258 | n=13, +102, +72 | n=10, **+29, +29** | **monotonic decay** |
| ±0.05% × 8h | A_mirror | n=21, +661, +657 | n=14, +137, +9 | n=11, **+65, +38** | **monotonic decay** |
| ±0.03% × 8h | A_mirror | n=95, +239, +21 | n=63, +148, +78 | n=27, **+88, −44** | **monotonic decay** |
| ±0.03% × 24h | A_mirror | n=95, +37, −54 | n=63, +151, +49 | n=27, **+7, −158** | **decay + 2026 fee-bound** |

All 5 PASS cells show **monotonic decay 2024 → 2025 → 2026** with 2026 era at-or-below fee floor in 3/5 cells. The "alpha" is **almost entirely a 2024-regime artifact** (perp listing inflation era, high-vol mean-reversion regime). Forward (2026+) extrapolation has structurally-decayed expected edge ≤ fee floor.

This matches paradigm 207 monotonic sign-flip decay pattern + paradigm 87 delisting / paradigm 136/202 RV intraday cross-family pattern — **alpha decay is family-universal** (Lesson #55 prescription out-of-scope).

---

## Item 8 candidate (Concentration + Temporal Independence) 3rd dogfood verdict

| metric | result | threshold | verdict |
|---|---|---|---|
| temporal_cluster_ratio | 0.929–0.978 (across all cells, 24h gap definition) | ≥ 0.5 PASS | **CONFIRMED** (event-anchored 8h boundary trigger naturally temporally independent — hypothesis validated) |
| sym_ci_pos_ratio (primary ±0.02% × 4h B_mirror) | 9/18 = 0.50 | ≥ 0.3 PASS | PASS but B_mirror three-gate FAIL on ci_lower |
| sym_ci_pos_ratio (sweep ±0.05% × 8h B_mirror) | 5/5 = 1.00 | ≥ 0.3 PASS | PASS but n_measurable=5 only (small-n CI degeneracy) |

**Item 8 partial confirm**: temporal_cluster dimension validates event-anchored sparse trigger hypothesis (3rd dogfood). sym_ci_pos dimension is recovered in mirror cells where present, but mirror cells are Lesson #39 antipattern artifacts — so the high sym_ci_pos is itself a mirror-inversion artifact, not bona fide concentration. **Item 8 needs amendment**: sym_ci_pos must be measured on A_focus (not mirror) to be a valid concentration signal.

---

## Family-distinct 5/5 strict audit (vs funding family Tier 4 retire)

| vs paradigm | axis | paradigm 208 distinct? |
|---|---|---|
| 73 (funding × OI bipolar joint) | joint event detection | **DISTINCT** (jump magnitude, single-signal funding) |
| 79 (funding level z-score) | level magnitude | **DISTINCT** (jump = Δ NOT level) |
| 96 (funding sign flip) | sign change | **DISTINCT** (magnitude, not directional flip) |
| 97 (funding term structure cs dispersion) | cross-sym dispersion | **DISTINCT** (per-sym) |
| 98 (funding regime stratify) | continuous regime detection | **DISTINCT** (event-anchored sparse triggers) |
| 99 (funding per-sym velocity) | continuous derivative | **DISTINCT** (single Δ step, not velocity smoothing) |
| 22 R-5 LIVE (funding z-score MR) | 30d z level MR | **DISTINCT** (sparse Δ jump event NOT continuous z) |
| 103 (cross-exchange funding spread) | cross-venue | **DISTINCT** (single-venue Binance) |
| 170 (funding DB backfill) | infrastructure | **DISTINCT** (paradigm-distinct) |

**5/5 strict family-distinct verified**. paradigm 208 R-0 HALT funding family Tier 4 retire 충돌 회피 자격 **PASS**.

However, R-1 verdict is BROAD_FALSIFIED — so funding family Tier 4 retire is **strengthened to 7 sub-class graveyards** (paradigm 73/79/96/97/98/99/103 + 208 jump-event-anchored axis newly exhausted). Funding family Tier 4 retire 결정적 강화: 7 distinct sub-class axes all R-1 BROAD_FALSIFIED, only level z-score MR (paradigm 22) + funding_dispersion ETCUSDT survived. Funding axis paradigm-grade alpha 공간 사실상 결정적 소진.

---

## Lesson #42 16th dogfood (B mirror cell, Lesson #69 7-item template + Item 8)

Lesson #42 NEGATIVE (B mirror PASSes with mathematical mirror identity → Lesson #39 sub-class B antipattern). 16th confirmed NEGATIVE.

---

## Verdict reasoning chain

1. **Funding Δ jump trigger has zero directional information** (mathematical mirror identity 0.00bp deviation 9/9 cells)
2. **Mirror PASS cells are Lesson #39 sub-class B mechanism-inverted artifacts** (real concentration but inverted direction = fee-floor reversal selection)
3. **Mirror alpha is dominantly 2024-regime artifact** (Lesson #69 Item 6 5th pattern monotonic decay, 2026 at-or-below fee floor)
4. **Unconditional mirror baseline is strongly negative** (−10.22bp / t=−15.66) — funding filter is at most 1.24x high-vol selection, insufficient to extract +302bp B_mirror without 2024-regime amplification
5. **Funding family Tier 4 retire 강화**: 7th sub-class graveyard (paradigm 73/79/96/97/98/99/103 + 208)

---

## Artifacts

- code: `backend/scripts/research/paradigm_208_funding_jump_event_r1.py`
- metrics: `backend/runs/research_track/paradigm_208_alt_per_sym_funding_rate_jump_event_anchored_8h_signed/r1__metrics.json`
- graveyard: this file

---

## Paradigm 209 next-action recommendation

Per [[feedback-persistence-over-efficiency]] + [[feedback-paradigm-campaign-continuous-parallel]] memory: **continue dispatch**, do NOT pause.

Given:
- 7 funding sub-class graveyards (family Tier 4 retire strengthened)
- 5 consecutive prior paradigm 178/199/200/201/202 + paradigm 203 MEMORIAL agent SELF-RECOMMEND saturation precedent (Lesson #69 Item 7 5-consecutive non-PASS → switch to user-provided hypothesis mode 의무)
- paradigm 207 graveyard + paradigm 208 graveyard = paradigm-architect 권고 채택 cycle, but B_mirror Lesson #39 sub-class B confirms continued mirror-inversion in event-anchored funding axes

**Recommendation for paradigm 209**: 
- **Path A (DEFAULT, user-provided hypothesis mode preferred)**: Request user hypothesis. Memory precedent paradigm 203 MEMORIAL — agent SELF-RECOMMEND saturation pattern.
- **Path B (paradigm-architect SELF-RECOMMEND, if user re-elects)**: Pivot to **non-funding NON-mirror-prone axis**. Funding family exhausted (7 graveyards). Mirror-prone categories: directional magnitude triggers on symmetric distributions (Lesson #39 candidate ex ante prescreen). Suggest **liquidation cascade post-capitulation alt directional 30m × 45m re-investigation with strict A_focus three-gate audit (mirror cells excluded ex ante by Lesson #39 amendment candidate)** — OR pivot fully to **non-Δ-magnitude axes** (e.g., venue-specific OI level acceleration with Lesson #69 Item 8 sym_ci on A_focus enforcement).

**Lesson #61 amendment permanent inventory check 의무** for paradigm 209 dispatch.

---

## Lesson candidates from paradigm 208

1. **Lesson #39 amendment candidate**: For paradigms with symmetric Δ-distribution triggers (funding Δ, return Δ, volume Δ), Lesson #39 sub-class B mirror-inversion antipattern is ex ante prescreen-able. If `A_focus + A_mirror + 2*fee ≈ 0bp` mathematically by construction, MIRROR cells must be excluded from PASS verdict ex ante. **3rd dogfood confirmed** (paradigm 108 sub-class A / paradigm 110 sub-class B / paradigm 208 sub-class B).

2. **Item 8 amendment candidate**: sym_ci_pos_ratio must be measured on A_focus / B_same continuation cells, NOT mirror cells. Mirror cells' sym_ci_pos is a mirror-inversion artifact (high sym_ci_pos in mirror = high sym_ci_neg in focus). 3rd dogfood reveals this dimension needs scope restriction. (CONFIRMED-자격 dogfood 3 in paradigm 206/207/208 with refinement.)

3. **Funding family Tier 4 retire 강화 7-graveyard documentation**: paradigm 73/79/96/97/98/99/103 + 208 axes all graveyarded. Only paradigm 22 (level z-score MR) + funding_dispersion (ETCUSDT exception only) survived. **Funding axis paradigm-grade directional alpha 결정적 소진**. Re-examination requires non-Δ-magnitude, non-level, non-sign-flip, non-velocity, non-dispersion, non-cross-venue, non-event-anchored novel axis (axis exhaustion verified).
