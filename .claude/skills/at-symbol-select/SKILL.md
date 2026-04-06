---
name: at-symbol-select
description: |
  AI 종목 선정 스킬. 시장 데이터 분석 → 후보 탐색 → 백테스트 경쟁 → 최적 종목 선택.
  "종목 선정", "종목 추천", "AI 종목", "심볼 선택", "symbol select" 등의 요청 시 사용.
  Claude 에이전트 자체가 FIND/SELECT의 AI 역할을 하며, 백테스트 스킬을 재활용한다.
allowed-tools: Read, Write, Edit, Bash(python:*), Bash(curl:*), Bash(wsl:*), Agent
version: 1.0.0
author: Antigravity Auto Trading
tags: [ai, symbol-selection, trading, backtest]
---

# AI 종목 선정 스킬

## Overview

백엔드 `ai_symbol_selection.py`의 3단계 파이프라인을 완전 독립 스킬로 구현.
**Claude 에이전트 자체가 AI** — Claude CLI 서브프로세스 호출 불필요.

```
┌─────────────────────────────────────────────────┐
│  Stage 1: FIND (에이전트가 직접 분석)             │
│  시장 데이터 → 검색 조건 매칭 → 후보 20개 선정    │
├─────────────────────────────────────────────────┤
│  Stage 2: COMPARE (백테스트 스킬 재활용)          │
│  후보 + 현재종목 → 14일 1m 백테스트 → 스코어링    │
├─────────────────────────────────────────────────┤
│  Stage 3: SELECT (에이전트가 직접 판단)           │
│  스코어 + 거래량 + 안정성 → 최종 1개 선택         │
└─────────────────────────────────────────────────┘
```

## 파이프라인 실행 절차

### Step 1: 세션 정보 확인

```bash
python3 .claude/skills/at-symbol-select/scripts/run_pipeline.py session-info \
  --session-id <SESSION_ID> --api-url http://localhost:8001
```

확인 사항:
- `ai_symbol_mode`: "ai" 여야 함
- `ai_search_conditions`: 검색 조건 텍스트
- `strategy_name`: 전략 이름
- `strategy_config`: 현재 파라미터
- `symbol`: 현재 종목
- `is_paper`: 모의/실거래 구분

### Step 2: FIND — 시장 데이터 수집 + 후보 탐색

```bash
# 시장 데이터 수집
python3 .claude/skills/at-symbol-select/scripts/run_pipeline.py fetch-market --futures --summary

# 전체 데이터 (에이전트가 분석할 JSON)
python3 .claude/skills/at-symbol-select/scripts/run_pipeline.py fetch-market --futures
```

**에이전트 역할 (FIND)**:
1. 시장 데이터 JSON을 읽고 `search_conditions`에 맞는 종목을 찾는다
2. 최대 20개 후보를 선정한다
3. 선물이면 각 후보에 direction(long/short)을 추천한다
4. 현재 종목과 동일 그룹의 종목은 제외한다

**출력 형식** (에이전트가 구성):
```json
[
  {"code": "BTCUSDT", "name": "BTC", "direction": "long", "reason": "강한 상승 추세..."},
  {"code": "ETHUSDT", "name": "ETH", "direction": "long", "reason": "기술적 지지..."},
  ...
]
```

### Step 3: COMPARE — 백테스트 경쟁

```bash
# 후보 목록으로 일괄 백테스트 (현재 종목 포함!)
python3 .claude/skills/at-symbol-select/scripts/run_pipeline.py batch-backtest \
  --candidates '[{"code":"BTCUSDT","direction":"long"},{"code":"ETHUSDT","direction":"long"},{"code":"CURRENTUSDT"}]' \
  --strategy rsi_martingale \
  --config '{"leverage":5}' \
  --days 14 \
  --capital 500 \
  --futures
```

**중요**: 현재 종목도 반드시 candidates에 포함하여 동일 조건에서 경쟁시킨다.

결과는 스코어 내림차순 JSON 배열로 출력됨.

### Step 4: SELECT — 최종 선택

**에이전트 역할 (SELECT)**:
스코어링 결과를 보고 최종 1개를 선택한다.

**판단 기준** (우선순위):
1. **스코어**: 가장 높은 score가 기본 선택
2. **신뢰도**: 사이클 수 10개 이상이어야 통계적 유의미
3. **안정성**: MDD가 -20% 이내
4. **현재 종목 우선**: 스코어 차이가 10% 이내면 현재 종목 유지 (전환 비용 회피)
5. **선물 방향**: FIND에서 추천한 direction과 백테스트 결과의 방향이 일치해야 함

### Step 5: APPLY — 결과 적용

```bash
# 종목 전환 적용 (새로운 백엔드 API 엔드포인트)
python3 .claude/skills/at-symbol-select/scripts/run_pipeline.py apply \
  --session-id <SESSION_ID> \
  --symbol ETHUSDT \
  --params '{"leverage":5,"position_side":"long"}' \
  --reason "ETHUSDT가 스코어 45.67로 1위. 현재 종목(BTCUSDT) 대비 23% 높은 점수." \
  --api-url http://localhost:8001
```

## 스코어링 알고리즘

백엔드 `_calculate_score()`와 100% 동일:

```
base_score = (total_return × 0.7) + (win_rate × 0.15)

reliability (사이클 수 기반):
  1~2회:  0.2~0.4  (매우 불안정)
  3~4회:  0.5~0.7  (낮은 신뢰도)
  5~9회:  0.76~1.0 (보통)
  10+회:  1.0~1.2  (안정, 보너스 있음)

final_score = base_score × reliability
```

## Scripts

| 파일 | 역할 |
|------|------|
| `scripts/fetch_market_data.py` | Binance 24hr 티커 → stock_data + ranking_data |
| `scripts/scoring.py` | 신뢰도 가중 스코어 계산 (백엔드 동일) |
| `scripts/run_pipeline.py` | 파이프라인 CLI 헬퍼 (fetch/backtest/score/apply) |

## 재활용하는 외부 스킬

| 스킬 | 용도 |
|------|------|
| `at-backtest` | COMPARE 단계 백테스트 실행 (`scripts/backtest.py`) |

## 데이터 소스

| 단계 | 소스 | 설명 |
|------|------|------|
| FIND | Binance REST API | 24hr 티커 데이터 (인증 불필요) |
| COMPARE | Binance REST API | 14일 1m OHLCV (fetch_exchange.py) |
| APPLY | Backend API | 세션 종목 전환 엔드포인트 |

## 제약 사항

- **Binance 전용**: 현재 Binance REST API만 지원. Kiwoom(한국 주식)은 백엔드 프록시 필요.
- **순차 실행**: 백테스트가 순차적으로 실행됨 (후보 20개 × 14일 = 약 5~10분)
- **API 엔드포인트 필요**: `POST /session/{id}/skill-symbol-switch` 엔드포인트가 백엔드에 있어야 APPLY 단계가 동작
- **실시간 진행 표시 없음**: 백엔드처럼 WebSocket 진행 표시는 미지원 (stdout 로그로 대체)

## 예시: 전체 파이프라인 실행

```
사용자: "BTCUSDT 세션의 AI 종목 선정 실행해줘. 조건은 '높은 변동성, 거래량 상위'"
에이전트:
  1. session-info로 세션 확인
  2. fetch-market --futures로 시장 데이터 수집
  3. 시장 데이터 분석 → 조건 매칭 후보 20개 선정
  4. batch-backtest로 후보+현재종목 백테스트 경쟁
  5. 결과 분석 → 최적 종목 선택
  6. apply로 백엔드에 적용
  7. 사용자에게 결과 보고
```
