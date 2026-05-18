# Phase 0 Fundamental Limitation Report
## paradigm `listing_pre_announce_leak_long_alt` — R-1 dispatch BLOCKED

**Date**: 2026-05-18 KST 16:25
**Agent**: paradigm-architect (life-changing campaign 2차 세션 third dispatch)
**Verdict**: **DISPATCH_IMPOSSIBLE_AS_SPECIFIED** — 가설 그대로는 데이터 인프라 본질 제약으로 R-1 실행 불가능. 4 대안 변형 evaluation 후 사용자 결정 대기.

---

## 1. 가설 원문 요약
- Binance Futures USDS-M perp listing announcement T-48h ~ T+5min window에서 informed trader pre-positioning detection → LONG alpha
- Entry: announcement_ts − 48h close, Exit: announcement_ts + 5min close
- Listed perp universe: 2024-01-01 ~ 2026-05-18, 388 events 확인

## 2. Phase 0 fundamental verification (실측 결과)

### 2.1 핵심 사실 — listed perp pre-announce window OHLCV 부재
Binance Futures USDS-M perp는 **onboardDate(=listing 시점)부터만 거래 시작**. 그 이전 시점 OHLCV는 데이터 자체가 존재하지 않음.

5/5 youngest listings 대상 data.binance.vision archive HTTP 직접 probe 결과:

| Symbol | onboard | T-48h date | HTTP (T-48h) | HTTP (post+1d, control) |
|---|---|---|---|---|
| BILLUSDT | 2026-05-07 | 2026-05-05 | **404 absent** | 206 present (60,691 bytes) |
| AMDUSDT | 2026-05-06 | 2026-05-04 | **404 absent** | 206 present (47,741 bytes) |
| QCOMUSDT | 2026-05-06 | 2026-05-04 | **404 absent** | 206 present (40,000 bytes) |
| USARUSDT | 2026-05-06 | 2026-05-04 | **404 absent** | 206 present (42,504 bytes) |
| AIGENSYNUSDT | 2026-04-29 | 2026-04-27 | **404 absent** | 206 present (60,167 bytes) |

→ **5/5 (100%) pre-announce archive ABSENT, 5/5 control archive PRESENT** = 데이터 인프라 본질 한계 확정

### 2.2 메커니즘 차원 진단
- paradigm 87 `binance_delisting_announce_short_alt`: announcement 시점 perp **이미 거래 중** (listed status) → announce ~ delist 사이 window OHLCV 가용 → R-1 dispatch 가능 (실제 PASS_R1_FULL 도달, 후 R-2 small-sample fragility로 graveyard)
- 본 paradigm `listing_pre_announce_leak_long_alt`: announcement 시점 perp **아직 거래 미시작** (pre-listed) → pre-announce OHLCV 부재 → R-1 dispatch 불가능

**Asymmetry 원인**: listing-side는 mechanism이 "신규 demand entry"인 반면 본 paradigm은 mechanism을 "기존 거래 신호 사전 detection"로 정의했으나 **그 신호의 measurement substrate(=listed perp 가격)가 시간 차원에서 존재하지 않음**. 이는 paradigm 87와 dual하지만 더 깊은 인프라 한계.

---

## 3. 4 대안 변형 evaluation (사용자 결정 대상)

### (i) Spot pre-existence variant ⭐⭐⭐ (가장 유망)
**Mechanism**: listed perp symbol이 Binance Spot에 **이미 거래 중**인 경우 한정 (subset). Pre-announce window는 spot 가격 변동으로 측정.

**Data availability 실측**:
- 최근 20 youngest (2026-04~05): **0/20 (0%)** spot pre-existence (미국 주식 토큰 + commodity perp 신규 카테고리 영향)
- 2024-01 ~ 2025-12 random 30: **7/30 = 23.3%** spot pre-existence
- 388 events × 23.3% ≈ **~90 effective events**

**Lesson #11 + #26 prescreen 예측**:
- 2-quadrant × 5 quarters = 10 cells → per-cell 9.0 (≪ 30 cutoff)
- 4-quadrant Symmetric Negative Test → per-cell 4.5 (절대 미달)
- 2-quadrant reduce + 사용자 명시 승인 시 per-cell **22.5** (여전히 미달)
- **n_measurable_quarters 5/10 < 4 cutoff 통과** but per-cell <30 cutoff FAIL

**Mechanism 평가**:
- Spot 가격이 perp listing 사전 가격 발견 substrate 합리적 (informed leak hypothesis 충실)
- 하지만 최근 1년 트렌드 (US equity tokenization 가속, exotic asset perps)는 spot pre-existence 비율 급감 — 시간 진행 시 더욱 sparse
- Bias risk: spot pre-existence가 있는 symbol은 이미 유동적 (잘 알려진 token) → "이미 efficient market" subset bias

**ETA**:
- Binance announcement scrape (cat 48 "New Crypto Listings"): paradigm 87 scrape_delistings.py base 재활용, ~15-20분
- Spot OHLCV 1m archive 백필 (~90 events × 3d window): ~10분 (data.binance.vision)
- R-1 script + execute: ~30-40분

**판정**: 메커니즘 alignment 우수 + 데이터 인프라 가용. 단 **per-cell sample density 22.5 (cutoff 30 미달)** + **n_measurable_quarters 만 통과** → **lesson #11 SAMPLE_INSUFFICIENT halt 예상** (paradigm 88 token unlock과 동형 fail). dispatch 가치 borderline.

### (ii) Cross-exchange pre-existence variant ⭐
**Mechanism**: 다른 거래소 (Bybit / OKX / Coinbase / Coinbase Pro / Kraken) spot/perp에 이미 거래 중인 경우 pre-announce window 가격 변동 측정.

**Data availability**:
- Bybit/OKX/Coinbase public REST API 가용 (yfinance 비제외) — 단 **memory rule [[feedback_credentials_in_db]] + 캠페인 universe binding [[feedback_universe_reframe_binance_perp]]**에 따라 "Binance 외 거래소 (Bybit/OKX/Coinbase 등)" 명시 제외 영역
- 사용자 explicit 승인 + universe binding 일시 해제 필요

**Mechanism 평가**:
- 사전 추정 pre-existence rate >70% (대부분 알려진 token은 다른 거래소에 먼저 listed)
- Sample density 회복 (388 × 0.7 = ~270 events → 4-quadrant 67.5/cell pass)
- 하지만 cross-exchange 가격 dynamics는 paradigm 자체 변경 (Binance perp informed leak ≠ cross-exchange spillover)

**ETA**:
- Universe binding 해제 결정 대기 (사용자 결정 필요)
- 데이터 source 추가 (Bybit/OKX REST API rate limit handling): ~1-2시간 백필 + ~30분 R-1

**판정**: 데이터 차원에서 sample 회복 가능 but **universe binding 위반** + **paradigm DNA 변경** (mechanism이 "Binance pre-announce leak" → "cross-exchange information cascade"로 본질 변경). **별도 paradigm 발의 + 별도 universe 결정**이 정확. 본 paradigm 변형으로는 부적합.

### (iii) Macro proxy variant ⭐ (가설 분리)
**Mechanism**: BTC/ETH의 pre-announce window 가격 movement가 향후 listing events에 어떻게 cluster하는지 측정 (macro proxy로 informed flow detection).

**Mechanism 평가**:
- BTC/ETH는 항상 trading → 데이터 인프라 가용
- 단 mechanism이 본 가설("listed symbol pre-positioning")과 분리됨 — BTC가 다음 listing event를 예측하는지 측정은 cross-asset event prediction 차원 paradigm
- 387 events × BTC pre-announce returns = 387 observations 가능 (4-quadrant 96.7/cell pass)

**Mechanism alignment 우려**:
- BTC 가격 변동은 listing announcement에 leading indicator일 이론적 근거 약함 (BTC는 macro driver, listing은 micro event)
- 통계적으로 발견되는 신호가 mechanism으로 해석 가능 여부 불명확

**ETA**: paradigm 87 scrape 17초 + BTC 1m OHLCV 이미 cached → R-1 ~20분

**판정**: 데이터/sample 충분. **하지만 paradigm DNA 본질 변경** (entry signal substrate가 listed symbol → BTC). 별도 paradigm 발의 (`listing_event_btc_macro_leading_indicator`) 가능 but 본 paradigm `listing_pre_announce_leak_long_alt`와 동일시 부적합. **신규 paradigm으로 분리 등록 권고**.

### (iv) Post-only variant (가설 폐기) ❌
**Mechanism**: pre-announce 차원 폐기, T+5min ~ T+24h post-announce window만 측정.

**평가**:
- Lifecycle `pump_decay` (이미 R-5 seeded) sub-spec과 차원 분리 어려움 (둘 다 announcement 직후 post-event)
- Listing의 가장 강한 mechanism은 onboard 시점 forced flow → 이미 lifecycle paradigm 단독 점유
- **신규 paradigm 가치 0** — lifecycle paradigm 직접 중복

**판정**: 명시적 폐기. 본 변형은 dispatch 가치 없음.

---

## 4. 종합 평가 + 권장

### 4.1 4 변형 ranking

| Variant | Mechanism alignment | Data availability | Sample density | DNA fidelity | 권장 |
|---|---|---|---|---|---|
| (i) Spot pre-existence | ⭐⭐⭐ (excellent) | ✅ archive 가용 | ⚠️ 22.5/cell (lesson #11 borderline) | ⭐⭐⭐ (close) | **유일한 정통 변형 but borderline SAMPLE_INSUFFICIENT** |
| (ii) Cross-exchange | ⭐⭐ (DNA shift) | ⚠️ universe binding 위반 | ✅ 67.5/cell pass | ⭐ (분리 paradigm) | 별도 paradigm 등록 필요, 본 paradigm 변형 부적합 |
| (iii) Macro proxy BTC | ⭐ (substrate 변경) | ✅ 충분 | ✅ 96.7/cell pass | ❌ (다른 paradigm) | 별도 paradigm 등록 필요 |
| (iv) Post-only | ❌ (lifecycle 중복) | N/A | N/A | N/A | **명시 폐기** |

### 4.2 핵심 결정 사항

**원본 가설 (`listing_pre_announce_leak_long_alt`)은 데이터 인프라 본질 제약으로 R-1 dispatch impossible** — 5/5 youngest listings pre-announce archive HTTP 404 confirmed.

3 productive 옵션 (사용자 결정 대상):

**옵션 A**: variant (i) Spot pre-existence로 paradigm 정의 수정 + R-1 dispatch
- Sample density 22.5/cell이 lesson #11 cutoff 30 미달 → **paradigm 88 token unlock과 동형 SAMPLE_INSUFFICIENT prescreen halt 예상**
- ETA ~50-70분 (scrape + spot OHLCV 백필 + R-1)
- **추천도**: 낮음 (paradigm 88 graveyard 학습 무시, 예측 가능한 fail)

**옵션 B**: variant (iii) BTC macro proxy로 신규 paradigm 등록 + 본 paradigm graveyard
- DNA 변경 — 신규 paradigm 발의 (`listing_event_btc_macro_leading_indicator` 또는 유사)
- 본 `listing_pre_announce_leak_long_alt` paradigm은 **DATA_INFRASTRUCTURE_IMPOSSIBLE** graveyard 등록
- **추천도**: 중간 (mechanism alignment 약함 but sample 충분 + 신규 paradigm slot)

**옵션 C**: 본 paradigm **DATA_INFRASTRUCTURE_IMPOSSIBLE graveyard** + 신규 lesson #28 등록
- 차세대 lesson: "Entry-side external event paradigm은 measurement substrate 시간 차원 존재 가능성 prescreen 의무. paradigm 발의 시점에 substrate availability verification (data.binance.vision archive probe) 강제"
- Category A entry-side sub-mechanism 확장 더 정밀한 후보 brainstorm (예: ETH/SOL network upgrade pre-event, ETF approval pre-vote, FOMC pre-announce 등 measurement substrate 항상 존재 paradigm 우선)
- **추천도**: 가장 높음 (research track 학습 가치 최대 + 다음 dispatch 자원 보존)

### 4.3 paradigm-architect 권장
**옵션 C 권장** — 본 paradigm은 graveyard 처리, lesson #28 등록, Category A entry-side 후보 재선정 후 다음 dispatch 결정.

근거:
1. **옵션 A는 lesson #11 + #26 동형 fail 예측 가능** (paradigm 88 token unlock SAMPLE_INSUFFICIENT 학습 직접 적용). 추가 R-1 cycle 자원 소모 후 동일 결론 도달.
2. **옵션 B는 paradigm DNA 본질 변경** = 새 paradigm 발의가 정확한 표현. 본 paradigm slot에 다른 mechanism 끼워넣지 않는 것이 INDEX cleanliness 유지.
3. **옵션 C는 lesson 도출 가치 최대** — paradigm-architect spec failure protocol에 "substrate existence prescreen" hook 추가 권고 (paradigm 87+88 sub-mechanism asymmetry lesson #27 + 본 lesson #28 누적은 Category A external event injection family 발의 패턴 강제화).

---

## 5. Halt + 사용자 결정 대기

**현 상태**: paradigm `listing_pre_announce_leak_long_alt` R-1 dispatch BLOCKED at Phase 0 verification. 데이터 인프라 본질 제약 5/5 listings 실증 확인. 4 대안 evaluation 완료.

**사용자 결정 대기 항목**:
- 옵션 A (variant i Spot pre-existence) / B (variant iii BTC macro 신규 paradigm) / C (graveyard + lesson #28) 중 선택
- 옵션 C 채택 시 신규 Category A entry-side 후보 brainstorm (ETH Pectra / SOL Firedancer / ETF approval / FOMC pre-event 등) 별도 turn 진행 결정

**산출물**:
- `backend/runs/research_track/listing_pre_announce_leak_long_alt/phase0_fundamental_limitation.md` (본 문서)

**INDEX 상태**: paradigm phase R-1 유지 (아직 graveyard 처리하지 않음 — 사용자 결정 후 처리)

---

KST 2026-05-18 16:25
