# Graveyard — alt_fear_greed_index_extreme_contrarian_bilateral_1d (paradigm #226)

**Date**: 2026-07-14 KST
**Phase reached**: R-1
**Verdict**: `DIFFUSE_POSITIVE_CONCENTRATION_FAIL_LIFE_CHANGING_FAIL` (Lesson #41 formal CONFIRMED 4th dogfood)

## Hypothesis
Alternative.me Crypto Fear & Greed Index (일일 composite 0-100) 극단 판독이 Binance USDT-M 알트 24-72h 컨트래리언 mean-reversion을 예측한다. FEAR≤25 → LONG / GREED≥75 → SHORT, 4-quadrant Symmetric Negative Test 결합.

## DNA dimensions
- Data source: **external sentiment composite (Alternative.me F&G, 2018-02-01~, 무료 무제한)** — NEW class, 226회 파라다임 중 최초
- Decision mode: bounded 0-100 raw score threshold × contrarian mean-reversion
- Time scale: daily trigger × 24h/48h/72h hold sweep
- Universe shape: 13 Binance USDT-M perp alts (paradigm 69 validated set)

## Phase results

### R-0 inventory
- Slug grep (fear/greed/fng/sentiment/alternative.me): **NO MATCH** (Lesson #61 amendment PASS)
- DNA 4-dim vs proximate paradigms 219-225: 3/5 novel + 2/5 boundary → dispatch PASS (Lesson #62)
- Family-proxy: no intersection with 20 retired families (Lesson #56 PASS)
- Alpha decay Item 6: no F&G/sentiment predecessor → N/A
- Lesson #40 threshold feasibility: PASS (raw bounded 0-100, empirical FEAR 24.2% + GREED 9.7%)
- Lesson #11 density: PASS (2704 A-focus + 1079 B-focus events, ≥30/quarter guaranteed)
- Lesson #28 substrate: PASS (HTTP 200, daily bounded scalar shape match)
- Lesson #30 window ratio: PASS (858d overlap / 2000d F&G span = 42.9%)

### R-1 four-quadrant × 3-hold sweep (n=12 cells)
Data window: 2024-01-02 → 2026-05-12 (861 days), fee 8bp round-trip.
Overlap trigger rate: FEAR≤25 = 159 days (18.5%), GREED≥75 = 119 days (13.8%).

**Primary cells (24h hold)**:

| Cell | n | edge_bp | signal_t_excess | ci_lower_bp | perm_p (1-side) | q_pos_t | syms_ci_pos | syms_mean_pos | 3-gate | conc |
|---|---|---|---|---|---|---|---|---|---|---|
| A_focus_FEAR_LONG | 2067 | **+30.4** | **+2.89** | **+10.68** | **0.000** | 5/6 (0.83) | **0/13** | 12/13 | ✅ | ❌ |
| A_mirror_FEAR_SHORT | 2067 | -46.4 | -2.95 | -66.9 | 0.000 (below) | 1/6 | 0/13 | 0/13 | ❌ | ❌ |
| B_focus_GREED_SHORT | 1545 | -33.3 | -0.64 | -67.9 | 0.234 (below) | 3/6 | 0/13 | 2/13 | ❌ | ❌ |
| B_mirror_GREED_LONG | 1545 | +17.3 | +0.99 | -17.1 | 0.145 | 2/6 | 0/13 | 8/13 | ❌ | ❌ |

**Full 12-cell hold sweep (Lesson #37)**:
- three-gate PASS cells: `A_focus_FEAR_LONG_h24`, `A_focus_FEAR_LONG_h48`, `B_mirror_GREED_LONG_h72`
- concentration PASS cells: **0 / 12** (universal syms_ci_pos 0/13 across all cells)
- Lesson #39 mirror antipattern: N/A (A_focus + A_mirror asymmetric direction-informative signal, not fee-drag mirror)

### Symmetric Negative Test (Lesson #19, 4-quadrant)
- A_focus PASS (three-gate) — mechanism real at pool level
- A_mirror strongly negative (opposite direction confirmed by identity, NOT flat null)
- B_focus FAIL (GREED contrarian null: sigex -0.64, edge -33bp but ceiling touches zero)
- B_mirror positive but sub-threshold — likely 2024-2026 BTC bull-drift residual overlap
- FEAR side works, GREED side does not — **direction-asymmetric mechanism** (Lesson #42 candidate cross-reference: capitulation MR real, euphoria MR absent). 이전 lesson #42 paradigm 117 dogfood와 완전 동형 클래스.

## Reason

**결정적 fail mode**: R-1 primary A_focus (FEAR × LONG × 24h)가 pool-level three-gate 완전 PASS
(signal_t_excess +2.89 / ci_lower +10.68bp / perm_p 0.000 / q_pos_t 5/6 = 0.83)한다.
그러나 **Concentration Gate 결정적 FAIL** — 12/13 심볼이 positive mean에도 불구하고
per-symbol bootstrap CI 통과 심볼이 **0/13** (universal). Per-sym n ≈ 159이 너무 얕아
bootstrap CI가 개별적으로 fee-adjusted zero를 배제 못 한다. **Lesson #41
DIFFUSE_POSITIVE_CONCENTRATION_FAIL 정확 매칭** — pool 알파는 real이지만 13 심볼에
너무 얇게 확산.

**Life-changing 4-dim 결정적 FAIL**: per-trade edge estimate 0.30%/trade << 2%/trade
floor. Trades/yr/sym 67.6은 capital util은 회복 가능하지만 **per-trade structural ceiling
이 fee-floor-bound** (paradigm 115/116/118 R-2 우주 확장 dogfood 정착 후 formal CONFIRMED
verdict `confirmed_but_narrow_scope_life_changing_fail`). Universe 25+ 확장이 syms_ci_pos
회복해도 per-trade 0.30% floor을 뚫을 수 없음.

**Family class 매칭**: 자문 등급 "Universe-aggregate scalar statistic family" (paradigm
115/116/118 3-dogfood CONFIRMED, F&G는 sentiment composite 형태의 universe-aggregate scalar
statistic — 개별 심볼별 signal이 없고 매크로 판독만 존재). 이 계열 4번째 실증 dogfood로
formal Tier 4 family retire 기준선 도달 임박.

**Lesson #42 cross-reference (direction-asymmetric MR mechanism)**: FEAR side는 mechanism
real, GREED side는 sigex -0.64 null. Paradigm 117 (capitulation × LONG real / PUMP × SHORT
null) 동형 - forced-deleveraging cycle이 non-symmetric, euphoria는 orthogonal forced-buy
pressure를 lack. F&G도 동일 asymmetry class.

## Lessons learned
- **Lesson #41 formal CONFIRMED 4th dogfood** (paradigm 115 + 116 + 118 + **226**)
  누적 — universe-aggregate scalar statistic (F&G, avg pairwise correlation, total
  volume share) 계열 pool-evidence-strong + concentration-fail + per-sym n<200 + per-trade
  edge <2%/trade 반복 패턴. Sentiment composite도 volume-share/correlation-aggregate와 동일
  구조. Meta-finding 4-dogfood 도달.
- **Lesson #42 candidate 2nd dogfood** (paradigm 117 + **226**) — extreme-magnitude ×
  mean-revert 클래스는 direction-asymmetric. FEAR/capitulation side works, GREED/PUMP side
  는 forced-buy pressure absence로 인해 null. Mechanism narrative 재구성 필요 ("fear-driven
  capitulation → bounce", NOT "extreme sentiment → mean-revert").
- **Advisory caution family 4th dogfood** — "Universe-aggregate scalar statistic family"
  paradigm 115/116/118/**226** 누적 4 dogfoods. **다음 dogfood (5th 누적) 시 formal Tier
  4 family retire** 기준 도달. sentiment composite/RV aggregate/correlation aggregate/volume
  share aggregate 모두 이 계열, 향후 R-0 halt 사전 차단 강력 권고.
- **NEW candidate — external sentiment composite substrate 최초 사용** — F&G API는 free
  unlimited로 (Lesson #28) 자체는 valid substrate. Structural infeasibility 아니라 alpha
  자체가 fee-floor-bound인 것이 문제. sentiment composite 계열 새 발의 시 per-sym n≥300
  + per-trade edge ≥2% 사전 estimate 의무.
- (기존 lesson 재확인) Lesson #16 Concentration Gate — pool sigex +2.89도 syms_ci_pos
  0/13이면 자동 halt. Lesson #37 hold sweep verdict scan은 non-focus PASS 2 셀 발견
  (A_focus h48 + B_mirror h72)했으나 모두 conc FAIL로 promotion 후보 아님.

## References
- code: `backend/scripts/research/paradigm226_alt_fear_greed_index_extreme_contrarian_bilateral_1d_r1.py`
- metrics: `backend/runs/research_track/alt_fear_greed_index_extreme_contrarian_bilateral_1d/r1__metrics.json`
- substrate: `backend/runs/research_track/alt_fear_greed_index_extreme_contrarian_bilateral_1d/fear_greed_daily.json` (n=2000 daily rows, 2021-01-20 → 2026-07-13)
- precedent (Lesson #41): paradigm 115/116/118 (universe-aggregate scalar statistic family)
- precedent (Lesson #42 direction-asymmetric MR): paradigm 117 (capitulation LONG real, PUMP SHORT null)
