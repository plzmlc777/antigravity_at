---
name: at-backtest
description: |
  Auto Trading 백테스트 스킬. 전략을 과거 데이터로 검증하고 파라미터를 최적화한다.
  "백테스트 해줘", "전략 테스트", "파라미터 최적화", "walk-forward", "전략 비교" 등의 요청 시 사용.
  기존 BacktestEngine과 API 엔드포인트를 활용하며, 새 코드를 작성하지 않고 기존 시스템을 호출한다.
allowed-tools: Read, Write, Edit, Bash(python:*), Bash(curl:*)
version: 1.0.0
author: Antigravity Auto Trading
tags: [backtest, optimization, strategy, trading]
---

# Auto Trading 백테스트 스킬

## Overview

기존 BacktestEngine, WaterfallBacktestEngine, 최적화 엔진을 활용하여 전략을 검증한다.
이 스킬은 **두 가지 실행 경로**를 병행한다:

1. **API 래퍼** — 기존 백엔드 API를 호출 (운영 엔진과 100% 동일한 결과)
2. **독립 스크립트** — `scripts/`의 자체 코드로 실행 (API 없이 독립 동작)

## 병행 개발 원칙

> **기존 통합 엔진(BacktestEngine)과 독립 스크립트는 항상 병행하여 작업한다.**
> 스킬의 독립 스크립트를 수정하거나 기능을 추가할 때는 반드시 기존 API 결과와 비교하여
> 동일성을 검증해야 한다. 이 원칙은 다른 기능을 스킬로 전환할 때도 동일하게 적용된다.

### 왜 병행하는가?

- **결과 검증**: 독립 스크립트의 로직이 기존 엔진과 동일한지 `scripts/compare.py`로 수치 비교
- **점진적 전환**: 기존 엔진을 유지하면서 스킬 코드의 정확성을 보장한 후에만 전환
- **회귀 방지**: 스킬 수정 시 기존 결과와 비교하여 의도치 않은 변경을 즉시 감지

### 검증 방법

```bash
# 동일 조건으로 API vs 독립 스크립트 결과 비교
cd .claude/skills/at-backtest/scripts
python3 compare.py --strategy dip_martingale --symbol 005930 --interval 1d --days 365
```

비교 결과에서 `total_cycles`, `total_return` 등 핵심 지표가 일치해야 전환 완료로 판정.
현재 상태: 로직 재현 진행 중 (미세한 처리 순서 차이로 인한 1~2 cycle 오차 존재).

## Prerequisites

- 백엔드 서버 실행 중 (http://localhost:8001) — API 래퍼 사용 시
- PostgreSQL DB 접속 가능 — 독립 스크립트 사용 시
- OHLCV 데이터 존재 (키움/바이낸스)

## Commands

| 명령어 | 설명 |
|--------|------|
| `/backtest` | 단일 전략 백테스트 실행 |
| `/optimize` | 파라미터 최적화 (Heavy Optimization) |
| `/walk-forward` | Walk-Forward 오버피팅 검증 |
| `/compare` | 전략 간 성과 비교 |

## 실행 방식

### 방식 1: API 호출 (기존 엔진, 운영 기준)
백엔드 API를 통해 백테스트를 실행한다:
```bash
# 단일 백테스트
curl -X POST http://localhost:8001/api/v1/strategies/{strategy_id}/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "005930",
    "interval": "1d",
    "days": 365,
    "initial_capital": 10000000,
    "config": {},
    "exchange_name": "Kiwoom"
  }'

# 바이낸스 선물
curl -X POST http://localhost:8001/api/v1/strategies/{strategy_id}/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "interval": "1h",
    "days": 90,
    "initial_capital": 10000,
    "config": {"leverage": 5, "position_side": "long"},
    "exchange_name": "Binance"
  }'
```

### 전략 목록 조회
```bash
curl http://localhost:8001/api/v1/strategies/list
```

### 방식 2: 독립 스크립트 (API 없이 직접 실행)
```bash
cd .claude/skills/at-backtest/scripts

# 백테스트 실행
python3 backtest.py --strategy dip_martingale --symbol 005930 --interval 1d --days 365

# JSON 출력
python3 backtest.py --strategy ema_momentum --symbol BTCUSDT --interval 1h --days 180 --json

# 전략 목록
python3 backtest.py --list

# API 결과와 비교
python3 compare.py --strategy dip_martingale --symbol 005930 --interval 1d --days 365
```

## 성과지표

### 기존 지표
| 지표 | 설명 | 기준 |
|------|------|------|
| total_return | 총 수익률 (%) | 양수 필수 |
| max_drawdown | 최대 낙폭 (%) | -20% 이내 권장 |
| win_rate | 승률 (%) | 50% 이상 권장 |
| profit_factor | 총이익/총손실 | 1.5 이상 권장 |
| sharpe_ratio | 리스크 조정 수익률 | 1.0 이상 권장 |
| total_cycles | 완료된 매매 사이클 수 | 30개 이상이어야 통계적 유의미 |
| avg_pnl | 사이클당 평균 손익 (%) | 양수 필수 |
| stability_score | 수익 안정성 (0-100) | 60 이상 권장 |
| acceleration_score | 최근 수익 가속도 | 양수면 개선 추세 |

### 결과 해석 가이드
- **Sharpe > 1.5 + MDD < 15%**: 우수한 전략
- **Sharpe > 1.0 + MDD < 20%**: 양호한 전략
- **Win Rate 높지만 Profit Factor 낮으면**: 소액 다승, 대액 패배 패턴
- **total_cycles < 30**: 통계적으로 신뢰 어려움, 기간 늘리기 권장

## 데이터 소스

| 거래소 | exchange_name | 지원 종목 | 인터벌 |
|--------|--------------|----------|--------|
| 키움증권 | Kiwoom | 한국 주식 (005930 등) | 1m, 5m, 1h, 1d |
| 바이낸스 현물 | Binance | 암호화폐 (BTCUSDT 등) | 1m, 5m, 15m, 1h, 4h, 1d |
| 바이낸스 선물 | Binance | USDM 선물 | 1m, 5m, 15m, 1h, 4h, 1d |

## 전략 파라미터

전략별 파라미터는 `references/strategies.md` 참조.
PARAMETER_SCHEMA의 `defaultOptRange` 필드에 최적화 추천 값이 정의되어 있음.

## 최적화

### Heavy Optimization (대규모 파라미터 탐색)
```bash
# 최적화 시작
curl -X POST http://localhost:8001/api/v1/strategies/heavy-optimize/{strategy_id} \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["BTCUSDT"],
    "parameter_ranges": {
      "dip_percent": [1, 2, 3, 5],
      "max_buy_count": [3, 5, 7]
    },
    "base_config": {"interval": "1h", "days": 90},
    "execution_mode": "fast"
  }'

# 진행 상태 확인
curl http://localhost:8001/api/v1/strategies/heavy-optimize/status/{task_id}

# 결과 CSV 다운로드
curl http://localhost:8001/api/v1/strategies/heavy-optimize/download/{task_id}
```

### 점수 계산 공식
```
score = (Return × Sharpe^1.2 × Stability) / MaxDrawdown^1.5
```

가중치 커스터마이징:
```bash
curl -X POST http://localhost:8001/api/v1/strategies/recalculate-scores \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "...",
    "weights": {
      "return_weight": 1.0,
      "sharpe_weight": 1.5,
      "stability_weight": 1.0,
      "mdd_weight": 1.5
    },
    "top_n": 20
  }'
```

## Walk-Forward 검증

오버피팅 여부를 판별하기 위해 In-Sample 최적화 → Out-of-Sample 검증을 롤링 수행.
상세 절차는 `commands/walk-forward.md` 참조.

### 독립 스크립트 최적화 (API 없이)

```bash
cd .claude/skills/at-backtest/scripts

# Grid Search (기본 범위 사용)
python3 optimize.py -s rsi_martingale --symbol SOLUSDT -i 1m -d 14 \
    --exchange BinanceFutures --leverage 5

# Grid Search (파라미터 지정)
python3 optimize.py -s rsi_martingale --symbol SOLUSDT -i 1m -d 14 \
    --exchange BinanceFutures --leverage 5 \
    --param "rsi_period=7,14,21" --param "trigger_level=25,30,35"

# 백엔드 호환 가중 점수 (Return^w * Sharpe^w * Stability^w / MDD^w)
python3 optimize.py -s rsi_martingale --symbol SOLUSDT -i 1m -d 14 \
    --exchange BinanceFutures --leverage 5 --scoring weighted --json

# Walk-Forward 검증 (과적합 탐지)
python3 optimize.py -s rsi_martingale --symbol SOLUSDT -i 1m -d 60 \
    --exchange BinanceFutures --leverage 5 --walk-forward --folds 3
```

**Walk-Forward 결과 해석**:
- `overfit_ratio < 0.2`: GOOD — 실전 적용 가능
- `overfit_ratio 0.2~0.5`: WARNING — 파라미터 단순화 권장
- `overfit_ratio > 0.5`: OVERFIT — 파라미터 범위 축소 또는 기간 확대 필요

## Scripts (독립 실행 코드)

| 파일 | 역할 |
|------|------|
| `scripts/fetch_data.py` | PostgreSQL 직접 조회 + 캔들 집계 (1m → 1h, 1d 등) |
| `scripts/strategies.py` | 전략 로직 재현 (dip_martingale, ema_momentum, rsi_martingale, time_momentum) |
| `scripts/metrics.py` | 성과지표 계산 (sharpe, mdd, win_rate, stability 등) |
| `scripts/backtest.py` | 독립 백테스트 엔진 (CLI) |
| `scripts/optimize.py` | Grid Search + Walk-Forward + 가중 점수 최적화 |
| `scripts/compare.py` | API 결과 vs 독립 결과 비교 검증 |

## Resources

- `commands/backtest.md` — /backtest 명령어 상세
- `commands/optimize.md` — /optimize 명령어 상세
- `commands/walk-forward.md` — Walk-Forward 검증 절차
- `commands/compare.md` — 전략 비교 절차
- `references/strategies.md` — 전략 목록 및 파라미터
- `references/metrics.md` — 성과지표 상세 정의
- `config/settings.yaml` — 기본 설정값
