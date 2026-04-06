# AI 종목 선정 파이프라인 참조

## 백엔드 원본 vs 스킬 매핑

| 백엔드 (ai_symbol_selection.py) | 스킬 대응 | 비고 |
|------|------|------|
| `_fetch_binance_market_data()` | `scripts/fetch_market_data.py` | 동일 포맷 |
| `_find_candidates()` → Claude CLI | 에이전트가 직접 분석 | CLI 호출 불필요 |
| `_compare_symbols()` → WaterfallEngine | `run_pipeline.py batch-backtest` → at-backtest | 독립 백테스트 |
| `_calculate_score()` | `scripts/scoring.py` | 100% 동일 알고리즘 |
| `_ai_select_best()` → Claude CLI | 에이전트가 직접 판단 | CLI 호출 불필요 |
| `switch_session_symbol()` | `POST /session/{id}/skill-symbol-switch` | 신규 엔드포인트 |

## 스코어링 공식

```
base_score = (total_return% × 0.7) + (win_rate% × 0.15)

reliability_multiplier:
  cycles 1~2:  0.3~0.4
  cycles 3~4:  0.55~0.7
  cycles 5~9:  0.76~1.0
  cycles 10+:  1.0~1.2

score = base_score × reliability
```

## FIND 판단 기준 (에이전트용)

시장 데이터에서 search_conditions에 맞는 종목을 찾을 때:

### 공통 기준
- USDT 페어만 (quoteVolume > $100K)
- 현재 세션 및 같은 그룹의 종목 제외
- 최대 20개 후보

### 선물 추가 기준
- 각 후보에 direction (long/short) 추천 필수
- 근거: 24h 가격 변동, 변동성, 거래량 추세

### 검색 조건 예시
| 조건 | 분석 방법 |
|------|----------|
| "높은 변동성" | volatility_top 랭킹 참조 |
| "거래량 상위" | volume_top 랭킹 참조 |
| "급등주" | change_top 랭킹 참조 |
| "과매도" | change_bottom 랭킹 참조 |
| "안정적" | 낮은 변동성 + 높은 거래량 |

## SELECT 판단 기준 (에이전트용)

1. **스코어 1위가 기본 선택**
2. **사이클 < 10**: 신뢰도 부족, 사이클 10+ 후보 우선
3. **MDD > -20%**: 위험, 감점 고려
4. **현재 종목과 스코어 차이 < 10%**: 현재 종목 유지 (전환 비용)
5. **동일 스코어면 사이클 수 많은 쪽 선택**

## 백테스트 기본 설정

| 항목 | 값 | 근거 |
|------|-----|------|
| 기간 | 14일 | 백엔드 동일 (단기 시그널 검증) |
| 인터벌 | 1m | 백엔드 동일 (분봉 기준) |
| 데이터 소스 | exchange (Binance API) | DB 의존성 없음 |
