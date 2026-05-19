# Graveyard — paradigm 100 `dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_neg_long_20d`

**Phase**: R-0 prescreen (HALT_BEFORE_R1)
**Verdict**: `SAMPLE_INSUFFICIENT_TEMPORAL_CONCENTRATION`
**Date**: 2026-05-19
**Dispatch**: ad-hoc R-1 (paradigm-architect agent invocation, Day 7 baseline 우선 모드 binding 유지)

## Hypothesis

KR equity EARNINGS_GUIDANCE_AMEND (가이던스 ±30% 변경) NEG surprise direction × LONG mean-reversion, hold sweep 5d/10d/20d/30d. Paradigm 93 B mirror neg×LONG side discovery (5d hold gross +123.84bp / prob_pos 94.2% / sigex +0.54 sub-grade) 정식화.

## Family-distinct 검증 — PASSED

[[feedback_family_retire_kr_post_earnings.md]]는 KR equity post-earnings/guidance **directional momentum** family를 Tier 4 retire. **Mean-reversion direction**은 명시적으로 family-distinct 허용 첫 항목. 본 hypothesis는 정확히 mean-reversion direction이므로 retire 외 valid path.

## Halt 사유 — Lesson #26 amendment auto-FAIL precondition

Paradigm 93의 `h2_guidance_events_ret_cache.joblib` (1,106 events / 2.4yr) 캐시 audit 결과:

| Track | Cell | n total | Q1 cluster | n_measurable_quarters |
|---|---|---|---|---|
| Fundamental (op_growth ≤ -30%) | NEG | 327 | 2024Q1=134 / 2025Q1=120 / 2026Q1=73 (100.0%) | **3** |
| Observable (pre_ret_5d ≤ -3%) | NEG | 259 | 2024Q1=75 / 2025Q1=88 / 2026Q1=95 (99.6%); 2025Q2=1 sub-cell | **3** |
| All events | both | 1106 | 2024Q1=350 / 2025Q1=377 / 2026Q1=374 (99.5%) | **3** |

[[paradigm_87 small-sample Concentration Gate blind spot]] / Lesson #26 amendment은 `n_measurable_quarters >= 4` 의무. 본 substrate는 **3 measurable quarters** = auto-FAIL precondition met.

## 구조적 진단

EARNINGS_GUIDANCE_AMEND은 KR 회계연도 종료 후 annual-results disclosure cycle에 filing 집중 (전년도 잠정실적 직전/병행). 2.4yr 윈도우는 정확히 3 Q1 (2024Q1 / 2025Q1 / 2026Q1)만 admit. **Hold horizon 5d → 10d → 20d → 30d 확장은 temporal independence를 추가하지 않는다** — events는 여전히 Q1-clustered이고 hold만 길어진다.

Paradigm 93의 5-fold TS-CV가 이미 `fold_count=1`로 collapse 했었다 ("fold_1(2024Q1+2025Q1+2026Q1)"). 본 paradigm 100은 같은 substrate에서 walk-forward 구조적 불가.

## Paradigm 93 baseline 비교 (5d hold)

| Cell | n | gross_bp | net_bp | t_stat | sigex | perm_p | ci_lower_bp |
|---|---|---|---|---|---|---|---|
| FUND B_mirror neg×LONG | 327 | +123.84 | +73.84 | 1.55 | **+0.54** | 0.293 | **-14.88** |
| OBS B_mirror neg×LONG | 259 | +159.66 | +109.66 | 1.97 | **+1.10** | 0.125 | **+9.24** |

5d hold에서 두 트랙 모두 sub-grade (sigex < 2.0). 20d hold에서 sigex 증폭 가설이 사실이라 하더라도 Concentration Gate (n_measurable_quarters=3) 자체가 R-1 통과를 막는다.

## Life-changing 4-dim eyeball

- nominal: 327 neg events / 2.4yr = 136/yr
- but Q1-cluster: 99.5% Q1 → ~109/Q1, ~0/year off-Q1
- 20d hold overlap: ~3-5 independent positions/Q1 × 3Q1 = **9-15 trades/yr effective**
- trades/yr ≥ 12 threshold: **marginal** (overlap policy dependent)

신호가 강했어도 4-dim trades/yr borderline.

## Lesson grid 통과 / 실패

| # | Lesson | Status |
|---|---|---|
| #11 sample density | per-cell 327 events ≫ 30 cutoff | ✅ PASS |
| #16 Concentration Gate | per-symbol top frac 0.034 < 0.10 | ✅ PASS (paradigm 93 검증) |
| #19 Symmetric Negative Test | 4-quadrant 인프라 paradigm 93 코드 가용 | ✅ ready |
| #20 narrow-scope 4-cond | N/A (4-cond 적용 사전 단계) | — |
| **#26 small-sample Concentration Gate amendment** | n_measurable_quarters=3<4 | ❌ **AUTO_FAIL precondition** |
| #27 entry-side immediate/delayed | information shock paradigm (forced-flow 아님), N/A | ✅ pass (correct classification) |
| #28 substrate availability | DART 공시 history 가용 | ✅ PASS |
| #29 cross-proxy strict | paradigm 93에서 양 트랙 인프라 가용 | ready but blocked by #26 |
| #30 short-data verdict | 2.4yr full-window cache 사용, ratio 1.0 | ✅ pass |
| Family retire | mean-reversion direction family-distinct | ✅ PASS |
| NARROW_SCOPE_LIFE_CHANGING_FAIL | 4-dim trades/yr marginal eyeball, formal 측정 사전 단계 | — |

## 영구 인프라 영향 — 없음 (재사용)

본 halt는 **새 백필/연산 0** — paradigm 93 영구 자산 (`h2_guidance_events_ret_cache.joblib` + DART universe + ohlcv_cache + fnltt_cache) 직접 audit만으로 decision 도출. 영구 자산 가치 재확인.

## DNA inventory

| Dim | paradigm 92 (H1) | paradigm 93 (H2) | paradigm 100 (this) |
|---|---|---|---|
| Substrate | DART 잠정실적 | DART 가이던스 ±30% | DART 가이던스 ±30% |
| Statistic | gap_proxy / YoY OP | YoY OP / pre_ret_5d | YoY OP / pre_ret_5d |
| Universe | KOSPI200+KOSDAQ150 | same | same |
| Mechanism | directional momentum LONG | directional momentum LONG | **mean-reversion LONG (distinct)** |
| Sample | 156 | 1106 | (subset 327/259) |
| Direction | LONG | LONG | **LONG (but post-NEG = mean-reversion)** |

5/6 일치, direction axis distinct (mechanism interpretation distinct). Family-distinct PASS.

## 권고

1. **EARNINGS_GUIDANCE_AMEND 가이던스-기반 mean-reversion paradigm 영구 폐기**. Same-substrate hold-extension/threshold-tweak도 동일 temporal-concentration defect 적용.
2. Family-distinct 후속 가능성:
   - **분기보고서 (quarterly reports)** 가용 시 4x/yr distribution → n_measurable_quarters 충족 가능 (R-0 prescreen 시 distribution 사전 측정 의무)
   - **단일판매·공급계약체결 contracts** 등 year-round filing 외부 trigger
   - **비-directional event volatility paradigm** (paradigm 92/93/100 모두 directional → 비-directional은 family-distinct)
3. Track 3 DART는 universe + fnltt + OHLCV cache 영구 자산으로 유지, 위 후속 후보 검증 시 즉시 활용 가능.
4. Lesson #26 amendment는 paradigm 87 (small-sample Concentration Gate blind spot)에 이어 **dogfood 3번째 성공** (87 R-2 적발 → 88+90 R-0 prescreen 차단 → 100 R-0 prescreen 차단). Q3 lesson index 확신 강화.

## 산출물 경로

- Metrics: `/home/hcpark/antigravity/backend/runs/research_track/dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_neg_long_20d/r1_prescreen_halt_metrics.json`
- Graveyard report: `/home/hcpark/antigravity/backend/runs/research_track/graveyard__dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_neg_long_20d.md` (this file)
- paradigm_index: `dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_neg_long_20d` → phase=`graveyard`
