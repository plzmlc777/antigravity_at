# Graveyard — paradigm 162 alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h

**Verdict**: `BROAD_FALSIFIED_DIRECTION_INVERTED`
**Phase**: R-1
**Date**: 2026-05-21 21:06 KST
**Wall clock**: 0.02 min
**Counter**: 162 (substantive R-1 increment post lifecycle_pump_decay R-5 promotion)

## Hypothesis

Per-symbol 24h rolling-high cross-up event를 anchor로 사용, anchor cross-up
직후 4h hold SHORT reversal mean-reversion (resistance-level reversal alpha).

A_focus: 24h new high cross-up × SHORT 4h hold (primary)

## R-0 inventory audit summary (Lesson #61 amendment 4th post-confirmation dogfood)

| Audit dim | Result |
|---|---|
| Slug grep | paradigm 117 + 158 magnitude-event family detected |
| DNA vs 117 strict count | 2/5 (mechanism direction + hold) BOUNDARY_PASS |
| DNA vs 158 strict count | 3/5 (entry-side anchor + mechanism + hold) STRICT_FAMILY_DISTINCT |
| Lesson #56 family proxy risk | HIGH (magnitude-event family 13 instances) |
| paradigm 158 A_mirror prior | 24h hold sub-fee (-1.98bp p90 / -23.63bp p95) |
| paradigm 117 R-1 4h B_same prior | gross +35.55bp sigex +1.87 sub-fee (3-gate FAIL) |
| Lesson #11 sample density | PASS (574.7/quarter ≫ 30 cutoff) |
| Lesson #28 substrate | PASS (12-col 4h joblib 13 alts) |
| Lesson #30 data window | PASS (93.75%) |
| Lesson #67/#68/#21 ESCAPE | PASS (per-sym anchor, no broadcast/session/stack) |

R-1 dispatch authorized: STRICT_FAMILY_DISTINCT vs paradigm 158 + 4h subspace
exploration informational value (paradigm 158 미탐색 timescale).

## Result — 4-quadrant SNT @ primary hold 4h

| Quadrant | n | gross bp | net bp | sigex | obs_t | ci [bp] | perm_p | q_pos | syms_ci_pos | 3-gate | Conc | edge % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A_focus high_anchor × SHORT** (primary) | **5172** | **-4.39** | **-12.39** | **-1.70** | **-4.44** | [-17.9, -7.4] | 0.043 | **0/10** | **0/13** | False | False | **-0.12** |
| A_mirror high_anchor × LONG | 5172 | +4.39 | -3.61 | +1.72 | -1.30 | [-8.6, +1.9] | 0.962 | 3/10 | 0/13 | False | False | -0.04 |
| B_same low_anchor × LONG | 5254 | -2.22 | -10.22 | -0.52 | -3.61 | [-16.1, -4.7] | 0.290 | 2/10 | 0/13 | False | False | -0.10 |
| B_mirror low_anchor × SHORT | 5254 | +2.22 | -5.78 | +0.66 | -2.04 | [-11.3, +0.1] | 0.763 | 3/10 | 0/13 | False | False | -0.06 |

**A_focus broad-falsified DIRECTION_INVERTED**: 5172 events, obs_t -4.44 deep negative,
q_pos 0/10 (모든 quarter 음수), syms_ci_pos 0/13. 24h new high → 4h SHORT reversal
hypothesis **directionally inverted** — 4h forward window는 약한 UP continuation
(A_mirror gross +4.39bp) but sub-fee.

## Hold sweep on A_focus_high_anchor_SHORT

| Hold | n | gross bp | net bp | sigex | obs_t | ci [bp] |
|---|---|---|---|---|---|---|
| 4h primary | 5172 | **-4.39** | -12.39 | -1.70 | -4.44 | [-17.9, -7.4] |
| 12h | 5168 | -2.92 | -10.92 | -0.89 | -2.29 | [-20.2, -1.4] |
| 24h | 5167 | +9.01 | +1.01 | +0.93 | +0.15 | [-12.6, +14.7] |

SHORT 방향 4h-12h consistent 음수, 24h flip to weak positive but sub-fee (9.01 < 16bp).
**Timescale-dependent direction**: short hold (4h-12h) anchor cross-up = continuation UP,
mid hold (24h) = ambiguous (sub-fee noise).

## Lesson #39 perfect mirror diagnostic (4th sub-class A dogfood)

| Side | A_focus | A_mirror | sum_abs | Class |
|---|---|---|---|---|
| A (high anchor) | -4.39 | +4.39 | **0.00** | **Sub-class A perfect mirror** (broad-uniform-negative joint = direction-bet noise + fee drag) |
| B (low anchor) | -2.22 | +2.22 | **0.00** | **Sub-class A perfect mirror** |

Both A + B perfect mirror = trigger event 자체 zero directional info. Joint signal
이 매수/매도 둘 다 net sub-fee 결과 — paradigm 162 mechanism은 fee-bound noise.

## Findings

### Lesson #56 OUTCOME-LEVEL FAMILY PROXY 14th instance CONFIRMED
- Magnitude-event family 누적 instances:
  - paradigm 117 R-3 OOS FAIL (alpha real + concentration heterogeneous)
  - paradigm 158 R-1 BROAD_FALSIFIED (FOMO continuation absent at 24h)
  - paradigm 162 R-1 BROAD_FALSIFIED_DIRECTION_INVERTED (anchor event reformulation 4h subspace fails)
- **anchor event reformulation** (return threshold → max-running event) 통한 family-distinct
  STRICT (3/5) 시도도 동일 OUTCOME 수렴 — axis-novelty alone alpha 보장 불가 결정적 강화
- Lesson #56 14 instances 누적 → magnitude-event family Tier 4 retire eligibility 재진입
  (lifecycle_pump_decay R-5 promotion으로 일시 해제했으나 magnitude-event 다른 sub-axis는 retire 유지)

### Lesson #42 mechanism CLASS asymmetric REFINEMENT (3rd dogfood)
- paradigm 117 R-3 caveat 1: capitulation MR LONG alpha + PUMP × continuation 미탐색
- paradigm 158 R-1: PUMP × LONG continuation 24h scale FALSE
- paradigm 162 R-1: 24h new high × LONG continuation **4h scale에서 weak positive (+4.39bp)** but sub-fee
- **Refinement**: continuation mechanism timescale-dependent, 4h hold에서 약한 신호 발현하나
  fee floor 미달. capitulation MR (LONG/24h)이 유일 alpha-bearing direction 강화.
- Lesson #42 3rd dogfood CONFIRMED 자격 elevated (3 dogfoods).

### Lesson #39 perfect mirror sub-class A 4th dogfood CONFIRMED
- A side sum_abs 0.00bp + B side sum_abs 0.00bp = **double perfect mirror**
- 4-quadrant 전체 broad-uniform-negative = sub-class A pattern
- mechanism inverted sub-class B 아님 (paradigm 110 type 미관찰)
- 4th dogfood CONFIRMED 자격 elevated (4 dogfoods)

### Lesson #8 universal LONG bias 6th dogfood — PARTIAL FAIL (sub-amendment candidate)
- A_mirror_high_anchor_LONG gross +4.39bp (positive)
- B_same_low_anchor_LONG gross **-2.22bp** (negative)
- **both_LONG_positive: FALSE** — 6 dogfoods 누적 중 첫 partial fail
- Lesson #8 amendment 가설: "anchor event class triggers는 LONG bias depleted vs magnitude
  threshold triggers (universal LONG bias depends on trigger statistic class)"
- 5 prior dogfoods 모두 magnitude/return threshold class. paradigm 162 anchor event는
  per-sym idiosyncratic timing-specific event — LONG bias underlying mechanism
  (general upward drift?) 약화.
- Lesson #8 **CONFIRMED 자격 deferred**, sub-amendment candidate.

### Lesson #62 family-distinct 7th boundary dogfood
- vs paradigm 117 strict count 2/5 BOUNDARY_PASS
- vs paradigm 158 strict count 3/5 STRICT_FAMILY_DISTINCT
- 그러나 BROAD_FALSIFIED outcome — **strict family-distinct ≠ alpha-bearing**
- Lesson #62 7th boundary dogfood CONFIRMED (6 prior + paradigm 162)

### Lesson #61 amendment 4th post-confirmation dogfood SUCCESS
- slug grep + DNA 4-dim table + family-retire eligibility cross-reference 모두 작성
- prior R-3+ outcomes (paradigm 117 + 158) cross-referenced explicitly
- paradigm 158 A_mirror predictive proxy + paradigm 117 R-1 4h B_same precedent direct citation
- amendment template strict template 4th consecutive post-confirmation dogfood SUCCESS.
- Lesson #61 amendment 강한 강화 (1st p159 inventory halt + 2nd p160 informed dispatch +
  3rd p161 inventory halt + 4th p162 informed dispatch with explicit prior precedent citation).

## Family-distinct strict 4-dim audit (Lesson #62)

| Dim | paradigm 117 | paradigm 158 | paradigm 162 | vs 117 | vs 158 |
|---|---|---|---|---|---|
| Statistic class | rolling 24h cum return ≤ -15% | rolling 24h cum return ≥ p90 | rolling 24h max cross-up event | partial | partial |
| Universe | 28 alts | 13 alts | 13 alts | partial | identical |
| Entry-side class | DRAWDOWN cross-down magnitude | PUMP cross-up magnitude | 24h high anchor cross-up | partial | STRICT |
| Mechanism alpha | capitulation MR LONG | FOMO continuation LONG | resistance reversal MR SHORT | STRICT | STRICT |
| Hold | 24h | 24h | 4h | STRICT | STRICT |

vs paradigm 117 strict count 2/5 — BOUNDARY_PASS
vs paradigm 158 strict count 3/5 — STRICT_FAMILY_DISTINCT

## Cumulative campaign state

- **162 paradigm graveyard** (consecutive parallel-campaign run)
- **Non-PASS streak: 32** (continuous-parallel policy active)
- **R-5 LIVE: 11** (lifecycle_pump_decay 보존)
- **R-5 yield: 11/162 = 6.79%**
- Magnitude-event family graveyards: paradigm 117 (R-3) + paradigm 158 (R-1) + paradigm 162 (R-1) = **3 cumulative**
- magnitude-event family Tier 4 retire eligibility:
  - lifecycle_pump_decay R-5 family escape attempt (Lesson #56 6th instance) 1개 active
  - 그러나 magnitude-event 다른 sub-axis 3 graveyards 누적 = 본 sub-axis retire 유지
  - paradigm 162가 STRICT 3/5 family-distinct로 분류되었으나 OUTCOME 동일 = axis-novelty 무력함 입증

## paradigm-architect spec amendment 권고 (Q3 §6.60 ratification batch)

### Lesson #42 CONFIRMED 정식 승급 (3 dogfoods)
- paradigm 117 R-3 caveat 1 (1st) + paradigm 158 R-1 (2nd) + paradigm 162 R-1 (3rd) = 3 dogfoods
- "magnitude-event 24h scale: capitulation MR LONG is sole alpha-bearing direction, 
  FOMO continuation absent at 24h, anchor reformulation at 4h subspace also fails"
- Candidate → CONFIRMED 자격 elevated

### Lesson #56 OUTCOME-LEVEL FAMILY PROXY 14th instance
- Magnitude-event family 14th instance (anchor event reformulation also family-proxy bound)
- axis-novelty (STRICT 3/5) alone alpha 보장 불가 결정적

### Lesson #39 perfect mirror sub-class A 4th dogfood CONFIRMED
- A side + B side double perfect mirror 첫 관찰
- Joint zero directional info → fee drag floor

### Lesson #8 universal LONG bias 6th dogfood PARTIAL FAIL
- anchor event trigger class에서 LONG bias depleted
- amendment candidate: "trigger statistic class에 따라 LONG bias 가변"
- 5/6 dogfoods PASS + 1 PARTIAL FAIL = 패턴 정합성 약화

### Lesson #61 amendment 4th post-confirmation dogfood SUCCESS
- 4 consecutive post-confirmation cases: p159 halt + p160 informed dispatch + p161 halt + p162 informed dispatch
- amendment template 영구 자산화

### Lesson #62 family-distinct 7th boundary dogfood
- STRICT 3/5 family-distinct outcome BROAD_FALSIFIED — strict ≠ alpha

## Artifacts

- `backend/scripts/research/paradigm162_alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h_r1.py`
- `backend/runs/research_track/alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h/r1__metrics.json`
- `backend/runs/research_track/alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h/r1__stdout.log`
- `backend/runs/research_track/alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h/TASK.md`
- this graveyard md

## Next-action (paradigm 163 recommendation with Lesson #61 amendment strict)

### Provenance audit framework

paradigm 163 candidate 후보:

1. **Option α: `alt_listing_post_30d_listing_pump_decay_extension_test_directional_30d`** (lifecycle_pump_decay R-5 측정 진행 중 사이 별도 변형 dispatch)
   - lifecycle_pump_decay = 30d hold SHORT, paradigm 163 = 동일 mechanism 60d hold extension test
   - **DNA vs paradigm 121 lifecycle_pump_decay**: 5/6 identical (statistic + universe + entry-side + mechanism + substrate, hold만 다름)
   - **Lesson #62 strict count vs lifecycle: 1/5 (hold only)** — FAIL
   - **R-0 HALT eligible** (DNA 5/6 listing family + R-5 active 직접 변형)

2. **Option β: `alt_funding_post_8h_boundary_carry_direction_per_sym_drift_test_directional_4h`** (post-boundary carry direction drift)
   - funding family Tier 4 retire (5 graveyards 73/79/96/97/98/99) + paradigm 22 funding_carry R-5 exception
   - DNA vs paradigm 22: statistic identical, only direction-conditioning 변형
   - **Lesson #62 strict count vs 22: ≤2/5** — funding family family-retire eligibility violated
   - **R-0 HALT eligible**

3. **Option γ: `alt_intraday_8h_volatility_spike_post_funding_window_continuation_directional_4h`** (post-funding-boundary vol spike continuation)
   - DNA vs paradigm 82 pre_funding_window_divergence: 4/6 (statistic similar substrate, mechanism class similar)
   - funding family Tier 4 + 5m microstructure advisory caution (paradigm 80+82+83+85 4 instances)
   - **Lesson #56 family proxy HIGH** (funding window family 4 graveyards)
   - **R-0 HALT 권고**

4. **Option δ ✓ RECOMMENDED: `alt_per_sym_volume_z_spike_post_low_volume_regime_breakout_continuation_directional_4h`** (low-vol regime breakout)
   - **Novel statistic class**: per-sym volume z (NOT magnitude/return/funding/anchor) trigger
   - **Mechanism**: low-vol regime accumulation breakout continuation (volatility regime axis)
   - **DNA vs all 162 paradigms**: volume z trigger 3 paradigms prior (taker_buy_vol family Tier 4 retire 72 + 23 + 60) — volume z family 자체도 retire eligibility
   - **Lesson #62 strict count vs taker_buy_vol family**: 2/5 (regime conditioning + per-sym vs aggregate) BOUNDARY
   - **Lesson #56 family proxy MEDIUM** (volume family 3 retired graveyards)
   - **substrate verified** (4h klines volume column 12-col cache)

5. **Option ε ✓ RECOMMENDED: `alt_btc_volatility_regime_x_alt_funding_carry_carry_filter_modifier_directional_8h`** (BTC vol regime modifier on funding carry)
   - **paradigm 22 funding_carry R-5 active** + BTC vol regime conditioning modifier
   - **DNA vs paradigm 22**: regime modifier added (4/6 DNA, vol regime filter axis novel)
   - **Lesson #62 strict count: 1-2/5** BOUNDARY (funding family retired 우회 attempt)
   - **R-5 active paradigm 22 modifier track** = lifecycle_pump_decay 패러다임처럼 family-retire 우회 candidate
   - **R-0 HALT 권고 (paradigm 22 R-5 변형 = lesson #56 family-proxy 강한 위험)**

6. **Option ζ ✓ STRONGLY RECOMMENDED: `alt_microstructure_orderflow_imbalance_cvd_divergence_post_session_open_continuation_directional_4h`** (session-open × CVD divergence)
   - **Fresh statistic class**: CVD (cumulative volume delta) microstructure axis
   - **Mechanism**: session open + CVD divergence directional continuation (order-flow imbalance)
   - **DNA vs all 162 paradigms**: CVD axis 직접 사용 paradigm 부재 (paradigm 86 funding_per_sym × cvd 4h divergence 변형 1개만, 그러나 funding-conditioned)
   - **Lesson #62 strict count: 3-4/5 STRICT family-distinct**
   - **substrate verification 필요**: 4h klines에서 CVD proxy 가능 여부 (taker_buy_vol / taker_buy_quote_vol 12-col cache verified)
   - **session boundary + microstructure** = paradigm 90 family Tier 4 retire 우회 (session_boundary single-axis 아닌 microstructure × session conditioning)

### Direct recommendation for paradigm 163 (per [[feedback-direct-recommendation]])

**Option ζ `alt_microstructure_orderflow_imbalance_cvd_divergence_post_session_open_continuation_directional_4h`** 1순위 권고:

- Fresh CVD microstructure axis (paradigm 86 funding-conditioned 변형 1개만 prior)
- substrate already verified (taker_buy_vol 12-col cache columns)
- Lesson #62 STRICT family-distinct 3-4/5 expected
- session × microstructure conditioning = single-axis 우회
- Lesson #56 family proxy low (CVD family 1 graveyard only)

대안: **Option δ volume z spike post low-vol regime breakout** (volume family Tier 4 retire 우회
attempt, BOUNDARY 2/5).

**HALT 권고 (R-0 inventory)**:
- Option α (lifecycle 30d extension test) — DNA 5/6 R-5 active
- Option β (funding direction conditioning) — funding family retire violation
- Option γ (post-funding vol spike continuation) — funding window family proxy
- Option ε (BTC vol regime × funding carry) — paradigm 22 R-5 modifier high proxy

## Memory policy adherence
- [[feedback-paradigm-campaign-continuous-parallel]] — 32-streak milestone 무관 dispatch 지속
- [[feedback-direct-recommendation]] — R-1까지 자율 진행 + paradigm 163 direct option ζ 권고
- [[feedback-no-freemium-trial]] — substrate 12-col joblib cache only
- [[feedback-life-changing-strategy-criterion]] — 4-dim hard-block enforced (edge -0.12% < 2%)
- [[feedback-persistence-over-efficiency]] — non-PASS streak 32 dispatch 지속 결정
- [[feedback-paradigm-architect-local-context]] — 4h klines archive substrate (DB-bound 격차 없음)
