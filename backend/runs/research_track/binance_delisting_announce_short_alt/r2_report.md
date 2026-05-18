# R-2 Report — binance_delisting_announce_short_alt

**Date**: 2026-05-18 (KST)
**Phase**: R-2 (Symmetric Negative Test 4-quadrant 완성 + Walk-forward 시간 robustness)
**Inherits**: R-1 PASS_R1_FULL (commit 925c5c04, n=57 events 2024-11~2026-04)
**OVERALL R-2 VERDICT**: **FRAGILE_TEMPORAL_WF_FAIL**

---

## 1. 가설 분해 (R-1 재기재)

- **데이터 차원**: External event injection (Binance announcement scrape × OHLCV 1m perp)
- **의사결정 모드**: Forced-exit liquidity drift (제도적 강제청산 압력)
- **시간 척도**: announce_ts+5min → delist_ts−24h (≈3-13d hold, median 8d)
- **Sub-hypotheses**:
  - A focus  : 상장폐지 발표 후 announce-window 내 SHORT alpha 존재 (forced-exit 흐름)
  - A mirror : 동일 window LONG (반증: 과매도-패닉-리버설 counter-hypothesis)
  - B same-sign : 상장폐지 시점 이후 24h LONG 회복 (continuation 반대 가설)
  - B mirror : 상장폐지 시점 이후 24h SHORT (continuation 가설)

---

## 2. Part 1 — 4-quadrant Symmetric Negative Test (Lesson #19 완성)

### B variant 데이터 가용성 (Lesson #22 source-frequency check)
- **n_with_post_delist_data = 57 / 57** (R-1 backfill 시점에 cache가 delist_ts+48h까지 포함)
- **n_meeting_1h_cutoff = 57 / 57** (full 24h B 측정 feasible, restricted fallback 불필요)
- post_delist_hours: min=48 / max=48 / median=48 — 균일 가용

### 4-quadrant matrix (fee_baseline = 16 bp round-trip)

| Variant | n | obs_t | sigex | ci_bp | perm_p | median% | win | 3gate | E-type | freq | concentration |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A focus SHORT** | 57 | +4.66 | +2.23 | [+782, +1951] | 0.062 | +14.6% | 71.9% | **PASS_both_fee_levels** | FAIL (median 14.6%<15, perm_p>0.05) | PASS | PASS (q=1.00 sign=72%) |
| A mirror LONG | 57 | −4.71 | −2.24 | [−1967, −798] | 0.064 | −14.8% | 26.3% | FAIL | FAIL | FAIL | FAIL |
| B same-sign LONG | 57 | −1.90 | −0.26 | [−1323, +58] | 0.416 | −5.13% | 17.5% | FAIL | FAIL | FAIL | FAIL |
| B mirror SHORT | 57 | +1.85 | +0.28 | [−74, +1307] | 0.406 | +4.97% | 82.5% | FAIL | FAIL | FAIL (sharpe sub-cutoff) | PASS (q=0.67 sign=83%) |

### 핵심 관찰

- **A focus** R-1 결과 정확 재현 (코드 결정성 확인)
- **A mirror** 정확히 대칭 음수 (perm null 비대칭 trap 없음)
- **B same-sign LONG**: 명백한 FAIL — post-delist 24h에 가격이 추가 하락하는 패턴 (continuation downside)
  - sign_ratio 17.5% → 47/57 syms가 음수 (post-delist 추가 dump)
  - 이는 **A focus SHORT 메커니즘이 delist_ts−24h에서 끝나지 않음**을 시사 (alpha tail 존재)
- **B mirror SHORT**: gross +5%/+4.97% median이지만 hold 1d → fee 8bp+slippage 8bp 후 sigex +0.28에 그침
  - **continuation 가설은 직관적으로는 옳지만 (sign_ratio 82.5%) 통계적으로 fee floor를 못 넘김**
  - n=57 표본수에서 perm_p 0.41 = 통계적 미약, three-gate 모든 항목 FAIL

### Lesson #19 4-quadrant 결과 명시
- **R-1에서 deferred 했던 B variant 2-quadrant 측정 완료**
- **SPLIT_PARADIGM 발생 안 함** (B same-sign LONG 명백 FAIL, B mirror SHORT borderline FAIL)
- **broad-falsified 아님** (A focus 단독 PASS는 유지)
- **B mirror SHORT의 borderline 양상은** Lesson #19 antipattern 회피 (4-quadrant 측정 안 했으면 별도 paradigm dispatch로 추가 자원 소모)이 의의

---

## 3. Part 2 — Walk-forward 시간 robustness (A focus SHORT)

### Chronological 70/30 split

| Split | n | obs_t | sigex | ci_bp | perm_p | median% | win | 3gate |
|---|---|---|---|---|---|---|---|---|
| IS (first 70%) | 40 | +4.31 | +2.09 | [+892, +2324] | 0.085 | +20.1% | 72.5% | **PASS** |
| OOS (last 30%) | 17 | +1.89 | +0.18 | [+28, +1596] | 0.460 | +5.47% | 70.6% | **FAIL** |

- **drift_ratio (|OOS mean| / |IS mean|) = 0.47** ← cutoff 0.50 미달
- **walk_forward_pass = False** — OOS three-gate FAIL + drift_pass FAIL

### 5-fold TS-CV (chronological) 보강

| k | n | mean_bp | sigex | ci_lo_bp | perm_p | 3gate |
|---|---|---|---|---|---|---|
| 0 | 11 | +1237 | −0.32 | −792 | 0.612 | FAIL |
| 1 | 11 | +1376 | +0.95 | +322 | 0.237 | FAIL |
| 2 | 11 | +1316 | +0.77 | +184 | 0.287 | FAIL |
| 3 | 11 | +2556 | +5.05 | +1826 | 0.000 | **PASS** |
| 4 | 13 | +567 | −0.43 | −350 | 0.614 | FAIL |

- **fold_pass_count = 1 / 5** (오직 k=3, 2025-Q4 무렵)
- 5 folds 모두 양수 mean이지만 **k=3 외에는 fee+sample 한계로 통계적 유의 못 달성**
- 표본수 n=11/fold가 perm bootstrap 본질적 어려움 (R-1 n=57이 minimum threshold)

### Walk-forward 진단
- IS 강함 + OOS 양수 방향 (ci_lower +28bp > 0 — slight positive territory) 유지
- 그러나 **OOS sigex +0.18**: fee-saturated null과 구분 불가
- **drift_ratio 0.47**: 시간이 흐를수록 mean magnitude가 일관되게 감소 (2024-Q4 +44bp → 2025-Q3 +1986bp → 2025-Q4 +1601bp → 2026-Q1 +1995bp → 2026-Q2 +650bp; OOS 17 events 대부분 2026-Q1+Q2)
- **2026 들어 alpha 감쇠 확연** — 시장 참여자들이 이 패턴을 학습/선반영하기 시작했을 가능성 (delisting 사전 leak / informed selling acceleration)

---

## 4. Part 3 — R-2 PASS criteria (E-type, A focus SHORT)

R-2 E-type 표준 cutoff:
- median_ret ≥ 15% → **FAIL** (14.6%, R-1 사전 경고)
- win_rate ≥ 55% → PASS (71.9%)
- perm_p ≤ 0.05 → **FAIL** (0.062)
- ci_lower > 0 → PASS (+782 bp)

**E-type PASS: False** — 2/4 fail, marginal.

---

## 5. 4-dim Frequency-First Gate (campaign binding, per variant)

| Variant | trades/yr | edge% | util% | sharpe | verdict |
|---|---|---|---|---|---|
| **A focus SHORT (baseline)** | 40.5 | +14.63 | 36.7 | 6.49 | **PASS** |
| A focus SHORT (stress 50bp) | 40.5 | +14.46 | 36.7 | 6.41 | PASS |
| A mirror LONG | 40.5 | −14.79 | 36.7 | −6.56 | FAIL |
| B same-sign LONG | 41.1 | −5.13 | 11.3 | −4.79 | FAIL |
| B mirror SHORT | 41.1 | +4.97 | 11.3 | +4.68 | FAIL (sharpe<5? — sub-cutoff in sharpe? check) |

Note: B mirror SHORT freq verdict = FAIL은 sharpe 4.68 > cutoff 1.5이지만 edge% 4.97 > 2.0이고 util 11.3 < 30. **capital_utilization_pct < 30** 단일 차원이 발목 (1d hold × 57 events / 543d window = 10.5% util).

---

## 6. R-2 R-3-eligibility 최종 판정

**Overall verdict**: **FRAGILE_TEMPORAL_WF_FAIL**

판단 근거 우선순위:
1. **A focus three-gate**: PASS_both_fee_levels (fragile-fee 아님)
2. **A focus E-type**: 2/4 fail (median 14.6 vs 15, perm_p 0.062 vs 0.05) — marginal but technically FAIL
3. **Walk-forward**: IS PASS / OOS three-gate FAIL / drift 0.47 < 0.50 / 5-CV 1/5 PASS
4. **B variants**: SPLIT_PARADIGM 아님, broad-falsified 아님 — A focus 단독 mechanism 유지

**Critical signal**: 2026 들어 OOS half (17 events 중 14개가 2026-Q1+Q2) 에서 alpha drift 명백.
가능한 원인:
- (a) Binance announcement 사전 leak / informed flow가 announce_ts 이전 진입 (announce-window edge 축소)
- (b) Market makers가 이 패턴을 학습해 announce 후 forced-exit 압력에 미리 대응 (price impact 사전 반영)
- (c) 2026 H1 시장 환경 변화 (vol regime 차이 등) — 우연일 가능성

R-3로 진행해도 robustness 통과 가능성 낮음. **권고: R-3 dispatch 보류 또는 narrow 옵션 검토.**

---

## 7. 사용자 의사결정 옵션

### Option 1 — Graveyard (FRAGILE_TEMPORAL)
- R-2 OOS sigex 0.18, drift 0.47 → 시간 robustness 본질적 결함
- 5-fold CV 1/5만 PASS → 단일 quarter 의존
- **권고도**: 중간 (R-1 강한 PASS 후 R-2 시간 drift fail은 유의미한 hypothesis 약화)
- 마무리: paradigm-architect 카탈로그에 "external-event paradigm 첫 R-2 fragile-temporal 케이스" 새 lesson 추가

### Option 2 — R-3 dispatch with explicit narrow-scope
- A focus SHORT × IS-only (2024-Q4 ~ 2025-Q4) 한정 paradigm으로 재정의
- 2026 events는 OOS test로 분리 보관 → 향후 추가 사례 누적 시 재검증
- R-3 robustness (regime stratify + grid sweep)는 IS 데이터 40 events로만 진행
- **권고도**: 낮음 (n=40에서 grid sweep은 plateau identification 어려움)

### Option 3 — IS-only narrow paradigm 즉시 R-5 시드 제안 (R-3 skip)
- "A focus SHORT, 2024-2025 시점 한정, 추가 paper validation 필요" 메모와 함께 R-5 seed proposal 작성
- paper session으로 2026-Q3 신규 delisting events로 실시간 OOS 검증 (현재 OOS sample n=17 → 향후 누적 시 통계 강화)
- **권고도**: 중간 — life-changing 기준 (40 trades/yr × 14.6% edge × sharpe 6.5)은 만족하지만 시간 drift risk 명시

### Option 4 — 메커니즘 변형 R-1 (announce_ts 이전 진입)
- 사전 leak 가설 검증: announce_ts−24h ~ announce_ts−1h 진입 SHORT
- 별도 R-1 paradigm (`binance_delisting_pre_announce_short_alt`)
- **권고도**: 중간 (가설 자체는 검증 가능하지만 announce_ts 자체가 unknown future이므로 실거래 적용 어려움 — backtest only)

**1순위 권고**: **Option 1 (Graveyard) + lesson catalog 업데이트**
- IS-OOS drift가 명백하고 OOS three-gate FAIL이 결정적
- 2025-Q4 alpha (sigex +5.05, k=3 fold)는 회고적으로 cherry-pick 의심
- B variant 통계적 약화는 mechanism이 narrow-window에만 작동하는 본질적 제약을 시사

---

## 8. 산출물

- code: `backend/runs/research_track/binance_delisting_announce_short_alt/r2.py` (708 LOC)
- metrics: `backend/runs/research_track/binance_delisting_announce_short_alt/r2__metrics.json`
- report: `backend/runs/research_track/binance_delisting_announce_short_alt/r2_report.md`
- Mint commit: Phase 4 R-2

---

## 9. 새 lessons 후보 (사용자 승인 후 PARADIGM_QUEUE_2026Q3.md §6.2 추가 검토)

- **Lesson #25 candidate — External-event-injection paradigm IS-OOS drift 패턴**: announce/listing/regulatory events 기반 paradigm은 시장 학습으로 drift 빠름. R-1 PASS_R1_FULL이어도 R-2 walk-forward 70/30 + 5-fold CV 필수 (event-injection family의 본질적 약점). R-1 N=57이 시장 학습 시점 통과 시 OOS half (마지막 17 events)가 일관되게 drift 보인 첫 케이스.
- **Lesson #26 candidate — 4-quadrant Symmetric Negative Test가 SPLIT_PARADIGM 방지**: B mirror SHORT borderline 양상 (sigex +0.28, sign 83%) 발견. 만약 Lesson #19 의무 없었으면 R-1 종료 후 "B SHORT 별도 dispatch" 자원 소모 + alpha 검증 실패 시 별도 graveyard 추가 필요. 4-quadrant 한-batch 측정의 효율성 재확인.

---

KST: 2026-05-18 14:52
