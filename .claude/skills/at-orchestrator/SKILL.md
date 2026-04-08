---
name: at-orchestrator
description: |
  AI 자율 트레이딩 오케스트레이터. 종목 선정 -> 파라미터 최적화 -> 라이브 배포 -> 모니터링 -> 재최적화 사이클.
  기존 스킬들을 파이프라인으로 연결하여 완전 자동 트레이딩 사이클 구현.
allowed-tools: Read, Write, Edit, Bash, Agent
version: 1.0.0
tags: [orchestrator, autonomous, pipeline, ai-trading]
---

# AT-Orchestrator: AI Autonomous Trading Pipeline

## Overview

기존 스킬들을 하나의 자동 사이클로 연결:



## Pipeline Steps

### Step 1: Symbol Selection (at-symbol-select)


### Step 2: Parameter Optimization (at-backtest/optimize)
Best symbol from Step 1 -> Grid Search -> Walk-Forward validation

### Step 3: Deploy (apply to session)
Best params from Step 2 -> Apply via skill-symbol-switch API

### Step 4: Monitor (at-monitor)
Health check loop -> If CRITICAL -> Re-trigger Step 1

## Scripts

| File | Role |
|------|------|
| scripts/pipeline.py | Full pipeline orchestrator |
