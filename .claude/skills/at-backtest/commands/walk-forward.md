---
name: walk-forward
description: Walk-Forward 오버피팅 검증. "오버피팅 검증", "walk-forward", "파라미터 안정성" 등의 요청 시 사용.
allowed-tools: Bash(curl:*), Bash(python:*), Read
---

# /walk-forward

In-Sample 최적화 → Out-of-Sample 검증을 롤링 수행하여 오버피팅을 탐지한다.

## Usage

```
/walk-forward <strategy_id> <symbol> [options]
```

## Examples

```
/walk-forward dip_martingale BTCUSDT
/walk-forward time_momentum BTCUSDT --is-days 180 --oos-days 60
```

## 개념

```
전체 데이터:  |======== IS-1 ========|=== OOS-1 ===|
                     |======== IS-2 ========|=== OOS-2 ===|
                                |======== IS-3 ========|=== OOS-3 ===|

IS  = In-Sample (최적화 구간)
OOS = Out-of-Sample (검증 구간)
```

- IS에서 최적 파라미터를 찾고, OOS에서 해당 파라미터로 백테스트
- IS 성과 >> OOS 성과이면 **오버피팅**
- IS 성과 ≈ OOS 성과이면 **안정적 전략**

## 실행 절차

### 1. 윈도우 설정 결정

| 인터벌 | IS 기간 | OOS 기간 | 총 데이터 | 윈도우 수 |
|--------|---------|---------|----------|----------|
| 1d (일봉) | 180일 | 60일 | 2년 | 3-4개 |
| 1h (시간봉) | 60일 | 20일 | 6개월 | 3-4개 |
| 5m (5분봉) | 30일 | 10일 | 3개월 | 3-4개 |

최소 3개 윈도우 이상이어야 통계적 의미가 있음.

### 2. 각 윈도우에서 실행

**윈도우 N마다 반복:**

**Step A: IS 구간 최적화**
```bash
curl -s -X POST http://localhost:8001/api/v1/strategies/heavy-optimize/{strategy_id} \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["{symbol}"],
    "parameter_ranges": {param_ranges},
    "base_config": {
      "interval": "{interval}",
      "from_date": "{is_start}",
      "to_date": "{is_end}",
      "initial_capital": {capital}
    },
    "execution_mode": "fast"
  }'
```

**Step B: 최적 파라미터 추출**
상태 조회에서 `top_results[0]`의 파라미터를 추출.

**Step C: OOS 구간 백테스트**
```bash
curl -s -X POST http://localhost:8001/api/v1/strategies/{strategy_id}/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "{symbol}",
    "interval": "{interval}",
    "from_date": "{oos_start}",
    "to_date": "{oos_end}",
    "initial_capital": {capital},
    "config": {best_params_from_step_b},
    "exchange_name": "{exchange}"
  }'
```

### 3. 결과 종합

모든 윈도우 결과를 표로 정리:

```
| Window | IS Period | OOS Period | IS Sharpe | OOS Sharpe | IS Return | OOS Return | Best Params |
|--------|-----------|------------|-----------|------------|-----------|------------|-------------|
| 1 | ... | ... | X.XX | X.XX | X% | X% | {...} |
| 2 | ... | ... | X.XX | X.XX | X% | X% | {...} |
| 3 | ... | ... | X.XX | X.XX | X% | X% | {...} |
| **평균** | | | X.XX | X.XX | X% | X% | |
```

### 4. 판정

| 패턴 | 의미 | 조치 |
|------|------|------|
| IS Sharpe ≈ OOS Sharpe | **안정적** — 파라미터 신뢰 가능 | 실전 투입 가능 |
| IS Sharpe >> OOS Sharpe | **오버피팅** — IS에서만 잘 됨 | 파라미터 범위 축소하거나 전략 수정 |
| OOS Return 지속 음수 | **전략 실패** — 실전에서 작동 안 함 | 전략 폐기 또는 근본적 수정 |
| 최적 파라미터가 윈도우마다 변함 | **불안정** — 시장 레짐 의존적 | 레짐 필터 추가 고려 |
| IS Sharpe < OOS Sharpe | **보수적 최적화** — 긍정적 시그널 | 가장 이상적인 결과 |

### 5. 추가 분석

- **Efficiency Ratio**: 평균 OOS Sharpe / 평균 IS Sharpe (0.5 이상이면 양호)
- **파라미터 안정성**: 윈도우별 최적 파라미터의 분산이 작을수록 좋음
- **레짐 의존성**: 특정 윈도우만 성과 급변하면 해당 기간 시장 상태 확인

## 주의사항

- IS와 OOS는 절대 겹치지 않아야 함 (데이터 누수 방지)
- OOS 기간이 너무 짧으면 노이즈에 취약
- 키움 분봉 데이터는 ~1년 제한 → 일봉으로 장기 검증 권장
- Walk-Forward 통과 ≠ 미래 수익 보장. 시장 구조 변화 가능성 항상 존재
