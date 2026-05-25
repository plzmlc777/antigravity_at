# GRAVEYARD — paradigm 159 `alt_calendar_anchor_DOW_or_HOD_directional_4h`

**Verdict**: `R0_HALT_BY_INVENTORY_DUPLICATE_LESSON_61_AMENDMENT_1ST_DOGFOOD_SUCCESS`
**Phase halted**: R-0 (R-1 NOT DISPATCHED)
**Dispatch attempt**: 2026-05-21 16:03 KST (paradigm 158 §6.55 next-action Option α explicit 1순위 recommendation)
**Wall clock**: 4 min (inventory audit only)

---

## TL;DR

paradigm 158 §6.55 next-action Option α 권고는 "DNA 0/6 with any prior" 주장했으나 Lesson #61 amendment 의무 inventory check 실행 시 paradigm 113 `intraday_hour_of_day_anchor_alt_directional_2h` (2026-05-20 R-1 BROAD_FALSIFIED) **검출**. Lesson #61 amendment 1st post-confirmation dogfood **정확한 catch case**: amendment가 catch하려고 설계된 stale recommendation 패턴이 paradigm 159 dispatch attempt에서 실제 발생.

R-0 halt 정당화 cumulative 신호:

1. **paradigm 113 graveyard advisory 명시** — "future temporal-axis paradigm (day-of-week, week-of-month, session-boundary close variants) should be advisory cautioned". paradigm 159는 정확히 day-of-week sub-axis
2. **paradigm 157 (NY close 21UTC session anchor 4h) 2026-05-21 BROAD_FALSIFIED Lesson #39B mechanism-inverted** + Lesson #68 candidate 1st dogfood (session-boundary anchor × 4h × cross-asset = fee-floor-bound mechanism-inverted antipattern). paradigm 159 4h calendar-anchor은 Lesson #68 candidate 2nd dogfood 정확 위치
3. **per-sym in-sample DOW/HOD fit = Lesson #21 axis-stacking sub-class** — 14 syms × 7 DOW = 98 cells multiple-testing selection bias artifact
4. **paradigm 156+157+158 §next-action 3개 연속 stale recommendation** — Lesson #61 amendment 누적 4번째 catch case

paradigm 159 R-1 NOT DISPATCHED. counter 159 사용 (substantive R-0 halt, paradigm 97 candidate inventory-halt 사례와 동일 처리).

---

## 1. Lesson #61 amendment inventory check (1st dogfood post-confirmation, SUCCESS catch)

### 1.1 Slug duplicate search 결과

| Slug | Date | Verdict | Calendar-anchor family member? |
|---|---|---|---|
| `intraday_hour_of_day_anchor_alt_directional_2h` (paradigm 113) | 2026-05-20 | BROAD_FALSIFIED | ✓ HOD anchor 2h |
| `alt_session_boundary_NY_close_21UTC_anchored_directional_4h` (paradigm 157) | 2026-05-21 | BROAD_FALSIFIED Lesson #39B | ✓ session-boundary 21UTC anchor 4h |
| `alt_5m_close_to_open_overnight_gap_z_normalized_atr_session_anchor_directional_4h` | (5m gap × session anchor variant) | (separate hypothesis, related family) | ✓ session anchor adjacent |
| `pre_funding_window_divergence_5m_alt_240m` (paradigm 82) | 2026-05-15 | BROAD_FALSIFIED 4-quadrant | ✓ 8h funding boundary cycle anchor |

**Calendar/clock-anchor family count: 2-3 cumulative graveyards** in 7 days.

### 1.2 paradigm 113 graveyard verbatim advisory

> "**Temporal axis (hour-of-day) family advisory caution candidate**: ... future temporal-axis paradigm (e.g. day-of-week, week-of-month, session-boundary close variants) should be advisory cautioned ... Hour-of-day axis combined with NON-momentum signals (e.g., volume z, OI z, premium z at anchor hr) might retain hypothesis space but is paradigm-distinct."

paradigm 159 candidate matches **"day-of-week"** explicit advisory term + does NOT match "NON-momentum signal" exception path (per-sym in-sample fit is selection bias, not external signal).

### 1.3 DNA 4-dim audit paradigm 113 vs 159

| Dim | paradigm 113 | paradigm 159 | Strict change? |
|---|---|---|---|
| Statistic class | HOD anchor × |z| momentum stacking | per-sym fitted DOW/HOD effect | PARTIAL |
| Universe scope | 13 alts universe-wide | 14 syms per-sym fit | PARTIAL |
| Entry-side class | anchor hour + signed |z|≥1 | DOW or HOD position alone | STRICT |
| Mechanism alpha | time-zone liquidity overlap continuation | per-sym idiosyncratic calendar effect | STRICT |

**Lesson #62 strict count: 2/4** — boundary threshold ≥2 marginal 충족. 단 prior family graveyard 누적 (113 + 157 + 82) 강한 prior 신호에 의해 strict count marginal로는 dispatch 부적절.

### 1.4 paradigm 158 §6.55 next-action Option α inventory pre-audit claim 검증

**§6.55 claim**: "DNA 0/6 with any prior. Lesson #67 escape (per-sym fitted, not broadcast). 5/5 fresh (statistic + universe + entry + mechanism + hold all novel)"

**실제 audit**: DNA 4/6 PARTIAL+STRICT (statistic + universe partial / entry + mechanism strict). Lesson #62 strict count 2/4 (NOT 5/5 fresh as claimed).

**Stale 원인**: paradigm 158 §next-action 작성 시 `ls research_track/` slug duplicate scan 미실행. amendment 명시 hook 1번 missing → catch failure → R-0 dispatch 진입.

### 1.5 paradigm 156+157+158 §next-action 누적 stale 패턴

| Source | Recommended paradigm | Pre-audit claim | Inventory check (post-hoc) | Stale? |
|---|---|---|---|---|
| paradigm 155 §6.52 | (paradigm 156) | (not analyzed here) | — | — |
| paradigm 156 §6.53 | paradigm 157 NY close 21UTC | NEW archetype C | OK (session-boundary 1st instance) | OK |
| paradigm 157 §6.54 | paradigm 158 24h drawdown reversion | fresh | DNA 6/6 paradigm 117 duplicate | **STALE** (R-0 detect) |
| paradigm 158 §6.55 | paradigm 159 calendar anchor | DNA 0/6 fresh | DNA 4/6 paradigm 113 family member | **STALE** (this dogfood detect) |

**Stale streak: 2 consecutive §next-action** (paradigm 157→158, 158→159). Lesson #61 amendment 효능 검증: amendment 적용 안 했으면 두 케이스 모두 R-1 dispatch → compute waste 누적.

---

## 2. R-0 multi-axis prescreen (axis-by-axis, all relevant 표시)

| Axis | Verdict | Note |
|---|---|---|
| 1. Family-distinct strict 4-dim (Lesson #62) | **MARGINAL 2/4** | strict count ≥2 충족하나 boundary, prior family graveyard 누적 시 halt 우선 |
| 2. Substrate availability (Lesson #28) | ✓ PASS | 4h klines 12-col joblib + UTC timestamp natively |
| 3. Sample density (Lesson #11) | ✓ PASS | per-cell ~124 obs > 30 cutoff |
| 4. SNT 4-quadrant (Lesson #19) | (would have applied) | 4-quadrant sign-conditional 가능 |
| 5. Data window ratio (Lesson #30) | ✓ PASS | 2.25yr / 2.4yr = 93.75% |
| 6. Retiming reframe (Lesson #62 sub) | NOT retiming | NEW anchor class (per-sym fit) vs paradigm 113 univ-wide |
| 7. OUTCOME-LEVEL family proxy (Lesson #56) | **FAIL** | calendar-anchor family 113+157 prior graveyards = outcome-level family proxy 활성 |
| 8. Axis stacking (Lesson #21) | **FAIL** | per-sym in-sample fit = calendar × selection-bias axis stacking sub-class. 98 cells multiple testing |
| 9. Same-bar same-substrate (Lesson #58) | EXEMPT | single bar single substrate |
| 10. Mirror antipattern | N/A | sign-cond bilateral 가능 |
| 11. Lesson #67 candidate (cross-asset broadcast) | ESCAPE | per-sym fitted (no broadcast) |
| 12. **Lesson #68 candidate (session-boundary anchor × 4h × cross-asset fee-floor-bound)** | **2nd dogfood adjacency** | 4h hold + universe (per-sym fit but cross-asset universe), structurally adjacent |
| 13. Intraday incompatibility (memory) | EXEMPT | 4h hold |
| 14. **Lesson #61 amendment inventory check** | **FAIL** (this dogfood) | paradigm 113 calendar-anchor family member detected |
| 15. Magnitude-event family Tier 4 cross-ref | N/A | calendar axis not magnitude axis |

**Halt-eligible axes**: #1 (marginal) + #7 (FAIL outcome-level family proxy) + #8 (FAIL per-sym in-sample selection bias) + #12 (2nd dogfood adjacency) + #14 (FAIL Lesson #61 amendment).

**Cumulative halt signal**: 4 FAIL axes + 1 MARGINAL + 1 adjacency = **R-0 halt strong consensus**.

---

## 3. paradigm-architect spec amendment notes

### Lesson #61 amendment 1st dogfood post-confirmation SUCCESS

- amendment text: "§next-action 작성 시 1) slug duplicate search 2) DNA 4-dim audit 3) prior R-3+ verdict 확인 의무"
- amendment 효능 검증: paradigm 159 R-0 4 min halt vs paradigm 113 R-1 0.89 min execution + R-2 dispatch 회피 → wall-clock + compute 모두 절약
- amendment hook missing identified: paradigm 158 §next-action 작성 시 inventory pre-audit 적용 안 됨 (claim "DNA 0/6 fresh" 거짓). amendment 의무 hook 강화 권고 — agent 측 §next-action template에 slug duplicate `grep -iE` 실행 결과 명시 의무.

### Lesson #21 axis-stacking sub-class 확장 권고 (per-sym in-sample fit = axis stacking)

- 기존 Lesson #21 axis stacking dogfoods: paradigm 83 OI 5m k-means 5-feature + paradigm 113 hour × |z| momentum
- NEW sub-class candidate: **per-sym in-sample selection fit = "calendar axis × selection-bias axis" stacking**
- Multiple testing artifact: 14 syms × N cells (N=7 DOW or 6 HOD) max-of-N selection → uncorrected inflation factor √(2 log N) ≈ 1.97x (N=7) or 1.86x (N=6)
- paradigm 159는 dispatch 안 했으므로 dogfood 사례는 아니지만, **R-0 prescreen 시점에 detect** 가능한 amendment 권고: Lesson #21 sub-finding (per-sym in-sample fit antipattern)

### Lesson #68 candidate strengthening (2nd dogfood adjacency avoided)

- 1st dogfood: paradigm 157 NY close 21UTC 4h session-boundary
- 2nd dogfood candidate (avoided): paradigm 159 calendar anchor 4h
- amendment: Lesson #68 candidate definition을 "session-boundary OR clock-anchor × 4h × cross-asset" broader category로 확장 권고. paradigm 159 dispatch 시 2nd dogfood 즉시 발생 likely → halt가 정당

### Lesson #56 OUTCOME-LEVEL family proxy 11th instance

- Calendar-anchor family 2 cumulative graveyards (paradigm 113 + 157) in 2 days → outcome-level family proxy 활성
- paradigm 156 §6.53 / 157 §6.54 / 158 §6.55 all claimed "NEW archetype C/D fresh axis class" but Lesson #56 strict 적용 시 calendar/clock-anchor outcome-level은 paradigm 113이 first instance
- paradigm 159 halt = Lesson #56 11th instance reinforcement

---

## 4. Next paradigm 160 recommendation

| Option | Hypothesis | Inventory (Lesson #61 amend strict) | Family-distinct count | Recommendation |
|---|---|---|---|---|
| **β (⭐⭐⭐)** | `alt_cross_exchange_volume_share_rotation_directional_4h` | DNA 3/6 with paradigm 103 family (substrate inherited), volume share sub-axis untouched | 3/4 (statistic + mechanism + entry novel) | Cross-exchange volume share rotation is family-distinct sub-axis (paradigm 103 funding-spread / 147 OI lead-lag / 148 price lead-lag 모두 다른 mechanism class) |
| γ (⭐⭐) | `alt_post_listing_relisting_day7_drawdown_directional_24h` | Lifecycle family Tier 4 retired BUT relisting sub-mechanism untouched | 3/4 | Lifecycle Tier 4 caution applies |
| δ ✗ | `alt_pump_dump_event_PER_SYM_p99_short_continuation_4h` | DNA 5/6 with paradigm 158, magnitude-event family-retire ELIGIBLE | 2/4 boundary | **차단 권고** (family-retire eligible 무력화) |
| ε ✗ | `alt_calendar_anchor_NON_momentum_signal_DOW_4h` (paradigm 113 advisory NON-momentum exception path) | DNA 4/6 with paradigm 113 family, Lesson #68 candidate 2nd dogfood risk | 3/4 | Lesson #68 2nd dogfood risk 높음, 차단 권고 |

**1순위 권고**: Option β `alt_cross_exchange_volume_share_rotation_directional_4h`.

**Lesson #61 amendment 의무 strict 적용 권고**: paradigm 160 §next-action 작성 시
1. `ls research_track/ | grep -iE "<axis terms>"` 실행 결과 텍스트 첨부
2. DNA 4-dim audit table 명시
3. prior R-3+ verdict scan 명시
4. **family-retire eligibility cross-reference** (NEW) — calendar-anchor / magnitude-event / funding / cross-exchange / lifecycle 등 매핑 표

---

## 5. Files

- TASK: `backend/runs/research_track/alt_calendar_anchor_DOW_or_HOD_directional_4h/TASK.md`
- Graveyard: `backend/runs/research_track/graveyard__alt_calendar_anchor_DOW_or_HOD_directional_4h.md`
- R-1 script: NOT GENERATED (R-0 halt)
- R-1 metrics: NOT GENERATED (R-0 halt)
- Audit references:
  - `backend/runs/research_track/graveyard__intraday_hour_of_day_anchor_alt_directional_2h.md` (paradigm 113)
  - `backend/runs/research_track/graveyard__alt_session_boundary_NY_close_21UTC_anchored_directional_4h.md` (paradigm 157)

---

## 6. Cumulative campaign counters

- 누적 graveyards: 158 → **159** (substantive R-0 halt with counter increment, paradigm 97 candidate inventory-halt 처리 동일)
- R-5 LIVE: **10** (unchanged)
- Non-PASS streak: 29 → **30** (milestone)
- R-5 yield: 10/159 = **6.29%**
- Lessons: 34 confirmed + 20 candidates → **34 confirmed + 20 candidates** (Lesson #61 amendment 1st post-confirmation dogfood SUCCESS, Lesson #21 sub-class candidate per-sym in-sample selection bias, Lesson #68 candidate 2nd dogfood adjacency avoided, Lesson #56 11th instance)
- **Calendar/clock-anchor family**: 2 cumulative (paradigm 113 + 157) — advisory caution 강화, paradigm 159 inventory halt prevents escalation to 3rd graveyard
- D-Day 2026-06-03 D-13
