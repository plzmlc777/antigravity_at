# Research Track Paradigm Queue — 2026-Q3 Round 2 (Q2 16/16 완료 후 새 차원 발굴)

> **목적**: PARADIGM_QUEUE_2026Q2 16/16 처리 완료 (1 R-5 시드 + 15 graveyard) 후 새 차원 paradigm 발굴.
> **제약**: premium 도메인 saturated 결정 — 추가 derivative/transformation 시도 권장 안 됨. 새 raw data 도메인 또는 novel statistical approach 우선.
> **목표**: 추가 R-5 시드 1-2개 발굴 + 새 차원 lessons 기록.

---

## 0. TL;DR — 우선순위 큐 (12 candidates)

| # | Paradigm | Category | §3 위험 | 데이터 | 추천도 |
|---|---|---|---|---|---|
| 1 | `liquidation_cascade_event` | 새 raw data | 데이터 backfill 필요 (Binance liq REST API) + §3-A | (필요) | ⭐⭐⭐ |
| 2 | `taker_buy_volume_5m_zscore` | 5m microstructure 새 컬럼 | §3-G TBS family but volume-normalized 다름 | microstructure joblib | ⭐⭐ |
| 3 | `realized_vol_regime_5m` | 5m vol 다른 차원 | §3-G vol_regime_breakout family but 5m | OHLCV 1m | ⭐⭐ |
| 4 | `oi_premium_5m_decoupling` | OI 5m + premium 5m joint | premium 5m backfill 필요 + §3-G | (premium 5m backfill 필요) | ⭐⭐ |
| 5 | `funding_premium_oi_4signal_majority` | 4-signal voting (joint_3 확장) | §3-G strong | 시드 4 paradigm 결합 | ⭐⭐ |
| 6 | `microstructure_smartmoney_consensus` | top_position_LSR / global_account_LSR ratio | §3-G TBS/LSR family | microstructure | ⭐ |
| 7 | `oi_funding_correlation_regime_5m` | 5m OI z + 8h funding aligned, corr regime | §3-G filter 의심 | microstructure + DB funding | ⭐ |
| 8 | `intraday_premium_cycle` | hour-of-day premium z bias | §3-F + premium 5m backfill 필요 | (필요) | ⭐ |
| 9 | `hmm_regime_premium` | HMM 2-3 state regime detection | 새 통계적 접근 | premium 1d | ⭐⭐ |
| 10 | `kalman_filter_premium_innovation` | Kalman residual extreme | 새 통계적 접근 | premium 1d | ⭐ |
| 11 | `change_point_detection_premium` | CUSUM/Bayesian structural break | 새 통계적 접근 | premium 1d | ⭐⭐ |
| 12 | `cross_funding_premium_lead_lag` | funding leads premium vs reverse, time-varying lag analysis | §3-G but lead-lag dynamics 새 차원 | DB funding + premium | ⭐ |

---

## 1. Candidates 상세

### #1 `liquidation_cascade_event` ⭐⭐⭐ (최강 후보, 데이터 backfill 필요)
- **데이터**: Binance liquidation REST API (`/fapi/v1/forceOrders` archive 또는 `data.binance.vision/futures/um/daily/liquidationSnapshot/`)
- **신호**: 5m 또는 1m 격자에서 large liquidation event 감지 → cascade 시작점 식별 → reversal 예측
- **가설**: 강제 청산 cascade 후 단기 reversal (over-stretched leverage flushed). 또는 cascade 가속 momentum (추가 청산 예측).
- **§3 위험**: §3-A rare-event (extreme cascade는 sparse), 데이터 backfill 필요
- **R-1 fail-fast**: liquidation magnitude threshold sweep, alpha+sharpe ≥ 0
- **추천**: 가장 강한 새 차원, 다른 domain 시드와 직교

### #2 `taker_buy_volume_5m_zscore` ⭐⭐ (microstructure 새 컬럼)
- **데이터**: microstructure joblib `taker_buy_sell_ratio` (graveyard 23) — 다른 컬럼 활용 검토 (taker_buy_volume_quote 등 backfill)
- **신호**: 5m taker_buy_volume의 30-bar z-score, momentum direction
- **가설**: large taker buy → momentum 시작 (smart money or retail FOMO)
- **§3 위험**: §3-G TBS family (graveyard) but volume-normalized 다른 차원
- **추천**: microstructure 데이터 다시 활용 가능

### #3 `realized_vol_regime_5m` ⭐⭐
- **데이터**: OHLCV 1m → 5m return
- **신호**: 5m return rolling 288-bar realized vol z-score, vol expansion 감지 후 momentum
- **가설**: vol expansion 시작점은 새 트렌드 시작 → follow direction
- **§3 위험**: §3-G vol_regime_breakout family (graveyard) but 5m granularity 새 차원
- **추천**: graveyard family 회피 위해 conservative

### #4 `oi_premium_5m_decoupling` ⭐⭐ (premium 5m backfill 필요)
- **데이터**: microstructure OI 5m + premium 5m (필요)
- **신호**: oi_price_decoupling (시드 1d) 5m analog
- **가설**: 5m OI 변화 + premium 변화 decouple/confirm 시 short-term reversal
- **§3 위험**: §3-G derivative of seeded paradigm but cross-domain (OI×premium new joint)
- **추천**: premium 5m backfill (1y, 14종) 후 시도

### #5 `funding_premium_oi_4signal_majority` ⭐⭐
- **데이터**: 4 시드 paradigm 신호
- **신호**: funding_carry + premium_index_zscore + premium_velocity_zscore + oi_price_decoupling 4-signal majority voting (3+/4 same direction → trade)
- **가설**: 4-way voting이 3-way (joint_3signal POSITIVE) 보다 strong selectivity
- **§3 위험**: §3-G strong but ensemble voting (POSITIVE precedent)
- **추천**: joint_3signal_ensemble과 비교 분석 가치

### #6-#12: 자세한 hypothesis는 각 candidate별로 새 세션에서 결정

---

## 2. fail-fast 결정 트리 (Q2 검증된 fast path)

```
R-1 SOL alpha+sharpe ≥ 0?
├─ NO → graveyard 즉시 (1 paradigm/day)
└─ YES → R-2 multi-symbol 10 paper-pool 종
        ├─ alpha pos < 6/10 OR sharpe pos < 4/10 → graveyard (§3-E)
        └─ alpha pos ≥ 6/10 → R-3 perm n=200 top 4 candidates
                ├─ random_mean이 real의 50%+ → §3-D 의심
                ├─ best perm σ < 2σ → graveyard
                ├─ 2-4σ → §3-G note + graveyard
                └─ ≥ 4σ AND multi-symbol consistency → R-5 candidate
                        ├─ Diversity check: 4σ+ 종목 이미 시드?
                        │   ├─ 같은 도메인 시드 → §3-G strong, R-5 SKIP
                        │   ├─ 다른 도메인 시드 → R-5 candidate ✓
                        │   └─ 시드 안 됨 → R-5 candidate ✓✓
                        └─ 사용자 승인 게이트 → 시드 procedure
```

---

## 3. 진행 추적 표

| Date | Paradigm # | Phase | Result | Decision |
|---|---|---|---|---|
| (예정) | #1 liquidation_cascade_event | (대기 — 데이터 backfill 필요) | — | — |
| (예정) | #2 taker_buy_volume_5m_zscore | (대기) | — | — |
| (예정) | #3 realized_vol_regime_5m | (대기) | — | — |
| (예정) | #4 oi_premium_5m_decoupling | (대기 — premium 5m backfill) | — | — |
| (예정) | #5 funding_premium_oi_4signal_majority | (대기) | — | — |
| (예정) | #6 microstructure_smartmoney_consensus | (대기) | — | — |
| (예정) | #7 oi_funding_correlation_regime_5m | (대기) | — | — |
| (예정) | #8 intraday_premium_cycle | (대기 — premium 5m backfill) | — | — |
| (예정) | #9 hmm_regime_premium | (대기 — hmmlearn 의존성 추가) | — | — |
| (예정) | #10 kalman_filter_premium_innovation | (대기) | — | — |
| (예정) | #11 change_point_detection_premium | (대기 — ruptures 의존성 추가) | — | — |
| (예정) | #12 cross_funding_premium_lead_lag | (대기) | — | — |

---

## 4. 새 세션 시작 시 명령

```
Read /home/hcpark/antigravity/backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md 후 다음 paradigm 진행해줘
```

또는 명시적으로:

```
Read /home/hcpark/antigravity/backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md 후 #N <paradigm name> 진행해줘
```

---

## 5. 영구 제거 후보 (saturation 결정)

다음 paradigm 시도 권장 안 됨:
- premium 도메인 추가 derivative/transformation (Q2 5/16 모두 graveyard)
- funding 도메인 단순 z 변환 (5 paradigm 시도, 2 시드 + 3 graveyard)
- cross-section price/vol regime (3 graveyard)
- simple AND/correlation filter on seeded signals (4 graveyard)
- 2차+ derivative paradigm (1차 위계 lesson)
- 1y data로 cross-section/rare-event 검증 (book_depth/funding 한계)

---

**END** — 큐 Q3는 새 raw data 도메인 + 새 통계적 접근 위주.
