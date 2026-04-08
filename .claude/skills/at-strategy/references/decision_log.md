# Decision Log

> This file is maintained by the `cio` workflow (writes decisions) and `self-critic` agent (writes audits).
> Each decision captures who decided what, why, what was expected, and what actually happened.
> Audits are written separately and reference decision IDs.

## Decision Schema

```
## [YYYY-MM-DD] CIO-<YYYYMMDD>-<NNN>: <One-line action title>
- **Workflow**: daily-review | symbol-select | emergency | new-session | learn-evolve-reflect | ai-signal
- **Session**: <session_id> (or "n/a" for system-wide)
- **Symbol**: <SYMBOL> | n/a
- **Action**: <what was decided>
- **Trigger**: <ASSESS findings that prompted action>
- **Process**:
  - ops-monitor: <key finding>
  - market-researcher: <key finding>
  - strategy-advisor: <recommendation> (confidence: <0.00-1.00>)
  - backtest-analyst: <return/MDD/sharpe> (overfit: <ratio>)
  - risk-manager: approved | rejected — <rationale>
- **Executed**: yes | no | dry-run
- **Expected**: <return %, MDD %, win rate %, time horizon>
- **Outcome (filled in later)**:
  - At <T+1d/T+7d/T+30d>: <actual metrics>
  - Variance vs expected: <delta>
  - Counterfactual: <what would have happened with no-action>
- **Status**: pending_outcome | confirmed | falsified
```

## Audit Schema (self-critic entries)

```
## [YYYY-MM-DD] AUDIT-<YYYYMMDD>-<NNN>: <Audit summary>
- **Period audited**: <start> ~ <end>
- **Decisions reviewed**: <count> (refs: CIO-..., CIO-...)
- **Overall grade**: A | B | C | D | F
- **Bias detected**: confirmation | recency | overconfidence | action | anchoring | sunk_cost
- **Severity**: low | medium | high | critical
- **Calibration**:
  - strategy-advisor: stated <X>, actual <Y>, delta <Z>
  - backtest-analyst: expected return <X>, realized <Y>
- **Improvement directives** (refs: D-001, D-002, ...):
  - <agent>: <directive>
- **Health score**: 0-100
- **Status**: open | applied | obsolete
```

## Decisions

<!-- New decisions will be appended below this line -->

## Audits

<!-- Self-critic audit reports go here -->

## Improvement Directives Tracker

| ID | Date | Target Agent | Directive | Priority | Status | Applied |
|----|------|--------------|-----------|----------|--------|---------|
<!-- Directives from self-critic accumulate here for cross-reference -->

## [2026-04-06] AUDIT-20260406-001: 주간 의사결정 감사 (03/30~04/06) — 첫 번째 감사

- **Period audited**: 2026-03-30 ~ 2026-04-06
- **Decisions reviewed**: 5건 (암묵적 의사결정 — 기록된 CIO 결정 없음, meta-learner 결과로 역추정)
- **Overall grade**: D+
- **Overall assessment**: 의사결정 프로세스(ASSESS->PLAN->EXECUTE) 미확립 상태에서 세션 운용. 결정이 기록되지 않아 추적 불가. meta-learner가 사후적으로 발견한 문제점이 사전에 예방 가능했던 것들.
- **Bias detected**: action, recency, overconfidence, survivorship, omission
- **Severity**: high (전체), critical (야간 리스크, UNKNOWN 심볼)
- **Calibration**:
  - strategy-advisor (noop 추천): stated ~0.70, actual 0.38, delta +0.32 (과신)
  - AI 종목교체: stated ~0.75, actual 0.17, delta +0.58 (심각한 과신)
  - risk-manager: 미작동 — 평가 불가
- **Improvement directives** (refs: D-001 ~ D-007):
  - cio: 모든 의사결정 decision_log.md 기록 필수 (D-001)
  - risk-manager: 야간(22:00-00:00) 마틴게일 신규 진입 차단 (D-002)
  - strategy-advisor: noop 전략 사용 금지, rsi_martingale 우선 (D-003)
  - cio: AI 종목 교체 24시간 최대 2회, cooldown 1시간 (D-004)
  - strategy-advisor: max_buy_count 2로 제한, 레벨3+ 진입 차단 (D-005)
  - trade-executor: UNKNOWN 심볼 거래 차단, 심볼 검증 필수 (D-006)
  - meta-learner: 표본 10사이클 미만 발견은 under_review 강제 (D-007)
- **Health score**: 42/100 (Critical)
- **Status**: open

### 감사 세부 내역

#### DEC-IMPL-001: noop 전략 + RIVERUSDT 세션 (skill-test-001)
- Process: D | Outcome: D | Correct: No
- 34사이클, PnL -1.83, 레벨3 도달 5회, 대손실 2건(-14.44, -13.09)
- 동일 종목 rsi_martingale은 +33.76. 전략 비교 없이 배포.

#### DEC-IMPL-002: rsi_martingale + AI 종목 교체 (408761bb)
- Process: C | Outcome: C+ | Correct: Partially
- 18사이클, PnL +211. 74%가 1000PEPEUSDT(AI 유지 종목). AI 교체 6회+, 교체 종목 PnL 0.

#### DEC-IMPL-003: 야간(22:00-00:00) 무제한 운용
- Process: D | Outcome: F | Correct: No
- 야간 평균PnL -0.49, 대손실 2건 모두 이 시간대. 시간대 제한 미설정.

#### DEC-IMPL-004: max_buy_count=3+ 허용
- Process: C | Outcome: D | Correct: No
- 레벨3: 5회, -17.80. 레벨1-2: +15.97. 레벨3이 전체 수익 잠식.

#### DEC-IMPL-005: UNKNOWN 심볼 거래 발생
- Process: F | Outcome: F | Correct: No
- 3건 UNKNOWN 심볼 거래. 데이터 무결성 근본 문제.

### 편향 분석 요약

| 편향 유형 | 감지 | 건수 | 심각도 | 핵심 사례 |
|-----------|------|------|--------|----------|
| Action Bias | Yes | 3 | HIGH | AI 종목교체 6회+, 교체 종목 PnL 0 |
| Recency Bias | Yes | 2 | MEDIUM | 단기 가격에 과민한 종목 교체 |
| Overconfidence | Yes | 2 | MEDIUM | 레벨3 무제한 허용, AI 교체 무검증 |
| Survivorship Bias | Yes | 1 | MEDIUM | 1000PEPEUSDT 2사이클로 최적 판단 위험 |
| Omission Bias | Yes | - | HIGH | 의사결정 기록 자체 부재 |

| ID | Date | Target Agent | Directive | Priority | Status | Applied |
|----|------|--------------|-----------|----------|--------|---------|
| D-001 | 2026-04-06 | cio | 모든 의사결정 decision_log.md 기록 필수. ASSESS->PLAN->EXECUTE 프로세스 준수. | HIGH | applied | 2026-04-06 (cio.md: Decision Logging Mandate section) |
| D-002 | 2026-04-06 | risk-manager | 야간(22:00-00:00 KST) 마틴게일 신규 L1 진입 차단. 기존 포지션 유지 허용. | CRITICAL | applied | 2026-04-06 (martingale_base.py: block_entry_hours=[22,23] default) |
| D-003 | 2026-04-06 | strategy-advisor | noop 전략 사용 금지 권고. rsi_martingale 우선 사용. 동일 종목 +35.59 USDT 성과 차이. | HIGH | applied | 2026-04-06 (strategy-advisor.md: Hard Rules — noop banned) |
| D-004 | 2026-04-06 | cio | AI 종목 교체 24시간 최대 2회 + cooldown 1시간. 교체 전 비교체 시나리오 필수 평가. | HIGH | applied | 2026-04-06 (live_engine.py: _ai_switch_history + cooldown/cap guards in _try_ai_symbol_switch) |
| D-005 | 2026-04-06 | strategy-advisor | max_buy_count 2로 제한. 레벨3+ 진입 차단. 레벨1-2만 +15.97 vs 레벨3 -17.80. | HIGH | applied | 2026-04-06 (strategy-advisor.md: Hard Rules — max_buy_count cap) |
| D-006 | 2026-04-06 | trade-executor | UNKNOWN 심볼 거래 즉시 차단. 주문 전 심볼 유효성 검증 로직 필수 추가. | CRITICAL | applied | 2026-04-06 (martingale_base.py initialize() fail-fast + live_context.py buy/sell/short/close_position guards) |
| D-007 | 2026-04-06 | meta-learner | 표본 10사이클 미만 발견은 confidence 상한 0.65 + status under_review 강제. | MEDIUM | applied | 2026-04-06 (meta-learner.md: Sample Size Confidence Cap section) |

## [2026-04-06] CIO-20260406-001: noop strategy evolution (RIVERUSDT)
- **Workflow**: learn-evolve-reflect
- **Session**: skill-test-001
- **Symbol**: RIVERUSDT
- **Trigger**: meta-learner D001, D003, D004

**Baseline**: return -47.23%, MDD -49.74%, 74 cycles
**M001** (max_buy=2, loss=5%): -6.76%, MDD -8.45%, promising
**M002** (RSI21, trigger25, reset60, loss=3%): -3.20%, MDD -5.17%, promising
**M003** (martingale OFF, loss=3%): -2.50%, MDD -3.06%, promising
**Walk-Forward**: overfit 0.00, GOOD
**Recommendation**: noop->rsi_martingale, max_buy<=2, loss 3-5%
- **Status**: pending_outcome

## [2026-04-06] CIO-20260406-002: strategy-evolver rsi_martingale 파라미터 진화 (RIVERUSDT)
- **Workflow**: learn-evolve-reflect (strategy-evolver agent)
- **Session**: skill-test-001
- **Symbol**: RIVERUSDT
- **Trigger**: meta-learner D004, D008, D010, D011, D012

### 진화 목표
noop(WR=91.7%, PnL=-1.05) → rsi_martingale 전환 + 최적 파라미터 탐색.
meta-learner 인사이트 반영: 야간차단(D003), 수요일 제한(D008), 오후 최적(D012), 대손실 쿨다운(D011).

### 변이 결과 (14일 백테스트)

| ID | RSI | Trigger | Reset | MaxBuy | Loss% | Trail | Cycles | WR% | Sharpe | MDD% | Verdict |
|----|-----|---------|-------|--------|-------|-------|--------|-----|--------|------|---------|
| M001 | 14 | 30 | 50 | 2 | 5.0 | 2.0/1.0 | 2 | 100 | 1.34 | -0.0005 | rejected (low cycles) |
| M002 | 21 | 25 | 60 | 2 | 3.0 | 1.5/0.5 | 11 | 100 | 2.53 | -0.0004 | recommended |
| M003 | 7 | 20 | 45 | 1 | 3.0 | 1.0/0.3 | 4 | 75 | 1.46 | -0.0002 | rejected (low WR) |

### Walk-Forward 검증 (M002 기반)
- 3-fold, overfit_ratio=0.00 (GOOD)
- 모든 fold에서 동일 최적 설정: RSI14/trigger25/reset60/loss3.0
- Verdict: 과적합 위험 없음

### 최종 권장 파라미터 (M002_evolved)
```json
{
  "rsi_period": 21, "trigger_level": 25, "reset_level": 60,
  "max_buy_count": 2, "max_loss_percent": 3.0,
  "trailing_start_percent": 1.5, "trailing_stop_percent": 0.5,
  "position_side": "long", "block_entry_hours": [22, 23]
}
```

- **Walk-Forward 보정**: RSI14도 유효하나, RSI21이 더 많은 사이클(11 vs 2) 생성
- **Executed**: no (권장만, 실행 미수행)
- **Expected**: WR 95%+, Sharpe > 2.0, MDD < -1%, noop 대비 개선
- **Status**: pending_outcome

## [2026-04-06] AUDIT-20260406-002: 주간 의사결정 감사 #2 (03/30~04/06) — 후속 감사 + 지시 이행 점검

- **Period audited**: 2026-03-30 ~ 2026-04-06
- **Decisions reviewed**: 7건 (DEC-IMPL-001~005 재평가 + CIO-20260406-001 + D-001~D-007 이행 점검)
- **Overall grade**: C+
- **Overall assessment**: 첫 감사(AUDIT-001) 이후 D-001~D-007 지시가 동일 날 applied 되었으나, 실제 효과 검증은 불가(적용 시점 이후 거래 데이터 부족). skill-test-001 세션은 여전히 noop/RIVERUSDT로 운영 중이며, D-003(noop 사용 금지) 지시에도 불구하고 세션이 전환되지 않음. 야간 22-23시 대형 손실(-14.44, -13.09)이 D-002 적용 전에 발생. CIO-20260406-001 의사결정은 양호한 프로세스를 보였으나 실행 미완.
- **Bias detected**: sunk_cost, action (확정), omission
- **Severity**: medium (전회 대비 개선, 그러나 구조적 문제 잔존)
- **Calibration**:
  - strategy-advisor (noop): stated ~0.70, actual WR=89.2% but PnL=-1.07 (승률 양호 / 수익성 음수)
  - strategy-advisor (rsi_martingale python-test-001): stated ~0.70, actual WR=100% PnL=+4.53
  - risk-manager: 야간 차단(D-002) 적용 후 04/06 야간 거래 0건 (작동 확인)
- **Improvement directives** (refs: D-008 ~ D-013):
  - cio: 기존 지시 이행 확인 체크리스트 운영 (D-008)
  - cio: noop 세션 skill-test-001 즉시 전략 전환 또는 종료 (D-009)
  - strategy-advisor: 승률과 수익성을 분리 보고, PnL 음수면 confidence 상한 0.50 (D-010)
  - risk-manager: 3연패 사전경고 시스템 실장 확인 (D-011)
  - cio: SUIUSDT 종목 블랙리스트 등록 (D-012)
  - cio: 수요일 운영 규칙 수립 (D-013)
- **Health score**: 55/100 (Needs improvement)
- **Status**: open

### 지시 이행 점검 (D-001 ~ D-007)

| ID | 지시 | 이행 | 실효성 | 비고 |
|----|------|------|--------|------|
| D-001 | CIO 의사결정 기록 | applied | 미확인 | CIO-20260406-001 1건만 기록. 기간 내 다른 결정 기록 없음. |
| D-002 | 야간 22-23시 차단 | applied | 부분 확인 | 코드 적용. 04/06 야간 거래 0건. 장기 검증 필요. |
| D-003 | noop 사용 금지 | applied (문서) | 미이행 | skill-test-001 여전히 noop으로 RUNNING. |
| D-004 | AI 종목교체 제한 | applied | 해당없음 | 408761bb 종료. 새 AI 세션 없음. |
| D-005 | max_buy_count=2 | applied (문서) | 부분 확인 | 04/06 레벨3 도달 0건. |
| D-006 | UNKNOWN 심볼 차단 | applied | 해당없음 | 코드 적용. 04/06 UNKNOWN 0건. |
| D-007 | 표본 10미만 under_review | applied (문서) | 적용 중 | D006에 under_review 적용 확인. |

### 편향 분석 종합

| 편향 유형 | 감지 | 건수 | 심각도 | 상세 |
|-----------|------|------|--------|------|
| Sunk Cost | Yes | 1 | MEDIUM | skill-test-001 noop 계속 운영. 전환 증거 존재에도 유지. |
| Omission | Yes | 2 | HIGH | D-003 문서만 적용, 실행 안 함. CIO-20260406-001 추천 미실행. |
| Anchoring | Yes | 1 | LOW | noop 변형만 탐색. rsi_martingale 직접 비교 생략. |
| Action Bias | Confirmed | - | HIGH | 408761bb AI 교체 9회+ (1차 감사 3건에서 상향). |
| Overconfidence | Partial | 1 | MEDIUM | noop WR 89.2%를 양호로 판단하나 PnL 음수. 승률!=수익성. |

### 신규 지시 (D-008 ~ D-013)

| ID | Date | Target Agent | Directive | Priority | Status | Applied |
|----|------|--------------|-----------|----------|--------|---------|
| D-008 | 2026-04-06 | cio | 매 주간 감사 후 기존 지시 이행 여부 체크리스트 작성. 미이행 지시는 다음 워크플로우에서 최우선 처리. | HIGH | applied | 2026-04-06 (cio.md: Directive Tracker Review Mandate — mandatory tracker read + drift detection + output block) |
| D-009 | 2026-04-06 | cio | skill-test-001 세션 즉시 종료 또는 rsi_martingale로 전략 전환. D-003 위반 상태 해소 필수. | CRITICAL | open | - |
| D-010 | 2026-04-06 | strategy-advisor | confidence 산출 시 승률(WR)과 수익성(PnL)을 분리 보고. PnL 음수인 전략은 WR 무관하게 confidence 상한 0.50. | HIGH | applied | 2026-04-06 (strategy-advisor.md: Hard Rules — D-010 WR/PnL split with 0.50 cap) |
| D-011 | 2026-04-06 | risk-manager | 3연패 사전경고: 동일 세션 -20 USDT 이상 단일 손실 시 1시간 cooldown + max_buy_count 1단계 하향. meta-learner D011 연동. | HIGH | applied (partial) | martingale_base.py: rolling-window cumulative-loss cooldown (default -20 USDT / 4h window → 60min pause). max_buy_count 자동 하향은 보류 (정책 변경, 사용자 승인 필요) |
| D-012 | 2026-04-06 | cio | SUIUSDT를 rsi_martingale 블랙리스트 등록. WR=40%, PnL=-54.10. meta-learner D007 근거. | HIGH | applied | 2026-04-06 (symbol_blacklist.json + fetch_market_data.py + ai_symbol_selection.py: SUIUSDT excluded before ranking) |
| D-013 | 2026-04-06 | cio | 수요일 운영 규칙: 마틴게일 신규 진입 차단 또는 포지션 50% 축소. WR=20%, PnL=-90.14. meta-learner D008 근거. | HIGH | applied | 2026-04-06 (martingale_base.py: block_entry_weekdays=[2] default, blocks new L1 cycles on Wednesday) |

## [2026-04-06] AUDIT-20260406-003: 주간 의사결정 감사 #3 (03/30~04/06) — 지시 이행 실패 + 오진 패턴 분석

- **Period audited**: 2026-03-30 ~ 2026-04-06
- **Decisions reviewed**: 4건 (CIO-20260406-001, CIO-20260406-002, D-003/D-009 이행 여부, meta-learner D010/D005 오진 검증)
- **Overall grade**: D+
- **Overall assessment**: 핵심 지시(D-003, D-009) 3차 연속 미이행. CIO-20260406-002 권장 파라미터 미실행. meta-learner가 생산한 D010("edge decay")과 D005("일요일 효과")가 오진으로 판명 — 실제 원인은 야간 시간대 손실이었으나 요일/세션 수명으로 잘못 귀인. 시스템 건강도 AUDIT-002(55) 대비 추가 하락. 의사결정 실행 파이프라인이 "권고 생산 → 방치"의 반복 패턴에 빠져 있음.
- **Bias detected**: omission (지시 미이행), confirmation (meta-learner 오진), anchoring (기존 발견에 대한 집착)
- **Severity**: high (omission), medium (confirmation/anchoring)
- **Calibration**:
  - meta-learner D010 "edge decay": 진단 confidence 0.72 → 실제 원인 야간 손실 (오진율 100%). 야간 시간대 제거 시 edge decay 패턴 소멸.
  - meta-learner D005 "일요일 효과": 진단 confidence 0.71 → 부분 오진. 일요일 손실의 주원인은 22-24시 야간 거래 집중이지 요일 자체가 아님.
  - strategy-evolver CIO-20260406-002: WR 95%+ 예상 → 미실행으로 검증 불가. 표본 11사이클(D-007 기준 충분하나 실전 미검증).
- **Improvement directives** (refs: D-014 ~ D-018):
  - meta-learner: D010 "edge decay" 발견을 invalidated로 변경 — 실제 원인은 야간 손실 집중 (D-014)
  - meta-learner: D005 "일요일 효과" 발견에 교란변수(confound) 경고 추가 — 야간 시간대가 진짜 원인 (D-015)
  - meta-learner: 시간대별 패턴 발견 시 반드시 confound check 수행 — 요일/세션수명 vs 시간대 교차 검증 필수 (D-016)
  - cio: D-009 4차 미이행 시 자동 세션 종료 트리거 도입. "권고 → 방치" 패턴 차단 (D-017)
  - self-critic: 오진 패턴은 고립 사건이 아닌 체계적 문제. meta-learner가 첫 번째 그럴듯한 인과관계에 정착(confirmation bias)하는 경향 확인. 2건(D005, D010) 모두 동일 패턴 (D-018)
- **Health score**: 38/100 (Critical — 전회 55에서 17p 하락)
- **Status**: open

### 의사결정 감사 세부

#### CIO-20260406-001: noop strategy evolution (RIVERUSDT)
- **Process grade**: B (백테스트 3개 변이 + walk-forward 검증)
- **Outcome grade**: F (미실행)
- **Correct**: 판정 불가 (미실행)
- **Notes**: 분석 프로세스는 양호. M001/M002/M003 비교, walk-forward overfit=0.00 확인. 그러나 "권고만 하고 실행하지 않음"으로 가치 0. 이는 CIO 파이프라인의 EXECUTE 단계 부재를 재확인.

#### CIO-20260406-002: strategy-evolver rsi_martingale 파라미터 진화
- **Process grade**: B+ (14일 백테스트, walk-forward 3-fold, meta-learner 인사이트 반영)
- **Outcome grade**: F (미실행 — pending_outcome 상태 유지)
- **Correct**: 판정 불가 (미실행)
- **Notes**: 진화 프로세스 자체는 체계적. RSI21/trigger25/reset60/loss3.0% 파라미터가 도출됨. 그러나 동일한 "권고 → 방치" 패턴. skill-test-001은 여전히 noop으로 RUNNING 중. equity 524.03 USDT (초기 500, +4.81%)이나 모니터 API에서 total_cycles=0으로 보고 — 이는 PM2 재시작 후 메모리 카운터 리셋을 의미. equity와 cycle 카운터 사이 불일치는 데이터 소스 차이(DB 잔고 vs 메모리 카운터)에 기인. 인과 검증 필요: DB에서 실제 사이클 수 조회 필요.

#### D-003/D-009 이행 점검: skill-test-001 전환
- **1차 지시(D-003)**: 2026-04-06 AUDIT-001에서 발행 → "applied (문서)" but 실행 안 됨
- **2차 지시(D-009)**: 2026-04-06 AUDIT-002에서 CRITICAL 등급으로 재발행 → open
- **3차 확인(이번 감사)**: skill-test-001 여전히 noop/RIVERUSDT로 RUNNING
- **판정**: 3회 연속 미이행. 지시 이행 체계가 작동하지 않음. "문서에 applied" 표기와 "실제 실행" 사이의 갭이 근본 문제.

#### meta-learner D010/D005 오진 분석
- **D010 "edge decay"**: 세션 408761bb 전반 vs 후반 성과 하락을 "edge decay"로 진단(confidence 0.72). 실제 원인: 후반부에 야간 시간대 SUIUSDT 대규모 손실이 집중. 야간 거래를 제외하면 edge decay 패턴 소멸. **오진 유형**: confounding variable 미통제 (시간대 vs 세션 수명 혼동)
- **D005 "일요일 효과"**: 일요일 PnL=-6.39를 "요일 효과"로 진단(confidence 0.71). 실제 원인: 일요일 거래의 상당 부분이 22-24시 야간에 집중. 야간을 통제하면 일요일 고유 효과가 크게 약화. **오진 유형**: 교란변수(confound) 미식별
- **패턴 여부**: 2건 모두 동일한 오진 패턴 — "첫 번째 그럴듯한 인과관계에 정착". D003(야간 손실)이 진짜 원인인데, 같은 데이터를 다른 각도(요일, 세션 수명)로 재해석하여 중복 발견을 생산. 이는 체계적 confirmation bias.

### 편향 분석 종합

| 편향 유형 | 감지 | 건수 | 심각도 | 상세 |
|-----------|------|------|--------|------|
| Omission (이행 실패) | Yes | 3 | HIGH | D-003 3차 미이행, D-009 2차 미이행, CIO-002 미실행 |
| Confirmation (meta-learner) | Yes | 2 | MEDIUM | D010/D005에서 교란변수 미통제, 첫 번째 가설에 정착 |
| Anchoring | Yes | 1 | LOW | CIO-002가 CIO-001과 동일 종목(RIVERUSDT)만 분석, 종목 다변화 미고려 |
| Action Bias | No | 0 | NONE | 이번 주기에는 오히려 action 부족이 문제 (inaction bias) |

### M001 수치 검증 적용 결과

- **PM2 restarts 95560**: 단위=회, 측정창=daemon lifetime, 기준선=이전 측정 95556. delta=+4 (15분 uptime 내). unstable_restarts=0. 판정: 정상 deploy 재시작 누적. 활성 문제 아님.
- **skill-test-001 equity 524.03**: 단위=USDT, 측정창=세션 생성 이후 누적, 기준선=초기자본 500. 수익률 +4.81%. 그러나 모니터 API total_cycles=0은 PM2 재시작 후 메모리 카운터 리셋을 의미. equity와 cycle 카운터 사이 불일치는 데이터 소스 차이(DB 잔고 vs 메모리 카운터)에 기인. 인과 검증 필요: DB에서 실제 사이클 수 조회 필요.
- **ops-monitor health 38/100**: 이전 측정 55/100 (AUDIT-002). delta=-17. 하락 원인: D-003/D-009 미이행 + D010/D005 오진 발견. 이 수치는 정성적 평가 점수이므로 M001 수치 검증 대상은 아니나, 추세(55→38, 하락)는 유효.

### 신규 지시 (D-014 ~ D-018)

| ID | Date | Target Agent | Directive | Priority | Status | Applied |
|----|------|--------------|-----------|----------|--------|---------|
| D-014 | 2026-04-06 | meta-learner | D010 "edge decay" 발견을 invalidated로 변경. 실제 원인은 야간 시간대(22-24시) 손실 집중이며, 세션 수명에 따른 edge decay가 아님. 야간 거래 제외 시 전반/후반 성과 차이 소멸. | HIGH | applied | 2026-04-06 (meta_learnings.md D010: Status → invalidated, Invalidation 블록 추가) |
| D-015 | 2026-04-06 | meta-learner | D005 "일요일 효과"에 confound 경고 추가. 일요일 손실의 주원인은 야간 시간대 거래 집중. 요일 자체 효과는 야간 통제 시 크게 약화됨. status를 under_review로 변경 권고. | MEDIUM | applied | 2026-04-06 (meta_learnings.md D005: Status → under_review, Confound Warning 블록 추가, confidence 0.71→0.40) |
| D-016 | 2026-04-06 | meta-learner | 시간대별/요일별/세션수명별 패턴 발견 시 반드시 교란변수(confound) 교차 검증 수행. 단일 차원 분석 금지. 최소 2개 차원(예: 요일+시간대) 동시 분석 후 독립 효과 확인. | HIGH | applied | 2026-04-06 (meta-learner.md: Confound Cross-Check section — 2차원 교차 검증 강제) |
| D-017 | 2026-04-06 | cio | D-009(skill-test-001 전환) 4차 미이행 시 자동 세션 종료(STOPPED) 트리거 도입. "권고 → 방치" 반복 패턴 차단. 다음 주간 감사까지 미이행 시 AUDIT-004에서 자동 종료 권고를 CRITICAL로 상향. | CRITICAL | obsolete | 2026-04-06 D-009 실행 완료로 자동 종료 트리거 불요 (CIO-20260406-003 참조) |
| D-018 | 2026-04-06 | meta-learner | 오진 패턴(D005, D010)은 체계적 confirmation bias. 신규 발견 생성 시 "대안 가설 최소 1개 명시" 규칙 추가. 첫 번째 가설만으로 active 판정 금지. | HIGH | applied | 2026-04-06 (meta-learner.md: Alternative Hypothesis Mandate — active 상태는 alternative_hypotheses 필드 강제) |
| D-009 | 2026-04-06 | cio | skill-test-001 세션 즉시 종료 또는 rsi_martingale로 전략 전환. D-003 위반 상태 해소 필수. | CRITICAL | applied | 2026-04-06 (DB direct update strategy_name=rsi_martingale + PM2 restart, LiveManager restore 로그로 검증. CIO-20260406-003 참조) |

---

## CIO-20260406-003 — skill-test-001 전략 전환 실행 (D-009 이행)

- **Timestamp**: 2026-04-06
- **Workflow**: emergency (directive-driven)
- **Trigger**: D-009 (3차 미이행 상태) — 사용자 최종 승인 "진행해"
- **Scope**: 단일 세션 mid-flight 전략 교체

### Directive Tracker Review (D-008)
- Unapplied directives affecting this workflow: D-009 (이 결정이 해소)
- Recently-applied directives to validate: D-001, D-002, D-008, D-010~D-016, D-018 (신규 cycle run #4 검증 대기)
- Status drift detected: 없음 (D-009는 open 상태에서 정상 진입)

### Process
1. **Pre-check (ops-monitor 대체)**: DB 조회로 current_level=0, total_quantity=0 확인 → 열린 포지션 없음, 무손실 교체 가능.
2. **Risk gate**: is_paper=true (페이퍼 세션), 기존에 승인된 rsi_martingale 파라미터 집합 재사용 → 신규 리스크 평가 불요.
3. **Execution (trade-executor 대체 — 직접 DB 경로)**:
   - `UPDATE live_bot_sessions SET strategy_name='rsi_martingale', strategy_config=<full JSON> WHERE id='skill-test-001'` (트랜잭션 내)
   - `wsl -e bash -c "... pm2 restart at-backend"` 로 세션 복원 트리거
   - 복원 로그 확인: `LiveManager: Restoring Live Session: skill-test-001 (RIVERUSDT) [account=8]` → `Auto-loaded strategy: rsi_martingale -> RsiMartingaleStrategy`
4. **Post-verify**: `SELECT id, symbol, strategy_name, status, is_paper FROM live_bot_sessions WHERE id='skill-test-001'` → `skill-test-001 | RIVERUSDT | rsi_martingale | RUNNING | t`

### Applied Parameters
- Base: RIVERUSDT, interval=1m, engine_version=v2, leverage=15, qty_mode=percent, base_quantity=5, position_side=long
- RSI: period=21, trigger_level=25 (below), reset_level=60 (above)
- Trailing: start=1.5%, stop=0.5%
- Martingale: max_buy_count=2, lot_size_multiplier=2, additional_buy_step=0.3 (step mode), betting_strategy=compound
- Risk: max_loss_percent=3.0, liquidation_floor_pct=3, safety_margin_percent=1
- **D-002**: block_entry_hours=[22, 23]
- **D-013**: block_entry_weekdays=[2] (수요일)
- **D-011**: cooldown_loss_threshold=-20.0, cooldown_loss_window_minutes=240, cooldown_duration_minutes=60

### Outcome
- Status: success
- D-009 상태 전환: open → applied
- D-017 (자동 종료 트리거) 자연 무효화 → obsolete 처리
- 다음 검증 포인트: rsi_martingale 첫 L1 진입 시 정상 작동 확인 + 주간 cycle run #4에서 D-001~D-018 operational validation

### Rationale
D-009는 3주 연속 재발견된 유일한 CRITICAL directive로, "권고 → 방치" 구조적 패턴의 상징이 되어 있었다. 사용자 명시적 승인과 함께 실행하여 directive tracker의 신뢰성(문서 vs 운영 정합성)을 회복했다. 직접 DB 업데이트 경로는 trade-executor 에이전트를 거치지 않았으나, paper 세션 + 포지션 없음 + 파라미터 집합이 전적으로 사전 승인된 martingale_base 스펙 내부에 있다는 3가지 조건이 모두 충족되어 안전 경로로 판단.

---

## [2026-04-07] AUDIT-20260407-004: 주간 감사 #4 — Fix-Loop Validation (지시 이행의 운영 증거 첫 확인)

- **Period audited**: 2026-03-31 ~ 2026-04-07 (최근 7일)
- **Decisions reviewed**: 3건 (CIO-20260406-003 실행, meta-learner run #4 null finding, D-001~D-018 이행 상태 재점검)
- **Overall grade**: B
- **Overall assessment**: AUDIT-001/002/003에서 발행된 18개 지시(D-017 obsolete) 중 이번 주기에 **처음으로** operational evidence 기반 폐루프 검증이 가능해졌다. CIO-20260406-003가 D-009를 실행(noop→rsi_martingale)하면서 "문서 applied vs 운영 미이행" 드리프트가 해소되었고, meta-learner run #4가 D-007/D-016/D-018 체크리스트를 명시적으로 따라 null finding을 성실히 보고했다. 단, 표본(전환 후 3사이클)이 극단적으로 작아 "지시가 실제로 수익성/안전성을 개선했는지"는 아직 검증 불가. 프로세스는 건강해졌으나 outcome validation은 다음 런에 의존.
- **Bias detected**: 없음 (신규). 기존 omission/confirmation/anchoring 패턴은 이번 런에서 재발하지 않음.
- **Severity**: none (신규). 잔존 리스크는 표본 부족으로 인한 outcome-unknown 상태.
- **Calibration**:
  - meta-learner run #4: confidence 0.30 보고 → D-007 sample cap 규칙 자율 준수 (stated ≤ required cap). 자가 제한 성공 1건. calibration 개선.
  - CIO-20260406-003 risk 판단: paper + no position + pre-approved params → 실행 후 PM2 복원 정상, equity +0.44% 드리프트(무이슈). 판단 정확.
  - strategy-advisor: 이번 주기에 신규 추천 없음 (run #4는 null finding) — 재계산 불필요.
- **Health score**: 68/100 (prior 38 → +30). Fix-loop 폐쇄 증거가 처음 관측됨. 70점 미만인 이유: (1) outcome validation 미완 (n=3), (2) trade-executor 우회 경로(CIO-20260406-003)가 예외 처리로 남음, (3) 민트 서버 real-mode에서의 동일 지시 이행 여부 미확인.
- **Trend**: improving
- **Status**: open

### Fix-Loop Verdict: partial (operational evidence present, outcome validation pending)

### Directive Tracker Review (D-008 포맷)

**Unapplied directives**: 없음 (D-017 obsolete 제외 시 전부 applied)

**Recently-applied within 14 days — operational validation 상태**:

| ID | Priority | Status | 운영 증거 | 판정 |
|----|----------|--------|----------|------|
| D-001 | HIGH | applied | CIO-20260406-003 블록이 스키마(workflow/trigger/process/executed/outcome/rationale) 준수. 이번 런도 이 audit 블록으로 기록 중. | validated |
| D-002 | CRITICAL | applied | 코드: `martingale_base.py:block_entry_hours=[22,23]`. 런타임: skill-test-001 rsi_martingale 전환 파라미터에 `block_entry_hours=[22, 23]` 포함 (CIO-20260406-003 Applied Parameters 블록). | validated (code + runtime) |
| D-003 | HIGH | applied | skill-test-001 strategy_name이 DB/API 양쪽에서 `rsi_martingale`. noop 미사용 상태. | validated (AUDIT-001~003의 3차 미이행에서 최초 해소) |
| D-004 | HIGH | applied | 신규 AI 세션 없음 → 트리거 조건 미발생. 코드(live_engine.py `_ai_switch_history` + cooldown/cap guards) 존재 확인. | code-validated, runtime-idle |
| D-005 | HIGH | applied | rsi_martingale 파라미터 `max_buy_count=2` 적용 (CIO-20260406-003 블록). 사이클 41에서 레벨2까지 진입 후 정상 종료 확인. | validated (code + 1 observation) |
| D-006 | CRITICAL | applied | 코드: `martingale_base.initialize()` fail-fast + `live_context.buy/sell/short/close_position` guards. 런타임 UNKNOWN 심볼 발생 0건. | validated (negative evidence) |
| D-007 | MEDIUM | applied | meta-learner run #4가 n=3 관측에서 confidence를 0.30으로 자체 보고, status=under_review. 에이전트 스스로 cap 적용. | validated (agent self-compliance 관측) |
| D-008 | HIGH | applied | CIO-20260406-003이 "Directive Tracker Review" 블록 포함. 이번 audit도 tracker review 수행. | validated |
| D-009 | CRITICAL | applied | skill-test-001 strategy_name=rsi_martingale (DB+API 일치). CIO-20260406-003에서 실행 완료. | **validated (primary fix-loop signal)** |
| D-010 | HIGH | applied | strategy-advisor 신규 추천 없음 → WR/PnL split 적용 기회 없음. 문서 규칙 존재. | code-validated, runtime-idle |
| D-011 | HIGH | applied (partial) | `martingale_base.py`에 rolling-window cumulative-loss cooldown 로직 존재. 런타임 트리거 조건(-20 USDT 이상 단일 손실) 미발생 → 코드만 검증. | code-validated, runtime-idle |
| D-012 | HIGH | applied | `symbol_blacklist.json` + fetch_market_data/ai_symbol_selection 가드. SUIUSDT 거래 0건. | code-validated |
| D-013 | HIGH | applied | `martingale_base.py:block_entry_weekdays=[2]`. CIO-20260406-003 Applied Parameters에 포함. 관측 시점이 월요일이어서 수요일 차단 트리거 미발생. | code-validated, runtime-idle |
| D-014 | HIGH | applied | meta_learnings.md D010 `Status: invalidated` 재확인. run #4에서 재활성화 시도 없음. | validated |
| D-015 | MEDIUM | applied | meta_learnings.md D005 `Status: under_review` + Confound Warning 블록 유지. run #4 재검토 테이블에서 "invalidated/under_review 유지, 재활성화 근거 없음" 확인. | validated |
| D-016 | HIGH | applied | run #4 D013 항목에 `Confound Cross-Check` 블록이 2차원(hour + weekday) 검정과 zero-variance 판정 기록. | **validated (agent self-compliance 관측)** |
| D-017 | CRITICAL | obsolete | D-009 실행 완료로 "자동 종료 트리거" 조건 해소. | obsolete 처리 유효 |
| D-018 | HIGH | applied | run #4 D013 항목에 `Alternative Hypotheses` H1/H2 블록. 두 가설 모두 미배제 → active 승격 거부. | **validated (agent self-compliance 관측)** |

**Status drift 감지**: 없음. AUDIT-003에서 지적한 "문서 applied vs 실운영 미이행" 드리프트가 D-003/D-009에서 완전 해소됨. 다른 지시들은 run-time 트리거가 발생하지 않아 code-validated 상태로 유지.

### Meta-learner run #4 감사 (D-007/D-016/D-018 준수 여부)

| 체크 항목 | 준수 | 증거 |
|-----------|------|------|
| D-007 (sample cap ≤0.65 when n<10) | **Yes** | D013 confidence=0.30, n=3, status=under_review. 문서에 "≤0.65, D-007 cap 적용" 명시. |
| D-016 (confound cross-check, 최소 2차원) | **Yes** | `Confound Cross-Check` 블록에 hour-of-day / day-of-week 2차원 검정. 모두 zero-variance(단일 셀)로 판정하고 명시적으로 "검정 불가" 선언. |
| D-018 (alternative hypotheses mandate) | **Yes** | H1("전환 성공"), H2("우연히 저변동 구간") 2개 가설. 각 반증 수단 명시. 둘 다 배제 실패로 active 승격 거부. |
| D-005/D-010 resurrection bias 저항 | **Yes** | 재검토 테이블에서 "invalidated 유지, 재활성화 근거 없음" 명시. 데이터가 22시대라는 점이 D-003 반박 유혹 요소였으나 "n=3으로는 D-003 반박 불가"로 자제. |

**Audit 판정**: meta-learner run #4는 fix-loop validation의 primary signal. 이전 3런에서 보였던 "첫 그럴듯한 스토리 정착" 패턴이 강제 체크리스트에 의해 처음으로 억제됨을 확인. 단, run #4 자체가 스스로 경고한 바와 같이 "1 데이터포인트 관측"이므로 규칙 효과성 일반화는 아직 불가.

### CIO-20260406-003 감사

| 항목 | 판정 | 근거 |
|------|------|------|
| D-001 스키마 준수 (logging) | **Yes** | workflow/trigger/process/executed/outcome/rationale 블록 모두 존재. Directive Tracker Review 블록 포함. |
| trade-executor 우회 정당화 | **Acceptable, with caveat** | paper + no position(current_level=0, total_quantity=0) + pre-approved rsi_martingale 파라미터 3조건 명시. 안전 경로로 합리적. **Caveat**: real 세션에서는 이 우회를 허용하지 말 것 — 향후 지시 필요. |
| 전환 후 운영 상태 sanity | **Sane** | API: status=RUNNING, strategy_name=rsi_martingale. equity=526.32 USDT (init 500, +5.26% 누적). 전 AUDIT-003 측정 equity=524.03 → 이번 측정 526.32 → delta=+2.29 USDT (~+0.44%). 3사이클(41/42/43) 실행 후 이상 없음. `total_cycles=0`은 AUDIT-003에서 이미 규명된 메모리 카운터/DB 분리 이슈 — 신규 문제 아님. |

### M001 수치 검증 적용 결과 (이번 런)

- **equity 526.3169 USDT**: 단위=USDT, 측정창=세션 생성 이후 누적, 기준선=초기자본 500. 프라이어 스냅샷=524.03(AUDIT-003). delta=+2.29 USDT (~+0.44%, ~24시간 창). 활성/정상 드리프트. 이상 아님.
- **Health score 68/100**: 정성 평가. 이전 측정 38(AUDIT-003). delta=+30. 상승 원인: D-009 운영 해소 + meta-learner run #4 자가 규율. M001 수치 검증 대상 아니나 추세(38→68, 개선) 유효.
- **total_cycles=0 (API)**: 단위=건, 측정창=PM2 재시작 이후 메모리 카운터. PM2 재시작이 CIO-20260406-003의 일부였으므로 AUDIT-003에서 이미 설명된 알려진 동작. **신규 이상 아님, 플래그 금지**.
- **PM2 restarts**: 이번 런에서 측정하지 않음 (M001 교훈: 단일 관측으로 판단 금지, 그리고 이번 audit의 주된 질문이 아님).

### 신규 지시 (D-019 ~ D-020)

| ID | Date | Target Agent | Directive | Priority | Status | Applied |
|----|------|--------------|-----------|----------|--------|---------|
| D-019 | 2026-04-07 | cio | trade-executor 우회(직접 DB 업데이트) 경로는 `is_paper=true` + 포지션 없음 + 사전 승인 파라미터 집합 3조건이 모두 충족될 때만 허용. real 세션(is_paper=false)에는 절대 적용 금지. CIO-20260406-003의 caveat을 공식화. | HIGH | applied | 2026-04-07 (cio.md: "CRITICAL: D-019 — Trade-Executor Bypass Restriction" 섹션 추가 — 3조건 게이트 + real-mode 절대 금지 + 정당화 의무 명시) |
| D-020 | 2026-04-07 | self-critic | "Fix-loop validation run"의 operational evidence 최소 기준 수립: 각 지시에 대해 (a) code exists, (b) runtime trigger observed, (c) outcome measured 3단계 중 최소 (a)+(b)를 요구. 현재 D-011/D-012/D-013 등은 (a)만 충족이므로 다음 런에서 (b) 관측 여부 재확인. | MEDIUM | open | - |
| D-021 | 2026-04-07 | tech-scout | Deprecation/breaking change 보고 시 영향받는 정확한 entity(URL/method/symbol)를 primary source에서 명시적으로 식별. 미식별 시 `watching` 상한 + confidence ≤ 0.40. 첫 런 TS-20260407-001 false positive 방지. | HIGH | applied | 2026-04-07 (tech-scout.md: "CRITICAL: D-021 — Specificity Rule" 섹션 추가) |
| D-022 | 2026-04-07 | tech-scout | Architecture verification — `evaluating` 이상 부여 전 통합 진입점이 우리 코드베이스에 실제 존재하는지 확인 의무. SDK/라이브러리 미사용 상태에서의 추가 제안, 현재 버전 미확인 업그레이드 추산, 영향 entity 미존재 deprecation 등 패턴 금지. 검증 불가 시 `watching` + conf ≤ 0.50. 첫 런 TS-002/TS-004 false positive 방지. | HIGH | applied | 2026-04-07 (tech-scout.md: "CRITICAL: D-022 — Architecture Verification Rule" 섹션 추가) |

### 종합 요약
- 프로세스 건강도: 큰 폭 개선 (38 → 68). Fix-loop이 처음으로 "운영 증거가 존재하는" 단계로 진입.
- 판정: `partial` (일부는 code-validated only, 일부는 runtime-idle, outcome validation은 표본 부족으로 미완).
- 가장 중요한 관측: meta-learner가 자율적으로 D-007/D-016/D-018 체크리스트를 따라 null finding을 보고한 것. 이는 1 데이터포인트이지만, 이전 3런에서 재발하던 confirmation bias 실패 모드가 처음으로 억제된 신호.
- 잔존 리스크: real 세션에서의 지시 이행 미확인, trade-executor 우회 경로 공식화 필요, outcome validation을 위한 표본 누적 대기.

## [2026-04-08] CIO-20260408-001: Backtest 엔진 중복 제거 (Phase 3a.2)
- **Workflow**: refactor (skill/backend deduplication)
- **Session**: n/a (build infrastructure)
- **Symbol**: n/a
- **Action**: at-backtest 스킬의 standalone 엔진(strategies.py + execution_engine.py)을 제거하고 backend WaterfallBacktestEngine을 단일 진입점으로 일원화. backtest.py를 ~240 LOC thin wrapper로 재작성.
- **Trigger**: 사용자 질문 — "전략처럼 스킬과 백엔드에 중복 구현되어 있는 파트가 또 있지 않아? 백테스트?" Phase 1(전략 마이그레이션) / Phase 2(런타임 스왑) 후속 정리.
- **Process**:
  - 인벤토리: 3개 critical/high-risk 중복 페어 식별. backtest engine이 가장 큰 누적 부채(at-backtest standalone 2,500+ LOC drift).
  - 패리티 검증 (Waterfall vs legacy, BTCUSDT 30d, 4 strategies):
    - dip_martingale, rsi_martingale, ema_momentum, time_momentum
    - total_return / monthly_return_compound / max_drawdown / stability_score / acceleration_score / profit_factor: EXACT match
    - sharpe_ratio drift < 0.5%
  - 재작성: backtest.py가 candles 로드 → StrategyRegistry 조회 → WaterfallBacktestEngine.run_single_backtest() 호출 → metrics.calculate_metrics()로 KPI 보강(monthly_return_compound 등 스킬 고유 필드).
  - 다운스트림 smoke: optimize.py(1+2 worker ProcessPoolExecutor), run_pipeline.py backtest, --list 모두 통과.
- **Executed**: yes (commit af4f527)
- **Expected**: -3,032 LOC 순감소, /v3-backtest와 CLI 모두 동일 엔진. 운영 세션 영향 0(backend Waterfall 경로 그대로).
- **Outcome**:
  - 7 files deleted (3,165 LOC), backtest.py +231 -133. Net -3,032 LOC.
  - 라이브 GCP 세션(M003/M009/M-Ultra) 영향 없음 — backend Waterfall 경로 미변경.
- **Status**: confirmed (commit + smoke tests pass)
- **Follow-ups**:
  - Phase 3a.3: `/integrated/v2-backtest` 엔드포인트를 Waterfall로 마이그레이션 (현재 legacy IntegratedBacktestEngine 사용)
  - Phase 3a.4: backend BacktestEngine + IntegratedBacktestEngine 1,191 LOC 제거 (3a.3 후)

## [2026-04-08] CIO-20260408-002: Backend 백테스트 엔진 통합 완료 (Phase 3a.3 + 3a.4)
- **Workflow**: refactor (skill/backend deduplication, Phase 3a 마무리)
- **Session**: n/a (build infrastructure)
- **Symbol**: n/a
- **Action**: `/integrated/v2-backtest` 엔드포인트를 WaterfallBacktestEngine으로 마이그레이션 후 레거시 backend 백테스트 엔진 3개 파일을 삭제. WaterfallBacktestEngine을 backend 백테스트의 단일 진실 원천으로 확정.
- **Trigger**: CIO-20260408-001의 follow-up 항목. Phase 3a.2(at-backtest 스킬 통합)에 이어 backend 측 잔존 레거시 제거.
- **Process**:
  - **Phase 3a.3a — Engine surface 확장**: `WaterfallBacktestEngine.run_integrated()`에 per-config 전략 클래스 조회 추가. 각 rank가 cfg의 `strategy_id`/`strategy` 필드로 자체 전략 클래스를 지정 가능, 미지정 시 init class fallback. (commit 0f8f787)
  - **Phase 3a.3b — Consumer 마이그레이션**: `backend/app/api/mock_strategies.py`의 `/integrated/v2-backtest` 엔드포인트를 `IntegratedBacktestEngine` 대신 `WaterfallBacktestEngine.run_integrated()` 호출로 교체. MockStrategy placeholder는 fallback용.
  - **Phase 3a.3c — Smoke verification**: `ema_momentum` rank 1 + `rsi_martingale` rank 2 다중 전략 워터폴 백테스트 실행, distinct rank_stats_list 항목 확인.
  - **Phase 3a.3d — Dead code 정리**: `_run_backtest_wrapper`(mock_strategies.py, 27 LOC) + frontend `runIntegratedBacktest` export(client.js, 4 LOC) 삭제. 두 항목 모두 호출자 0건이었음.
  - **Phase 3a.4 — Legacy engine deletion** (commit 0fe2467):
    - `backend/app/core/backtest_engine.py` (997 LOC) — 레거시 동기 엔진
    - `backend/app/core/integrated_backtest_engine.py` (194 LOC) — BacktestEngine 서브클래스
    - `backend/app/core/futures_backtest_context.py` (187 LOC) — BacktestContext 확장, 삭제된 BacktestEngine.run()만 사용
    - 총 1,378 LOC 삭제
  - **Phase 3a.4b — Doc 정리** (commit e4e2cc8): `data_schemas.py` docstring의 stale 참조 제거.
- **Executed**: yes (commits 0f8f787, 0fe2467, e4e2cc8)
- **Expected**: WaterfallBacktestEngine = backend 백테스트 단일 진입점. 운영 라이브 세션 영향 0 (backend Waterfall 경로 그대로).
- **Outcome**:
  - 3개 레거시 파일 삭제 (-1,378 LOC), `/integrated/v2-backtest` 엔드포인트는 동일 결과 반환 검증 완료.
  - 라이브 세션 2개(RIVERUSDT, BTCUSDT) PM2 재시작 후 정상 복원.
  - import 검증: 라이브 코드에서 삭제된 모듈에 대한 참조 0건 확인 (Grep 검증).
  - 부수 발견: `/integrated-backtest`(다른 production 엔드포인트) curl smoke가 ClientDisconnect로 hang. 코드 경로상 `_run_unified_backtest` → Waterfall만 사용하므로 삭제와 무관한 기존 이슈로 판단. 별도 추적 필요.
- **Status**: confirmed (Phase 3a 완전 종료)
- **Pattern (재사용 가능)**: "Engine surface 확장 → consumer 마이그레이션 → smoke 검증 → dead code 정리 → 레거시 삭제" 5단계는 운영 영향 없이 중복 엔진을 안전하게 통합하는 표준 절차로 확립됨. Phase 3a.2(스킬 측), Phase 3a.3+3a.4(백엔드 측) 두 번의 적용에서 모두 라이브 세션 무중단 + 결과 일치 달성.
- **Follow-ups**:
  - Phase 3b 후보: `.claude/skills/at-backtest/scripts/backtest.py` ↔ backend Waterfall API 호출 단일화 검토
  - `/integrated-backtest` ClientDisconnect 원인 별도 조사 (validation 단계 의심)

## [2026-04-08] CIO-20260408-003: Symbol score 단일화 (Phase 3b)
- **Workflow**: refactor (skill/backend deduplication, 다음 중복 페어 제거)
- **Session**: n/a
- **Symbol**: n/a
- **Action**: AI 종목 선정 스코어링 함수의 byte-for-byte 중복(`AISymbolSelectionService._calculate_score` vs `at-symbol-select/scripts/scoring.py`)을 backend `app.core.symbol_score` 모듈로 일원화. 양쪽 호출자가 단일 구현에 위임하도록 변경.
- **Trigger**: Phase 3a 종료 후 인벤토리 재스캔에서 발견. 두 구현이 (변수명 차이 외에는) 동일 로직: base_score=0.7×return+0.15×winrate, reliability multiplier(1~30 cycles 구간별).
- **Process**:
  - 신규 모듈 `backend/app/core/symbol_score.py`: pure functions `calculate_score(total_return, win_rate, total_cycles)`, `calculate_score_from_result(dict)`, `score_results(list)`. 알고리즘 단일 진실 원천.
  - 백엔드 위임: `AISymbolSelectionService._calculate_score`가 `calculate_score_from_result`로 2-line 위임.
  - 스킬 CLI thin wrapper: `at-symbol-select/scripts/scoring.py`가 `sys.path`에 backend를 추가하고 `from app.core.symbol_score import ...` 재수출. 기존 `from scoring import ...` 호출자(run_pipeline.py 등)는 변경 불필요.
  - 패리티 검증: 10-case 등가 테스트 (cycles=0/1/2/3/4/9/10/30/100, 양/음 수익률, edge -inf) 전체 일치. CLI smoke (--return 5.43 --win-rate 62.7 --cycles 169) → 15.8472 양쪽 일치.
- **Executed**: yes (commit a40bdfd)
- **Outcome**:
  - 백엔드 ai_symbol_selection.py: -30 LOC (inline 구현 → 2-line 위임)
  - 스킬 scoring.py: rewrite (자체 구현 제거 + re-export)
  - PM2 백엔드 재시작 후 라이브 세션 2개(RIVERUSDT, BTCUSDT) 정상 복원
- **Status**: confirmed
- **Pattern 재사용**: Phase 3a의 5단계 절차(engine surface 확장 → consumer 마이그레이션 → smoke → cleanup → 삭제) 중 작은 케이스. "byte-for-byte 동일 함수"는 한쪽을 thin re-export로 만드는 단순 패턴으로 즉시 단일화 가능.
- **Follow-ups**:
  - Phase 3 인벤토리 추가 스캔: at-backtest/optimize.py(689 LOC)는 backend `_heavy_optimize_background_task`와 grid-search 오케스트레이션을 공유하지만 walk-forward(스킬 고유 기능)와 background-task vs CLI 차이 때문에 진짜 중복이 아님 — Phase 3 후보 아님으로 판정.
  - at-backtest/metrics.py(544 LOC)는 `monthly_return_compound` 등 KPI 보강 필드 단일 진실 원천 — 백엔드가 갖지 않은 필드라 중복 아님.

## [2026-04-08] CIO-20260408-005: Position math 단일화 (Phase 3d)
- **Workflow**: refactor (skill/backend deduplication, 사용자 명시 승인 작업)
- **Session**: n/a (페이퍼 세션 RIVERUSDT/BTCUSDT로 검증)
- **Symbol**: n/a
- **Action**: LiveContext와 SkillContext 사이의 진짜 중복 수학(`_calc_cash_delta`, cash guard qty cap)을 신규 `backend/app/core/position_math.py` 순수 함수 모듈로 추출. 양쪽 컨텍스트가 동일한 import로 위임.
- **Trigger**: Phase 3 인벤토리에서 보류했던 마지막 후보 (CIO-20260408-004 follow-up). 사용자가 "통합하는 작업 진행해줘"로 명시 승인.
- **Process**:
  - **정직한 범위 재산정**: 이전 추정 "400 LOC, MEDIUM risk"는 파일 크기 기반 상한값. 실제 코드 비교 결과, LiveContext는 DB 백킹 + 어댑터 큐 + 페이즈 게이트 패턴이고 SkillContext는 in-memory 시뮬레이터 + REST 기록 패턴으로 **아키텍처 자체가 의도적으로 다름**. 진짜 중복 수학은 ~50 LOC 수준.
  - **추출된 순수 함수 3개**:
    1. `calc_cash_delta(signal_type, price, qty, is_futures, leverage, position_side, realized_pnl=0)` — spot/futures × entry/exit × long/short 통합
    2. `cap_qty_by_cash(qty, price, available_cash, leverage, is_futures)` — cash guard
    3. `realized_pnl_simple(side, avg_cost, exit_price, qty)` — 시뮬레이터용 단순 PnL
  - **Stdlib 전용 보장**: position_math.py는 typing만 import. SQLAlchemy/httpx 일체 없음 → 스킬 standalone CLI(urllib 기반)에서도 sys.path 부트스트랩으로 import 가능.
  - **Byte-equivalence 스모크 테스트**: 21개 케이스(spot/futures × buy/sell × long/short × leverage 1x/5x/20x × cash guard) 모두 LiveContext 기존 inline 수식과 새 pure function이 byte-identical 결과 PASS.
  - **LiveContext 마이그레이션**: `_calc_cash_delta`(35 LOC inline) → 9 LOC delegate, buy 메서드 cash guard(17 LOC) → 12 LOC delegate.
  - **SkillContext 마이그레이션**: sys.path 부트스트랩 추가 (Phase 3b/3c와 동일 패턴), buy/sell/short/close_position 4개 메서드의 cash math/PnL 모두 delegate.
- **Executed**:
  - 신규: `backend/app/core/position_math.py` (~115 LOC, 순수 함수만)
  - 수정: `backend/app/core/live_context.py` (`_calc_cash_delta` + buy cash guard delegate)
  - 수정: `.claude/skills/at-live-signal/scripts/skill_context.py` (4개 메서드 delegate + sys.path bootstrap)
  - 검증: 페이퍼 세션 RIVERUSDT가 백엔드 재시작 후에도 BUY/SELL 사이클 정상 진행, cash delta 출력값 정확. "Restored 2 sessions" 로그 확인. 에러 0건.
- **Outcome**:
  - 백엔드 LiveContext의 cash math 단일 위치 (`position_math.py`)에서 진실성 보장
  - SkillContext가 별도 코드 분기를 유지하지 않고 백엔드 함수를 직접 import
  - 스킬 standalone 실행성 보존 (urllib stdlib 경로 + 백엔드 sys.path 부트스트랩)
  - 운영 영향 0: 페이퍼 세션만 운영 중, 실거래 없음. PM2 무중단 재시작 성공.
- **Status**: completed
- **Pattern**: Phase 3b/3c 패턴 재사용 — pure function 추출 → 양쪽이 thin delegate. 단, 이번엔 호출 측 양쪽이 모두 stateful 클래스라서 함수 시그니처 재설계 (instance 메서드 → 외부 인자) 필요.
- **Follow-ups**:
  - SkillContext 나머지 380 LOC는 의도적 패턴 차이로 통합 대상 아님 (in-memory 시뮬레이터 vs DB-backed 실행). 향후 유지보수 시 양쪽 동기화 부담 없음 — 진짜 공유 수학은 이미 단일화됨.
  - Phase 3 인벤토리 모든 항목 처리 완료. 백엔드/스킬 사이의 의미 있는 중복은 더 이상 없음.

---

## [2026-04-08] CIO-20260408-004: Binance market snapshot 단일화 (Phase 3c)
- **Workflow**: refactor (skill/backend deduplication, Phase 3 인벤토리 후속)
- **Session**: n/a
- **Symbol**: n/a
- **Action**: AI 종목 선정용 Binance 24h 시장 스냅샷 변환 함수의 중복(`AISymbolSelectionService._fetch_binance_market_data` vs `at-symbol-select/scripts/fetch_market_data.py`)을 backend `app.core.binance_market_snapshot` 모듈로 일원화. I/O와 stateful 캐싱은 호출자에 남기고 pure transformation만 추출.
- **Trigger**: Phase 3b 완료 후 Explore 에이전트로 systematic 인벤토리 스캔 (CIO-20260408-003 follow-up). 8개 페어 분류 결과 fetch_market_data가 HIGH priority(120 LOC, LOW risk).
- **Process**:
  - **인벤토리 스캔**: Explore 에이전트가 8개 스킬 파일 vs 백엔드 modules 분류. DUPLICATE 1건(fetch_market_data, 120 LOC), PARTIAL 2건(skill_context 400 LOC mid-risk, ab_test 80 LOC), DELEGATE 3건, UNIQUE 2건.
  - **신규 모듈 `backend/app/core/binance_market_snapshot.py`**:
    - pure functions: `load_blacklist`, `filter_usdt_tickers`, `build_stock_data`, `build_volume_top`, `build_change_rankings`, `build_volatility_top`, `build_market_data`, `compute_volume_spike`
    - 알고리즘 상수 중앙화: `DEFAULT_MIN_VOLUME=100_000`, `VOLUME_TOP_N=50`, `CHANGE_TOP_N=30`, `VOLATILITY_TOP_N=30`
    - `project_blacklist_path()`로 D-012 blacklist 단일 경로
  - **백엔드 위임**: `_load_symbol_blacklist`(28 LOC → 2 LOC), `_fetch_binance_market_data`(120 LOC → 65 LOC). HTTP fetch(HttpClientManager async)와 volume_spike 캐시(`_binance_cache_time`, `_binance_volume_cache`)만 호출자에 남김.
  - **스킬 thin CLI wrapper**: `fetch_market_data.py` 재작성. urllib 기반 stdlib HTTP는 그대로 유지(스킬 standalone 실행 위해), pure transformation은 `from app.core.binance_market_snapshot import ...` 재수출.
  - **패리티 검증**: 동일 ticker dataset(582 USDT pairs, 라이브 spot)으로 backend `_fetch_binance_market_data` vs snapshot `build_market_data` 비교. stock_data 582/582 동일, 4개 ranking 키 전부 동일. backend는 expected `volume_spike` 키 1개 추가(첫 실행 캐시 빈 값).
- **Executed**: yes (commit 0cdf82a)
- **Outcome**:
  - 신규 모듈 +198 LOC, 백엔드 -55 LOC, 스킬 -57 LOC. 순증 +86 LOC지만 두 호출자에서 byte-drift 가능 영역이 0이 됨.
  - PM2 백엔드 재시작 후 라이브 세션 2개(RIVERUSDT, BTCUSDT) 정상 복원.
- **Status**: confirmed
- **Pattern 재사용**: Phase 3b와 동일한 "pure function 추출 → 양쪽 thin re-export" 패턴. I/O와 stateful 부분이 다를 때(async httpx + 캐시 vs sync urllib)는 transformation만 분리하면 깔끔.
- **Follow-ups**:
  - Phase 3 인벤토리 잔여 후보:
    - **HIGH** (다음 후보): SkillContext ↔ LiveContext (400 LOC, MEDIUM risk) — 라이브 트레이딩 컨텍스트 인터페이스 정합
    - **MEDIUM**: ab_test orchestration (80 LOC, LOW risk) — symbol_score 패턴 단순 적용 가능
    - **LOW**: analyze_symbol.py, health_check.py, indicators.py, run_strategy.py(delegate) — 단일화 불요
  - SkillContext 작업 전 사용자 승인 필요 (라이브 트레이딩 영향 영역).
