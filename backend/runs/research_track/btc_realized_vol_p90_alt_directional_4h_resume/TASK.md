# paradigm 155 — btc_realized_vol_p90_alt_directional_4h_resume

**Created**: 2026-05-21 KST
**Counter**: 155 (cumulative)
**Phase**: R-0_HALT_BY_DNA_DUPLICATE_AND_PRIOR_FALSIFICATION
**Type**: E (event-driven)
**Status**: GRAVEYARD (pre-execution halt)
**Slug**: `btc_realized_vol_p90_alt_directional_4h_resume`

---

## Hypothesis

paradigm 69 (`btc_rv_spike_highvol_filter_alt_long_240m`, R-5 active 2026-05-14) macro proxy를 4h hold + directional (sign-conditional bilateral) variant로 resume.

- BTC 30m RV z(30d) ≥ +2.5 rising edge + 60m cooldown
- BTC 30d rolling vol ≥ p90 of past 90d (HIGH vol regime)
- 13 alts × **sign-conditional**: BTC up→LONG, BTC down→SHORT
- Hold: **270m → 240m** (~11% reduction, retiming)
- TP +5% / SL none (paradigm 69 동일)

**Intended mechanism integration**: paradigm 67 H5 sign-split 발견 (BTC up-trig LONG t=+3.58 / BTC down-trig LONG t=-2.73 / 240m hold) + paradigm 69 HIGH-vol filter mechanism 결합.

**Sub-hypotheses**:
- A focus: BTC up × alt LONG → paradigm 69 동등 또는 강화 expected
- A mirror: BTC up × alt SHORT → null/음수 expected
- B same-sign: BTC down × alt SHORT → **paradigm 67 H5 contra-direction confirm 가설**
- B mirror: BTC down × alt LONG → 강한 음수 expected (paradigm 67 H5 direct)

---

## R-0 inventory prescreen — DECISIVE HALT

### Audit 1: Lesson #62 CONFIRMED retiming reframe family-distinct 4-dim audit

| Dimension | paradigm 69 | paradigm 155 | Strict change? |
|---|---|---|---|
| Trigger statistic | BTC RV p90 + z≥2.5 | **동일** | NO |
| Universe | 13 alts | **동일** | NO |
| Hold timing | 270m | 240m | **PARTIAL** (~11% reduction, retiming family) |
| Entry-side / event time | BTC RV spike + HIGH-vol | **동일** | NO |
| Sign-conditioning | LONG unsigned | sign-cond bilateral | **STRICT** (1) |
| Filter rule | p90 HIGH-vol AND BTC sign | p90 HIGH-vol AND sign-split | **PARTIAL** (paradigm 69 이미 BTC up-only filter) |

**Strict 변화 count: 1/6** (sign-conditioning만). **Lesson #62 CONFIRMED ≥2 strict dim 변화 의무 미충족.**

추가로 paradigm 69 R-5 seed_proposal §config에 `btc_ret_sign_filter = "positive"` 명시 — paradigm 69 자체가 이미 BTC up-side sign-conditional이며, paradigm 155의 A focus quadrant는 paradigm 69의 정확한 재현. sign-conditioning은 **새로운 mechanism 추가 아닌 paradigm 69 sub-quadrant 확장**.

**→ Lesson #62 audit FAIL.**

### Audit 2: Prior falsification — paradigm 70 mirror SHORT (CRITICAL)

paradigm 70 `btc_rv_spike_highvol_down_alt_short_240m` (graveyard 2026-05-14, 메모리 [[project-paradigm-btc-rv-highvol-short]]):

- Trigger: BTC RV p90 HIGH-vol + BTC down (BTC ret < 0)
- Universe: 13 alts (identical to paradigm 155)
- Direction: SHORT
- Hold: **240m (정확히 paradigm 155 hold)**
- = **paradigm 155 B same-sign quadrant와 정확히 100% 동일**

paradigm 70 R-1 측정 (n=793, hold=240m, p90 cutoff):
- h1 net_mean **-49.00bp**, t **-3.62**, sig_t_ex **-2.48**
- bootstrap CI [-75.56, -22.69] **전부 음수, prob_positive=0.0005**
- perm_p_one_sided_above 0.997
- 13/13 alts 모두 음수 (h3_alts_pos_ge_10=False)
- 5/5 holds 모두 음수 (h4_pos_count=0, holds 180/210/240/270/300 전부)
- h6 cross-check: paradigm 69 LONG +112.88bp vs paradigm 70 SHORT -49.00bp = **13σ 격차** (메모리 명시 시장 미시구조 방향 비대칭)

**B same-sign quadrant는 R-1 미실행 결정적 falsified.**

paradigm 70 verdict_reason: "BTC-up sign filter 무력 (signed≈unsigned)" + 메모리 명시 "시장 미시구조 방향 비대칭". 즉 paradigm 67 H5 BTC down-trig 음수 t=-2.73이 invertible mirror가 아닌 **본질적 SHORT-side fee-floor saturation + asymmetric microstructure**임을 paradigm 70이 결정적으로 입증.

### Audit 3: Prior falsification — paradigm 68 R-3.5 (BTC RV up-cond LONG 240m)

paradigm 68 `btc_rv_spike_up_conditional_alt_long_240m` R-3.5 graveyard (2026-05-14, 메모리 [[project-paradigm-btc-rv-up-cond]]):

- Trigger: BTC RV z≥2.5 + BTC up
- Direction: LONG
- Hold: **240m (정확히 paradigm 155 hold)**
- = **paradigm 155 A focus quadrant와 사실상 동일** (단 vol p90 filter 추가 차이만)

paradigm 68 R-3.5 결과:
- r3_baseline (no p90 filter): n=2626 net +15.22bp t=+2.94 sig_t_ex +5.29
- short_lookback_vol_stratification: HIGH n=689 +59.99bp t=+4.30 / **LOW n=702 -2.48bp** / **MID n=637 -70.39bp t=-8.35** / UNKNOWN n=598 +75.61bp
- lowvol filter variant (LOW + MID): n=975 **-9.08bp** t **-1.65** sig_t_ex -0.06 → **lowvol_filter variant 8/24 plateau cells 0/24 PASS**
- verdict: GRAVEYARD ("aggregate PASS but vol regime stratify reverses hypothesis")
- **paradigm 69 R-5 seed가 paradigm 68 R-3.5 graveyard의 HIGH-only narrow variant**

→ paradigm 155 A focus는 이미 paradigm 69 R-5 seed로 **production 상태**, R-1 ad-hoc 재측정 가치 없음. Lesson #56 SELF-validation track으로 분류하려면 paradigm 69 R-5 paper baseline (Day 7 = 오늘) 측정값과 cross-comparison해야지 R-1 ad-hoc rerun으로는 신호 부재.

### Audit 4: DNA 5/6 dimension overlap check

paradigm 155 vs paradigm 69 + paradigm 68 + paradigm 70 (3-paradigm union):

| DNA dim | paradigm 155 | paradigm 69 | paradigm 68 | paradigm 70 |
|---|---|---|---|---|
| Data source | BTC 30m RV + 13 alts 1m | 동일 | 동일 | 동일 |
| Statistic | z-score(30d) ≥ +2.5 | 동일 | 동일 | 동일 |
| Regime filter | p90 HIGH-vol | 동일 | (없음 R-3.5는 stratify) | 동일 |
| Universe | 13 alts | 동일 | 동일 | 동일 |
| Hold timing | 240m | 270m | 240m | 240m |
| Direction logic | sign-cond bilateral | LONG unsigned | LONG unsigned | SHORT unsigned |

→ paradigm 155 = paradigm 69 (A focus, 270m→240m partial) ∪ paradigm 70 (B same-sign 정확 동일). **DNA 5/6 overlap with 2 prior graveyards + 1 R-5 seed.**

### Audit 5: Lesson #19 Symmetric Negative Test 4-quadrant info value

paradigm 155 4-quadrant 측정 시 expected 결과는 다음과 같습니다 (prior measurements 종합):

| Quadrant | Prior measurement source | Expected verdict |
|---|---|---|
| A focus (BTC up × LONG) | paradigm 69 R-5 n=767 +112.88bp t=+9.23 sig_t_ex +10.40 (270m), paradigm 67 BTC up sub-cell +186.5bp t=+3.58 (240m) | **PASS (known)** |
| A mirror (BTC up × SHORT) | paradigm 70 h7 (signed≈unsigned) + paradigm 69 mirror logic | **FAIL_INVERTED** (known) |
| B same-sign (BTC down × SHORT) | **paradigm 70 R-1 정확 일치 n=793 -49.00bp t=-3.62 sig_t_ex -2.48 13/13 alts neg 5/5 holds neg** | **FAIL_BROAD (known)** |
| B mirror (BTC down × LONG) | paradigm 67 H5 BTC down-trig LONG n=2756 -150.14bp t=-2.73 | **FAIL_INVERTED (known)** |

**4/4 quadrants의 expected verdict가 prior measurements로 결정적**. R-1 측정 의무 (Lesson #19) 충족하더라도 새로운 정보 0bit. Lesson #19 dogfood 의미는 joint-trigger paradigm의 **broad-falsified 사전 진단**이며, paradigm 155는 4 sub-cells 각각이 별도 paradigm으로 이미 R-1 ~ R-5 (paradigm 69) 완료된 case.

### Audit 6: Lesson #61 next-action provenance

paradigm 154 직전 §next-action option β로 paradigm-architect agent가 권고 — **provenance 적법**. 그러나 권고 시점에 paradigm 70/68 결과를 invariant cross-reference 없이 sign-cond bilateral mechanism integration alpha를 가정. **권고 자체가 paradigm 70 mirror antipattern + paradigm 68 lowvol stratify reversal evidence cross-check 누락**. provenance 적법 ≠ mechanism feasibility.

### Audit 7: Lesson #56 OUTCOME-LEVEL family proxy SELF-validation

paradigm 155가 paradigm 69 self-extension 의도이나, paradigm 69의 270m hold vs paradigm 155의 240m hold는 **partial retiming + Lesson #62 strict dim count 1/6**으로 family proxy 의미가 약함. 진정한 SELF-validation은 paradigm 69 R-5 paper baseline Day 7/Day 30 measurement (오늘 2026-05-21 Day 7 baseline 측정 예정)에서 발생. R-1 ad-hoc rerun은 paper baseline 측정 대체 아님.

---

## R-0 Verdict

### Result: **R0_HALT_BY_DNA_DUPLICATE_AND_PRIOR_FALSIFICATION**

**4가지 독립 fail axis 누적**:

1. **Lesson #62 strict dim count fail**: 1/6 strict (sign-cond) — 의무 ≥2 미달
2. **DNA 5/6 overlap**: paradigm 69 (A focus 5/6) + paradigm 70 (B same-sign 6/6 정확 일치) + paradigm 68 (A focus 240m 4/6) 누적
3. **B same-sign quadrant prior decisive falsification**: paradigm 70 n=793 -49bp t=-3.62 sig_t_ex -2.48 13/13 alts neg 5/5 holds neg + 13σ asymmetry vs paradigm 69
4. **4-quadrant info value 0bit**: 4/4 quadrants prior measurements로 결정적 — R-1 측정 of new alpha 가능성 부재

### Falsification mechanism (categorical)

paradigm 67 H5 sign-split 발견 (BTC up-trig LONG t=+3.58 / BTC down-trig LONG t=-2.73)이 **invertible mirror가 아닌 asymmetric microstructure** — paradigm 70 mirror SHORT graveyard가 명시적 입증. 즉:
- BTC up + alt LONG = real alpha (paradigm 69 R-5)
- BTC down + alt SHORT ≠ symmetric mirror alpha — **fee-floor + asymmetric microstructure로 음수**
- sign-cond bilateral integration은 단순 quadrant union, mechanism layer 추가 아님

paradigm 155는 paradigm 69 (A focus production) + paradigm 70 (B same-sign graveyard) 합집합이며, sub-cells 독립 측정값 합산 = mean(known +112bp + known -49bp + known -100bp + known -150bp) / 4 = **~-47bp/trade aggregate** (well below fee floor). 4-cell narrow scope 자격 시도 시 Lesson #20 4-cond all-pass 의무 + Concentration Gate 별도 통과 필요하나 prior measurements가 1/4 PASS only (paradigm 69 A focus only) → Lesson #20 자격 불가.

---

## Graveyard classification

**Verdict**: R0_HALT_BY_DNA_DUPLICATE_AND_PRIOR_FALSIFICATION

**Family proxy contribution**: btc_rv_p90_alts_directional sub-class **5번째 누적 graveyard** (62 contagion + 67 recovery + 68 up-cond R-3.5 + 70 mirror SHORT + **155 sign-cond bilateral**). paradigm 69 LONG R-5 seeded exception 유일. **btc_rv_p90_alts family 추가 variant Tier 4 retire 권고** (paradigm 69 mirror/sign-cond/retiming/2-quadrant 등 모든 sub-class 소진).

**Lessons cross-reference**:
- Lesson #62 CONFIRMED retiming reframe — strict dim count 1/6 fail (dogfood 통과)
- Lesson #19 Symmetric Negative Test — 4-quadrant prior measurement coverage 사례
- Mirror hypothesis antipattern (메모리 명시 paradigm 70 graveyard) — 직접 dogfood
- Lesson #56 SELF-validation track — paper baseline measurement이 R-1 ad-hoc rerun보다 우선

---

## Lesson #66 candidate (NEW)

**Title**: "Sign-conditional bilateral reframe of unidirectional R-5 paradigm가 mirror antipattern + dim-count fail double-bind"

**Statement**: R-5 active unidirectional paradigm X (예: LONG-only)을 sign-conditional bilateral (LONG+SHORT)로 reframe 시:
1. 새 quadrant 중 mirror direction이 이미 별도 paradigm Y로 graveyard된 경우 = mirror antipattern direct violation
2. 동시에 trigger/universe/regime filter 동일 유지하면 Lesson #62 strict dim count ≤1 → CONFIRMED retiming reframe family-distinct audit fail
3. 두 조건 동시 발생 시 R-0 prescreen halt 의무 — R-1 측정 정보값 0bit

**Dogfood candidate**: paradigm 155 (paradigm 69 R-5 sign-cond reframe → paradigm 70 mirror antipattern + Lesson #62 1/6 strict)

**Second dogfood 요건**: 향후 다른 R-5 paradigm sign-cond reframe 시도 시 동일 패턴 발생 시 CONFIRMED 승급.

---

## Next-action recommendation

1. **Today: Day 7 baseline measurement 우선** — paradigm 69 R-5 paper baseline 2026-05-21 Day 7 (오늘) 측정 예정. paradigm 155 ad-hoc rerun보다 production paradigm 69의 실측 baseline이 SELF-validation primary source. 메모리 [[project-paradigm-campaign-continuous-parallel]] 정책상 baseline 측정과 paradigm dispatch 병렬 트랙이지만, paradigm 155처럼 4/4 quadrant 사전 결정 case는 dispatch 가치 부재.

2. **Family retire 권고 ratification**: btc_rv_p90_alts sub-class family Tier 4 formal retire (62+67+68+70+155 5-graveyard 누적, paradigm 69 R-5 exception only). 향후 BTC RV + 13 alts + p90 vol filter axis variant 자동 차단.

3. **Lesson #62 dogfood success**: paradigm-architect r0_inventory_check가 retiming-only reframe family-distinct 4-dim audit으로 R-1 자원 사전 차단. Lesson #62 CONFIRMED 정식 승급 1 dogfood 추가.

4. **다음 dispatch axis 권고**: btc_rv family 추가 variant 대신 **다른 macro proxy axis** — 예: BTC funding rate p90 regime + alt directional, BTC open interest velocity p90 + alt sign-cond, BTC liquidation density regime + alt 등 **trigger statistic class 자체 변경** (Lesson #62 ≥2 strict dim 만족).
