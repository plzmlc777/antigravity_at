# 전략 목록 및 파라미터

> 최신 전략 목록은 `curl http://localhost:8001/api/v1/strategies/list`로 확인.
> 새 전략이 추가되면 자동 발견됨 (StrategyRegistry auto-discovery).

## 전략 목록

| ID | 이름 | 유형 | 방향 | 거래소 |
|----|------|------|------|--------|
| dip_martingale | 눌림목 마틴게일 | 마틴게일 | Long | 주식/현물/선물 |
| ema_momentum | EMA 모멘텀 | 추세추종 | Long | 주식/현물/선물 |
| time_momentum | 시간대 모멘텀 | 시간 기반 | Long | 주식/현물 |
| rsi_martingale | RSI 마틴게일 | RSI+마틴게일 | Long | 주식/현물/선물 |
| chart_pattern | 차트 패턴 | 패턴인식 | Long/Short | 현물/선물 |
| us_market_follow | 미국장 추종 | 상관관계 | Long | 주식 |
| funding_rate_arb | 펀딩비 차익거래 | 선물 Arb | Long/Short | 선물 전용 |
| spot_futures_hedge | 현선물 헷지 | 헷지 | Long/Short | 현물+선물 |

## 전략 상세

### dip_martingale (눌림목 마틴게일)
- **원리**: 가격 하락 시 단계별 추가 매수, 반등 시 일괄 매도
- **핵심 파라미터**:
  - `dip_percent`: 초기 매수 하락률 (%)
  - `level_gap_percent`: 추가 매수 간격 (%)
  - `max_buy_count`: 최대 매수 횟수
  - `lot_size_multiplier`: 추가매수 배율 (마틴게일 배수)
  - `trailing_stop_percent`: 트레일링 스탑 (%)
- **적합 시장**: 횡보~약세장에서 반등 포착
- **리스크**: 일방적 하락 시 대규모 손실

### ema_momentum (EMA 모멘텀)
- **원리**: 빠른 EMA가 느린 EMA를 상향 돌파 시 매수
- **핵심 파라미터**:
  - `ema_fast_period`: 빠른 EMA 기간
  - `ema_slow_period`: 느린 EMA 기간
- **적합 시장**: 추세장
- **리스크**: 횡보장에서 잦은 손절 (whipsaw)

### time_momentum (시간대 모멘텀)
- **원리**: 특정 시간대 진입 + 모멘텀 확인 + 트레일링 스탑
- **핵심 파라미터**:
  - `start_time`: 진입 시작 시간
  - `delay_minutes`: 시가 대기 시간
  - `target_percent`: 목표 수익률 (%)
- **적합 시장**: 장 초반 모멘텀이 강한 종목
- **리스크**: 갭 하락 시 초기 손실

### rsi_martingale (RSI 마틴게일)
- **원리**: RSI 과매도 시 매수, 마틴게일 추가매수
- **핵심 파라미터**:
  - `rsi_period`: RSI 기간
  - `oversold_level`: 과매도 기준
  - `overbought_level`: 과매수 기준 (청산)
- **적합 시장**: 평균회귀 성향 종목
- **리스크**: 추세적 하락 시 과매도 지속

### chart_pattern (차트 패턴)
- **원리**: 기술적 패턴(이중바닥, 삼각수렴 등) 인식 후 진입
- **핵심 파라미터**:
  - `pattern_type`: 패턴 유형
  - `sensitivity`: 민감도

### funding_rate_arb (펀딩비 차익거래)
- **원리**: 높은 펀딩비율 이용한 선물 차익거래
- **핵심 파라미터**:
  - `min_funding_rate`: 최소 펀딩비율
- **거래소**: 바이낸스 선물 전용
- **특징**: REQUIRES_FUTURES = True

### spot_futures_hedge (현선물 헷지)
- **원리**: 현물 매수 + 선물 매도로 시장 중립 포지션
- **핵심 파라미터**:
  - `hedge_ratio`: 헷지 비율

## 공통 파라미터

모든 전략에 적용되는 공통 파라미터:

| 파라미터 | 설명 | 기본값 |
|---------|------|--------|
| interval | 캔들 주기 | 전략별 다름 |
| trailing_stop_percent | 트레일링 스탑 (%) | 전략별 |
| max_loss_percent | 최대 손실 제한 (%) | 전략별 |
| betting_strategy | 베팅 전략 (fixed/kelly) | fixed |

### 선물 전용 파라미터

| 파라미터 | 설명 | 기본값 |
|---------|------|--------|
| leverage | 레버리지 배수 | 1 |
| position_side | 포지션 방향 (long/short/both) | long |
| liquidation_floor_pct | 청산가 안전 마진 (%) | 5 |

## 전략 추가 방법

1. `backend/app/strategies/{id}.py` 생성 (BaseStrategy 또는 MartingaleBase 상속)
2. `PARAMETER_SCHEMA` 정의
3. `backend/app/core/strategy_registry.py`에서 자동 발견됨 (재시작 불필요)
4. `strategy-builder` 에이전트 사용 시 위 과정 자동화
