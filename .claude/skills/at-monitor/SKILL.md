---
name: at-monitor
description: |
  Live session monitoring skill. Health checks, anomaly detection, auto-intervention.
allowed-tools: Read, Bash, Agent
version: 1.0.0
tags: [monitoring, alerting, health-check, live-trading]
---

# AT-Monitor

## Commands

- health_check.py: Single health check for all RUNNING sessions
- monitor.py: Continuous monitoring with auto-intervention

## Health Grades

- HEALTHY: MDD > -10%, WR > 50%, cycles > 10
- WARNING: MDD -10% to -20% or WR 40%-50%
- CRITICAL: MDD < -20% or WR < 40% with cycles > 10
- STALE: No trades for 1+ hours

## Auto Actions

- log: Log only
- pause: Pause CRITICAL sessions
- symbol-switch: Trigger AI symbol selection
