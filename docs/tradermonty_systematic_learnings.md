# tradermonty/claude-trading-skills 시스템적 학습 문서

**작성일**: 2026-04-29
**작성자**: hcpark + Claude Code
**문서 목적**: tradermonty 검토 결과 중 **Antigravity 자동매매 시스템에 향후 도입 가치가 있는 시스템 패턴**을 정리. 매매 전략 자체는 검증 결과 직접 차용 가치 낮음 → **메타 인프라/자동화 패턴**에 집중.
**상태**: 문서화만, 즉시 구현 X. 향후 결정 시 참조용.

---

## 1. 배경 — 왜 이 문서가 필요한가

### 1-1. 매매 전략 검증 결과 (즉시 도입 가치 없음)

| 전략 | 백테스트 결과 (BTC daily, 2022-2026) | 평가 |
|---|---|---|
| VCP | +15% (PF 3.22, 9 trades) | 빈도 부족, B&H 미달 |
| Breakout | +2% (PF 1.26, 8 trades) | 약함 |
| Pair Trade (BTC/ETH) | -14% (0% 승률, 7 trades) | 실패 |
| CANSLIM, 배당 3종 | 미검증 (펀더멘털 데이터 없음) | 인프라 없음 |
| Buy-and-Hold (벤치마크) | +62% | — |

**원인 진단**:
- tradermonty 전략은 **미국 주식 다종목 풀** 환경에서 설계됨
- 단일 BTC에 적용 시 진입 빈도 부족 → 통계적 우위 상실
- 페어 트레이딩은 코인테그레이션 가정 무너짐 (BTC/ETH 7.3%만 cointegrated)
- 펀더멘털 의존 전략은 본인 OHLCV 인프라로 구현 불가

### 1-2. 그러나 시스템 인프라는 학습 가치 큼

51개 스킬 중 매매 전략은 8개. **나머지 43개가 메타 인프라/자동화/오케스트레이션** — 이 부분이 본인 SISDS 파이프라인과 직접 비교 가능.

---

## 2. Antigravity 시스템과의 매핑 비교

### 2-1. 현재 본인 시스템 (SISDS Pipeline)

```
sandbox → audition → graduated → paper → live (running) → degraded
```

에이전트:
- `cio` (오케스트레이터)
- `strategy-builder` (전략 생성)
- `sandbox-researcher` (sandbox 단계 연구)
- `audition-judge` (graduated 승급 결정)
- `paper-scheduler` (paper 운영)
- `live-monitor` (live 감시)
- `meta-learner` (트레이드 분석)
- `meta-observer` (시스템 자체 감시)
- `skill-architect` (자동 skill 생성)
- `risk-manager` (VETO 권한)

### 2-2. tradermonty 시스템

```
session_logs → idea_mining → skill_design → review → PR
                                                       ↓
                                                  (병합 후)
session_logs → skill_improvement_loop → 일일 1개 자동 개선
                                                       ↓
                                                    PR 갱신

Edge Pipeline:
  Hint → Concept → Strategy → Reviewer (REVISE 루프) → Candidate → Export
```

스킬 (메타 인프라만):
- `skill-designer`, `skill-idea-miner`, `skill-integration-tester`, `dual-axis-skill-reviewer`
- `edge-hint-extractor`, `edge-concept-synthesizer`, `edge-strategy-designer`, `edge-strategy-reviewer`, `edge-candidate-agent`, `edge-pipeline-orchestrator`, `edge-signal-aggregator`
- `trader-memory-core`, `trade-hypothesis-ideator`, `signal-postmortem`, `strategy-pivot-designer`

---

## 3. 향후 도입 가치가 있는 7개 시스템 패턴

### 3-1. 일일 자동 개선 루프 (Skill Improvement Loop)

**tradermonty 구현**:
```
launchd cron 매일 05:00 →
  1. logs/.skill_improvement_state.json에서 다음 스킬 선택 (라운드로빈)
  2. dual-axis-skill-reviewer로 0-100 점수
  3. 점수 < 90이면 claude -p로 SKILL.md/references 자동 수정
  4. 재채점으로 개선 검증
  5. 개선 시 PR 생성, 실패 시 롤백
```

**본인 시스템과 비교**:
- 본인은 `meta-observer`가 있지만 시스템 전체 감시 (전략 단위 자동 개선 X)
- `strategy-evolver` 에이전트는 변형 생성만 하고 자동 개선 루프 없음

**도입 가치**: ★★★★
**작업량 추정**: 1~2주 (본인 SISDS에 'continuous improvement' 단계 추가)

**도입 시 설계 방향**:
```
PM2 cron 매일 새벽 →
  1. 'graduated' 또는 'live' 상태 전략 1개 라운드로빈 선택
  2. Antigravity dual-axis 평가 (자동 통계 + LLM 정성)
  3. 점수 미달 시:
     a. strategy-evolver가 변형 후보 N개 생성
     b. paper로 1주일 실행
     c. 우월 시 graduated 전략 교체
  4. PR 대신 DB에 status='evolved' 표시
```

**리스크**:
- 자동 개선이 잘못 동작하면 검증된 전략 망가뜨릴 수 있음
- LLM 비용 (매일 1회 × 365일)
- → 초기엔 PR/승인 게이트 필수

---

### 3-2. 주간 아이디어 마이닝 + 일일 생성 파이프라인

**tradermonty 구현**:
```
주간 (토 06:00) — Mining:
  ~/.claude/projects/<project>/ 세션 로그 7일치 스캔
  6가지 결정론적 신호 검출:
    1. Skill 사용 빈도 (skills/*/ 경로 참조)
    2. Error 패턴 (exit !=0, is_error 플래그, exception 키워드)
    3. 반복 도구 시퀀스 (3+ 도구 × 3+ 회 반복)
    4. Automation 키워드 (영/일)
    5. Unresolved 요청 (사용자 메시지 후 5분+ 무응답)
    6. (도구 사용 추출)
  → logs/.skill_generation_backlog.yaml 갱신
  Composite = 0.3×Novelty + 0.3×Feasibility + 0.4×Trading Value
  Jaccard similarity > 0.5로 중복 제거

일일 (07:00) — Generation:
  백로그 최고점 → skill-designer 설계 → reviewer 검증 → PR
```

**본인 시스템과 비교**:
- 본인 `skill-architect` 에이전트가 gap_signal 큐 소비 → 새 skill 생성
- 다만 **gap_signal 자동 발굴 메커니즘은 미구현** (`meta-learner`가 일부 담당)
- 6신호 중 본인 시스템에 적용 가능: 1, 2, 3, 5

**도입 가치**: ★★★★★
**작업량 추정**: 1주 (gap_signal 발굴 자동화)

**도입 시 설계 방향**:
```python
# meta-learner 에이전트 보강
def mine_gap_signals_from_logs(days=7):
    logs = load_recent_sessions(days)
    candidates = []

    # 신호 1: Skill 사용 빈도 → 인기 영역의 보강 스킬
    skill_freq = count_skill_invocations(logs)
    candidates += [skill_to_gap_signal(s, freq) for s, freq in skill_freq.items() if freq >= 5]

    # 신호 2: Error 패턴 → 자동 진단/복구 스킬
    errors = extract_error_patterns(logs)
    candidates += [error_to_gap_signal(e) for e in errors if e["count"] >= 3]

    # 신호 3: 반복 시퀀스 → 워크플로 자동화 스킬
    sequences = detect_repetitive_sequences(logs, min_tools=3, min_reps=3)
    candidates += [seq_to_gap_signal(s) for s in sequences]

    # 신호 5: Unresolved 요청 → 즉시 답 필요한 정보 스킬
    unresolved = detect_unresolved_requests(logs, gap_minutes=5)
    candidates += [req_to_gap_signal(r) for r in unresolved]

    # 점수화 + 중복 제거
    scored = [score_candidate(c) for c in candidates]
    deduped = jaccard_dedupe(scored, threshold=0.5)

    # gap_signals 테이블에 INSERT
    save_to_db(deduped)
```

**리스크**:
- 노이즈 후보 다수 → 검증 게이트 필요
- 본인 세션 로그 사용 — 프라이버시 / 민감 정보 유출 검토 필요

---

### 3-3. Edge Pipeline의 REVISE 루프

**tradermonty 구현**:
```
[1] Edge Hint Extractor      → 리서치 티켓
[2] Edge Concept Synthesizer → 추상 개념
[3] Edge Strategy Designer   → strategy.yaml 초안
[4] Edge Strategy Reviewer   → PASS / REVISE / REJECT
       │
       ├─ REVISE (최대 2회): apply_revisions → 재검토
       ├─ PASS + export_ready_v1 → [5] Candidate
       └─ REJECT: 종료

품질 게이트:
  - PASS 평결
  - export_ready_v1 플래그
  - exportable entry_family
  --strict-export: 경고 1건이라도 있으면 REVISE로 강등
```

**본인 시스템과 비교**:
- 본인 `audition-judge`는 **단판 평가** (winner 1명만 graduated, 나머지 eliminated)
- REVISE 메커니즘 없음 → 마진으로 떨어진 전략 즉시 폐기
- 일부 좋은 전략이 사소한 결함 때문에 graveyard 직행 가능성

**도입 가치**: ★★★★
**작업량 추정**: 3~5일

**도입 시 설계 방향**:
```
audition-judge:
  result = evaluate(strategy)
  if result.verdict == "PASS":
    promote_to_graduated(strategy)
  elif result.verdict == "REVISE" and strategy.revise_count < 2:
    feedback = result.feedback
    revised = strategy_evolver.apply_revisions(strategy, feedback)
    re-enter audition queue with revise_count + 1
  else:
    eliminate_to_graveyard(strategy)

# 또는 monthly-resurrect와 결합
# REVISE → resurrected 상태로 변환, 다음 사이클 재진입
```

**리스크**:
- 무한 REVISE 방지 (max 2회) 필수
- LLM 비용 증가 (1회 audition → 최대 3회)

---

### 3-4. Trader Memory Core의 하이브리드 저장소

**tradermonty 구현**:
```
state/
├── theses/
│   ├── _index.json                # 빠른 쿼리용 경량 인덱스
│   ├── thesis_001.yaml            # 풀 메타데이터 (각 thesis별)
│   ├── thesis_002.yaml
│   └── ...
└── journal/
    └── pm_thesis_001.md           # 사후분석 마크다운

3단계 라이프사이클:
  IDEA → ENTRY_READY → ACTIVE → CLOSED

CLI 인터페이스:
  thesis_store.py list --ticker AAPL --status ACTIVE
```

**본인 시스템과 비교**:
- 본인은 PostgreSQL `live_bot_sessions` + `trades` 테이블에 저장
- 구조화 데이터엔 강하지만 **Git 친화적 백업/공유 불가능**
- 메타분석 시 SQL 쿼리 필요 → AI 에이전트가 직접 읽기 불편

**도입 가치**: ★★★ (보조 저장소로)
**작업량 추정**: 2~3일

**도입 시 설계 방향**:
```
# DB → YAML 동기화 백그라운드 작업
# state/strategies/{strategy_id}.yaml — strategy 정의 + 성과 요약
# state/sessions/{session_id}.yaml — 세션 메타
# state/journal/pm_{session_id}.md — 사후분석

# 기존 PostgreSQL은 그대로 유지 (실시간 거래용)
# YAML 미러는 메타학습 / Git 추적 / 분석용
```

**용도**:
- meta-learner 에이전트가 SQL 없이 YAML 직접 읽기
- Git 커밋으로 전략 성과 시계열 추적
- 다른 머신/서버에 동기화 (rsync git)

---

### 3-5. Dual-Axis Skill Reviewer

**tradermonty 구현**:
- 자동 채점 (deterministic, code-only)
- 옵션 LLM 채점 (정성 평가)
- 두 축 결합 → 최종 0-100 스코어
- 스코어 < 90이면 자동 개선 트리거

**본인 시스템과 비교**:
- 본인 `audition-judge`는 KPI(12% 복리, overfit_ratio < 0.3) 기준 통과/탈락만 판정
- "왜 떨어졌나" 정성 피드백 없음 → REVISE 못함

**도입 가치**: ★★★
**작업량 추정**: 1주 (audition-judge 보강 + LLM 평가 추가)

**도입 시 설계 방향**:
```
audition-judge 평가 항목:
  Auto axis (deterministic, 0-100):
    - KPI compound return (가중치 30%)
    - Overfit ratio inverse (가중치 25%)
    - Sharpe ratio (가중치 20%)
    - Max DD inverse (가중치 15%)
    - Trade count adequacy (가중치 10%)

  LLM axis (qualitative, 0-100):
    - 전략 로직 명확성
    - 파라미터 합리성
    - 시장 체제 적응성
    - 리스크 관리 견고성

  Final = 0.7 × Auto + 0.3 × LLM
  >= 90: PASS (graduated 승급)
  70-89: REVISE (재시도 1회)
  < 70: REJECT (graveyard)
```

**리스크**:
- LLM 평가 비용 (audition마다 1회)
- 정성 평가의 일관성 (같은 전략 다른 점수 가능)

---

### 3-6. Strategy Pivot Designer

**tradermonty 구현**:
- 백테스트 정체(stagnation) 감지
- "구조적 pivot" 제안 — 단순 파라미터 튜닝이 아닌 전략 구조 자체 변경
- 예: RSI 매수 → MACD + RSI 조합으로 변환

**본인 시스템과 비교**:
- 본인 `strategy-evolver`는 변형 생성하지만 **파라미터 변형 위주**
- 구조적 pivot (전략 종류 자체 변경) 없음
- monthly-resurrect는 graveyard 부활만 함

**도입 가치**: ★★★
**작업량 추정**: 1주

**도입 시 설계 방향**:
```
strategy-evolver:
  if 'parameter tuning' 결과 KPI 개선 < 5% (over 3 iterations):
    → call strategy_pivot_designer
    → identify structural change opportunities:
       - 추가 지표 결합 (RSI → RSI+MACD)
       - 시간대 변경 (1h → 4h)
       - Long-only → Long+Short
       - 단일 진입 → DCA (분할 매수)
    → generate 3 structural variants
    → submit each as new sandbox strategy
```

---

### 3-7. Edge Signal Aggregator (다중 신호 통합)

**tradermonty 구현**:
- 8개 상위 스킬 결과 통합
- 가중치 조정 가능
- 모순 신호 로깅
- 확신도 대시보드 (JSON + Markdown)

**본인 시스템과 비교**:
- 본인 `signal-synthesizer` 에이전트가 유사 역할
- 다만 다중 전략 신호 통합보다는 **기술/뉴스/온체인 데이터 합성** 중심
- 여러 graduated 전략의 동일 심볼 동시 신호를 합성하는 메커니즘 없음

**도입 가치**: ★★ (이미 부분 구현됨)
**작업량 추정**: 3~5일 (signal-synthesizer 확장)

---

## 4. 도입하지 말아야 할 것들

### 4-1. 매매 전략 코드 직접 차용

**이유**: 검증 결과 BTC/단일 종목엔 부적합. 미국 주식 다종목 풀 환경에 맞춰져 있음.

**예외**: VCP의 **Trend Template (Minervini 7조건)** 자체는 추세 시장 필터로 가치 있음. 다만 매매 전략으로보다는 **시장 체제 판별 보조 도구**로 활용 검토.

### 4-2. FMP / FINVIZ / Alpaca API 의존

**이유**:
- FMP는 미국 주식 펀더멘털 — 본인 한국주식/Binance 시스템과 무관
- FINVIZ Elite ($39.5/월) — ROI 불명
- Alpaca는 페이퍼 트레이딩 — 본인 자체 paper 엔진 보유

### 4-3. Skill Designer의 자동 스킬 생성

**이유**:
- 본인 `skill-architect` 에이전트가 이미 동일 역할
- 두 시스템 병행 시 충돌
- → 본인 skill-architect를 보강하는 방향이 합리적

---

## 5. 우선순위 매트릭스

| # | 항목 | 도입 가치 | 작업량 | 우선순위 | 비고 |
|---|---|---|---|---|---|
| 3-2 | Skill Idea Miner 6신호 → meta-learner 보강 | ★★★★★ | 1주 | **최고** | 즉시 가치 명확 |
| 3-1 | 일일 자동 개선 루프 | ★★★★ | 1~2주 | 높음 | LLM 비용 검토 필요 |
| 3-3 | Edge Pipeline REVISE 루프 | ★★★★ | 3~5일 | 높음 | audition-judge 보강 |
| 3-4 | Trader Memory Core 하이브리드 저장소 | ★★★ | 2~3일 | 중간 | Git 추적 부수효과 ★ |
| 3-5 | Dual-Axis Skill Reviewer | ★★★ | 1주 | 중간 | LLM 일관성 우려 |
| 3-6 | Strategy Pivot Designer | ★★★ | 1주 | 중간 | 구조 변경은 리스크 큼 |
| 3-7 | Edge Signal Aggregator | ★★ | 3~5일 | 낮음 | 부분 구현됨 |

**합산 작업량 (전체 도입 시)**: 약 5~7주

---

## 6. 이번 검증에서 얻은 추가 인사이트 (전략 설계 일반)

### 6-1. "거래 빈도 vs 위험 통제"의 트레이드오프
- 엄격한 전략 = 빈도 ↓ + DD ↓
- 느슨한 전략 = 빈도 ↑ + DD ↑
- VCP는 -67% DD를 -4.5%로 줄였지만 +62%를 +15%로 줄임
- → **전략 자체보다 시장 노출 시간(time in market)이 결정 요인**

### 6-2. 단일 자산 통계 전략의 한계
- 99% Cointegration 페어가 다종목 풀에서 1~2쌍 정도 나옴
- 단일 페어(BTC/ETH) 적용 = 통계 가정 깨짐
- **다종목 동시 운용이 통계 전략의 핵심**

### 6-3. 트레일링 스톱 vs 고정 R-multiple
- BTC 같은 트렌드 자산: **트레일링 우위** (큰 winner 잡음)
- 횡보 자산: 고정 R-multiple 우위 (조기 익절)
- → 시장 체제별 청산 룰 차별화 필요

### 6-4. "복잡한 전략 = 좋은 전략" 아님
- Pair Trade가 가장 복잡 + 가장 나쁜 결과
- VCP는 중간 복잡도 + 가장 좋은 결과
- 단순 Buy-and-Hold가 모두를 이김 (이 시장 한정)

---

## 7. 향후 결정 포인트

이 문서를 기반으로 다음 결정이 필요할 때 참조:

### Trigger 1: SISDS 자가개선 강화 필요 시
→ 3-1 (자동 개선 루프) + 3-2 (아이디어 마이닝) 도입 검토
→ 우선순위 1, 2 항목 결합

### Trigger 2: audition-judge 정확도 부족 발견 시
→ 3-3 (REVISE 루프) + 3-5 (Dual-Axis Reviewer) 도입
→ 우선순위 3, 5 결합

### Trigger 3: 메타 학습 데이터 부족 / Git 추적 필요 시
→ 3-4 (Hybrid 저장소) 도입
→ 우선순위 4

### Trigger 4: Strategy 폐기율 너무 높을 때
→ 3-6 (Pivot Designer) 도입
→ 우선순위 6

---

## 8. 참고 자료

- 원본 저장소: https://github.com/tradermonty/claude-trading-skills
- 백테스트 결과:
  - VCP: `scripts/tradermonty_validation/vcp/output/`
  - Breakout: `scripts/tradermonty_validation/breakout/output/`
  - Pair Trade: `scripts/tradermonty_validation/pair_trade/output/`
- Plugin reference JSON: `docs/claude_trading_plugins_reference.json`
- 검증 일시: 2026-04-29
- 검증자: hcpark + Claude Code

---

## 9. 변경 이력

- 2026-04-29: 초안 작성 (전체 7개 패턴 + 우선순위 + 결정 트리거)
