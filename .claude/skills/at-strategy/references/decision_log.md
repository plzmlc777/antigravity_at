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
