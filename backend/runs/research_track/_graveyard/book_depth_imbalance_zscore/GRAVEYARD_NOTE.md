# book_depth_imbalance_zscore — Graveyard Note (2026-05-06, 25th paradigm)

## 설계
1d granularity LOB imbalance from `runs/book_depth/{SYM}_bookdepth.joblib`. Daily `imbalance_mean` = (bid_depth - ask_depth)/(bid+ask) rolling 30-day z-score. fade vs follow modes tested. **진짜 새 데이터 도메인** (passive limit-order pressure, OI/funding/premium 모두와 직교).

## 데이터 한계
- 1y coverage only (May 2025-May 2026, 364 days) — vs premium_index 800일/microstructure 2y
- **6 symbols only**: LINK, AVAX, SOL, DOGE, BTC, ETH (paper-pool 4종 + BTC/ETH)
- imbalance_mean 분포 right-truncated (max +0.26, min -1)

## R-1 SOL sweep (fade and follow)
**fade mode best**:
- z=1.0 h=5: alpha **+79.67** sharpe **+1.89** PF 1.79 wr 64 mdd 18.4 (25 trades) ⭐ best
- z=1.0 h=3: alpha +44 sharpe +0.44 (31 trades)
- z=2.0 h=3: alpha +43 sharpe +0.56 (5 trades)

**follow mode**: 모두 sharpe ≤ +0.77, weaker

## R-2 multi-symbol (fade z=1.0 h=5, 6 종)
| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades |
|---|---|---|---|---|---|---|
| **SOLUSDT** | **+79.67** | **+1.89** | 18.4 | 64.0 | **1.80** | 25 |
| **ETHUSDT** | **+61.57** | **+1.83** | **14.8** | **71.4** | **1.88** | 21 |
| BTCUSDT | +24.15 | +0.52 | 24.5 | 60.9 | 1.24 | 23 |
| DOGEUSDT | +44.45 | -0.07 | 33.6 | 54.5 | 0.98 | 22 |
| AVAXUSDT | +29.95 | -0.86 | 41.8 | 47.4 | 0.72 | 19 |
| LINKUSDT | +10.94 | -1.94 | 50.9 | 34.6 | 0.56 | 26 |

**alpha pos: 6/6 ✅** sharpe pos: 3/6, alpha mean +42

## R-3 perm test n=200 (fade z=1.0 h=5)
| Symbol | Real α | perm_p | rand_mean | σ | Result |
|---|---|---|---|---|---|
| **ETHUSDT** | 61.57 | **0.0350** | 15.26 | **2.2σ** | ✅ PASS |
| SOLUSDT | 79.67 | **0.0500** | 32.56 | 1.8σ | borderline PASS |
| BTCUSDT | 24.15 | 0.2750 | 12.23 | 0.5σ | ❌ FAIL |
| DOGEUSDT | 44.45 | 0.3600 | 38.98 | 0.2σ | ❌ FAIL |

**2/4 perm PASS** — paradigm-level evidence weak.

## Per-symbol gate score
- **ETH**: alpha 62/150=41% / sharpe 1.83/2.0=92% / mdd ✅ / wr ✅ / PF 1.88/2.0=94% → **2/5 strict + 3/4 robustness = 5/9**
- **SOL**: alpha 80/150=53% / sharpe 1.89/2.0=95% / mdd ✅ / wr ✅ / PF 1.79/2.0=90% → **2/5 strict + 3/4 robustness = 5/9**

## 비교 — 시드된 paradigms 대비 weak

| Paradigm | Best perm σ | Best alpha | Best sharpe | Strict cutoff |
|---|---|---|---|---|
| **premium_index_zscore** (24th seeded) | **9.0σ** | **+348** | **+3.15** | **5/5** |
| oi_price_decoupling (21st seeded) | 6.7σ | +146 | +1.73 | 4-5/5 |
| funding_dispersion (seeded) | strong | +138 | +3.50 | 4/5 |
| autocorr_regime (seeded) | strong | +116 | +1.25 | 3/5 |
| **book_depth_imbalance** (graveyard) | **2.2σ** | +80 | +1.89 | **2/5** |

book_depth는 alpha/sharpe magnitude는 autocorr 수준이지만 perm σ가 결정적으로 약함 (2.2σ vs autocorr LINK 강한 perm). single-symbol overfit 우려.

## R-3 SKIPPED for R-5 seed → graveyard

## Lesson
- LOB imbalance는 약한 directional signal 존재 (4× random_mean ratio for ETH)이지만 magnitude 한계
- 1y/6 symbols 데이터로는 paradigm robustness 입증 불충분
- ETH는 single-symbol R-5 seed 후보였으나:
  - paper-pool에 ETH 없음 (paper-pool 14종은 alt-focused)
  - perm 0.035 2.2σ는 시드된 paradigms (5-9σ)와 결정적 격차
  - 2/4 perm PASS는 paradigm-level conclusion 약함
- **재시도 가치**: book_depth 데이터 2y+ 누적 후 (2027-05~) + 14종 backfill 확장 후 재평가 가능. 현재로선 시드 권장 안 됨.

## 전략적 통찰 (4 graveyards in microstructure 도메인 후)
- 22 top_global_lsr_divergence (R-2 alpha 2/10)
- 23 taker_flow_zscore (R-2 alpha 3/10)
- 25 book_depth_imbalance_zscore (perm 2/4 PASS borderline)

**LOB-level/positioning state signals는 5m/1d granularity에서 모두 weak**. 강한 signal은 OI flow (oi_price_decoupling), funding rate level/dispersion (funding_carry/funding_dispersion), premium basis (premium_index_zscore) — **commitment / basis / flow** dimensions 본질. 다음 후보 방향: 다른 시간축 paradigm (e.g., weekly aggregation), 또는 multi-feature joint signals.
