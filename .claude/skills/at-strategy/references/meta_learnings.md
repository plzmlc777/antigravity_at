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
- **Confidence**: 0.71
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
- **Status**: active

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
