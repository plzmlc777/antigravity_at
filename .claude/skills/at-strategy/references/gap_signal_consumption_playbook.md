# Gap Signal Consumption Playbook

> **Audience**: main 대화 턴 Claude Code (not cio, not any subagent)
> **Authority**: CIO-20260408-008 (infra) + CIO-20260408-009 (2-hop 제약 발견 + 실행 경로 확정)
> **Related**: `.claude/agents/skill-architect.md`, `backend/app/api/gap_signals.py`

## Why this playbook exists

gap_signals DB 큐(`backend/app/models/gap_signal.py`)는 meta-learner / self-critic / cio 등이 발행한 "시스템 능력의 공백" 신호를 skill-architect 가 소비하여 신규 스킬을 자동 생성하도록 설계됨.

원래 계획(CIO-008)은 cio 의 "Phase 0 INTELLIGENCE" 단계에서 cio 가 직접 폴링 → skill-architect 를 `Agent` 툴로 dispatch → PATCH 하도록 하는 것. **CIO-009 에서 이 경로가 동작하지 않음이 증명됨**: Claude Code 런타임에서 서브에이전트 → 서브에이전트 의 2-hop `Agent` 툴 호출이 차단됨. main 턴 → 서브에이전트 1-hop 은 정상.

**결론**: gap_signal 소비는 main 대화 턴 Claude 가 수행한다. cio 는 관여하지 않는다.

## When to run this playbook

- 사용자가 명시적으로 요청할 때 (예: "gap_signals 큐 처리해줘", "pending gap 확인")
- meta-learner / self-critic 리뷰 직후 (이들이 새 signal 을 POST 했을 가능성)
- 주요 워크플로우 사이클 시작 전 (선택적) — 큐가 비어있으면 즉시 넘어감
- 사용자 승인 후 주기 실행 (단발성 트리거)

**Anti-pattern**: cio, strategy-advisor, risk-manager 등 **서브에이전트 내부**에서 이 플레이북을 수행하려 하지 말 것. 반드시 main 턴에서.

## The routine (Phase 0 equivalent, main-turn edition)

### Step 1 — Poll pending queue

```bash
curl -s 'http://localhost:8001/api/v1/gap-signals?status=pending&limit=10'
```

- 응답이 `[]` → 종료 (silent skip). 사용자에게 "pending gap_signals 없음" 정도만 간단 보고.
- 응답에 signal 이 있으면 Step 2.

### Step 2 — Family-based routing (CIO-20260408-014)

Before dispatching, inspect `proposed_intent.family` of each signal to determine the correct consumer:

| `proposed_intent.family` | Dispatch target | Output artifact |
|---|---|---|
| `at-monitor` / `at-strategy` / `at-backtest` / any `at-*` | **`skill-architect`** | Pure analytical primitive (`.claude/skills/**/scripts/*.py`) |
| `strategy` | **`strategy-builder`** (autonomous mode) | Trading strategy subclass (`.claude/skills/at-live-signal/scripts/strategies/<id>.py`) |
| (missing / unknown) | — | PATCH as `failed` with `failure_reason: "unknown_family"` |

Route each signal individually — a single pending batch may contain mixed families.

### Step 2a — Dispatch skill-architect (family starts with `at-`)

```
Agent(
  subagent_type="skill-architect",
  description="Consume gap signal",
  prompt="""
    gap_signal consumption from DB queue (id=<N>, signal_id=<SID>).

    ## Full signal payload
    <JSON from Step 1 response>

    ## Task
    1. Reuse Before Create 규칙 강제: 이미 동일 intent 의 스킬이 존재하면 재생성 금지
    2. 신규 스킬이 필요하면 SKILL.md + scripts 생성 + self-test + reproducibility gate
    3. 해시 계산 및 응답 JSON 포함

    ## Required response JSON
    {
      "signal_id": "...",
      "action_taken": "reuse_existing|regenerated|failed",
      "existing_skill_path": "...",
      "fixture_hash": "...",
      "output_hash": "...",
      "self_test_exit_code": 0,
      "risk_manager_verdict": "approved|rejected|pending_review|n/a",
      "notes": "..."
    }
  """
)
```

### Step 2b — Dispatch strategy-builder (family == `strategy`)

```
Agent(
  subagent_type="strategy-builder",
  description="Generate new strategy",
  prompt="""
    Autonomous mode dispatch (CIO-20260408-014). proposed_intent.family == "strategy".
    Follow the "Autonomous Mode" section of strategy-builder.md. Do NOT ask any questions.

    ## Full gap_signal payload
    <JSON from Step 1 response>

    ## Required response JSON (see strategy-builder.md Autonomous Workflow Step 8)
    {
      "agent": "strategy-builder",
      "mode": "autonomous",
      "signal_id": "...",
      "action_taken": "generated|reuse_existing|failed",
      "strategy_id": "...",
      "class_name": "...",
      "file_path": "...",
      "file_lines": ...,
      "parent_class": "MartingaleBase|BaseStrategy",
      "py_compile_exit_code": 0,
      "import_check": "ok|failed",
      "notes": "..."
    }
  """
)
```

**중요 — 순차 실행**: 두 dispatch 경로 모두 파일을 생성하므로 여러 signal 을 병렬 dispatch 하지 말 것. 하나씩 순차 처리. 서로 다른 family 가 섞여 있어도 DB 순서대로 하나씩.

### Step 3 — PATCH result back to queue

```bash
curl -s -X PATCH http://localhost:8001/api/v1/gap-signals/<signal_id> \
  -H 'Content-Type: application/json' \
  -d '{
    "status": "<final_status>",
    "consumed_by": "skill-architect (via main-turn)",
    "result": <skill-architect response JSON>
  }'
```

**Final status 결정 규칙** (consumer 별):

skill-architect 응답:
| 결과 | PATCH status |
|---|---|
| `action_taken: reuse_existing` + self_test PASS | `consumed` |
| `action_taken: regenerated` + self_test PASS + risk_manager approved | `consumed` |
| `action_taken: regenerated` + risk_manager rejected | `rejected` |
| `action_taken: failed` 또는 self_test FAIL 또는 dispatch 자체 크래시 | `failed` |

strategy-builder 응답 (CIO-014):
| 결과 | PATCH status |
|---|---|
| `action_taken: generated` + `py_compile_exit_code: 0` + `import_check: "ok"` | `consumed` |
| `action_taken: reuse_existing` | `consumed` |
| `action_taken: failed` 또는 `py_compile_exit_code != 0` 또는 `import_check: "failed"` | `failed` |
| dispatch 자체 크래시 | `failed` |

**Note**: strategy-builder 는 risk-manager VETO 대상이 아님 — 생성된 전략 파일은 **backtest/paper 경쟁 파이프라인** 에 자동 진입하며, 실거래 승급 결정은 별도 에이전트 영역. 즉, 전략 생성 자체에는 "rejected" 상태가 존재하지 않음 (컴파일 통과 = consumed, 실패 = failed).

**PATCH 엔드포인트 주의사항 (CIO-009 에서 발견)**:
- URL 경로는 **문자열 `signal_id`** (예: `/GAP-20260408-001`) — numeric row id 가 아님
- signal_id 에 포함된 하이픈(`-`) 은 URL 에 그대로 사용 가능, escape 불필요

### Step 4 — Report to user

간략 요약만:
```
pending gap_signals N건 처리 완료:
  - <signal_id>: consumed (reuse_existing, byte-identical)
  - <signal_id>: rejected (risk-manager VETO: <reason>)
  - <signal_id>: failed (<failure_mode>)
```

## Failure modes to handle

1. **skill-architect dispatch 자체가 에러** (Agent 툴 exception): 해당 signal 을 `failed` 로 PATCH 후 다음 signal 로 진행. 루프 전체를 중단하지 말 것.
2. **skill-architect 응답이 valid JSON 이 아님**: `failed` 로 PATCH, `result.failure_mode = "invalid_json_response"` 기록.
3. **PATCH 자체가 실패** (404/500): 재시도 1회, 여전히 실패 시 사용자에게 보고하고 해당 signal 은 DB 에서 여전히 `pending` 상태로 남김 (다음 루프에서 재시도됨).

## What this playbook does NOT do

- ❌ cio 의 ASSESS/PLAN/EXECUTE 워크플로우 실행 (cio 가 별도로 관리)
- ❌ 실거래 주문 발행 (skill-architect 는 스킬 생성만, 실행은 risk-manager VETO + cio 별도 승인)
- ❌ gap_signal 자동 발행 (meta-learner / self-critic 이 별도 수행, 이 플레이북은 소비만)
- ❌ 대화창 바깥 지속 실행 — main 턴이 능동적으로 호출되어야 함 (진짜 자율 루프는 A2 standalone runner 필요, 별도 미래 작업)

## Verified evidence (CIO-20260408-009)

### Failing path (do NOT use)
```
main turn
  └─ Agent(cio)
       └─ Agent(skill-architect)   ← FAILS: "Task(subagent) tool unavailable in CIO runtime"
```
Test: `GAP-20260408-002-rerun` — cio polled queue successfully, marked as `failed` with `failure_mode: dispatch_crash`.

### Working path (use this)
```
main turn
  ├─ Bash(curl GET /api/v1/gap-signals?status=pending)
  ├─ Agent(skill-architect)        ← WORKS: 1-hop dispatch
  └─ Bash(curl PATCH /api/v1/gap-signals/<sid>)
```
Test: `GAP-20260408-003-mainturn` — byte-identical with CIO-006 manual dry-run:
- fixture_hash: `bfacd8233a8e1106a3235d07ca40e2b566869308525cb1075186d1b76ad4fc81`
- output_hash: `d95eb7c0437dc1994f9bb1446b3a083672779ed4ac6ad0201c3f61bc79ab4f40`
- action_taken: `reuse_existing`
- Final status: `consumed`

## Migration note: "Phase 0 in cio.md" is deprecated

CIO-008 에서 cio.md 에 추가했던 `Phase 0 INTELLIGENCE` 섹션은 CIO-009 에서 삭제됨. cio 는 Phase 1 ASSESS 부터 시작. 이 플레이북이 그 기능을 대체함.
