---
name: backtest
description: 단일 전략 백테스트 실행. "백테스트 해줘", "전략 테스트" 등의 요청 시 사용.
allowed-tools: Bash(curl:*), Read
---

# /backtest

단일 전략을 과거 데이터로 검증한다.

## Usage

```
/backtest <strategy_id> <symbol> [options]
```

## Examples

```
/backtest dip_martingale BTCUSDT
/backtest time_momentum 005930 --interval 1d --days 365
/backtest ema_momentum ETHUSDT --interval 1h --days 90 --leverage 3
```

## 실행 절차

### 1. 전략 목록 확인
```bash
curl -s http://localhost:8001/api/v1/strategies/list | python3 -m json.tool
```

### 2. 전략 파라미터 확인
응답의 `parameter_schema`에서 해당 전략의 파라미터와 기본값을 확인한다.

### 3. 백테스트 실행
```bash
curl -s -X POST http://localhost:8001/api/v1/strategies/{strategy_id}/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "{symbol}",
    "interval": "{interval}",
    "days": {days},
    "initial_capital": {capital},
    "config": {strategy_params},
    "exchange_name": "{exchange}"
  }'
```

### 4. 결과 분석

응답에서 핵심 지표를 추출하여 표로 정리:

```
| 지표 | 값 | 판정 |
|------|-----|------|
| Total Return | X% | ✅/❌ |
| Max Drawdown | -X% | ✅/❌ (< -20%) |
| Win Rate | X% | ✅/❌ (> 50%) |
| Sharpe Ratio | X.XX | ✅/❌ (> 1.0) |
| Profit Factor | X.XX | ✅/❌ (> 1.5) |
| Total Cycles | XX | ✅/❌ (> 30) |
```

### 5. 판정 기준

| 등급 | 조건 |
|------|------|
| **우수** | Sharpe > 1.5, MDD < 15%, WR > 55%, PF > 2.0 |
| **양호** | Sharpe > 1.0, MDD < 20%, WR > 50%, PF > 1.5 |
| **보통** | Sharpe > 0.5, MDD < 30%, PF > 1.0 |
| **불량** | 위 조건 미달 |

## 파라미터 가이드

### 거래소별 기본값

**키움 (한국 주식)**:
- exchange_name: "Kiwoom"
- interval: "1d" (일봉 권장, 분봉은 ~1년 제한)
- days: 365
- initial_capital: 10000000 (1천만원)

**바이낸스 현물**:
- exchange_name: "Binance"
- interval: "1h" 또는 "4h"
- days: 90~180
- initial_capital: 10000 (USDT)

**바이낸스 선물**:
- exchange_name: "Binance"
- interval: "1h"
- days: 90
- initial_capital: 10000
- config에 leverage, position_side 추가

## 주의사항

- 키움 분봉 데이터는 약 1년(4000캔들)까지만 제공 (API 정책)
- total_cycles < 30이면 통계적 유의미성 부족
- 선물 백테스트 시 leverage와 position_side 필수 설정
- 백테스트 결과는 과거 성과이며 미래 수익을 보장하지 않음
