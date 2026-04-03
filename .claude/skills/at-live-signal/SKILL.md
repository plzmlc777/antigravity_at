---
name: at-live-signal
description: |
  라이브 세션에 외부 시그널을 제출하는 스킬.
  캔들 데이터를 분석하여 기술 지표 기반 매매 시그널을 생성하고,
  POST /submit-signal API를 통해 v2 엔진에 주입한다.
  Python 전략 모듈과 병행하여 비교 검증할 수 있다.
  "시그널 분석", "스킬 매매", "캔들 분석" 등의 요청 시 사용.
allowed-tools: Read, Bash(python:*), Bash(curl:*)
version: 0.1.0
author: Antigravity Auto Trading
tags: [signal, live-trading, skill, technical-analysis]
---

# AT-Live-Signal: 라이브 시그널 제출 스킬

## Overview

라이브 트레이딩 세션에서 **Python 전략 모듈과 병행**하여 외부 시그널을 제출하는 스킬.
동일한 ExecutionEngine 파이프라인을 거쳐 필터링/실행된다.

```
Python 전략: Strategy.on_data(candle) → context.buy() → SignalInterceptContext → Engine → Order
이 스킬:     analyze_candles.py → submit_signal.py → POST /submit-signal → Engine → Order
```

## 사용 흐름

### 1. 캔들 분석
```bash
python .claude/skills/at-live-signal/scripts/analyze_candles.py \
  --session-id <SESSION_ID> \
  --api-url http://localhost:8001
```
- GET /session/{id}/candles로 최근 캔들 데이터 조회
- RSI, EMA, MACD 등 기술 지표 계산
- 매매 시그널 판단 및 출력

### 2. 시그널 제출
```bash
python .claude/skills/at-live-signal/scripts/submit_signal.py \
  --session-id <SESSION_ID> \
  --side buy \
  --quantity 100 \
  --source "skill:rsi_analysis" \
  --api-url http://localhost:8001
```
- POST /session/{id}/submit-signal로 시그널 제출
- ExecutionEngine 필터 체인 평가 후 실행/거부

### 3. 시그널 비교
```bash
# 전략 모듈 시그널
curl http://localhost:8001/api/v1/live/session/<ID>/signals?source=strategy

# 스킬 시그널
curl http://localhost:8001/api/v1/live/session/<ID>/signals?source=skill
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/live/session/{id}/submit-signal` | 외부 시그널 제출 |
| GET | `/api/v1/live/session/{id}/candles?limit=100` | 캔들 데이터 조회 |
| GET | `/api/v1/live/session/{id}/signals?source=skill` | 스킬 시그널 조회 |

## 병행 비교 원칙

> Python 전략 모듈과 스킬이 동시에 시그널을 생성하되,
> source 태그로 구분하여 각각의 성과를 비교한다.
> 스킬 시그널이 전략 모듈보다 우수한 경우에만 채택을 고려한다.

## 주의사항

- `source`는 반드시 `"skill"`로 시작해야 함 (API 검증)
- v2 엔진(`engine_version: "v2"`) 세션에서만 동작
- `orders_enabled=false`이면 시그널이 기록되지만 주문은 실행되지 않음
- NoOpStrategy(`strategy_name: "noop"`)와 함께 사용하면 스킬만 시그널 생성
