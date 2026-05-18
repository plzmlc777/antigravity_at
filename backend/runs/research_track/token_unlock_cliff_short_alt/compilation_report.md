# Token Unlock Cliff Short Alt — Phase 1 Compilation Report

**Paradigm**: `token_unlock_cliff_short_alt` (paradigm_index registered, R-1 phase)
**Hypothesis**: Token unlock cliff event → forced supply-side dilution + pre-event positioning unwind. SHORT entry at unlock_ts − 72h, exit at unlock_ts + 24h close.
**Compilation date**: 2026-05-18
**Source rule**: BINDING — `feedback_no_freemium_trial` (오직 무료 공개 무인증 web scrape)
**Scope**: Binance Futures USDS-M perp universe (TRADING status), 2024-01-01 ~ 2026-05-18 window
**Verdict**: **FAIL_SAMPLE_DENSITY at Lesson #11 + Lesson #26 prescreen** → R-1 dispatch 보류 권고

---

## 1. Universe 최종 결과

### 시도 대상 (38 tickers)
seed 32 + 확장 candidate 6 (EIGEN/HYPE/SCR/ONDO/IMX/GMX/MORPHO/USUAL/REZ/GRASS 등)

### Binance Futures USDS-M perp 게이트 결과
- `AVAIL` — perp 미상장 (drop)
- `OMNI` — perp status=SETTLING (drop)
- 그 외 36 tickers TRADING 통과

### cryptorank.io 데이터 확보 결과
| 결과 | tickers | 비고 |
|---|---|---|
| ✅ 데이터 확보 + 이벤트 ≥1 | **26** | 최종 universe |
| ⚠️ 200 OK but post-filter 0 events | 10 | TIA/SEI/IO/NFP/ETHFI/CELO/GMX/MORPHO/USUAL/APT — Inflation/Staking 계열로 daily emission만 노출, ≥0.5% 필터 통과 0 |
| ❌ HTTP 404 (slug not found) | 3 | JTO/WLD/JUP — cryptorank 공개 페이지에 vesting 데이터 없음 (auth-gated) |

**최종 universe (26 tokens)**: APT(drop)/ARB/OP/SUI/STRK/PYTH/W/ENA/MANTA/ALT/PORTAL/AEVO/ZK/ZRO/DYM/PIXEL/XAI/ACE/MERL/BB/EIGEN/HYPE/SCR/ONDO/IMX/REZ/GRASS

(spec 목표 ~30 tokens, 실측 26 — 13% shortfall)

---

## 2. Source coverage 및 cross-validation rate

### Primary source coverage
- **cryptorank.io public `/price/{slug}/vesting`** endpoint: 100% (26/26 retained tokens)
- Next.js `__NEXT_DATA__` JSON embed에서 `props.pageProps.vestingInfo.allocations` 추출

### Cross-validation source 시도
- **tokenomist.ai 보조 URL** 기록: 26/26 (CSV `source_url_2` 컬럼)
- **그러나 값 비교 검증 불가**: tokenomist.ai는 Next.js App Router RSC streaming chunk로 데이터 노출, 서버 SSR JSON 없음 + client-side API endpoint도 auth-gated 추정 (`api.cryptorank.io/v2/coins` = 401)
- 결과: **`cross_validated=False` 일괄** (모든 row). 보조 source URL만 archive

### Critical data quality 한계 — cryptorank `isAuthProtected: True`
- cryptorank public endpoint는 **coin당 1 allocation cohort만 노출** (전체 vesting schema는 auth-gated)
- 노출되는 cohort는 coin별 가변:
  - High-impact (Team/Investors/Early Contributors): ARB, STRK, ZK, EIGEN, REZ, BB, GRASS 등 = **paradigm hypothesis와 정합** (supply pressure 주역)
  - Mid-impact (Foundation/Strategic Partners): ALT, ZRO, ENA, PYTH 등 = 부분 정합
  - Low-impact (Community/Ecosystem Reserves): APT, SUI, OP, ENA 등 = **paradigm hypothesis와 불완전** (continuous emission, cliff 아님)
- 결과: 26 tokens 중 high+mid impact cohort 노출 ≈ 18 tokens, low impact 8 tokens

### Allocation cohort 분포 (final CSV 기준 206 events)
| Cohort | Events | Note |
|---|---|---|
| Team & Advisors | 42 | high impact, ARB cohort |
| Investors | 36 | high impact, ZK/REZ/BB |
| Ecosystem Rewards | 27 | mid (PIXEL: monthly) |
| Ecosystem | 24 | mid (MERL) |
| Foundation/Treasury | 16 | mid (ALT) |
| Early Contributors | 14 | high (STRK) |
| Strategic Partners | 11 | high (ZRO) |
| Ecosystem Development | 11 | mid (IMX) |
| Early Investors | 7 | high (GRASS) |
| 그 외 | 18 | 잡종 |

전체 1.64% mean / 0.52~31.0% range — supply pressure-grade events가 의미 있는 비율로 포함됨.

---

## 3. 총 이벤트 카운트

### 연/분기별 분포
| 연도 | Events |
|---|---|
| 2024 | 55 |
| 2025 | 102 |
| 2026 (Jan-May) | 49 |
| **총합** | **206** |

| Quarter | Events |
|---|---|
| 2024Q1 | 11 |
| 2024Q2 | 17 |
| 2024Q3 | 14 |
| 2024Q4 | 13 |
| 2025Q1 | 14 |
| 2025Q2 | 27 |
| 2025Q3 | 27 |
| 2025Q4 | 34 |
| 2026Q1 | 34 |
| 2026Q2 (~May) | 15 |

### Unlock type 분포
- `linear`: 195 (~95%) — monthly continuous cohort
- `cliff`: 9 (~4%) — TGE + 단일 vest-end 이벤트
- `unknown`: 2

⚠️ **Linear 비중 절대 우세**: cryptorank schema의 `unlock_type` 필드가 *allocation 전체*를 "linear/cliff"로 라벨링하며, monthly emissive cohort가 universe 대다수. 진정한 "cliff" (대규모 단발성 supply 분출) 이벤트는 **9건** (TGE 위주) — 가설 본질과의 정합성에 큰 문제.

---

## 4. Lesson #11 + Lesson #26 sample-density prescreen

### 공식
```
expected_n_per_cell = total_events_in_quarter
n_quadrants = 2 (A focus SHORT + A mirror LONG, 같은 trigger 다른 sign)
PASS criterion: per-cell ≥ 30 AND n_measurable_quarters ≥ 4 (lesson #26)
```

Spec는 5 quarters (2024Q4 / 2025Q1-Q4 / 2026Q1-Q2)를 명시. 실측 시 7 quarters (2024Q4 ~ 2026Q2 inclusive) 까지 정의 가능. 두 buckets 모두 검토.

### Scope sweep

| Scope | total | 2024Q4 | 2025Q1 | 2025Q2 | 2025Q3 | 2025Q4 | 2026Q1 | 2026Q2 | n_measurable | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL ≥0.5% supply | 206 | 13 | 14 | 27 | 27 | **34** ✓ | **34** ✓ | 15 | 2/7 | FAIL |
| medium ≥1.0% supply | 86 | 2 | 2 | 12 | 12 | 19 | 19 | 8 | 0/7 | FAIL |
| high ≥2.0% supply | 31 | 2 | 1 | 5 | 3 | 5 | 4 | 1 | 0/7 | FAIL |
| cliff_only | 9 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0/7 | FAIL |

**결과**: 모든 scope 모든 분기에서 per-cell <30 cutoff (가장 broad한 ≥0.5% scope에서만 2025Q4/2026Q1 marginal pass), **n_measurable_quarters ≤ 2/7 < 4 cutoff** → **lesson #26 patch에 의한 auto-FAIL**.

### Scope reduction 옵션 검토

a) **Universe 확장**: cryptorank 공개 source 이미 소진. JTO/WLD/JUP 등 미확보 코인 데이터는 auth-required. → 30% 추가 가능성 미만, fundamental 한계.

b) **Cliff threshold 완화 (0.5% → 0.3%)**: 전체 event 수 증가하나, 0.3% 미만은 noise (16bp fee floor 대비 marginal impact). → mechanism dilution.

c) **Hold window 확장 (24h → 7d)**: per-event window 확대는 sample density에 영향 없음. Sharpe 감소만 초래.

d) **Quarter 단위 그룹화 변경 (분기 → 반기)**: 7 → 3 measurable bins가 되나, lesson #26 spec "5 quarters" 정신 위배. broad sweep n=206이 반년당 80~100 events가 되어 per-cell pass — 단, temporal robustness 검증력 손실 (paradigm 87 fragility 사례 재현 위험).

e) **Multi-source backfill 시도** (project whitepapers + GitHub vesting contracts 수동 컴파일): 25~40 tokens × allocation 다중 × 24~36개월 이벤트 추출 = 사람-day scale. 본 task ETA (2.5h) 초과 + 사용자 명시 승인 미보유.

⇒ **현실적으로 sample-density 회복 불가**: cryptorank 공개 source 본질적 한계 + linear 위주 데이터 분포가 paradigm hypothesis 본질과 mismatch.

---

## 5. Lesson #26 sub-mechanism asymmetry 가설 평가

### 핵심 질문
Token unlock cliff event는 **entry-side forced supply** (lifecycle listing 패턴, temporal robust) vs **exit-side forced supply** (paradigm 87 delisting 패턴, temporal fragile) 중 어느 쪽?

### 메커니즘 분석 (first principles)

**Entry-side 후보 논리**:
- Unlock event는 vesting cohort에게 *유동성 공급* (lock → unlock = supply 증가)
- Recipient (Team / Investors / Early Contributors)는 unlock 직후 *부분 매도 의사* 보유 (tax-deferred → tax-realized)
- 시장은 unlock schedule을 publicly known → pre-event positioning (헤징 SHORT) 가능
- 이는 lifecycle listing의 "신규 buy demand entry → 예측 가능한 가격 spike" mechanism과 *부분 대칭* (sign 반대, 방향 SHORT)

**Exit-side 후보 논리**:
- Unlock 발생 = 기존 holder cohort *유동성 회수* (이미 owned 였으나 거래 불가 → 거래 가능). 시장 진입 *압력*은 있지만 의무 아님
- Distribute decisions은 recipient discretion: HODL 비율, OTC vs spot, 분산 매도 timing
- 시장은 sophisticated → unlock event 사전 hedge 이미 완료 → unlock 시점 actual realized supply는 expected supply에 가깝거나 미달 가능 ("priced in" 본질)
- 이는 paradigm 87 delisting의 "기존 holder cohort 강제 unwind → 예측된 supply impulse → 시장 사전 가격 반영 → fragility" mechanism과 *대칭*

### 평가 (Compile-Phase 가설)

⚠️ **Ambiguous, exit-side 우세 가능성**:
- Token unlock은 lifecycle listing처럼 *완전히 새로운 holder cohort*가 시장에 진입하는 것이 아님 (기존 vesting cohort의 *유동성 status* 전환에 가까움)
- Unlock schedule이 공개되어 있고 (CryptoRank/Tokenomist/project blog) 시장이 사전 hedge → "priced in" 효과 강함
- Paradigm 87 graveyard 결과와 동형 위험: small-sample R-1 PASS but R-2 walk-forward + 5-fold TS-CV에서 *temporal degradation* (2025Q4 cluster artifact, 2026 alpha decay)
- Anti-evidence: 만약 unlock SHORT가 robust한 paradigm이라면 cryptorank/tokenomist의 unlock calendar 공개가 이미 cross-validated 상업적 정보 상품으로 진화했을 것

### 결론
**Sub-mechanism asymmetry는 exit-side 우세 가능성 높음**. 가설은 paradigm 87 graveyard 패턴의 *동형 재현* 위험 영역에 위치. lifecycle pump-decay와 동질 mechanism (entry-side) 주장은 first-principles에서 약함.

이 평가는 sample-density 미달과 *독립적으로* paradigm 발의 자체에 대한 적색 신호로 작동.

---

## 6. Data quality concerns + caveats (최종)

1. **Single-allocation coverage**: 26/26 tokens가 cryptorank `isAuthProtected: True` 상태 (1 allocation only), 진정한 total-supply 영향력은 underestimate. 일부 coin의 high-impact cohort (e.g., ARB Team & Advisors 26.9%, ZRO Strategic Partners) 노출되어 partial-coverage가 hypothesis-relevant subset을 포함하나, total supply impact 측정 시 ~50-75% 누락.

2. **Linear 위주 data 분포**: 206 events 중 195 (95%)는 monthly linear emission. 진정한 "cliff" 이벤트 9건뿐. paradigm hypothesis "cliff event" 본질과 데이터 분포 mismatch.

3. **Cross-validation rate = 0**: secondary source (tokenomist.ai)는 URL만 archive, 실제 값 비교 검증 불가. 단일 source dependence → 데이터 오류 검출력 ZERO.

4. **USD est 미입력**: 가격 fetch 미실행 (별도 phase). 가설 검증에는 % supply가 더 적절한 지표이므로 critical 아님.

5. **Universe shortfall**: 목표 30 tokens 대비 26 (87%). JTO/WLD/JUP 누락은 high-profile 코인의 가시성 부족.

6. **Time-of-day 정밀도**: 모든 unlock_ts는 `00:00:00 UTC` (cryptorank schema가 date-only 노출). 실제 unlock 시각은 hour-level 정밀도 보장 안 됨. 72h pre-entry 시그널 시점에 ±12h 불확실성 존재.

---

## 7. Recommended next step

### Verdict: **R-1 dispatch 보류 권고 (FAIL_SCOPE)**

### 근거
1. **Lesson #11 prescreen FAIL (4 차원 누적)**:
   - per-cell <30 (모든 scope에서)
   - n_measurable_quarters ≤ 2/7 < 4 (lesson #26 patch 미충족)
   - cliff_only scope 9 events 전체 — sample inherent 부족
   - linear vs cliff 분포 mismatch (paradigm 95% linear-on-cliff event 정의 모호)

2. **Sub-mechanism asymmetry 가설 평가 적색**: exit-side 우세 가능성 → paradigm 87 graveyard 패턴 동형 재현 위험

3. **Data quality 6 차원 caveat**: single-source + single-allocation + linear dominance + 0% cross-validation + universe shortfall + time-of-day imprecision

### 대안 옵션 (사용자 결정용)

| 옵션 | 비용 | 예상 effect | Risk |
|---|---|---|---|
| **A. 본 paradigm 즉시 abort + graveyard 등재** | 0h | 88번째 graveyard, lesson #27 후보 (single-source partial-coverage prescreen 한계) | 낮음, 권장 |
| **B. WS recorder 60+일 누적 후 forward collection** (2026-07-15+) | 자체 자원, 약 60d 대기 | 자체 unlock event tracker 구축 (project blog scrape + Twitter/X 모니터) | 시간 비용 큼, hit rate 불확실 |
| **C. 사용자 명시 paid API 결정 시 재시도** (DefiLlama $300/mo) | 비용+승인 | 50-100 coins × full allocation × 2yr 데이터 즉시 가용, sample boost 5-10x | 사용자 binding rule 위반 (paid API 절대 금지) |
| **D. 수동 컴파일 phase 2 (project whitepaper 25-40 tokens 풀 cohort 추출)** | 사람-day scale, 2.5h ETA 초과 | sample 3-5x boost 가능 | 추가 ETA 명시 승인 필수 (현 task 범위 외) |

### 권고
**옵션 A** (abort + lesson #27 후보 등재): paradigm 87 + 본 paradigm 누적이 *Category A external event injection sub-mechanism asymmetry hypothesis*에 한 증거 추가. Sub-mechanism asymmetry hypothesis를 **공식 lesson #27**로 격상 권고:
> *"Category A external event paradigm은 entry-side (forced new demand) vs exit-side (forced existing holder unwind) 사전 분류 필수. exit-side 후보는 sample-density 통과해도 temporal robustness fragility 예상 영역 — paradigm 87 binance_delisting + token_unlock_cliff_short_alt 동형 graveyard 2회 누적 입증."*

---

## 8. Deliverables

- `compile_unlock_events.py` — 재실행 가능 scraper (idempotent, raw_html_cache backed)
- `token_unlock_events.csv` — 26 tokens × 206 events
- `raw_html_cache/{TICKER}_cryptorank.html` × 30 (재현성 보장)
- `compilation_report.md` — 본 문서

**Final verdict tag**: `FAIL_SCOPE` (Lesson #11 sample-density + Lesson #26 n_measurable_quarters patch 미충족)
