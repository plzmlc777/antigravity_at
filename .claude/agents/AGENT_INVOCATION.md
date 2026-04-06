# Agent Invocation Guide

## ⚠️ Important: Custom Agents Are NOT Auto-Registered

`.claude/agents/*.md` 파일을 만들어도 `subagent_type`으로 자동 등록되지 않습니다.
시스템에 등록된 subagent_type만 직접 호출 가능:
- general-purpose, statusline-setup, Explore, Plan, claude-code-guide
- trading-analyst, stock-searcher, strategy-builder, symbol-evaluator (legacy)

## How to Invoke Custom Agents

### Pattern: general-purpose with embedded instructions
```
Agent(
  subagent_type="general-purpose",
  description="Test ops-monitor",
  prompt="""You are the Operations Monitor agent. Read your full instructions
from /home/hcpark/antigravity/.claude/agents/ops-monitor.md and follow them exactly.

Your task:
API URL: http://localhost:8001
Check depth: deep

Execute all steps and return the JSON response per the output format spec."""
)
```

The agent reads its own behavioral spec from the .md file and executes accordingly.

## ⚠️ Critical Limitation: No Nested Dispatch

The `general-purpose` agent does NOT have access to the `Agent`/`Task` tool.
This means CIO (or any orchestrator) cannot truly dispatch sub-agents in parallel
when running via the workaround pattern — it must execute each sub-agent's logic
inline by reading their .md spec.

**Implication**: For true parallel sub-agent orchestration, the orchestrator
(CIO) MUST be invoked from the **main conversation** (which has Agent tool access),
and it dispatches each sub-agent as a separate `general-purpose` Agent call.

**Recommended pattern for daily-review**:
```
Main conversation:
  ├─ Agent(general-purpose, "ops-monitor task") ─┐
  └─ Agent(general-purpose, "market-researcher task") ─┴─ parallel
  → Main parses both JSONs
  → If non-HEALTHY: Agent(general-purpose, "strategy-advisor task")
  → ...continues
```

The CIO .md spec is then a **playbook the main conversation follows**, not
an autonomous agent. This is the only way to get real parallelism until
custom agents become natively registerable.

## Verified Agents (Phase A)

| Agent | Status | Test Date | Notes |
|-------|--------|-----------|-------|
| ops-monitor | ✅ Verified | 2026-04-06 | Returns valid JSON. health_check.py + PM2 + API checks all work. |
| market-researcher | ✅ Verified | 2026-04-06 | Returns valid JSON. WebSearch + regime + event risks + impact mapping all work. |
| trade-executor | ✅ Verified | 2026-04-06 | Read-only status-check verified. API query + JSON output format work. |
| risk-manager | ✅ Verified | 2026-04-06 | Portfolio query + risk evaluation + conditional approval w/ veto power verified. |
| strategy-advisor | ✅ Verified | 2026-04-06 | Reasoning-based recommendations work. Path lookup for at-strategy skill needs improvement (fell back to reasoning). |
| backtest-analyst | ✅ Verified | 2026-04-06 | Real backtest executed (BTCUSDT, 7d, 27 cycles, WR 81%). Fixed CLI flags in agent .md (--futures/--config not --exchange/--params). |
| cio | ✅ Verified (as playbook) | 2026-04-06 | Workflow logic verified. CIO operates as a playbook executed by main conversation, not an autonomous agent. Main conversation dispatches sub-agents via parallel general-purpose Agent calls then synthesizes. True parallelism confirmed in Phase A-6. |
| meta-learner | ⏳ Pending | - | - |
| strategy-evolver | ⏳ Pending | - | - |
| self-critic | ⏳ Pending | - | - |
| signal-synthesizer | ✅ Verified | 2026-04-06 | 3-domain quick synthesis with data_provenance tracking. Returned HOLD with watch_triggers (institutional vs technical decoupling identified). |
