# graveyard — paradigm 255 alt_funding_rate_24h_delta_z_bilateral_3d_5d

**Date (KST)**: 2026-08-13
**Phase**: R-0_GRAVEYARD
**Verdict**: `R0_HALT_COMPOUND_LESSON_56_OUTCOME_FAMILY_PROXY_LESSON_62_DNA_5_OF_6_OVERLAP_LESSON_61_SLUG_HIT_LESSON_39_MIRROR_ANTIPATTERN_PREDICTED`
**Dispatch mode**: user_provided_hypothesis
**Compute saved**: ~45 min (R-1 not dispatched)

---

## Hypothesis (as submitted)

Binance USDT-M perpetual 8h funding_rate 24h cumulative delta
(Δfunding_24h = funding_rate[t] - funding_rate[t-3]) 는 레버리지 심리의 **가속도**
를 측정한다. 이 delta의 rolling 30d (90 cycles) z-score가 극단적일 때:
- z ≥ +T (24h 롱 편향 급증) → SHORT
- z ≤ -T (24h 디레버리지/숏 누적) → LONG

4-quadrant bilateral SNT, 14-alt cohort, hold 3d/5d, T∈{1.0, 1.5, 2.0}.

---

## Why halted at R-0

### 1. Lesson #61 slug grep — 직접 히트

`funding.*delta`, `delta.*funding`, `funding.*velocity`, `funding.*acceleration`
grep 결과가 즉시 다음 3개 falsified paradigm 을 반환:

- **paradigm 99** `funding_cycle_8h_differential_velocity_per_sym` —
  BROAD_FALSIFIED_MIRROR_ONLY (2026-05-19)
- **paradigm 97/98** `funding_velocity_cross_section_dispersion` — BROAD_FALSIFIED
- **paradigm 96** `funding_sign_flip` — BROAD_FALSIFIED

### 2. Lesson #62 DNA 5/6-dim 중복 — HARD FAIL vs paradigm 99

| 차원 | paradigm 99 (prior) | paradigm 255 (current) | overlap |
|---|---|---|---|
| substrate | binance_funding_rate DB 8h | binance_funding_rate DB 8h | ✓ |
| statistic | per-sym 30d rolling z of Δfunding_8h (=f[t]-f[t-1]) | per-sym 30d rolling z of Δfunding_24h (=f[t]-f[t-3]) | ✓ (proxy-isomorphic) |
| mechanism | 레버리지 편향 급증 → MR fade | 레버리지 가속 → 청산압력 → MR/반전 | ✓ (동일 story) |
| universe | 14-alt USDT-M cohort | 14-alt USDT-M cohort (동일 리스트) | ✓ |
| direction scheme | 4-quadrant bilateral SNT | 4-quadrant bilateral SNT | ✓ |
| hold frame | 4h / 8h / 16h intraday | 3d / 5d swing | ✗ (유일 상이 차원) |

**overlap = 5/6 → HARD FAIL (Lesson #62 threshold)**

**statistic proxy-isomorphism 실측 근거** (BTC/ETH/SOL/DOGE 4-sym DB 측정,
n=2644-2911 cycles/sym):

- Pearson corr(z_Δf_8h, z_Δf_24h) = **0.4725, 0.5001, 0.4725, 0.4824**
  → mean 0.485, 두 z-score 는 24% 분산 공유
- |z_8h| ≥ 2.0 극단 발화시 z_24h 부호 일치율 = **0.84, 0.87, 0.84, 0.87**
  → 5-of-6 확률로 동일 신호 반환
- 수학적으로 Δf_24h = Δf_8h[t] + Δf_8h[t-1] + Δf_8h[t-2] (3 개 연속 8h delta 의 합)
  → 선형결합, 동일 velocity 통계 클래스

즉 파라다임 255 은 파라다임 99 의 **윈도우 재파라미터화 (window
re-parameterization)** 에 불과하다. Lesson #62 원문 사례 (paradigm 172 →
paradigm 99 identical MR mechanism per-sym history z) 와 정확히 같은 구조.

### 3. Lesson #56 outcome-level family proxy — funding family Tier 4 retire

funding own-history velocity/delta directional bet 계열의 **누적 falsified
11 건**:

| 파라다임 | 판정 |
|---|---|
| 79 funding extreme level directional | graveyard |
| 96 funding sign flip categorical | BROAD_FALSIFIED all 4 quadrants n=6934 |
| 97 funding_velocity cross_section_dispersion | BROAD_FALSIFIED |
| 98 (P2 batch variant) | BROAD_FALSIFIED |
| **99 funding_cycle_8h_differential_velocity_per_sym** | **BROAD_FALSIFIED_MIRROR_ONLY** — LC edge 0.24% << 2% gate, 0/13 syms ci_pos, symmetric LONG bias artifact |
| 132 funding extreme × CVD joint | R-0 HALT Lesson #40 STRUCTURAL |
| 138 funding per-sym z × CVD | R-0 HALT Lesson #40 asymmetry inheritance |
| 156 funding own-history hybrid | graveyard |
| 172 funding term-structure divergence | R-0 INVENTORY_HALT Lesson #62 vs paradigm 99 |
| 243 funding rolling 30d skewness bilateral | graveyard — Lesson #39 sub-class B −2·fee identity ALL cells |
| 246 funding sign flip sustained N-event | graveyard |
| 250 funding percentile extreme contrarian short 7d | R-0 HALT_COMPOUND |

funding family R-5 예외 = paradigm 22 뿐 (narrow 3-sym MR endpoint exit 8h
cycle — 파라다임 255 의 14-sym swing 3-5d 와는 config 3/3 모두 상이).

파라다임 255 은 **12번째 falsified 계열 멤버**가 될 것이 명백하다.

### 4. Lesson #39 mirror antipattern 예측

- paradigm 99 실측: 4-quadrant 중 B mirror LONG 만 3-gate PASS (n=1304 +24bp
  perm_p=0.028) 이나 LC edge 0.24% << 2% gate, 나머지 3-cell 은 −7~−40bp,
  0/13 syms ci_pos → mirror-only PASS 패턴 = symmetric directional bias
  artifact (mechanism alpha 아님).
- paradigm 243 실측: A_focus + A_mirror = **exact −2·fee identity** 모든
  (T, hold) 셀에서 성립 (Lesson #39 sub-class B mechanism-inverted 확진).

Δfunding_24h 는 Δfunding_8h 의 선형결합이므로 동일한 대칭 편향 artifact 를
상속받는 것이 확률적으로 확실하다. R-1 을 돌려도:

**예상 판정: BROAD_FALSIFIED_MIRROR_ONLY 또는 NARROW_SCOPE_LIFE_CHANGING_FAIL**
(perm_p 는 marginal 통과 가능, 그러나 edge < 2% gate + Concentration 0/13 ci_pos)

### 5. Lesson #55 prescription rescue scope — OUT_OF_SCOPE

- Predecessor (paradigm 99) 는 4-quadrant 모두에 걸친 uniform anti-alpha,
  0/13 syms ci_pos, hold sweep 4h/8h/16h 전 셀 focus 3-gate FAIL.
- 제안된 처방: hold 4h~16h → 3d~5d 로 **horizon 연장**.
- 이는 **mechanism differentiator 가 아니라 spatial re-scan**.
- 정보성 alpha decay 는 다음 cross-family 사례에서 monotonic 확진:
  paradigm 87 delisting, paradigm 136/202 RV intraday.
- 3-5d hold 는 paradigm 99 의 monotonic anti-alpha decay 곡선의 tail 에 위치
  → 개선 근거 zero.

**Lesson #55 6th out-of-scope dogfood.**

### 6. Lesson #11 sample density — 실측 (참조용)

R-0 HALT 상황에서도 audit trail 완결을 위해 실측:

- BTC/ETH/SOL/DOGE 4-sym × n=2644-2911 cycles.
- Trigger rate at |z_24h|≥1.0 ≈ 14-16% / at |z_24h|≥1.5 ≈ 6-8% / at
  |z_24h|≥2.0 ≈ 2-3%.
- Expected n per cell at T=2.0, 14 syms × 4 quarters × 2 quadrants ≈ **60**.
- Lesson #11 threshold (≥30) PASS. → **density 는 문제 아님**, 그러나 상위
  DNA 붕괴로 무의미.

### 7. Lesson #77 substrate diversity

funding_rate_DB 는 non-OHLCV → PASS. 그러나 family retire 상황에서는
substrate diversity 만으로 R-1 진입 자격 미충족.

---

## G1·G2 미실행 사유

G0 R-0 HALT 상태에서는 **tier3_gate.py 를 호출하지 않는다** — 실행 자체가
family retire 정책 (Lesson #56) 위반. R-1 백테스트 스크립트 (`paradigm_253_...
_r1.py`) 도 생성하지 않는다.

이는 프로토콜 §Failure protocols 의 다음 두 조건을 동시에 만족한다:

- "Hypothesis is clear duplicate of existing R-3+ paradigm" → paradigm 99 완전
  중복 (5/6 dim, statistic proxy-isomorphic corr=0.485, sign-agree 0.86).
- Lesson #56 family-proxy R-0 HALT 규범.

---

## 재발의 조건 (재도전 시 필수 요건)

향후 funding delta / velocity 계열에서 재도전할 경우, 다음 조건 중 하나 이상
을 명시적으로 충족해야 한다:

1. **direction-inverting mechanism** — paradigm 99 mirror-only PASS 를
   focus-side PASS 로 변환하는 이론적 근거 (예: 특정 레짐/시간대 조건부).
2. **direction differentiator observable** — paradigm 99 의 uniform
   anti-alpha 를 heterogeneous subset (특정 sym cohort 또는 volatility
   regime) 로 분리할 수 있음을 empirical evidence 로 제시.
3. **substrate family shift** — funding_rate 를 벗어난 새로운 substrate
   (예: cross-exchange spread, options implied leverage) 결합 — 단, 결합
   상대 substrate 도 별도 family retire 아니어야 함 (CVD 는 paradigm 132/138
   에서 이미 STRUCTURAL 처리됨).
4. **direction-agnostic edge** — MR/momentum directional bet 대신 volatility
   / dispersion 지표로 재정의 (paradigm 22 narrow-scope R-5 유일 성공 모드).

이 4 조건 어느 것도 충족 못하면 재발의 금지.

---

## 산출물

- `backend/runs/research_track/paradigm_255_funding_rate_24h_delta_z_bilateral_3d_5d/r0_prescreen.json`
- `backend/runs/research_track/paradigm_255_funding_rate_24h_delta_z_bilateral_3d_5d/r0_dna_collision_empirical.json`
- `backend/runs/research_track/graveyard__paradigm_255_funding_rate_24h_delta_z_bilateral_3d_5d.md` (this file)

## Lessons dogfooded (this halt)

- **#61** slug grep direct hit (3 falsified predecessors)
- **#62** DNA 5/6 overlap vs paradigm 99 (empirical proxy-isomorphism corr=0.485 sign-agree 0.86 at extreme)
- **#56** outcome-level family proxy — 12th funding family graveyard
- **#55** prescription-rescue scope OUT_OF_SCOPE (horizon extension not mechanism differentiator) — 6th cumulative dogfood
- **#39** mirror antipattern predicted (linear combination inherits paradigm 99 mirror-only + paradigm 243 −2·fee identity)
- **#11** sample density measured (adequate) — informational only
- **#77** substrate non-OHLCV — PASS but insufficient
