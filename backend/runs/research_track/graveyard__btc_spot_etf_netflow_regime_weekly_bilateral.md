# graveyard — btc_spot_etf_netflow_regime_weekly_bilateral

**Date**: 2026-08-08
**Verdict**: GRAVEYARD (G1 FAIL, G2 PASS)
**Phase reached**: R-1 (tier3 gate)

---

## 가설 요약

2024-01-11 미국 현물 BTC ETF 승인 이후 authorized participants 가 ETF 창설/환매를 위해
BTC 현물을 매수/매도해야 하므로, **일일 총 순유입액(aggregate daily net flow)** 이
기관 수요 사이클의 프록시가 된다는 가설. 5일 누적 순유입의 90일 롤링 백분위 순위를
계산하여 상위(≥0.80) 시 LONG, 하위(≤0.20) 시 SHORT, 14일 보유.

**Substrate**: SoSoValue openapi `/openapi/v2/etf/historicalInflowChart`
(type=us-btc-spot). 무인증 공개 엔드포인트, 300개 일봉 창(2025-05-29 → 2026-08-07).

**Universe**: BTCUSDT (단일 종목, tier3 재설계 기준 다종목 요구 없음)

## G0 결과

| 항목 | 결과 |
|---|---|
| DNA 중복 (5/6) | PASS — ≤2/6 (오케스트레이터 사전확인 + 슬러그 grep 확인) |
| Lesson #28 substrate 가용성 | PASS — SoSoValue openapi 접근 확인, FarSide/Coinglass 는 Cloudflare 차단 |
| Lesson #11 표본 밀도 | MARGINAL — 300일 × 20% × 20% = 60 후보 → 오버랩 방지 후 20 실현 (N_TRADES_MIN 딱 통과) |
| G2 cycle margin 사전 | PASS — hold 20160 / cycle 1440 = 14.0x >> 3.0x |

## R-1 결과 (T+1 표준)

| 지표 | 값 |
|---|---|
| n_trades | 20 |
| n_long / n_short | 8 / 12 |
| win_rate | 45.0% |
| mean_net_ret | +1.626% |
| median_net_ret | -0.599% |
| sharpe (annualized) | 1.05 |
| **long_edge** | **-1.34% (역)** |
| **short_edge** | **+3.60% (정)** |
| first / last signal | 2025-07-17 / 2026-07-20 |

**비대칭 신호**: SHORT 만 작동, LONG 은 손실. 즉, "ETF 유출/약세 → 14일 후 하락" 은
성립하지만 "ETF 유입/강세 → 14일 후 상승" 은 성립하지 않음. 중위값은 음수(-0.60%)로
소수 대박 short 이 통계를 만드는 구조 (Lesson #81 부분 재현).

## Tier3 Gate 판정 (CLI 강제)

```
[G1] 시간가중 성과 (반감기 90일)
  단순 엣지         +1.6258%
  시간가중 엣지     +0.9964%
  시간가중 t        0.418          기준 >= 1.5    ← FAIL
  최근 1/3 엣지     +0.4682%       기준 > 0
  과거 1/3 엣지     -2.1694%
  decay_ratio       N/A (과거 음수·최근 양수 → 통과)
  → G1 FAIL — 시간가중 t 0.42 < 1.5

[G2] 실행가능성 (차단형)
  edge_after_1bar   1.6598%
  roundtrip_friction 0.0800%
  delay_retention   1.666  ← T+2 가 T+1 보다 더 나음, 지연에 견고
  net_headroom      20.75  ← 기준 >= 3.0 훨씬 상회
  cycle_margin      14.0   ← 기준 >= 3.0 훨씬 상회
  → G2 PASS
```

**gate_result JSON**: `runs/research_track/btc_spot_etf_netflow_regime_weekly_bilateral/tier3_gate__BTCUSDT.json`

## 실패 원인 분석

1. **표본이 너무 작다**. 300일 창에서 오버랩 없는 신호는 20개. σ=7.88% 인데 μ=1.63%
   이면 표준오차 1.76%p, t-stat 은 원래 0.92. 시간가중 후 n_eff 가 더 줄어 t=0.42.
2. **최근 성과가 약하다**. 과거 1/3(2025-07~2025-11) 은 평균 -2.17% 였고 최근
   1/3(2026-04~2026-07) 은 +0.47%. 방향은 살아났지만 크기가 게이트에 못 미친다.
3. **비대칭 메커니즘**. SHORT 만 (+3.60%) 유효, LONG (-1.34%) 은 완전히 역. 양방향
   가설이지만 실제로는 단방향 SHORT-only 가 실제 알파라 봐야 한다 — 하지만 SHORT
   12개만으로는 표본 부족.
4. **G2 는 완벽하다**. lookahead clean, 지연 견고성 확인(T+2 가 오히려 더 좋음),
   실행주기 여유 14x, 마찰 여유 20x. 신호는 실행 가능하나 신호 자체가 약함.

## 다음 연구 방향 (있다면)

- **SHORT-only 단방향화 재발의는 하지 말 것**. 20개→12개로 표본 더 줄어 t-stat 
  악화, 사후선택 편향 위험.
- **표본 확장의 두 경로**:
  1. SoSoValue 프리미엄 API 로 2024-01-11 시점까지 백필 (유료 → [[feedback_no_freemium_trial]] 
     에 걸림, 불가)
  2. 개별 ETF (IBIT / GBTC / FBTC 등) 별 flow 스크래핑으로 사이드-차원 추가 →
     별도 substrate audit 필요, 크로스-소스 검증 필요
- **트리거 다각화 금지**. 3d rolling / 60d percentile 등으로 재시도하는 것은
  Lesson #37 (전체 sweep 필수) 을 인용해 표본 재활용 다중 검정 함정으로 봐야 한다.
- ETF flow 축은 **원래 표본이 부족한 것**이 근본 원인 (2년 반짜리 트랙레코드).
  이 축의 재발의는 최소 2027년 이후, 총 표본이 두 배가 되기 전에는 하지 않는다.

## 학습 (교훈 후보)

**Lesson #82 candidate — ETF-flow-like macro-institutional signal 은 4년 이상 트랙레코드가
필요하다**. 반년 hold × 20% top/bottom 트리거 조합에서 오버랩 없는 실현 표본은
연 15-25개 뿐. G1 wt_t ≥ 1.5 를 달성하려면 최소 60-80개 표본이 필요하고, 이는
3-4년 flow 창을 요구. SoSoValue openapi 는 300일만 제공하므로 이 축의 진지한
연구는 데이터 창이 늘어난 뒤 하는 것이 순서다.

Lesson #11 sample density 의 매크로 관측치 변형 — 하나의 아침 뉴스가 하나의
관측치가 되는 시그널은 R-1 이전에 "몇 년치 데이터가 필요한가" 를 먼저 계산해야 한다.

## 산출물

- code: `backend/scripts/research/poc_btc_spot_etf_netflow_bilateral.py`
- trades JSON: `backend/runs/research_track/btc_spot_etf_netflow_regime_weekly_bilateral/r1_trades.json`
- trades delayed: `.../r1_trades_delayed.json`
- trades full: `.../r1_trades_full.json`
- metrics: `.../r1_metrics.json`
- signals debug: `.../r1_signals_debug.csv`
- **gate result**: `.../tier3_gate__BTCUSDT.json`
