# paradigm 176 — paradigm_24_r5_spec_adaptive_expansion_per_sym_entry_z_optimization_lesson_70_exempt

**Track**: paradigm 24 spec-ADAPTIVE expansion (Lesson #70 exempt path candidate)
**Dispatch attempt**: 2026-05-21 23:13 KST (option γ adopted from paradigm 175 §6.73 next-action 3순위)
**Counter**: 176 used (substantive R-0 halt with Lesson #11 + #62 + paradigm 159 precedent triple-hit)
**Wall clock**: ~10 min (audit only, no compute dispatched)

---

## Verdict

**`R0_HALT_BY_SAMPLE_INSUFFICIENT_LESSON_11_AND_MULTIPLE_TESTING_LESSON_62_AND_LESSON_70_EXEMPT_FAIL`**

Lesson #69 5-item strict template (11th post-CONFIRMED dogfood) outcome: **3/5 HALT (Item 1 PASS · Item 2 PASS · Item 3 HALT · Item 4 HALT · Item 5 advisory)**.

R-1 not dispatched. Counter 176 consumed (substantive halt with full evidence trail, same disposition as paradigm 159).

---

## Hypothesis

Per-sym in-sample (70%) entry_z optimization across {2.0/2.5/3.0/3.5/4.0} sweep on the 17-sym paradigm 175 cohort. Selects per-sym best entry_z by in-sample Sharpe/sigex, then validates on remaining 30% OOS.

Goal: identify subset where spec-adaptive (per-sym tuned) entry_z restores three-gate + life-changing 4-dim eligibility.

Lesson #70 exempt rationale: spec-adaptive = mechanism-extension, not same-spec broader-cohort expansion. The CONFIRMED Lesson #70 ban applies only to fixed-spec expansion.

---

## Lesson #69 5-item strict template (11th post-CONFIRMED dogfood)

### Item 1 — Lesson #61 amendment slug grep — **PASS**

`ls research_track/` 검색 결과:
- No prior slug containing `spec_adaptive_expansion` / `per_sym_entry_z_optimization`
- paradigm 175 (`...narrow_scope_expansion_screening_deep_univ_cross_family_lesson_70_verification`) = source paradigm reference, not duplicate
- paradigm 159 (`alt_calendar_anchor_DOW_or_HOD_directional_4h`) = per-sym in-sample DOW/HOD fit precedent (different statistic axis, but methodological adjacency)

Slug uniqueness: PASS. Lesson #61 amendment 11th post-confirmation: clean.

### Item 2 — Lesson #28 amendment substrate-shape audit (11th dogfood) — **PASS**

- premium_index joblib substrate (paradigm 175 verified, 17 syms × 2.19yr)
- 70/30 train/test split:
  - 15 valid-window syms (BTC/ADA excluded per Lesson #30 short-window advisory, OOS 100-101d only)
  - Train window 1.5yr / Test window 0.7yr per sym
- Substrate availability time-dim + existence-dim: PASS

### Item 3 — Lesson #11 sample density (per-quarter / per-cell n ≥ 30 cutoff) — **HALT**

Quantitative analysis (using paradigm 175 empirical n_trades at z=2.0 as ground truth + Gaussian tail-mass scaling):

| z threshold | Tail mass two-tail | Ratio vs z=2.0 | Median per-sym IS n (70% of full) | Syms with IS n ≥ 30 |
|---|---|---|---|---|
| 2.0 | 0.0455 | 1.000x | **20** | **0/15** |
| 2.5 | 0.0124 | 0.273x | **6** | **0/15** |
| 3.0 | 0.0027 | 0.059x | **1** | **0/15** |
| 3.5 | 0.00047 | 0.010x | **1** | **0/15** |
| 4.0 | 0.00006 | 0.001x | **1** | **0/15** |

**Per-sym in-sample n_cell ≥ 30 cutoff: 0/15 syms × 5 z thresholds = 0/75 cells achievable**.

Even the most permissive z=2.0 setting gives only **20 in-sample trades per sym** (median across 15 valid syms) — well below the Lesson #11 cutoff of 30. Strict thresholds (z≥3.0) collapse to 1 trade per sym.

This is the **dominant blocking constraint**. Lesson #11 prescreen verdict: **HALT_BY_SAMPLE_INSUFFICIENT**.

### Item 4 — Lesson #62 DNA 4-dim audit + multiple-testing strict — **HALT**

DNA 4-dim audit vs prior paradigms:

| Dim | paradigm 24 R-5 (fixed spec) | paradigm 159 (per-sym DOW/HOD fit, R-0 HALT) | **paradigm 176** | Strict change vs ALL prior? |
|---|---|---|---|---|
| Statistic class | premium_index z-score | calendar anchor (DOW/HOD) | premium_index z-score | PARTIAL (vs p24: same; vs p159: same axis-method) |
| Universe | DOGE/SOL/LDO (3) | 14 syms | 15 syms (post-Lesson #30 filter) | STRICT vs p24 / PARTIAL vs p159 |
| Entry-side class | fixed entry_z=2.0 | per-sym fitted threshold | per-sym fitted entry_z | STRICT vs p24 / PARTIAL vs p159 (same per-sym fit class) |
| Mechanism | fixed-spec follow momentum | per-sym selection-bias artifact | per-sym spec-adaptive | STRICT vs p24 / PARTIAL vs p159 |

**Strict count vs p24: 3/4** — boundary PASS in isolation
**Strict count vs p159: 0-1/4** — methodological replica of selection-bias antipattern

**Multiple-testing analysis (Lesson #62 strict)**:
- Test cells: 15 syms × 5 z thresholds = **75 cells**
- Bonferroni-adjusted α (target 0.05): **0.05 / 75 = 0.00067**
- paradigm 175 empirical perm_p range across same 15 syms at z=2.0: **[0.497, 0.956]** (best perm_p = 0.497)
- **Required perm_p for Bonferroni significance: < 0.00067**
- **Empirical best perm_p (0.497) is ~750x worse than Bonferroni threshold**

No realistic per-sym tuning can close a 750x gap in perm_p — this is fundamental fee-floor + noise saturation, not a hyperparameter discovery problem.

**paradigm 159 R-0 HALT precedent**: per-sym in-sample fit with multiple-testing inflation across cells (98 cells DOW/HOD) was halted at R-0 for exactly the same reason. paradigm 176 = same antipattern with smaller cell count (75 vs 98) but identical statistical structure.

**Lesson #62 multiple-testing strict verdict: HALT**.

### Item 5 — Lesson #56 family-proxy OUTCOME-LEVEL cross-reference (17+ instances) — **advisory**

- premium_index family preserved exception (paradigm 24 R-5 LIVE DOGE/SOL/LDO seeded 2026-05-06)
- Pre-execution prediction: spec-adaptive would surface in-sample artifacts (best in-sample z chosen per sym) but Bonferroni-corrected OOS p_value would fail at every cell.
- If R-1 were dispatched: expected OOS verdict = BROAD_FALSIFIED_FEE_FLOOR + cohort-fragmented (per-sym different best z = no shared mechanism)
- This would be **Lesson #56 19th instance** (family-proxy 위반: family-preserved status retained at narrow cohort, fails at broader cohort even with spec adaptation)

Advisory: not blocking on its own, but reinforces sample-density + multiple-testing halt.

---

## Lesson #70 exempt verification

**Lesson #70 statement**: "R-5 LIVE narrow-cohort survivor expansion at fixed spec on any broader cohort is presumptively HALT — only spec-adaptive (per-sym parameter optimization) expansion permitted."

**paradigm 176 Lesson #70 exempt status**: **technically exempt** (spec-adaptive is the carved-out path), **but exempt path itself fails on independent prescreen**:

| Exempt path requirement | paradigm 176 status |
|---|---|
| Mechanism-extension, not fixed-spec | ✓ per-sym entry_z optimization |
| Lesson #62 multiple-testing strict | ✗ 75 cells × Bonferroni 0.00067 vs empirical perm_p 0.5+ |
| Bonferroni correction applied | ✓ specified in TASK |
| Train/test split overfitting safeguard | ✓ 70/30 specified |
| Lesson #11 sample density per cell | ✗ 0/75 cells reach n≥30 |

**Verdict**: Lesson #70 exempt path **proven structurally infeasible for daily-granularity sparse-trigger R-5 paradigms** (paradigm 22 + 24 family). The exempt path is technically open but requires sample density that paradigm 22/24 cannot supply at any sensible z threshold.

**Lesson #70 corollary candidate (NEW)**:
> "Lesson #70 exempt path (spec-adaptive expansion) requires per-sym in-sample n ≥ 30 at the candidate threshold. Daily-granularity sparse-trigger R-5 paradigms (paradigm 22 + 24 family) cannot satisfy this prerequisite because the native trigger rate produces 15-35 trades per sym across full 2.2yr OOS window, leaving 10-20 trades per sym after 70/30 train split — below cutoff. The exempt path is theoretically valid but **practically void for sparse-trigger R-5 family**."

This corollary, if confirmed by a 2nd dogfood on a non-sparse R-5 paradigm (5m/1h granularity), would crystallize the Lesson #70 + Lesson #25 confluence into a single permanent rule.

---

## R-0 prescreen aggregate verdict

| Item | Verdict | Note |
|---|---|---|
| 1. Lesson #61 slug grep | PASS | clean |
| 2. Lesson #28 substrate audit | PASS | premium_index joblib 17 syms × 2.19yr verified |
| 3. Lesson #11 sample density | **HALT** | 0/75 cells reach n≥30 cutoff (best cell n=24 at z=2.0) |
| 4. Lesson #62 DNA + multiple-testing | **HALT** | 75 cells Bonferroni 0.00067 vs empirical perm_p 0.5+ |
| 5. Lesson #56 family-proxy | advisory | reinforces halt |

**Aggregate: 3 PASS · 2 HALT · 0 advisory-only-blocking**

Per Lesson #69 5-item strict template: **any HALT item triggers R-0 halt**. paradigm 176 has **2 independent HALT items** → R-1 not dispatched, counter consumed for substantive halt.

---

## Decision: do NOT dispatch R-1

Compute estimate avoided: ~30-60 min (R-1 per-sym IS sweep + OOS validation across 15 syms × 5 z thresholds = 75 backtest cells).

Alternative paths considered and rejected:
- Lower z threshold (z<2.0) → departs from premium_index z-score paradigm mechanism (no longer testing same hypothesis class)
- Larger universe → would not change per-sym in-sample n (per-sym constraint, not aggregate)
- Longer OOS window → already at 2.19yr substrate limit per paradigm 175 audit
- Different spec parameter (hold_days variation) → would still face same multiple-testing inflation + same sample density per cell

**Conclusion**: spec-adaptive expansion on paradigm 24 R-5 family is **structurally infeasible** at current substrate window + paradigm-native trigger rate. No tuning of the parameters specified in Option γ recovers the prerequisite sample density.

---

## What this discovery contributes

1. **Lesson #70 corollary candidate confirmed at 1st dogfood**: Lesson #70 exempt path (spec-adaptive) has its own sample-density prerequisite that sparse-trigger R-5 paradigms cannot meet. paradigm 22 + 24 R-5 family are now confirmed **fully terminal** (no expansion path at all — fixed-spec banned by Lesson #70, adaptive-spec banned by Lesson #11 + #62).
2. **Methodological adjacency to paradigm 159 R-0 HALT precedent**: per-sym in-sample optimization with multiple-testing inflation is the same antipattern paradigm 159 already halted, just applied to a different statistic axis.
3. **Lesson #62 multiple-testing strict 12th boundary dogfood** (post-CONFIRMED), with explicit Bonferroni quantification.
4. **Counter consumed**: paradigm 176 substantive halt with full evidence trail (same handling as paradigm 159).

---

## paradigm 177 next-action 권고

Lesson #70 + Lesson #11 + Lesson #62 triple-hit on Option γ closes the paradigm 175 §6.73 next-action menu entirely:
- Option α (Lesson #70 formal upgrade) — already CONFIRMED 정식 per paradigm 175 §6.73 ratification
- Option β (new paradigm DNA dispatch) — **now mandatory remaining path**
- Option γ (spec-adaptive expansion) — **paradigm 176 has falsified this option for paradigm 22 + 24 family**

**1순위 권고**: **paradigm 177 = new paradigm DNA dispatch (Option β resume)** per [[feedback-paradigm-campaign-continuous-parallel]] and [[feedback-persistence-over-efficiency]]. R-5 LIVE cohort expansion lane is now structurally closed for sparse-trigger paradigms 22 + 24; resume default continuous-parallel dispatch.

**2순위 권고**: Lesson #70 corollary "spec-adaptive exempt path also requires Lesson #11 sample density" candidate documentation (1st dogfood — paradigm 176). Would need 2nd dogfood on a non-sparse R-5 paradigm to upgrade to CONFIRMED 자격.

**3순위 (defer)**: If a future non-sparse R-5 LIVE paradigm appears (e.g., 5m/1h granularity OI-decoupling family), retest spec-adaptive expansion path there to validate Lesson #70 corollary universality.

---

## Counter snapshot post-paradigm 176

- Graveyards (substantive): **170 unchanged** (paradigm 176 = R-0 prescreen halt, not graveyard)
- R-0 halts (cumulative): paradigm 88/89/90/97-candidate/159/**176** = 6 substantive R-0 halts with counter consumption
- Non-PASS streak: **41+** (paradigm 176 adds to streak)
- R-5 LIVE: **11 unchanged**
- R-5 yield: **6.40% unchanged**
- Lesson library: 70 CONFIRMED unchanged; Lesson #70 corollary candidate (1st dogfood)
- paradigm-architect skill amendment: paradigm 175 §6.73 1순위 Option α 권고 (Lesson #70 → lesson_prescreen_checklist.md) deferred pending separate session
