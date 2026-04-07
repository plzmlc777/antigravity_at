## Strategy-Evolver 결과: `rsi_martingale` × `261520`

### Fitness Ranking (JSON)

```json
{
  "agent": "strategy-evolver",
  "symbol": "261520",
  "strategy": "rsi_martingale",
  "baseline": {
    "total_return": 2.38,
    "sharpe": 4.76,
    "mdd": -0.4,
    "win_rate": 55.84,
    "cycles": 77,
    "profit_factor": 6.17
  },
  "ranking": [
    {
      "rank": 1,
      "id": "M005",
      "params": {"rsi_period": 14, "trigger_level": 25, "reset_level": 65, "max_buy_count": 5, "lot_size_multiplier": 2.5, "additional_buy_mode": "step", "additional_buy_step": 1.5, "trailing_start": 2.0, "trailing_stop": 1.0},
      "return": 34.59, "sharpe": 1.77, "mdd": -4.14, "win_rate": 91.3,
      "verdict": "promising",
      "note": "수익률 압도적이나 과적합 비율 0.68 — 장기 검증 필수"
    },
    {
      "rank": 2,
      "id": "M002",
      "params": {"rsi_period": 21, "trigger_level": 20, "reset_level": 60, "trailing_start": 3.0, "trailing_stop": 1.5},
      "return": 2.65, "sharpe": 1.31, "mdd": -2.85, "win_rate": 100.0,
      "verdict": "promising",
      "note": "과적합 비율 음수(견고), 단 거래 4회로 표본 부족"
    },
    {
      "rank": 3,
      "id": "M001",
      "params": {"rsi_period": 7, "trigger_level": 25, "reset_level": 45, "trailing_start": 1.0, "trailing_stop": 0.5},
      "return": 1.84, "sharpe": 0.58, "mdd": -15.12, "win_rate": 82.22,
      "verdict": "rejected",
      "note": "MDD -15% 악화, 리스크 대비 보상 부족"
    },
    {
      "rank": 4,
      "id": "M003",
      "params": {"rsi_period": 9, "trigger_level": 35, "reset_level": 55, "max_buy_count": 6, "lot_size_multiplier": 1.5, "trailing_start": 1.5, "trailing_stop": 0.8},
      "return": -12.66, "sharpe": -0.56, "mdd": -26.01,
      "verdict": "rejected",
      "note": "6레벨 마틴게일 과다진입 → MDD -26%"
    },
    {
      "rank": 5,
      "id": "M004",
      "params": {"rsi_period": 5, "trigger_level": 30, "reset_level": 50, "trailing_start": 0.5, "trailing_stop": 0.3, "max_buy_count": 3},
      "return": -13.20, "sharpe": -0.96, "mdd": -15.22,
      "verdict": "rejected",
      "note": "타이트 트레일링이 정상 변동에 조기 청산 유발, PF 0.11"
    }
  ],
  "next_steps": [
    "M005 → 60/90일 장기 백테스트로 과적합 최종 확인",
    "M005 → 모의거래 2주 실시간 검증",
    "M002 → 60일+ 백테스트로 표본 15회 이상 확보 후 재평가",
    "하이브리드: 기준선 파라미터 + M005의 step-down 추가매수만 부분 적용"
  ]
}
```

### 핵심 인사이트

| | 기준선 | M005 (1위) | M002 (2위) |
|---|---|---|---|
| Return | 2.38% | **34.59%** | 2.65% |
| Sharpe | **4.76** | 1.77 | 1.31 |
| MDD | **-0.4%** | -4.14% | -2.85% |
| Win Rate | 55.8% | **91.3%** | 100% |
| 과적합 | - | 0.68 (높음) | **-0.47 (없음)** |

- **M005**가 수익률 기준 압도적이나 과적합 비율 0.68로 실전 전 장기 검증 필수
- **M002**는 견고하지만 거래 횟수(4회)가 너무 적어 통계적 신뢰도 부족
- 기준선 전략은 **Sharpe 4.76**으로 안정성/일관성에서 여전히 우수
- 추천: M005의 `step-down 추가매수 모드`를 기준선 파라미터에 부분 적용하는 하이브리드 접근
