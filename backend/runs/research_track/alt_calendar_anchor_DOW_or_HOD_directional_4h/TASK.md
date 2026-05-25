# paradigm 159 R-0 inventory_check dogfood — `alt_calendar_anchor_DOW_or_HOD_directional_4h`

**Status**: `R0_HALT_BY_INVENTORY_DUPLICATE_LESSON_61_AMENDMENT_1ST_DOGFOOD_SUCCESS`
**Phase reached**: R-0 (R-1 NOT DISPATCHED)
**Dispatch attempt**: 2026-05-21 16:03 KST (paradigm 158 §6.55 next-action Option α explicit 1순위 recommendation)
**Wall clock**: 4 min (inventory audit only)

---

## TL;DR

paradigm 158 §6.55 next-action Option α 권고가 **자체적으로 DNA 0/6 fresh 주장** 했으나, Lesson #61 amendment 의무 inventory check (slug duplicate search 의무 사항) 실행 시 **paradigm 113 `intraday_hour_of_day_anchor_alt_directional_2h` (2026-05-20 R-1 BROAD_FALSIFIED) 발견**. paradigm 159 DNA는 4-dim audit에서 **2/4 strict + 2/4 partial 변경** (Lesson #62 ≥2 strict threshold 마진 충족), 그러나:

1. **paradigm 113 graveyard 명시적 advisory** ("Hour-of-day axis combined with NON-momentum signals might retain hypothesis space" — paradigm 159 per-sym in-sample fit은 NON-momentum signal이 아니라 selection bias)
2. **paradigm 157 (NY close 21UTC session anchor 4h) 2026-05-21 BROAD_FALSIFIED Lesson #39 sub-class B mechanism-inverted** + NEW **Lesson #68 candidate** "session-boundary anchor × 4h hold cross-asset = fee-floor-bound mechanism-inverted antipattern" 1st dogfood. paradigm 159 4h calendar-anchor은 Lesson #68 candidate 2nd dogfood 정확 위치
3. **per-sym in-sample DOW/HOD fit = Lesson #21 axis-stacking sub-class** (calendar axis × in-sample selection bias). 98 cells (14 syms × 7 DOW) 중 best 선택 후 aggregate = classic data-snooping
4. paradigm 158 §6.55 next-action 자체가 **Lesson #61 amendment의 stale recommendation 패턴 4번째 사례** (paradigm 156+157+158 모두 §next-action에서 prior calendar-anchor paradigm 113 인지 못함)

**Verdict**: R-0 halt. paradigm 113 graveyard advisory + paradigm 157 session-anchor falsification + Lesson #68 candidate 2nd dogfood adjacency가 cumulative 신호로 dispatch 부적절. Lesson #61 amendment **1st dogfood successful catch** — 정확히 amendment가 catch하려고 설계된 패턴 (next-action provenance audit으로 stale recommendation 차단).

---

## 1. Lesson #61 amendment INVENTORY CHECK (1st dogfood post-confirmation)

### 1.1 Slug duplicate search

```
$ ls backend/runs/research_track/ | grep -iE "calendar|dow|hod|anchor|session_bound|seasonal"
alt_5m_close_to_open_overnight_gap_z_normalized_atr_session_anchor_directional_4h
alt_session_boundary_NY_close_21UTC_anchored_directional_4h          # paradigm 157
graveyard__alt_session_boundary_NY_close_21UTC_anchored_directional_4h.md
graveyard__intraday_hour_of_day_anchor_alt_directional_2h.md          # **paradigm 113 — CRITICAL**
intraday_hour_of_day_anchor_alt_directional_2h
pre_funding_window_divergence_5m_alt_240m
```

**CRITICAL DETECTION**: paradigm 113 `intraday_hour_of_day_anchor_alt_directional_2h` (R-1 BROAD_FALSIFIED 2026-05-20).

paradigm 158 §6.55 next-action Option α inventory pre-audit claimed "**DNA 0/6 with any prior**" — **이 주장 거짓**. Lesson #61 amendment exact catch.

### 1.2 paradigm 113 graveyard verbatim advisory (relevant excerpt)

> "**Temporal axis (hour-of-day) family advisory caution candidate**: this is the FIRST hour-of-day paradigm test in 112 paradigm queue. Single instance does NOT warrant family retire. However, future temporal-axis paradigm (e.g. day-of-week, week-of-month, session-boundary close variants) should be advisory cautioned given (a) graveyard funding_cycle_8h family lesson 'funding × non-funding multi-axis (e.g., funding × vol regime × time-of-day) remains untested' was speculative, and now (b) hour-of-day × |z| momentum is directionally falsified (broad-uniform-negative). Hour-of-day axis combined with NON-momentum signals (e.g., volume z, OI z, premium z at anchor hr) might retain hypothesis space but is paradigm-distinct."

**paradigm 159 검토**:
- "day-of-week" → paradigm 159 explicit candidate (DOW 또는 HOD)
- "session-boundary close variants" → paradigm 157 (NY close 21UTC) 이미 BROAD_FALSIFIED
- "Hour-of-day axis combined with NON-momentum signals" → paradigm 159은 per-sym **in-sample fit** (NON-momentum signal 아닌 selection-bias artifact)

### 1.3 paradigm 113 vs paradigm 159 DNA 4-dim audit

| Dim | paradigm 113 (HOD × |z| 2h) | paradigm 159 (per-sym DOW/HOD 4h) | Strict change? |
|---|---|---|---|
| Statistic class | hour-of-day anchor × signed |z|≥1 conjunction | per-sym fitted DOW/HOD calendar-position effect | **PARTIAL** (both calendar-anchor; 159 drops |z| stacking, adds per-sym fit) |
| Universe scope | 13 alts universe-wide | 14 syms (BTC + 13 alts) per-sym idiosyncratic fit | **PARTIAL** (essentially same universe, fit method differs) |
| Entry-side class | anchor hour {00,07,13,21} + signed |z|≥1 conjunction | DOW or HOD calendar position alone (no magnitude conjunction) | **STRICT** (drops magnitude axis, replaces with selection) |
| Mechanism alpha | time-zone liquidity overlap continuation | per-sym fitted directional effect (idiosyncratic calendar) | **STRICT** (universe-wide → per-sym idiosyncratic) |

**Lesson #62 strict count: 2/4 STRICT + 2/4 PARTIAL = boundary threshold ≥2 strict 마진 충족**.

### 1.4 paradigm 157 + 113 cumulative calendar-anchor family count

| Paradigm | Date | Verdict | Family |
|---|---|---|---|
| 113 | 2026-05-20 | BROAD_FALSIFIED Lesson #21 + #39A | hour-of-day × |z| momentum 2h |
| 157 | 2026-05-21 | BROAD_FALSIFIED Lesson #39B mechanism-inverted | session-boundary 21UTC NY close 4h |

**2 graveyards in 2 consecutive days** in calendar/clock-anchor axis class.

### 1.5 Lesson #68 candidate adjacency

paradigm 157 graveyard:
> "**NEW Lesson #68 candidate (1st dogfood)**: 'Session-boundary anchor × 4h hold cross-asset = fee-floor-bound mechanism-inverted antipattern'. Required for CONFIRMED 자격: 1+ more dogfood (e.g., London close 16 UTC anchor, Asia open 00 UTC anchor with similar 4h × cross-asset structure)"

**paradigm 159는 Lesson #68 candidate 2nd dogfood 정확 위치**:
- ✓ 4h hold (same)
- ✓ cross-asset universe (14 alts same)
- ✓ calendar/clock anchor (DOW + HOD 모두 clock-anchor sub-class)
- ✗ per-sym fit은 universe-wide anchor가 아니지만, structural global clock 자체가 동일 family

paradigm 159 R-1 BROAD_FALSIFIED 시 Lesson #68 candidate 2nd dogfood → 3 dogfoods CONFIRMED 자격 1 step 부족 (London close 별도 시도 필요). **단 paradigm 159 dispatch 자체가 family adjacency 인지 미흡 → halt 권고**.

### 1.6 prior R-3+ verdict scan (Lesson #61 amendment 3rd checklist item)

paradigm 113 / 157 모두 R-1 only graveyards, R-3+ 도달 paradigm 부재 in this family.

paradigm 22 funding 8h boundary anchor R-5 LIVE = cycle-boundary cash-flow event (forced funding payment) ≠ calendar/clock anchor mechanism. cross-reference 면제.

---

## 2. Lesson #21 axis-stacking sub-class concern (per-sym in-sample fit)

### 2.1 Hypothesis structure analysis

paradigm 159 mechanism: per-sym 각 sym에서 가장 강한 calendar effect (DOW 또는 HOD) fit → directional bias trade.

**fit dimension**: 14 syms × 7 DOW = 98 candidate cells, 또는 14 × 6 HOD = 84 cells.

In-sample 70:30 split:
- training 70% (1.575yr) → best per-sym DOW (or HOD) 추출
- test 30% (0.675yr) → validate

**문제점**:
1. **Per-sym selection multiple testing**: 7 DOW or 6 HOD에서 best 선택 = 7-fold multiple comparison per sym. uncorrected best |t| inflation factor √(2 log 7) ≈ 1.97x at 7 cells (extreme value statistics for max of i.i.d. normals).
2. **Aggregate-of-bests bias**: 14 syms × best-of-7 = 14 independent best-of-7 statistics aggregated. Sample-cumulative bias inflates aggregate t by similar factor.
3. **Lesson #21 anti-synthesis dogfood**: paradigm 113 graveyard 명시 "Joint is WORSE than either axis alone. Stacking the two NULL axes compounds fee drag without synthesizing alpha." paradigm 159은 **calendar axis × in-sample selection axis** = 동일 anti-synthesis 패턴 (each axis is weak, joint creates spurious selection artifact)

### 2.2 Universe-wide alternative

Hypothesis 변경 가능 path: 14 syms × 7 DOW cells × 4h holds **universe-wide aggregate** (NOT per-sym selection). 단 paradigm 157 NY close 21UTC = universe-wide calendar anchor at single hour, BROAD_FALSIFIED 4h × cross-asset에서 fee-floor-bound. paradigm 159 universe-wide DOW/HOD는 paradigm 157과 family-distinct strict count 1-2/4 미달 (Lesson #62 threshold 부족).

**결론**: paradigm 159는 dispatch 가능한 변형이 두 가지 — (a) per-sym fit = Lesson #21 selection bias, (b) universe-wide aggregate = paradigm 157 family-overlap. 양쪽 모두 inventory check halt 정당화.

---

## 3. paradigm 156+157+158 §next-action stale recommendation 패턴 (Lesson #61 amendment 4th cumulative dogfood)

| Paradigm §next-action | 권고 paradigm | inventory pre-audit claim | actual prior | stale 여부 |
|---|---|---|---|---|
| §6.53 paradigm 156 | (paradigm 157 alt_session_boundary_NY_close_21UTC) | "NEW archetype C" | (NY close 4h anchor 새로움 PASS) | OK |
| §6.54 paradigm 157 | (paradigm 158 alt_extreme_24h_drawdown_24h_reversion_long) | "fresh" | paradigm 117 DNA 6/6 duplicate | **STALE** (R-0 inventory HALT detect) |
| §6.55 paradigm 158 | (paradigm 159 alt_calendar_anchor_DOW_or_HOD_directional_4h) | "DNA 0/6 with any prior" | paradigm 113 calendar-anchor family member | **STALE** (R-0 inventory HALT detect, this dogfood) |

**Lesson #61 amendment 4번째 누적 dogfood**:
- 1-3rd: paradigm 150/156/157 §next-action provenance audit ratifications
- **4th (paradigm 158→159)**: explicit inventory duplicate catch — paradigm 113 calendar-anchor family adjacent missed

**Lesson #61 amendment 효능 입증**: amendment 적용 안 했으면 paradigm 159 R-1 dispatch → likely BROAD_FALSIFIED (paradigm 113 + 157 cumulative 강한 prior) + Lesson #21 axis-stacking 4th dogfood + Lesson #68 candidate 2nd dogfood. amendment 적용으로 wall-clock 4 min에 halt, compute waste 차단.

---

## 4. Verdict & next-action

### Verdict
- `R0_HALT_BY_INVENTORY_DUPLICATE_LESSON_61_AMENDMENT_1ST_DOGFOOD_SUCCESS`
- R-1 NOT DISPATCHED
- counter 159 사용 (R-0 substantive halt, paradigm 97 candidate 분류와 동일 처리: counter 증가 + graveyard 등재)

### Next paradigm 160 권고 (Lesson #61 amendment 의무 적용 strict)

paradigm 158 §6.55 후보 option β/γ/δ 재평가:

| Option | Hypothesis | Inventory pre-audit (Lesson #61 amend strict) | Family-distinct strict count | Note |
|---|---|---|---|---|
| **β (⭐⭐⭐ 권고)** | `alt_cross_exchange_volume_share_rotation_directional_4h` (Binance vs Bybit volume share shift > p90 → directional) | DNA 3/6 with paradigm 103 cross-exchange family (substrate inherited, R-1 BROAD_FALSIFIED_FEE_FLOOR). Cross-exchange OI/funding family Tier 4 (paradigm 147 INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION). **Volume share variant family-distinct strict NOT yet tested** (paradigm 103 was funding-spread, paradigm 147+148 were OI lead-lag + price lead-lag) | 3/4 (statistic novel volume share rotation, mechanism novel migration flow, entry novel relative shift, universe NOT novel) | Bybit V5 + Binance volume substrate verified. Cross-exchange family caution applies but volume share is sub-axis untouched in 103/147/148 |
| γ | `alt_post_listing_relisting_day7_drawdown_directional_24h` (newly relisted token 7d post-relist drawdown filter) | Lifecycle family (paradigm 87/88/89/90) Tier 4 retired. Relisting sub-mechanism is family-distinct (NOT delisting/listing/unlock/stablecoin). DNA 4/6 inherits lifecycle substrate | 3/4 (mechanism novel + entry novel + universe novel — but lifecycle family caution) | Untested sub-mechanism but lifecycle Tier 4 caution applies |
| δ | `alt_pump_dump_event_PER_SYM_p99_short_continuation_4h` (extreme tail PUMP at p99 + 4h hold SHORT mean-reversion) | DNA 5/6 with paradigm 158 (same statistic, opposite direction, opposite hold). **Magnitude-event family-retire ELIGIBLE** (paradigm 117+158) → δ 차단 강 권고 | 2/4 boundary (extreme tail direction novel only) | Family-retire eligibility 직전 sub-axis, dispatch 비권장 |
| ε (NEW from this halt) | `alt_calendar_anchor_DOW_UNIVERSAL_NON_MOMENTUM_signal_directional_4h` (paradigm 113 graveyard advisory 명시 NON-momentum signal × DOW/HOD conjunction — e.g., volume z, OI z at DOW anchor) | DNA 4/6 with paradigm 113 (calendar axis shared, NON-momentum signal exception path explicitly opened by 113 graveyard) | 3/4 (statistic novel via NON-momentum signal, entry novel, mechanism novel) | paradigm 113 graveyard 명시 exception path. Lesson #68 candidate 2nd dogfood risk 여전 존재 |

**메타 권고 1순위**: **Option β** — `alt_cross_exchange_volume_share_rotation_directional_4h`. Reasoning:
1. **Family-distinct strict 3/4**: 가장 깨끗한 path (volume share rotation은 paradigm 103 funding-spread / 147 OI lead-lag / 148 price lead-lag 어디에도 측정 안 됨)
2. **Inventory check PASS**: slug duplicate 부재, DNA 3/6 with cross-exchange family but volume share is family-distinct sub-axis
3. **Substrate**: Bybit V5 7/7 deep-syms × 2.5yr 영구 자산 (paradigm 103에서 검증됨) + Binance 4h klines
4. **Lesson #56 OUTCOME-LEVEL caution**: cross-exchange family 3 graveyards (103/147/148) 누적이지만 sub-axis volume share **outcome-level family-distinct**: 가설 mechanism은 "exchange volume migration flow" (paradigm 103+147+148 all "lead-lag delay" or "funding/OI cross-arbitrage" — different mechanism class)

**메타 권고 2순위**: Option γ — relisting day7 (lifecycle family-distinct sub-mechanism, untouched).

**Option δ 차단 권고 strict**: magnitude-event family-retire eligible (paradigm 117+158) — formal retire 가능 단계. δ dispatch 시 family-retire 무력화 위험.

### Lesson #61 amendment 의무 strict 적용 (paradigm 160 §next-action 작성 시)
1. slug duplicate search (자동) — `ls .../research_track/ | grep -iE "<axis terms>"`
2. DNA 4-dim audit (manual) — statistic/universe/entry/mechanism vs ALL prior R-1+ paradigms
3. prior R-3+ verdict 명시적 audit (manual)
4. **family-retire eligibility cross-reference** (NEW from this halt) — magnitude/funding/cross-exchange/lifecycle/calendar-anchor 등 axis class 사전 매핑
5. Lesson #62 strict count ≥ 3/4 권고 (≥2 marginal 허용했으나 boundary case에서 prior-family graveyard 누적 시 halt 우선)

---

## 5. Campaign 진행 상태 갱신 (2026-05-21 16:03 KST paradigm 159 R-0 halt 후)

- 누적 graveyards: 158 → **159** (substantive R-0 halt counter increment — paradigm 97 candidate inventory-halt 분류와 동일 처리)
- R-5 LIVE: **10** (unchanged)
- Non-PASS streak: 29 → **30** (R-0 halts streak에 포함, milestone)
- R-5 yield: 10/159 = **6.29%**
- Lessons: 34 confirmed + 20 candidates → **34 confirmed + 20 candidates** (Lesson #61 amendment 4th cumulative dogfood 1st post-confirmation SUCCESS, Lesson #21 axis-stacking sub-class per-sym selection bias xref, Lesson #68 candidate 2nd dogfood adjacency avoided)
- Funding axis Tier 4: 11 cumulative (unchanged)
- Magnitude-event family: 2 cumulative (paradigm 117 R-3 + 158 R-1) — **family-retire ELIGIBLE** (paradigm 158 §6.55 ratified, formal retire pending Q3 batch ratification)
- **Calendar/clock-anchor family**: 2 cumulative (paradigm 113 + 157) — paradigm 159 inventory halt prevents 3rd graveyard. family-retire NOT yet eligible (≥2 graveyards already, advisory caution 강화)
- D-Day 2026-06-03 D-13
