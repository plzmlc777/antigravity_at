# Graveyard — paradigm-133-candidate `dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_long_60d_extended_hold`

**Phase**: R-0 inventory prescreen (HALT_BEFORE_R1)
**Verdict**: `INVENTORY_HALT_FAMILY_DISTINCT_FAIL_LESSON_26_AUTO_FAIL_PRECONDITION`
**Date**: 2026-05-21 10:30 KST
**Counter status**: NOT incremented (inventory-halt sub-class; paradigm 133 counter remains reserved for next valid dispatch — same precedent as paradigm 97 candidate funding_dispersion inventory-halt)
**Dispatch context**: ad-hoc R-1, continuous-parallel policy, 5-streak threshold position after paradigm 129/130/131/132

## Hypothesis

EARNINGS_GUIDANCE_AMEND (가이던스 ±30% 변경, paradigm 92/93 substrate) + observable filter pre_ret_5d < -3% × LONG mean-reversion, hold=**60d** (extension from paradigm 100 5d/10d/20d/30d sweep). 4-quadrant SNT: A focus oversold MR, A mirror oversold continuation, B focus overbought MR (SHORT), B mirror overbought continuation. Paradigm 93 B mirror neg×LONG side discovery (5d gross +123.84bp / prob_pos 94.2% / sigex +0.54 sub-grade) 60d hold extension 본격 검증 시도.

## Family-distinct 권한 검증

| Check | Status |
|---|---|
| KR equity post-earnings/guidance directional momentum family Tier 4 retire | ✅ PASSED (mean-reversion direction explicitly allowed) |
| **Lesson #44 amendment 15th xref dogfood** | ❌ **FAILED** (paradigm 100 graveyard 6/6 DNA overlap) |

## Halt 사유 — 3가지 독립 blockers (any one sufficient)

### Blocker 1: Lesson #44 amendment 15th xref dogfood (PRIMARY)

`backend/runs/research_track/graveyard__dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_neg_long_20d.md` (paradigm 100, 2026-05-19 graveyard) DNA overlap analysis:

| Dimension | paradigm 100 (graveyard) | paradigm 133 candidate | Distinct? |
|---|---|---|---|
| Trigger | EARNINGS_GUIDANCE_AMEND ±30% | EARNINGS_GUIDANCE_AMEND ±30% | ❌ identical |
| Direction | LONG mean-reversion | LONG mean-reversion | ❌ identical |
| Filter | pre_ret_5d ≤ -3% (observable track) | pre_ret_5d < -3% | ❌ subset/equivalent |
| Universe | KOSPI200+KOSDAQ150 | same | ❌ identical |
| Substrate | DART AMEND events 2.4yr cache | same | ❌ identical |
| Hold | 5d/10d/20d/30d sweep | 60d extension | ⚠ partial (hold extension only) |

**Distinct proof attempt via 60d hold extension — REFUTED by paradigm 100 graveyard explicit prohibition**:

> "Hold horizon 5d → 10d → 20d → 30d 확장은 temporal independence를 추가하지 않는다 — events는 여전히 Q1-clustered이고 hold만 길어진다" (paradigm 100 §30)

> "EARNINGS_GUIDANCE_AMEND 가이던스-기반 mean-reversion paradigm 영구 폐기. **Same-substrate hold-extension/threshold-tweak도 동일 temporal-concentration defect 적용**" (paradigm 100 §87)

paradigm 100 graveyard가 hold-extension class를 명시적으로 사전 차단. 60d extension은 5d/10d/20d/30d sweep의 단순 연장이며 paradigm 100 §87 prohibition 정확 적용 대상.

### Blocker 2: Lesson #26 amendment auto-FAIL precondition (RE-INHERITED)

| Item | Value |
|---|---|
| substrate cache | `backend/runs/dart_track/h2_guidance_events_ret_cache.joblib` (paradigm 93/100 공유 영구 자산) |
| n_measurable_quarters (observable track pre_ret_5d<-3%) | **3** |
| Lesson #26 amendment threshold | n_measurable_quarters ≥ 4 |
| 60d hold extension의 quarter count delta | **0** |
| Verdict | AUTO_FAIL precondition reaffirmed |

Quarterly distribution recap (paradigm 100 §23 inherit):
- 2024Q1: 75
- 2025Q1: 88
- 2025Q2: 1 (sub-cell)
- 2026Q1: 95
- Q1 concentration: 99.6%

60d hold은 quarter count를 추가하지 않는다 — 같은 3 Q1 substrate.

### Blocker 3: Life-changing 4-dim 60d hold 결정적 악화

| Metric | paradigm 100 (5d/20d) | paradigm 133 (60d) |
|---|---|---|
| n_events_observable_neg | 259 | 259 |
| nominal trades/yr (2.4yr) | 108 | 108 |
| Q1 concentration | 99.6% | 99.6% |
| trading_days/Q1 | 60 | 60 |
| hold/Q1 ratio | 8.3%-33% | **100% (full overlap)** |
| effective independent positions/Q1 | 3-5 | **1-2** |
| **effective trades/yr** | 9-15 (marginal) | **3-6 (decisive FAIL)** |
| trades/yr ≥ 12 threshold | borderline | **categorical FAIL** |

60d hold가 paradigm 100 marginal 상황을 결정적 fail로 악화. life-changing 4-dim categorical 차단.

## paradigm 93/100 baseline 비교 (왜 60d hope가 무효한가)

paradigm 100 graveyard §40-41이 이미 사전 차단 논리 제시:

> "5d hold에서 두 트랙 모두 sub-grade (sigex < 2.0). 20d hold에서 sigex 증폭 가설이 사실이라 하더라도 Concentration Gate (n_measurable_quarters=3) 자체가 R-1 통과를 막는다."

60d hold도 동일 — sigex 증폭이 일어나더라도 Concentration Gate 통과 불가, R-2 walk-forward 불가, life-changing 4-dim 불가.

## Lesson grid

| # | Lesson | Status |
|---|---|---|
| #11 sample density | per-cell 259 events ≫ 30 cutoff | ✅ would PASS (blocked upstream) |
| #19 SNT 4-quadrant | infrastructure paradigm 93 code 가용 | ✅ ready but blocked |
| #21 individual-vs-joint sigex | would measure AMEND alone vs AMEND+filter at R-1 | N/A blocked |
| **#26 amendment small-sample CG** | n_measurable_quarters=3<4 | ❌ **AUTO_FAIL** |
| #27 entry-side immediate/delayed | information shock paradigm | ✅ pass classification |
| #28 substrate availability | DART AMEND filings 2.4yr cache 가용 | ✅ PASS |
| #29 cross-proxy strict | paradigm 93 인프라 가용 | ✅ ready but blocked |
| #30 short-data verdict | cache full-window 1.0 ratio | ✅ PASS |
| #40 threshold attainability | pre_ret_5d -3% empirical attainable | ✅ PASS (paradigm 93 검증) |
| **#44 amendment 15th xref** | paradigm 100 6/6 DNA overlap, distinct REFUTED | ❌ **FAILED (15th dogfood)** |
| #46 REFINEMENT 8th stratified n=50×4q + sign-flip | N/A blocked (would be 8th dogfood opportunity) | — |
| NARROW_SCOPE_LIFE_CHANGING_FAIL | 60d hold categorical 3-6 trades/yr | ❌ FAIL (eyeball) |
| Family retire | mean-reversion direction family-distinct allowed | ✅ PASS |

## 영구 인프라 영향 — 없음 (재사용만)

본 halt는 **새 백필/연산 0** — paradigm 93/100 영구 자산 (`h2_guidance_events_ret_cache.joblib` + DART universe + ohlcv_cache + fnltt_cache) audit + paradigm 100 graveyard xref만으로 decision 도출. inventory-halt 카테고리.

## Counter 결정

- **Counter NOT incremented** — paradigm 133 카운터는 reserved 상태 유지
- 정밀 precedent: paradigm 97 candidate funding_term_structure_cross_sym_dispersion R-0 inventory halt (counter 미증가, batch P1에서 paradigm 97/98/99 재할당)
- 4-streak non-PASS 또한 유지 (129/130/131/132) — inventory-halt가 streak을 연장하지 않음 (paradigm 97 precedent)

## DNA inventory 표 (paradigm 92 → 93 → 100 → this)

| Dim | p92 (H1) | p93 (H2) | p100 (mean-rev 5-30d) | candidate (mean-rev 60d) |
|---|---|---|---|---|
| Substrate | DART 잠정실적 | DART AMEND ±30% | DART AMEND ±30% | DART AMEND ±30% |
| Statistic | gap_proxy / YoY OP | YoY OP / pre_ret_5d | YoY OP / pre_ret_5d | YoY OP / pre_ret_5d |
| Universe | KOSPI200+KOSDAQ150 | same | same | same |
| Mechanism | directional momentum LONG | directional momentum LONG | mean-reversion LONG | mean-reversion LONG |
| Hold | 5d | 5d | 5d/10d/20d/30d | 60d |
| Distinct vs p100 | — | — | (base) | hold extension only — explicit prohibited by §87 |

## 권고

1. **EARNINGS_GUIDANCE_AMEND-based mean-reversion paradigm 영구 폐기 재확인** (paradigm 100 §87 강화).
2. Same-substrate hold-extension/threshold-tweak/filter-variant 모두 동일 차단 적용. 향후 ad-hoc dispatch 시 paradigm 100 graveyard cross-reference 의무.
3. Family-distinct 후속 가능성 (paradigm 100 §88 권고 유지):
   - **분기보고서 quarterly reports** 4x/yr distribution (Q1+Q2+Q3+Q4) → n_measurable_quarters 4+ 가능. Mean-reversion direction family-distinct exception 또는 non-directional event vol paradigm 필요.
   - **단일판매·공급계약체결 contracts** year-round filing — **CAUTION**: `dart_supply_contract_announce_kr_equity_vol_expansion_5d` 이미 graveyard 존재. 변형 dispatch 시 Lesson #44 16th xref 의무.
4. **continuous-parallel policy 권고: paradigm 133 counter는 binance side 또는 non-DART universe candidate에 할당**. DART KR side는 paradigm 100 + 132 + this 3-deep deferred (family-fatigue 회피).
5. Lesson #44 amendment 15th dogfood 정식 성공 — 5/6 DNA + hold-extension explicit prohibition class detection 첫 사례. 4-dim DNA + explicit class prohibition cross-check 패턴 확립.

## 산출물 경로

- Prescreen metrics: `/home/hcpark/antigravity/backend/runs/research_track/dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_long_60d_extended_hold/r0_prescreen.json`
- Graveyard report: `/home/hcpark/antigravity/backend/runs/research_track/graveyard__dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_long_60d_extended_hold.md` (this file)
- Cross-reference: paradigm 100 graveyard `backend/runs/research_track/graveyard__dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_neg_long_20d.md`
- paradigm_index: NOT registered (inventory-halt, counter reserved)
