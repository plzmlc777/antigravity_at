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

---

## 6. 2026-05-14 Mid-Q3 Update — Lessons + 2024 백필 통합

> **목적**: 2026-05-14 burst (8 graveyard + 3 infrastructure + 1 R-5 시드)에서 얻은 lessons + 2024 OHLCV 백필 환경 변경을 Q3 큐에 반영.

### 6.1 환경 변경 사항 (Q3 §1 candidates 시작 전 mandatory baseline)

| 자원 | 이전 | 2026-05-14 이후 |
|---|---|---|
| OHLCV 1m 14 syms | 380일 (2025-04~2026-05) | **2.4년 (2024-01~2026-05)**, 9.7M rows 추가 |
| OHLCV joblib cache | 없음 | `backend/runs/ohlcv_cache/{SYM}_1m.joblib` × 14 (~250MB), 3-5s load/sym |
| Perm test 인프라 | inline ad-hoc (fee drag trap 위험) | `scripts/research/_perm_utils.py` (fee_aware/block_perm/bootstrap_ci) **의무 사용** |
| Gate evaluator | `evaluate_e()` legacy only | `evaluate_e_new()` for `_perm_utils` schema, 자동 detect |
| Funding rate DB | 1y (2025-05~) | **변화 없음** — funding 도메인 paradigm은 별도 백필 필요 |
| Premium joblib | 1y | **변화 없음** — premium 도메인은 별도 백필 필요 |
| Microstructure joblib | 5m × 1.5yr | **변화 없음** — OI/LSR/taker 도메인은 별도 백필 |

→ **OHLCV-only paradigm은 sample 1.7x 즉시 활용 가능**. Funding/premium/OI 기반은 별도 백필 필요.

### 6.2 R-1/R-3 mandatory checklist (8 lessons 통합)

1. **`_perm_utils` 의무 사용** — fee_aware_perm_test + bootstrap_ci. perm_p_two_sided + null_mean_t 반드시 보고.
2. **Three-gate strict** (R-1 pass): `signal_t_excess ≥ 2.0` AND `ci_lower > 0` AND `perm_p_two_sided ≤ 0.10`. legacy `|t|≥2 OR perm_p≤0.10` deprecated.
3. **Sign-conditional H5 split 의무** — unsigned hypothesis는 즉시 BTC sign 또는 가설 신호 sign으로 split하여 sub-paradigm 잠재성 검토.
4. **Vol regime stratify (R-3)** — best cell를 BTC 30d vol regime (p25/p50/p75/p90)별로 stratify. 한 regime이라도 강하게 음수면 sub-paradigm 후보 또는 graveyard 사유.
5. **OHLCV joblib cache 사용** — DB ORDER BY 13min vs cache 30s. R-3 ≥ 2 alts 사용 시 의무.
6. **LOCAL execution 우회 방지** — paradigm-architect agent 호출 시 prompt에 explicit `mint@183.99.228.81` 명시. 호출 후 BTCUSDT 1m count 확인 (= 1,241,280 expected).
7. **Mechanical vs Substantive verdict** — quarter denominator artifact 인지. 측정 가능한 모든 quarter PASS면 substantive PASS로 인정 가능.
8. **Mirror hypothesis antipattern** (70번째 graveyard 2026-05-14) — paradigm X의 LONG 측면이 +X bp여도 mirror SHORT는 +X bp가 **아니다**. 시장 미시구조 방향 비대칭 (UP-trigger = momentum continuation / DOWN-trigger = mean reversion 가능성). Mirror도 별도 R-1 검증 의무. precedent: paradigm 69 UP×LONG +113bp vs mirror DOWN×SHORT -49bp = **13σ 격차**. 또한 graveyard의 H5 sub-finding을 mirror 정량 evidence로 자동 채택 금지 — 별도 R-1으로 확정.

### 6.3 Fee Floor 사전 추정 룰 (새)

R-1 호출 전 다음 검증:
- Expected gross |return| per trigger event ≥ **16 bp** (= 2 × 8 bp fee + buffer)
- 추정 방식: mechanism의 absolute size estimate × hit rate
- 미달 시 발의 보류 (skewness/btc_rv_recovery graveyard pattern 회피)

### 6.4 Q3 §1 candidates 재분류 (Tier system)

기존 12 candidates + 2026-05-14 lessons 적용:

#### Tier 1 — 즉시 시도 가치 매우 높음

**~~A. `btc_rv_spike_HIGHVOL_down_alt_short_240m`~~ — 2026-05-14 GRAVEYARD (70번째)** ❌
- 가설 falsified: mirror SHORT는 **-49bp** (precedent +150 bp 잠재 가정 wrong)
- H6 측정: paradigm 69 UP×LONG +112.9bp vs mirror DOWN×SHORT -49bp = **13σ 격차**
- Mechanism 비대칭: UP-trigger = momentum continuation / DOWN-trigger = mean reversion rebound
- Lesson 통합 → §6.2 #8 (Mirror antipattern)

**#1 `liquidation_cascade_event`** (큐 §1 #1 유지)
- 데이터 백필 필요: Binance liq REST API `/fapi/v1/forceOrders` 또는 archive
- 백필 ETA 검토 필요 (별 turn에서 평가)
- 시도 가치: 새 데이터 차원, large effect (cascade 5%+ move)
- Pre-est gross: 200+ bp 가능 (rare event but huge)

#### Tier 2 — Mechanism distinct, 시도 가치 있음

**NEW D. `btc_oi_velocity_regime_alt_long_240m`** (paradigm 69 의 OI velocity 변형)
- 가설: BTC 30m OI growth z-score ≥ +2.5 + HIGH vol p90 → 13 alts LONG
- DNA: paradigm 69 mechanism (vol cascade) but OI velocity trigger 대신 RV
- Mid-fitness: oi_price_decoupling 시드와 다른 차원 (velocity ≠ decoupling)
- 데이터: microstructure joblib 5m OI 컬럼 보유

**#2 `taker_buy_volume_5m_zscore`** (큐 §1 #2)
- 2024 백필로 sample 1.7x 증가 시 LSR-style noise 우회 가능성
- 단 graveyard 60 (LSR contrarian) 패턴 위험
- 가설 전제: BTC up-trigger 같은 sign-conditional 적용 후 검증

#### Tier 3 — 데이터 백필 후 시도 (별 turn)

**#4 `oi_premium_5m_decoupling`** — premium 5m 백필 필요
**#12 `cross_funding_premium_lead_lag`** — funding 1y 한계, sample 부족

#### Tier 4 — 영구 제거 권장 (saturation / antipattern 확정)

| Q3 # | paradigm | 제거 사유 |
|---|---|---|
| #3 | `realized_vol_regime_5m` | paradigm 69가 이미 vol regime을 entry condition으로 활용 (substantive 중복) |
| #5 | `funding_premium_oi_4signal_majority` | §3-F filter mechanism antipattern (Q2 4/4 graveyard) |
| #6 | `microstructure_smartmoney_consensus` | LSR family direct extension (graveyard 60 직접 회피) |
| #7 | `oi_funding_correlation_regime_5m` | §3-F corr filter antipattern |
| #8 | `intraday_premium_cycle` | §3-F calendar + premium saturated (Q2 §5) |
| #9 | `hmm_regime_premium` | premium domain saturated (Q2 §5 명시) |
| #10 | `kalman_filter_premium_innovation` | premium domain saturated |
| #11 | `change_point_detection_premium` | premium domain saturated |

→ Q3 12 candidates 중 **8개 Tier 4 제거**, 2개 Tier 2-3 보존, 2개 Tier 1 (단 #1만 큐 원본). **새 2 candidates (A, D)는 Q3 큐에서 시작.**

### 6.5 Updated Schedule (2026-05-14 ~ 2026-06-13 Day 30 검증 전)

Day 30 검증까지 30일. 일일 1-2 candidate fail-fast:

| 우선순위 | candidate | 데이터 백필 필요? | ETA | 상태 |
|---|---|---|---|---|
| ~~1~~ | ~~A `btc_rv_HIGHVOL_down_alt_short_240m`~~ (mirror SHORT) | 없음 | R-1 5-10분 | **GRAVEYARD 2026-05-14** ❌ |
| 1 | D `btc_oi_velocity_regime_alt_long_240m` | 없음 (microstructure 보유) | R-1 10-15분 | 대기 |
| 2 | #1 `liquidation_cascade_event` | Binance liq archive 백필 평가 | 별 turn 평가 | 대기 |
| 3 | #2 `taker_buy_volume_5m_zscore` (sign-cond 변형) | 없음 (microstructure) | R-1 10-15분 | 대기 |
| 4 | #4 `oi_premium_5m_decoupling` | premium 5m 백필 ETA 평가 | 별 turn | 대기 |

#### Day 30 검증 가까워질 때 (2026-06-08~13)
- Paper baseline 측정 우선 (paradigm 69 13 sessions Day 30)
- 새 paradigm 시도 PAUSE — capacity 확보

### 6.6 Quick command (new candidate R-1 templ)

```bash
# Sign-conditional mirror variant (A)
Read /home/hcpark/antigravity/backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md §6.4 후
paradigm-architect 호출 — A 가설로 R-1 PoC ONLY 진행.
prompt: "_perm_utils 사용 + Mint mint@183.99.228.81 명시 + 1241280 BTC count 확인 + R-1 only halt".
```

---

**END Mid-Q3 Update** — 다음 candidate (Tier 1 A) R-1 즉시 시도 가능.
