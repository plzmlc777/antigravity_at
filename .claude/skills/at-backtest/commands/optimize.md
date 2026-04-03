---
name: optimize
description: 파라미터 최적화 실행. "최적화 해줘", "파라미터 탐색", "최적 파라미터 찾아줘" 등의 요청 시 사용.
allowed-tools: Bash(curl:*), Read
---

# /optimize

Heavy Optimization으로 파라미터 조합을 대규모 탐색한다.

## Usage

```
/optimize <strategy_id> <symbol> [param_ranges]
```

## Examples

```
/optimize dip_martingale BTCUSDT
/optimize time_momentum 005930 --params '{"target_percent": [1,2,3,5], "max_buy_count": [3,5,7]}'
```

## 실행 절차

### 1. 전략의 PARAMETER_SCHEMA 확인
```bash
curl -s http://localhost:8001/api/v1/strategies/list | \
  python3 -c "import sys,json; data=json.load(sys.stdin); [print(json.dumps(s['parameter_schema'],indent=2,ensure_ascii=False)) for s in data if s['id']=='{strategy_id}']"
```

`defaultOptRange` 필드에서 추천 최적화 값을 확인한다.

### 2. 최적화 시작
```bash
curl -s -X POST http://localhost:8001/api/v1/strategies/heavy-optimize/{strategy_id} \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["{symbol}"],
    "parameter_ranges": {param_ranges},
    "base_config": {
      "interval": "{interval}",
      "days": {days},
      "initial_capital": {capital}
    },
    "execution_mode": "fast"
  }'
```

응답에서 `task_id`를 저장한다.

### 3. 진행 상태 확인
```bash
curl -s http://localhost:8001/api/v1/strategies/heavy-optimize/status/{task_id} | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Progress: {d.get(\"progress\",0):.1f}% | Top Score: {d.get(\"top_results\",[{}])[0].get(\"score\",0):.2f}')"
```

### 4. 결과 분석

상위 결과를 표로 정리:

```
| 순위 | 파라미터 | Return | Sharpe | MDD | WinRate | Score |
|------|---------|--------|--------|-----|---------|-------|
| 1 | ... | X% | X.XX | -X% | X% | X.XX |
```

### 5. (선택) 가중치 재계산
```bash
curl -s -X POST http://localhost:8001/api/v1/strategies/recalculate-scores \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "{task_id}",
    "weights": {
      "return_weight": 1.0,
      "sharpe_weight": 2.0,
      "mdd_weight": 2.0,
      "stability_weight": 1.5
    },
    "top_n": 10
  }'
```

## 최적화 팁

- **execution_mode: "fast"**: ProcessPool 병렬 실행 (CPU 코어 활용)
- **execution_mode: "standard"**: 순차 실행 (메모리 절약)
- 파라미터 조합 수 = 각 범위 크기의 곱. 10만 이상이면 시간 오래 걸림
- `defaultOptRange`를 먼저 사용하고, 좋은 구간을 좁혀서 재탐색
- 가중치 재계산으로 MDD 중시 vs Return 중시 비교 가능
