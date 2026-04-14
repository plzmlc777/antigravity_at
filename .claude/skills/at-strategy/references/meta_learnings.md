# Meta-Learnings Knowledge Base

> This file is maintained by the `meta-learner` agent.
> Each entry captures a discovered pattern with evidence, actionable rules, and confidence.
> Entries below 0.7 confidence are excluded. Stale entries should be reviewed and invalidated over time.

## Schema

Each discovery entry follows this structure:

```
## [YYYY-MM-DD] <Discovery Title>
- **ID**: D<NNN>
- **Type**: temporal_pattern | parameter_sensitivity | cross_strategy | failure_signature | edge_decay | regime_shift | anomaly
- **Impact**: critical | high | medium | low
- **Confidence**: 0.00 ~ 1.00
- **Sample Size**: <N trades / sessions>
- **Date Range**: <start> ~ <end>
- **Pattern**: <description>
- **Evidence**: <metrics, session IDs, statistics>
- **Actionable Rule**:
  - Condition: <when>
  - Action: <what to do>
  - Anti-condition: <when NOT>
  - Anti-action: <what to avoid>
- **Status**: active | invalidated | under_review
```

## Discoveries

<!-- New discoveries will be appended below this line -->

## [2026-04-06] noop 마틴게일 레벨3 도달 시 대규모 손실 발생 패턴
- **ID**: D001
- **Type**: failure_signature
- **Impact**: critical
- **Confidence**: 0.82
- **Sample Size**: 34 사이클 (skill-test-001 세션)
- **Date Range**: 2026-04-05 ~ 2026-04-06
- **Pattern**: noop 전략에서 마틴게일 레벨3에 도달한 사이클은 평균 PnL -3.56 USDT, 승률 60%로 레벨1(+0.48, 96.2%) 대비 극심한 성과 저하. 레벨3 도달 시 2건의 대규모 손실(-14.44, -13.09 USDT)이 전체 누적 수익을 잠식.
- **Evidence**:
  - 레벨1: 26사이클, 평균PnL +0.48, 승률 96.2%, 누적 +12.38
  - 레벨2: 3사이클, 평균PnL +1.20, 승률 100%, 누적 +3.59
  - 레벨3: 5사이클, 평균PnL -3.56, 승률 60%, 누적 -17.80
  - 세션 skill-test-001, RIVERUSDT, cycle_id 19(-14.44), cycle_id 24(-13.09)
  - 두 대규모 손실 모두 22:00-00:00(야간 시간대)에 발생
- **Actionable Rule**:
  - Condition: 마틴게일 레벨3 도달 + 야간 시간대(22:00-00:00 KST)
  - Action: max_buy_count를 2로 제한하거나, 레벨3 진입 전 max_loss_percent를 더 타이트하게 설정
  - Anti-condition: 레벨1-2에서 해소되는 사이클
  - Anti-action: 불필요한 개입 자제 (레벨1-2 승률은 96%+로 양호)
- **Status**: active

## [2026-04-06] rsi_martingale AI 종목 교체 시 비검증 종목 진입 위험
- **ID**: D002
- **Type**: failure_signature
- **Impact**: high
- **Confidence**: 0.75
- **Sample Size**: 8 사이클 (408761bb 세션, 6개 종목)
- **Date Range**: 2026-04-02 ~ 2026-04-04
- **Pattern**: AI 종목 교체로 전환된 종목(EDGEUSDT, AIOTUSDT 등) 중 PnL 0인 경우 다수. 반면 AI가 유지 판단한 1000PEPEUSDT는 201.35 USDT 수익. AI 교체 빈도 과도(24시간 내 6회+).
- **Evidence**:
  - 1000PEPEUSDT (AI 유지): 2사이클, 총 PnL +201.35
  - EDGEUSDT (AI 교체): 1사이클, PnL 0
  - AIOTUSDT (AI 교체): 1사이클, PnL 0
  - UNKNOWN 심볼 발생: 데이터 무결성 문제
- **Actionable Rule**:
  - Condition: AI 종목 교체 직후 신규 진입
  - Action: 교체 후 최소 1시간 cooldown 설정, 교체 빈도 하루 최대 2회 제한
  - Anti-condition: AI가 유지 판단한 종목
  - Anti-action: 사이클 완료까지 보호
- **Status**: active

## [2026-04-06] 야간 시간대(22:00-00:00) 손실 집중 패턴
- **ID**: D003
- **Type**: temporal_pattern
- **Impact**: high
- **Confidence**: 0.72
- **Sample Size**: 52 사이클 전체
- **Date Range**: 2026-03-30 ~ 2026-04-06
- **Pattern**: 22:00-00:00 시간대는 유일하게 평균 PnL이 음수(-0.49)인 구간. 큰 손실 2건 모두 이 시간대에 발생. 11:00-17:00은 안정적 양의 수익.
- **Evidence**:
  - 22시: 6거래, 평균PnL -0.49, 승률 83.3%
  - 11-17시: 30거래, 승률 100%, 평균PnL +0.55
- **Actionable Rule**:
  - Condition: 22:00-00:00 시간대 + 마틴게일 전략
  - Action: 신규 진입 차단 또는 max_buy_count 1단계 하향
  - Anti-condition: 11:00-17:00 시간대
  - Anti-action: 정상 운용
- **Status**: active

## [2026-04-06] rsi_martingale이 noop 대비 확연한 수익성 우위
- **ID**: D004
- **Type**: cross_strategy
- **Impact**: high
- **Confidence**: 0.80
- **Sample Size**: rsi_martingale 18사이클 vs noop 34사이클
- **Date Range**: 2026-03-30 ~ 2026-04-06
- **Pattern**: 동일 종목(RIVERUSDT) 기준 rsi_martingale 승률 100%, 평균PnL +2.81 vs noop 승률 91.2%, 평균PnL -0.05. RSI 트리거가 불필요한 진입을 걸러주는 효과.
- **Evidence**:
  - rsi_martingale RIVERUSDT: 12사이클, 총PnL +33.76, 레벨2 도달 0건
  - noop RIVERUSDT: 34사이클, 총PnL -1.83, 레벨3 도달 5건
- **Actionable Rule**:
  - Condition: 전략 선택 시
  - Action: noop 대신 rsi_martingale 우선 사용
  - Anti-condition: RSI 시그널 장시간 미발생 횡보장
  - Anti-action: noop 유지하되 레벨 제한(max 2) 적용
- **Status**: active

## [2026-04-06] 일요일 거래 성과 저조 패턴
- **ID**: D005
- **Type**: temporal_pattern
- **Impact**: medium
- **Confidence**: 0.71 → **0.40 (downgraded, D-015)**
- **Sample Size**: 일요일 35사이클 vs 평일 15사이클
- **Date Range**: 2026-03-30 ~ 2026-04-06
- **Pattern**: 일요일 평균PnL -0.18, 승률 91.4%로 평일 대비 저조. 전체 거래의 67%가 일요일에 집중.
- **Evidence**:
  - 일요일: 35사이클, 총PnL -6.39
  - 월요일: 9사이클, 총PnL +9.09, 승률 100%
  - 금요일: 5사이클, 총PnL +208.62, 승률 80%
- **Actionable Rule**:
  - Condition: 일요일 + 마틴게일 전략
  - Action: 포지션 크기 축소 또는 진입 빈도 제한 검토
- **Confound Warning (D-015, audit #3 2026-04-06)**: 일요일 손실의 상당 부분이 22-24시 야간 시간대 거래에 집중. 야간 시간대(D-003)를 교란변수로 통제하면 "일요일 자체 효과"는 크게 약화. meta-learner가 시간대 통제 없이 요일 차원만 분석하여 중복 발견을 생산한 사례.
- **Status**: ~~active~~ → **under_review (D-015)**

## [2026-04-06] 1000PEPEUSDT가 rsi_martingale 최적 종목
- **ID**: D006
- **Type**: parameter_sensitivity
- **Impact**: medium
- **Confidence**: 0.70
- **Sample Size**: 2사이클
- **Date Range**: 2026-04-03
- **Pattern**: 1000PEPEUSDT에서 2사이클 201.35 USDT 수익(세션 수익의 74%). 거래량 폭증 + 낮은 가격 변동성 조건.
- **Evidence**:
  - 사이클15: PnL +196.88, 사이클16: PnL +4.47
  - AI 유지 판단: "거래량 폭증 대비 가격 변동 미미"
- **Actionable Rule**:
  - Condition: 거래량 상위 + 가격 변동률 < 2% + RSI 전략
  - Action: 해당 종목 우선 진입, AI 유지 판단 시 교체 억제
- **Status**: under_review (표본 부족, 추가 검증 필요)

## Invalidated / Archived

<!-- Stale or disproven patterns go here for historical record -->


---

## [2026-04-06] 주간 메타-러닝 리뷰 #2 신규 발견 (2026-03-30 ~ 2026-04-06)

> 분석 범위: 전체 197건 거래, 66 사이클, 3개 세션(408761bb, skill-test-001, python-test-001), 2개 전략(rsi_martingale, noop)
> 최근 7일: 54 사이클

---

## [2026-04-06] SUIUSDT rsi_martingale 대규모 손실 집중 (전략-종목 부적합)
- **ID**: D007
- **Type**: cross_strategy
- **Impact**: critical
- **Confidence**: 0.85
- **Sample Size**: 5 사이클 (세션 408761bb)
- **Date Range**: 2026-04-02 ~ 2026-04-04
- **Pattern**: SUIUSDT에서 rsi_martingale 5사이클 중 3건 손실, 총 PnL -54.10 USDT. 평균 PnL -10.82로 전 종목 중 유일한 대규모 음수. 최대 손실 -52.08(레벨3, 수요일 20시). 반면 AVAXUSDT(7사이클, +437.50)와 극명한 대조.
- **Evidence**:
  - SUIUSDT: 5사이클, WR=40.0%, PnL=-54.10, Avg=-10.82, 최대손실=-52.08
  - AVAXUSDT: 7사이클, WR=71.4%, PnL=+437.50, Avg=+62.50
  - 대규모 손실 3건 모두 수요일(Wed)에 발생
  - 레벨3-4까지 도달한 사이클에서 집중 발생
- **Actionable Rule**:
  - Condition: SUIUSDT + rsi_martingale
  - Action: SUIUSDT 종목을 rsi_martingale 운용 대상에서 제외하거나 max_buy_count=2로 제한
  - Anti-condition: AVAXUSDT, 1000PEPEUSDT 등 검증 종목
  - Anti-action: 기존 파라미터로 정상 운용
- **Status**: active

## [2026-04-06] 수요일(Wed) 전략 성과 극심한 저조 패턴
- **ID**: D008
- **Type**: temporal_pattern
- **Impact**: high
- **Confidence**: 0.78
- **Sample Size**: 66 사이클 전체 (수요일 5사이클)
- **Date Range**: 2026-03-09 ~ 2026-04-06
- **Pattern**: 수요일 5사이클 중 4건 손실, WR=20%, 총 PnL=-90.14. 다른 요일 대비 압도적 최저 성과. 목요일(+178.94, WR=100%)과 극명한 대비.
- **Evidence**:
  - 수요일: 5cyc, WR=20.0%, PnL=-90.14, Avg=-18.03
  - 목요일: 2cyc, WR=100%, PnL=+178.94, Avg=+89.47
  - 금요일: 5cyc, WR=80%, PnL=+208.62, Avg=+41.72
  - 월요일: 15cyc, WR=93.3%, PnL=+291.15, Avg=+19.41
  - 수요일 손실 3건 모두 SUIUSDT 세션에서 발생
- **Actionable Rule**:
  - Condition: 수요일 + 마틴게일 전략 (특히 SUIUSDT)
  - Action: 신규 진입 차단 또는 포지션 크기 50% 축소
  - Anti-condition: 월/목/금요일
  - Anti-action: 정상 운용 (월요일 특히 양호)
- **Status**: active

## [2026-04-06] rsi_martingale 408761bb 세션 Edge Decay 감지
- **ID**: D009
- **Type**: edge_decay
- **Impact**: high
- **Confidence**: 0.75
- **Sample Size**: 20 사이클 (세션 408761bb)
- **Date Range**: 2026-03-09 ~ 2026-04-04
- **Pattern**: 세션 전반(10사이클) 평균PnL=42.36, WR=70% vs 후반(10사이클) 평균PnL=19.63, WR=60%. 평균 수익 54% 감소, 승률 10%p 하락.
- **Evidence**:
  - 전반 10사이클: Avg=42.36, WR=70%
  - 후반 10사이클: Avg=19.63, WR=60%
  - 수익 감소율: 54%
  - 후반부에 SUIUSDT 대규모 손실 포함
- **Actionable Rule**:
  - Condition: 세션 운영 2주 이상 경과 + 최근 승률 60% 미만
  - Action: 파라미터 재최적화 또는 세션 재시작 검토
- **Status**: active

## [2026-04-06] noop 전략 skill-test-001 후반부 성과 하락 추세
- **ID**: D010
- **Type**: ~~edge_decay~~ → **invalidated (D-014)** — 실제 원인은 야간 시간대 손실 집중
- **Impact**: ~~medium~~ (무효)
- **Confidence**: 0.72 → **invalidated**
- **Sample Size**: 36 사이클 (세션 skill-test-001)
- **Date Range**: 2026-04-05 ~ 2026-04-06
- **Pattern**: 전반 18사이클 Avg=+0.81, WR=94.4% vs 후반 18사이클 Avg=-0.86, WR=88.9%. 후반부에서 음수 전환.
- **Evidence**:
  - 전반: 18cyc, Avg=+0.81, WR=94.4%
  - 후반: 18cyc, Avg=-0.86, WR=88.9%
  - 총 PnL: -1.05
  - 대형 손실 2건이 후반에 집중
- **Invalidation (D-014, audit #3 2026-04-06)**: 후반부 "대형 손실 2건"이 모두 22-24시 야간 시간대(SUIUSDT 포함)에 집중. 야간 거래를 제외하면 전반/후반 avg PnL 차이 소멸. 이는 **edge decay가 아니라 D-003(야간 손실 집중) 패턴의 다른 각도 재발견**. 세션 수명에 따른 알파 감소가 아님.
- **Actionable Rule**: (무효화됨)
- **Status**: ~~active~~ → **invalidated (D-014)**

## [2026-04-06] 3연패 패턴: rsi_martingale 사전 경고 신호 발견
- **ID**: D011
- **Type**: failure_signature
- **Impact**: critical
- **Confidence**: 0.80
- **Sample Size**: 3연패 1건 (세션 408761bb)
- **Date Range**: 2026-04-02 ~ 2026-04-04
- **Pattern**: 3연속 손실(-23.99, -52.08, -23.99) 직전에 이미 대규모 손실(-24.04)이 선행. 총 4연패 구간에서 -124.10 USDT 손실.
- **Evidence**:
  - 사전 3사이클 PnL: [-24.04, +13.32, +9.92]
  - 3연패 PnL: [-23.99, -52.08, -23.99], 총 -100.06
  - 모든 손실이 SUIUSDT 또는 AVAXUSDT에서 레벨3+ 도달 시 발생
  - 수요일(Wed) + 저녁/야간 시간대에 집중
- **Actionable Rule**:
  - Condition: 동일 세션에서 -20 USDT 이상 단일 손실 발생
  - Action: 즉시 cooldown(1시간) 적용 + max_buy_count 1단계 하향 + 운영자 알림
  - Anti-condition: 단일 손실 < -5 USDT
  - Anti-action: 정상 운용 유지
- **Status**: active

## [2026-04-06] 오후 시간대(12-18시) 최적 거래 구간 확인
- **ID**: D012
- **Type**: temporal_pattern
- **Impact**: high
- **Confidence**: 0.82
- **Sample Size**: 최근 7일 54사이클 중 오후 26사이클
- **Date Range**: 2026-03-30 ~ 2026-04-06
- **Pattern**: 12-18시(KST) 구간 승률 100%, 평균 PnL=+8.39. 전체 시간대 중 거래량 최다 + 승률 최고.
- **Evidence**:
  - 오후(12-18): 26cyc, WR=100%, PnL=+218.15, Avg=+8.39
  - 오전(06-12): 15cyc, WR=80%, PnL=+6.54, Avg=+0.44
  - 저녁(18-24): 12cyc, WR=83.3%, PnL=+23.45, Avg=+1.95
- **Actionable Rule**:
  - Condition: 12-18시 KST
  - Action: 정상 포지션 크기 허용, 신규 진입 적극 허용
  - Anti-condition: 20-24시 KST
  - Anti-action: 포지션 크기 축소 또는 신규 진입 자제
- **Status**: active

---

## 기존 발견 검증 결과 (2026-04-06 리뷰 #2)

| ID | 제목 | 검증 결과 |
|----|------|-----------|
| D001 | noop 레벨3 손실 | confirmed - 36사이클 재검증, 패턴 유효 |
| D002 | AI 종목 교체 위험 | confirmed - 세션 종료로 추가 데이터 없음 |
| D003 | 야간 22-24시 손실 | confirmed + 확장 - 23시 WR=50% Avg=-3.88 추가 확인 |
| D004 | rsi > noop | confirmed - rsi 12cyc WR=100% vs noop 36cyc WR=91.7% |
| D005 | 일요일 저조 | confirmed - 일요일 35cyc PnL=-6.39 vs 월요일 +291.15 |
| D006 | 1000PEPE 최적 | under_review - 표본 2사이클, 추가 데이터 필요 |

---

## Meta-pattern: Self-Critic Over-Interpretation Bias (2026-04-06)

- **ID**: M001
- **Type**: agent_behavior_bias
- **Impact**: high
- **Confidence**: 1.0 (직접 관측)
- **Sample Size**: 1 confirmed case
- **Discovered**: 2026-04-06, weekly cycle audit run #2

### 케이스
self-critic이 `pm2 describe at-backend`의 `restarts: 95555` 수치를 보고 "비정상 재시작 루프, 메모리 누수 또는 백그라운드 버그 의심"으로 CRITICAL 등급 권고. 실제 검증 결과:
- PM2 restart counter는 daemon lifetime 누적값 (자동 reset 없음)
- 두 번의 연속 deploy 사이 카운터 증가량: 정확히 +1 (95555 → 95556)
- 즉, 95k는 그동안의 모든 deploy/restart 누적이지 활성 crash loop 아님
- 동시에 진짜 버그(`live_manager.py:1390` AttributeError on shutdown — `BinanceWebSocket`에 없는 `websocket` 속성 참조)는 별도로 존재. 우연히 같은 컴포넌트(at-backend)와 연관되어 인과 혼동을 강화

### 편향 진단
**Attention Bias + Spurious Causation**: 큰 숫자(95k)에 attention이 끌리면서, 같은 영역의 실제 버그(AttributeError)와 인과적으로 연결시킴. "큰 숫자 = 큰 문제 = 인접한 버그가 원인"이라는 추론 체인은 검증되지 않은 가설.

### Actionable Rule (self-critic agent 개선용)
- **Condition**: 수치 기반 권고를 작성할 때 (특히 카운터, 누적값, 비율)
- **Required check**: 단위·시간창·기준선 명시 후, 동일 단위로 연속 측정 2회 이상으로 추세 확인 (예: t0/t1 두 시점 비교)
- **Forbidden phrasing**: "비정상", "의심", "X로 추정" 같은 단정적 인과 추론을 검증 없이 쓰지 말 것
- **Required phrasing**: "측정값 X (단위: Y, 측정창: Z, 기준선: W). 인과 검증 필요: A/B/C"

### 시스템 영향
- self-critic이 생성하는 directive 신뢰도 저하 — 사용자가 매번 1차 검증 필요
- 다음 사이클에서 self-critic agent spec에 "수치 해석 가드" 추가 필요

### Status
- detected: 2026-04-06
- recorded_in: meta_learnings.md M001
- next_action: self-critic agent spec에 numeric-claim verification rule 추가 (다음 작업)

---

## [2026-04-07] 주간 메타-러닝 리뷰 #4 — Null Finding (자기규율 검증 런)

> 분석 범위: 운영 중 세션 1개(skill-test-001, RIVERUSDT, rsi_martingale, paper),
> 전환 후 사이클 3건 (cycle_id 41/42/43, 모두 2026-04-06 22:29~22:55 KST).
> 이전 런에서 축적된 누적 통계 API는 비인증으로 접근 불가 상태.

### D013 — Insufficient Post-Switch Sample (Honest Null)
- **ID**: D013
- **Type**: meta (data-availability)
- **Impact**: low (정보용)
- **Confidence**: 0.30 (≤0.65, D-007 cap 적용)
- **Sample Size**: 3 사이클 (< 10, D-007 위반)
- **Date Range**: 2026-04-06 22:29 ~ 22:55 KST (약 26분)
- **Pattern**: skill-test-001 세션이 어제(2026-04-06) noop → rsi_martingale로 전환된 직후이므로
  전환 후 신규 사이클이 3건에 불과. 모두 RIVERUSDT 단일 종목, 단일 시간대(22시대), 단일 요일.
  전략·종목·시간대·요일 중 어느 차원에서도 독립 분산이 없어 **유의미한 패턴 추출 자체가 불가능**.
- **Evidence**:
  - 사이클 41: entry 11.805 → exit 11.772 (레벨2까지 진입, CLOSE PnL ≈ -0.03%)
  - 사이클 42: 11.718 → 11.730 (레벨1, +0.10%)
  - 사이클 43: 11.914 → 11.926 (레벨1, +0.10%)
  - 총 3사이클 모두 KST 22시대, 월요일, RIVERUSDT, paper 모드
  - 분산 없음: symbol=1, hour_bucket=1, weekday=1, strategy=1
- **Confound Cross-Check (D-016 강제 적용)**:
  - 후보 가설 A: "전환 직후 rsi_martingale이 안정적으로 작동한다"
    - 대체 차원(hour-of-day): 3건 모두 22시 → 시간대 변이 없음, 검정 불가
    - 대체 차원(day-of-week): 3건 모두 월요일 → 요일 변이 없음, 검정 불가
    - 결과: **confounded by zero-variance** — 단일 셀 관측치로 어떤 주장도 불가능
  - 후보 가설 B: "22시대이지만 RSI 필터 덕분에 D-003(야간 손실) 회피"
    - 3건 중 레벨2까지만 도달, 큰 손실 0건 → 가설과 **불모순**이지만, n=3으로 통계적 의미 없음
    - 결과: **inconclusive** — D-003 반박 근거로 사용 금지
- **Alternative Hypotheses (D-018 강제 적용)**:
  - H1: "rsi_martingale 전환이 성공적이다"
    - 반증 수단: 최소 10사이클 수집 후 WR/Avg PnL 재평가
    - 현 상태: 미검증 (n=3)
  - H2: "rsi_martingale 전환이 단지 저변동 구간을 우연히 만났다"
    - 반증 수단: 같은 기간 RIVERUSDT 가격 변동폭 vs 과거 22시대 변동폭 비교
    - 현 상태: 미실시 — 현재 3건 내 high-low 스프레드 < 0.2%로 저변동 가설과 **불모순**
  - 결론: 어느 가설도 배제 불가 → `under_review` 유지 필수
- **Actionable Rule**:
  - Condition: 세션 전략 전환 직후
  - Action: 최소 10사이클 또는 3일 중 더 긴 기간 경과 전까지 **패턴 주장 금지**. 표본 부족 — 추가 데이터 수집 필요.
  - Anti-condition: n ≥ 10 이면서 hour/weekday/symbol 중 최소 2차원 분산 > 0
  - Anti-action: 정상 분석 재개
- **Status**: under_review (D-007 small-sample cap)

### 기존 발견 재검토 (D001~D012)
| ID | 제목 | 이번 런 재검토 결과 |
|----|------|---------------------|
| D001 | noop 레벨3 손실 | unchanged — 이전 런들에서 교차검증. 현 세션은 rsi_martingale 전환으로 noop 신규 데이터 없음. **stale 아님** (패턴이 역사적 사실로 기록). |
| D002 | AI 종목 교체 위험 | unchanged — 해당 세션(408761bb) 종료. 신규 데이터 0. |
| D003 | 야간 22-24시 손실 | **주의**: 이번 런 3사이클이 모두 22시대이며 소폭 이익. n=3으로는 D-003 반박 불가. D-003은 여전히 `active` 유지. |
| D004 | rsi > noop | unchanged — 동일 종목 교차 비교는 이번 런에서 불가 (noop 데이터 없음). |
| D005 | 일요일 저조 | **invalidated (D-015) 유지** — 교란 재확인, 재활성화 근거 없음. |
| D006 | 1000PEPE 최적 | under_review 유지 — 신규 데이터 0. |
| D007~D012 | 리뷰 #2 발견들 | 이번 런 데이터가 이들 중 어떤 것도 검증/반박할 교차분산을 제공하지 않음. 전부 상태 유지. |
| D010 | noop edge decay | **invalidated (D-014) 유지** — 재활성화 근거 없음. |

### 이번 런 자기규율 체크 (run #4 validation goal)
- [x] D-007 sample cap 적용: D013 confidence = 0.30 (≤0.65), status = under_review
- [x] D-016 confound cross-check 기재: `evidence.confound_check` 필드 2차원 검정 기록
- [x] D-018 alternative_hypotheses 필드: H1/H2 제시 후 둘 다 배제 실패 → active 승격 거부
- [x] 표본 부족 시 패턴 조작 대신 null finding 보고 (task의 honest-report 요구 이행)
- [x] D005/D010 재활성화 시도 없음 — invalidation 유지

### Meta-observation
run #1~#3에서 확인된 "첫 그럴듯한 인과 스토리로 정착(confirmation bias)" 실패 모드가, 이번 run #4에서는
강제 체크리스트(D-007/D-016/D-018)에 의해 처음으로 억제됨. 데이터가 부족하면 "모른다"로 답하는
규율이 실제로 동작함을 확인. 단, 이는 1 데이터포인트 관측이므로 **규칙 효과성 자체도 under_review**.
다음 런에서 충분한 표본이 쌓였을 때 false-positive suppression이 실제로 작동하는지 재검증 필요.


---

## [2026-04-11] 주간 메타-러닝 리뷰 #5 — Full Analysis (2026-04-04 ~ 2026-04-11)

> 분석 범위: 434건 거래, 140 사이클(skill-test-001), 27 사이클(408761bb)
> 기간: 2026-04-04 ~ 2026-04-10
> SISDS 상태: W15 CRITICAL

---

## [2026-04-11] D003 업데이트: 야간 21-24시 손실 집중 — 140사이클 대규모 재검증
- **ID**: D003 (업데이트)
- **Type**: temporal_pattern
- **Impact**: critical (medium → critical 승격)
- **Confidence**: 0.88 (0.72 → 0.88, 표본 4배 증가)
- **Sample Size**: 140 사이클 (skill-test-001 전체)
- **Date Range**: 2026-04-05 ~ 2026-04-10
- **Pattern**: 21-24시(UTC) 시간대가 전체 손실의 90% (10건 중 9건)을 집중. 특히 21시 UTC가 WR=57.1%, Avg=-5.71로 최악. 반면 09-17시(UTC)는 WR 93-100%.
- **Evidence (140 사이클 재검증)**:
  - 야간(21-01h): 34사이클, WR=82.4%, Avg=-1.92, 총PnL=-65.28
  - 주간(09-15h): 60사이클, WR=93.3%, Avg=+0.09, 총PnL=+5.15
  - 오후(15-21h): 46사이클, WR=95.7%, Avg=+0.52, 총PnL=+23.99
  - 21시: 7사이클, 3패(WR=57.1%), 총PnL=-39.96 (단일 시간대 최대 손실)
  - Config 효과: block_entry_hours=[22,23] 적용 후 loss_rate 11.6%→2.8%
- **Confound Cross-Check**: 요일 통제 후에도 21-24h 손실 집중 유지. independent.
- **Actionable Rule**: block_entry_hours를 [21,22,23]으로 확장 (현재 [22,23])
- **Status**: active (강화)

## [2026-04-11] noop/RIVERUSDT 고빈도 소규모 수익 + 저빈도 대규모 손실 구조
- **ID**: D014
- **Type**: failure_signature
- **Impact**: critical
- **Confidence**: 0.90
- **Sample Size**: 140 사이클
- **Date Range**: 2026-04-05 ~ 2026-04-10
- **Pattern**: noop 전략 PnL 극단적 비대칭. WR=91.4%이지만 Avg Win(+0.64)이 Avg Loss(-11.83)의 1/18. Total PnL = -36.14 (음수). Profit Factor = 0.69. 마틴게일 구조적 위험의 교과서적 사례.
- **Evidence**:
  - 128승 / 10패 / 2무, WR=91.4%, Total PnL = -36.14 USDT
  - Avg Win: +0.64, Max Win: +4.63, Avg Loss: -11.83, Max Loss: -16.93
  - Profit Factor: 81.98/118.12 = 0.69
  - 상위 5패 합계: -74.50 USDT (전체 손실의 63%)
- **Actionable Rule**: noop → rsi_martingale 전환, max_buy_count=2, trailing_stop > 0 유지
- **Status**: active

## [2026-04-11] 화요일(Tue) 성과 저조 패턴
- **ID**: D015
- **Type**: temporal_pattern
- **Impact**: high
- **Confidence**: 0.75
- **Sample Size**: 140 사이클
- **Date Range**: 2026-04-05 ~ 2026-04-10
- **Pattern**: 화요일 64거래 중 6패, Total=-51.07 (유일한 대규모 음수 요일). 목(0패, +24.98), 금(0패, +6.45) 대조.
- **Confound Warning**: 1일(Apr 7) 표본. 시장 이벤트 vs 요일 구조 구별 불가.
- **Status**: under_review

## [2026-04-11] block_entry config 효과 정량 검증
- **ID**: D016
- **Type**: parameter_sensitivity
- **Impact**: critical
- **Confidence**: 0.82
- **Sample Size**: before=69, after=71 사이클
- **Date Range**: 2026-04-05 ~ 2026-04-10
- **Pattern**: block_entry_hours=[22,23] + block_entry_weekdays=[2] + cooldown 적용 후 loss_rate 11.6%→2.8%, Total PnL -48.14→+12.00. meta-learning→config→실증 사이클 최초 완성.
- **Recommendation**: block_entry_hours를 [21,22,23]으로 확장
- **Status**: active

## [2026-04-11] SISDS 파이프라인 CRITICAL — 전략 생성 0% 통과율
- **ID**: D017
- **Type**: anomaly
- **Impact**: critical
- **Confidence**: 0.95
- **Sample Size**: W15 전체 (2건 생성, 0건 통과)
- **Date Range**: 2026-04-07 ~ 2026-04-11
- **Pattern**: bollinger_reversion, volume_spike_entry 모두 0건 거래로 eliminated. 공통: trailing_stop=0 또는 entry 조건 과도.
- **Actionable Rule**: strategy-builder에 trailing_stop > 0 필수 + dry-run 검증 추가
- **Status**: active

## [2026-04-11] rsi_martingale 408761bb 종합 — 종목별 극심한 편차
- **ID**: D018
- **Type**: cross_strategy
- **Impact**: high
- **Confidence**: 0.80
- **Sample Size**: 21 사이클
- **Date Range**: 2026-03-10 ~ 2026-04-04
- **Pattern**: 총 +619.83 USDT. AVAXUSDT(+437.50, 71%), 1000PEPEUSDT(+201.35, 32%), SUIUSDT(-54.10, -9%).
- **Actionable Rule**: WR < 50% 종목(5+ 사이클) 자동 제외
- **Status**: active

---

## 기존 발견 재검증 (2026-04-11 리뷰 #5)

| ID | 제목 | 재검토 | 상태 변경 |
|----|------|--------|-----------|
| D001 | noop 레벨3 손실 | config로 해결됨 | active → resolved |
| D003 | 야간 손실 | 140cyc 재확인, 21h 확장 권고 | active (강화) |
| D004 | rsi > noop | noop PnL=-36 vs rsi +620 | active |
| D005 | 일요일 저조 | 시간대 교란 약화 | under_review |
| D008 | 수요일 저조 | 화요일이 더 저조 | active → under_review |
| D012 | 오후 최적 | 46cyc WR=95.7% 재확인 | active |
| D013 | Post-switch null | 140cyc으로 해소 | resolved |
