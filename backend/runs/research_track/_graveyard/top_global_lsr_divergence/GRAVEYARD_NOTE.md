# top_global_lsr_divergence — Graveyard Note (2026-05-06, 22nd paradigm)

## 설계
5m granularity microstructure joblib에서 `toptrader_position_ls_ratio` (smart money positioning) 와 `global_account_ls_ratio` (retail crowd) 격차의 rolling 288-bar(24h) z-score를 신호로 사용. 두 모드 테스트:
- `follow_top`: divergence z 양수 = smart money long-er → LONG
- `fade_top`: 반대 (smart money 역방향)

## R-1 SOL sweep 결과 (follow_top)
| spec | alpha | sharpe | mdd | trades |
|---|---|---|---|---|
| z=1.0 h=12 | -64.7 | -5.07 | 98.2 | 6208 |
| z=1.5 h=12 | -57.1 | -3.68 | 91.7 | 3957 |
| z=2.0 h=24 | +5.3 | -0.47 | 52.2 | 1242 |
| z=2.5 h=24 | +21.7 | -0.17 | 43.6 | 613 |
| **z=2.5 h=48** | **+30.6** | **+0.11** | 40.1 | 428 |
| z=2.0 h=48 | +17.2 | -0.12 | 49.3 | 813 |

best (z=2.5 h=48) borderline R-1 PASS (alpha+sharpe ≥ 0).
fade_top은 모든 sweep에서 catastrophic 음수 (alpha -65~-15).

## R-2 multi-symbol (10종, follow_top z=2.5 h=48)
| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades |
|---|---|---|---|---|---|---|
| **AVAXUSDT** | **+86.7** | **+0.84** | 37.1 | 49.1 | 1.13 | 434 |
| **SOLUSDT** | **+30.6** | **+0.11** | 40.1 | 49.5 | 1.02 | 428 |
| ETCUSDT | -0.8 | -1.35 | 68.8 | 46.3 | 0.82 | 460 |
| LINKUSDT | -12.1 | -1.13 | 60.9 | 46.8 | 0.83 | 432 |
| COMPUSDT | -17.1 | -1.89 | 73.3 | 38.9 | 0.75 | 463 |
| AXSUSDT | -27.2 | -1.68 | 78.5 | 37.8 | 0.76 | 500 |
| UNIUSDT | -27.7 | -1.25 | 83.8 | 44.1 | 0.79 | 447 |
| LDOUSDT | -32.6 | -1.18 | 94.9 | 45.2 | 0.77 | 465 |
| HBARUSDT | -36.9 | -2.51 | 79.1 | 40.8 | 0.66 | 419 |
| DOGEUSDT | -51.2 | -3.08 | 98.2 | 40.2 | 0.44 | 418 |

- **alpha pos: 2/10 (20%)** ❌ — funding_window_anomaly(10/10) 같은 §3-E 패턴조차 안 됨
- **sharpe pos: 2/10** ❌
- alpha mean -8.82 (강한 음수 평균)
- best AVAX 0/5 cutoff (PF 1.13 < 2, sharpe 0.84 < 2, alpha 87 < 150, mdd 37 > 28, wr 49 < 50)

## 보조 시도: top_account_vs_position 차원 (size disparity)
5종 quick test, fade_size mode:
- DOGE alpha +75 sharpe +0.6 (best)
- AVAX alpha +34 sharpe +0.3
- HBAR alpha +17 sharpe +0.1
- LINK alpha -24 sharpe -0.6
- SOL alpha -12 sharpe -0.8
3-4/5 weak positive but PF max 1.14 << 2.0 cutoff

## R-3 SKIPPED — paradigm-level fail
R-2 alpha 2/10 + sharpe 2/10 → 시드된 5 paradigm(alpha 9-10/10) 대비 catastrophically 약함. perm test 의미 없음.

## Lesson
- LSR (long/short ratio) 데이터는 상관관계가 noisy. top vs global 격차는 systematic 신호 아니고 종목별 microstructure 특성이 크게 다름 (AVAX/SOL만 follow_top 작동, 나머지는 fade)
- `oi_price_decoupling` 시드(perm 0.000 6.7σ)와 결정적 격차 — OI flow는 진짜 신호, LSR positioning은 약함
- "Smart money vs retail" classic intuition 5m granularity에서 microstructure 측정으로는 입증 안 됨
- 동일 데이터 도메인(microstructure joblib) 다른 컬럼(`taker_buy_sell_ratio`)이 다음 후보. **TBS는 실현된 aggressive flow ratio라 LSR(positioning state)와 본질적으로 다른 signal class** — 더 dynamic, less noisy 가능
