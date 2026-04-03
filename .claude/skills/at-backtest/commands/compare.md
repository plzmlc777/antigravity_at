---
name: compare
description: 전략 간 성과 비교. "전략 비교", "어떤 전략이 나아?", "A vs B" 등의 요청 시 사용.
allowed-tools: Bash(curl:*), Read
---

# /compare

동일 조건에서 여러 전략의 성과를 비교한다.

## Usage

```
/compare <strategy_a> <strategy_b> [strategy_c...] <symbol> [options]
```

## Examples

```
/compare dip_martingale time_momentum BTCUSDT
/compare ema_momentum rsi_martingale chart_pattern 005930 --interval 1d --days 365
```

## 실행 절차

### 1. 동일 조건으로 각 전략 백테스트

모든 전략을 **동일한 symbol, interval, days, capital**로 실행:

```bash
# 전략 A
curl -s -X POST http://localhost:8001/api/v1/strategies/{strategy_a}/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol":"{symbol}","interval":"{interval}","days":{days},"initial_capital":{capital},"config":{},"exchange_name":"{exchange}"}'

# 전략 B (동일 조건)
curl -s -X POST http://localhost:8001/api/v1/strategies/{strategy_b}/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol":"{symbol}","interval":"{interval}","days":{days},"initial_capital":{capital},"config":{},"exchange_name":"{exchange}"}'
```

### 2. 비교 테이블 생성

```
| 지표 | 전략 A | 전략 B | 전략 C | 승자 |
|------|--------|--------|--------|------|
| Total Return | X% | X% | X% | ? |
| Sharpe Ratio | X.XX | X.XX | X.XX | ? |
| Max Drawdown | -X% | -X% | -X% | ? |
| Win Rate | X% | X% | X% | ? |
| Profit Factor | X.XX | X.XX | X.XX | ? |
| Total Cycles | XX | XX | XX | ? |
| Stability | X.XX | X.XX | X.XX | ? |
| **종합 점수** | X.XX | X.XX | X.XX | **?** |
```

### 3. 종합 점수 계산

```
종합 점수 = (Return × Sharpe^1.2 × Stability) / MaxDrawdown^1.5
```

### 4. 통합 백테스트 (Waterfall 모드)

여러 전략을 동시에 실행하여 우선순위 기반 시그널 경쟁:

```bash
curl -s -X POST http://localhost:8001/api/v1/strategies/integrated/v2-backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "{symbol}",
    "interval": "{interval}",
    "days": {days},
    "configs": [
      {"strategy_id": "{strategy_a}", "rank": 1, "config": {}},
      {"strategy_id": "{strategy_b}", "rank": 2, "config": {}}
    ],
    "exchange_name": "{exchange}"
  }'
```

Waterfall 모드에서는 순위가 높은 전략의 시그널이 우선 적용된다.

### 5. 판정 가이드

| 상황 | 권장 |
|------|------|
| A가 모든 지표에서 우세 | A 선택 |
| A는 수익 높고 B는 MDD 낮음 | 리스크 선호도에 따라 선택 |
| 단일 성과는 A, Waterfall은 A+B | 통합(Waterfall) 사용 |
| 두 전략 성과 비슷 | Walk-Forward로 안정성 추가 검증 |
