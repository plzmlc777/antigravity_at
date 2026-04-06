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

## Verified Agents (Phase A)

| Agent | Status | Test Date | Notes |
|-------|--------|-----------|-------|
| ops-monitor | ✅ Verified | 2026-04-06 | Returns valid JSON. health_check.py + PM2 + API checks all work. |
| market-researcher | ✅ Verified | 2026-04-06 | Returns valid JSON. WebSearch + regime + event risks + impact mapping all work. |
| trade-executor | ✅ Verified | 2026-04-06 | Read-only status-check verified. API query + JSON output format work. |
| risk-manager | ⏳ Pending | - | - |
| strategy-advisor | ⏳ Pending | - | - |
| backtest-analyst | ⏳ Pending | - | - |
| cio | ⏳ Pending | - | - |
| meta-learner | ⏳ Pending | - | - |
| strategy-evolver | ⏳ Pending | - | - |
| self-critic | ⏳ Pending | - | - |
| signal-synthesizer | ⏳ Pending | - | - |
