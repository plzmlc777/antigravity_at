---
name: at-orchestrator
description: |
  Cross-skill orchestration. Chains health-check → parameter optimization → config apply
  for autonomous AI trading cycles. Drives the weekly meta-cycle that ties at-monitor,
  at-backtest, at-symbol-select together.
allowed-tools: Read, Bash, Agent
version: 1.0.0
tags: [orchestration, autonomous, weekly-cycle, pipeline]
---

# AT-Orchestrator

Autonomous pipeline that wires individual skills into end-to-end cycles. Runs as
the top-level driver behind cron jobs and ad-hoc CIO sub-agent dispatches.

## Commands

- pipeline.py run --session-id <ID> — health check → optimize → apply for one session
- pipeline.py optimize --session-id <ID> — grid search via at-backtest only
- pipeline.py auto — scan all RUNNING sessions and orchestrate as needed
- weekly_cycle.sh — weekly meta-cycle (symbol scout + strategy evolve + KPI gate)
- run_weekly_cycle.sh — cron entrypoint wrapper

## Flow

1. **at-monitor** identifies CRITICAL sessions (MDD/WR/cycles thresholds)
2. **at-backtest/optimize** runs grid search on candidate parameters
3. Best config is applied to the session via the live API
4. Optionally **at-symbol-select** triggers symbol switch when KPI compound gap
   exceeds the v1.5.12.0 monthly target

## Outputs

- runs/ directory keeps per-cycle JSON traces consumed by /api/v1/agents/activity
- decision_log.md entries (CIO-YYYYMMDD-NNN) for any operator-visible action
