---
description: 새 paradigm 1개를 R-1 분리 모드로 자율 발의 + 진행. R-1 결과 후 사용자 승인 게이트.
---

# /new-paradigm — R-1 분리 모드 paradigm 발굴

새 paradigm 1개를 자율로 발의하고 R-1 PoC까지만 진행합니다. R-2/R-3는 사용자 명시적 승인 후 별도 호출 (background polling 화면 도배 방지 — `[[agent-long-background-polling]]` lesson).

## 컨텍스트 로드

다음을 순서대로 Read:
1. `/home/hcpark/antigravity/.claude/plans/new_paradigm_session_primer.md` — 운영 원칙 + DNA 매트릭스 + 게이트 기준
2. memory `feedback_agent_long_background_polling.md` — R-1 분리 protocol 이유

## 실행 순서

### Step 1 — 카탈로그 조회 (Mint SSH 필수)
```bash
ssh mint@183.99.228.81 "cd ~/auto_trading/backend && source venv/bin/activate && PYTHONPATH=. python3 -m scripts.research.paradigm_index list"
ssh mint@183.99.228.81 "cd ~/auto_trading/backend && source venv/bin/activate && python3 -m scripts.paper_session_cli status | tail -50"
```

### Step 2 — DNA 미탐색 차원 식별
- 4-tuple (data source × decision mode × time scale × universe shape)
- 기존 R-5 시드 paradigms와 5/6 차원 이상 겹치면 STOP
- §3-G/§3-F/§3-H/§3-A/§3-N graveyard 패턴 회피 (PARADIGM_QUEUE_2026Q2.md §3 참조)
- 미탐색 데이터 dimension 우선 (microstructure joblib 컬럼 / DB 테이블 / 외부 free API)

### Step 3 — 가설 발의 보고 (1회)
사용자에게 다음 6항목 보고 후 즉시 진행:
- 가설 한 문장
- DNA 4-tuple
- 기존 시드 9개와의 거리 (차원별)
- 기대 alpha 사전 추정 (% / month + sharpe + t-stat)
- 폐기 조건 (R-1 어느 결과면 즉시 graveyard)
- 자체 평가 (시드 가능성 % vs 폐기 가능성 %)

### Step 4 — paradigm-architect 호출 (R-1 ONLY)

**필수 prompt 제약**:
> "Execute R-1 PoC ONLY. Halt after R-1 completion regardless of PASS/FAIL/borderline. Do NOT proceed to R-2 without explicit follow-up invocation. Do NOT spawn background tasks for R-2/R-3 perm tests. R-1 PoC must complete in foreground within 15 min."

호출 형식:
```
Agent({
  subagent_type: "paradigm-architect",
  description: "<paradigm_name> R-1 only",
  prompt: "..."  // 가설 + R-1 ONLY 제약 + 폐기 기준
})
```

### Step 5 — Background 잔여 검증 (필수)

R-1 종료 보고 받은 직후:
```bash
# 1. Mint process 확인 — 살아있으면 kill
ssh mint@183.99.228.81 "ps -ef | grep -E 'python3.*research' | grep -v grep || echo NONE"

# 2. Local task 파일 확인 — 새로 생성/수정되는지 모니터링
ls -la /tmp/claude-1000/-home-hcpark-antigravity/*/tasks/ 2>/dev/null
```

살아있는 background process 발견 시 즉시 kill + 이유 보고.

### Step 6 — R-1 결과별 분기

| R-1 결과 | 액션 |
|---|---|
| **PASS** (alpha+sharpe ≥ 0, 폐기 조건 미해당) | 사용자에게 "R-2 진행 승인 요청 — 새 호출로 multi-symbol expand할까요?" 묻기 |
| **FAIL** (폐기 조건 trigger) | INDEX graveyard 등록 확인 + lesson 한 줄 보고 + "다른 paradigm 발의할까요?" 묻기 |
| **borderline** (PASS 기준 애매) | 핵심 metrics 보고 + 사용자 판단 요청 |

## 중요 규칙

- **본 명령은 R-1까지만**. R-2/R-3/R-4는 별도 명령 또는 명시적 사용자 승인.
- **paradigm-architect는 R-1 only mode로 호출**. R-2 자동 진행 금지.
- **Mint 운영 원칙 준수** — 모든 DB/joblib/process 조회 SSH 통해 Mint에서.
- **데이터 백필 금지** — 이미 확보된 데이터만 사용. 30분+ ETA 발생 시 STOP.
- **호출 종료 후 background 검증 필수** — task 파일 + Mint ps 둘 다.

## R-2 진행 시 (별도 trigger)

R-1 PASS 후 사용자 승인 받으면 별도 prompt로:
> "이전 R-1 PASS한 `<paradigm_name>` R-2 진행. paradigm-architect 호출 — prompt에 'R-2 multi-symbol expand ONLY, halt after R-2 regardless of result' 명시. 종료 후 mint ps 검증."
