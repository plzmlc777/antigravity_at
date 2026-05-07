# Research Track — Next Paradigm Runbook (2026-05-06 — **Q2 16/16 + Q3 #1-9 graveyard, 8 시드** (#4 wick_reversal_multibar SOL R-5 single-symbol exception seed) — 57 paradigms)

> **본 문서 목적**: 새 Claude Code 세션이 컨텍스트 잃지 않고 다음 paradigm을 즉시 시도할 수 있도록 self-contained 운영 가이드.
>
> **새 세션 지시 명령** (사용자 → Claude):
> ```
> Read /home/hcpark/antigravity/backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md 후 다음 paradigm 진행해줘
> ```

---

## 0. TL;DR — 한 화면 요약

| 항목 | 값 |
|---|---|
| **현 시점** | 2026-05-06 |
| **시도 완료 paradigms** | **57** (49 graveyard + **8 시드** ⭐ + 1 데이터 누적 중) — Q2 16/16 + Q3 #1-9 graveyard. **Q3 #4 wick_reversal_multibar SOL 4.49σ R-5 single-symbol exception seed 2026-05-06**. 8 antipatterns + distribution-moment saturated. |
| **2026-Q2 큐 outcome** | **1 R-5 시드** (#10 premium_velocity AVAX+HBAR) + **2 POSITIVE graveyards** (#14 calendar concentration, #6 inversion) + 13 graveyards (§3-G family/filter, §3-A rare-event) |
| **2026-Q3 큐 outcome (진행 중)** | Q3 #1 oi_funding_corr_regime §3-D graveyard (random_mean 55-85% real). **Q3 #2 wick_reversal POSITIVE 3σ borderline** (intra-bar OHLC wick shape **NEW dimension**, R-2 10/10 alpha mean +58.36, R-3 SOL 3.34σ + AVAX 2.99σ perm_p=0.0 — 4σ 미달 but 0/200 random beat real). |
| **시드된 paradigms** | `funding_carry` (HBAR/AXS/COMP), `autocorr_regime` (LINK/UNI), `funding_dispersion` (ETC), `cross_symbol_lead_lag` (DOGE), `oi_price_decoupling` (AVAX), `premium_index_zscore` (DOGE/SOL/LDO), `premium_velocity_zscore` (AVAX/HBAR), **`wick_reversal_multibar` (SOL ⭐ NEW single-symbol exception)** |
| **최근 시드 (2026-05-06)** | **`wick_reversal_multibar` 1종** (single-symbol exception 사용자 승인): SOL 99107ad5-edd (alpha 61.94/sharpe 1.41/PF 1.45/perm **4.49σ**, intra-bar OHLC SHAPE 5m **NEW dimension**, §3-C 1/4 multi-symbol). Diversity: SOL은 premium_index_zscore 시드 (premium 1d 도메인), wick_reversal_multibar는 intra-bar OHLC 5m (다른 도메인 + 다른 timeframe). |
| **데이터 도메인 status** | (1) **OHLCV 1m** 14+ 종 1-2y, (2) **funding rate 8h** 18 종 1y, (3) **microstructure joblib 5m** 800일 14종 (OI/LSR/TBS), (4) **premium_index joblib 1d** 800일 14종, (5) **book_depth joblib 1d** 365일 6 종. |
| **모든 도메인 saturation 결정** | premium 1d (5 paradigm 모두 weak), funding 1y (5 paradigm), OI 5m (1 시드 + acceleration weak), book_depth 365d (rare-event 한계), cross-section price/vol (3 graveyard) |
| **다음 마일스톤** | 2026-05-11 Day 7 (5종 시드), 2026-05-13 Day 7 (premium 5종 + premium_velocity 2종), **2026-06-05 Day 30 검증 (총 13 sessions: 시드 7 paradigms 누적)** |
| **다음 paradigm 후보** | (자세히는 §2 참조) **새 차원 도메인** 위주: liquidation events, multi-domain ensemble voting, intraday cycles (5m), HMM regime detection, microstructure 5m × premium 1d cross-TF |

---

## 1. 새 세션 시작 시 Context Load 순서

```bash
# 1. 본 runbook (이 문서) — 전체 status
Read /home/hcpark/antigravity/backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md

# 2. paradigm 진행 인덱스 (각 paradigm 결과 상세)
Read /home/hcpark/antigravity/backend/runs/research_track/INDEX.md

# 3. 큐 완료 요약 (이전 16 paradigms outcome)
Read /home/hcpark/antigravity/backend/runs/research_track/PARADIGM_QUEUE_2026Q2.md

# 4. 트랙 마스터 plan
Read /home/hcpark/antigravity/.claude/plans/research_track_master.md

# 5. 시드 sessions 운영 상태 확인
cd /home/hcpark/antigravity/backend && source venv/bin/activate
python3 -m scripts.paper_session_cli status
python3 -m scripts.milestone_check
```

---

## 2. 다음 paradigm 후보 — Round 2 (PARADIGM_QUEUE_2026Q3)

**시간 비용 0 + premium 도메인 saturation 회피 + 새 차원 발굴**.

### 2-A0. NEW DIMENSION proven exists — 향후 우선 시도 (Q3 #2 lesson, 2026-05-06)

| Rank | 후보 | 근거 | 추천도 |
|---|---|---|---|
| ~~0~~ | ~~`wick_reversal_volume_filter`~~ | **Q3 #3 graveyard 2026-05-06**: §3-H monotonic degradation 3rd confirm | ✗ |
| ~~0~~ | ~~`wick_reversal_multi_bar`~~ | **Q3 #4 graveyard 2026-05-06**: SOL 4.49σ PASS ⭐ but 1/4 multi-symbol consistency = §3-C single-symbol-fit. multi-bar averaging은 clean-signal sym에서만 작동 | POSITIVE single-sym ✗ R-5 |
| **0** | `wick_reversal_aggtrades` | aggTrades backfill (BTC 17mo 이미 있음, 14 paper-pool 종 backfill 필요) 후 trade-level liquidation proxy 정확도 향상 | ⭐⭐⭐ (truly new domain) |

### 2-A. 새 raw data 도메인 (최우선)

| Rank | 후보 | 차원 | 데이터 | §3 위험 | 추천도 |
|---|---|---|---|---|---|
| **1** | `liquidation_cascade_event` | Binance liquidation API 1y backfill 후 large liq 후 reversal | 새 도메인 (강력 직교) | 데이터 backfill 필요 (Binance liquidation REST endpoint), §3-A rare event | ⭐⭐⭐ |
| **2** | `taker_buy_volume_5m_zscore` | 5m taker_buy_volume / total_volume rolling z, momentum signal | microstructure joblib (taker_buy_sell_ratio 다른 컬럼) | §3-G TBS family (graveyard 23) but volume-normalized 다른 차원 | ⭐⭐ |
| **3** | `realized_vol_regime_5m` | 5m return rolling 288-bar realized vol z, vol regime change 후 momentum | OHLCV 1m → 5m | §3-G vol_regime_breakout family (graveyard) but 5m granularity 다름 | ⭐⭐ |
| **4** | `funding_premium_oi_4signal_majority` | 4-signal voting (joint_3signal_ensemble의 4-signal 확장) | 시드 paradigm 4개 결합 | §3-G strong (joint_3signal POSITIVE 였지만 R-5 SKIP) | ⭐⭐ |
| **5** | `intraday_premium_cycle` | hour-of-day premium z bias map (5m premium aggregation 필요) | premium 5m backfill 또는 minute aggregation | §3-F calendar (time_of_day graveyard family) but premium-specific | ⭐ |

### 2-B. 새 차원 derived signal (premium/funding/OI 도메인 외)

| Rank | 후보 | 차원 | 추천도 |
|---|---|---|---|
| ~~6~~ | ~~`oi_funding_correlation_regime_5m`~~ | **Q3 #1 graveyard 2026-05-06**: §3-D random_mean 55-85% of real, §3-J two-seeded-fade-joint antipattern | ✗ |
| **7** | `microstructure_smartmoney_consensus` | top_position_LSR / global_account_LSR ratio 변화, retail-vs-smart positioning regime | ⭐ (top_global_lsr_divergence graveyard 22, but combined ratio 새 metric) |
| **8** | `oi_premium_5m_decoupling` | OI 5m + premium 5m (backfill 필요) joint at 5m granularity | ⭐⭐ (oi_price_decoupling 5m 시드의 premium analog) |

### 2-C. 새 통계적 접근

| Rank | 후보 | 차원 | 추천도 |
|---|---|---|---|
| **9** | `hmm_regime_premium` | Hidden Markov Model 2-3 state regime detection on premium series | ⭐⭐ (regime detection 본격 ML) |
| **10** | `kalman_filter_premium_innovation` | Kalman filter residual extreme as signal | ⭐ |
| **11** | `wavelet_premium_decomposition` | wavelet 다중 scale premium signal extraction | ⭐ (compute heavy) |
| **12** | `change_point_detection_premium` | structural break detection (CUSUM/Bayesian) on premium series | ⭐⭐ |

### 2-D. 데이터 누적 대기

- `positioning_dynamics` (3-I): 60일 누적 후 R-1, **2026-07-03 시작 예정**.
- 추가 backfill 가치 큰 후보: book_depth 2y (현재 365d), funding 2y (현재 1y) — 큐 #6/#12/#16 재시도 가치 있음.

### 2-E. 영구 제거 (saturation 결론)

- ~~premium 도메인 추가 paradigm~~: vol/calendar/spread/ensemble/derivative 모두 graveyard. 시드된 premium_index_zscore + premium_velocity_zscore가 95%+ 정보 capture.
- ~~funding 도메인 단순 z 변환~~: 5 paradigm 시도, 2 시드(carry/dispersion) + 3 graveyard. 추가 derivation은 §3-G.
- ~~cross-section price/vol~~: 3 graveyard. BTC dominance/systemic이 individual prediction 신호 압도.
- ~~simple AND/correlation filter on seeded signals~~: filter mechanism antitpattern (§3-G).

---

## 3. Anti-patterns — 자동 graveyard 조건 (큐 16개에서 강화 확인)

### 3-A. Rare-event (small sample trap)
**증상**: extreme threshold로 7-15 trades sharpe 1.5+ → threshold 낮추면 sharpe 음수
**예시**: hurst_regime (10 trades sharpe 2.24 → 145 trades sharpe -0.94), book_depth_concentration #12 (6 trades BTC sharpe 3.18 → R-3 1.41σ FAIL)

### 3-B. Truncation bias (max-bars trap)
**증상**: `--max-bars 50000` PoC 매력적 → full data 정반대
**규칙**: max-bars 절대 사용 금지

### 3-C. Single-symbol fit
**증상**: 1 symbol PASS perm 4σ+, 다른 symbols all <2σ
**예시**: oi_change_acceleration_squeeze #9 ETC 3.98σ outlier (5/7 random), funding_premium_spread_zscore #8 SOL 3.10σ + ETC 0.08σ

### 3-D. Directional bias (bear/bull OOS)
**증상**: random_mean이 real alpha의 50%+ — random shuffle도 양수 alpha 자주 생성
**예시**: premium_volatility_regime #1 random_mean 31-40 vs real 88, cross_asset_premium_spread #2 AVAX/UNI random > real

### 3-E. Multi-symbol weak (paradigm-level fail)
**증상**: alpha pos 5/14 미만 OR sharpe pos 5/14 미만
**예시**: cross_symbol_correlation_regime, time_of_day_seasonality, cross_section_dispersion_breakout

### 3-F. In-sample optimization (calendar bias)
**예시**: monthly_premium_seasonality #5, weekday_DoW_combined #14 (POSITIVE but §3-G)

### 3-G. Family extension (가장 흔한, 큐에서 9건)
**증상**: 시드 paradigm의 derived metric/transformation/filter — perm σ가 component보다 항상 약함
**예시**: 
- premium-vol family (#1 range / #7 range_med / #11 GK) all graveyard
- premium calendar (#5 monthly / #14 DoW) §3-G strong
- premium ensemble (#15 multi-zwin) — single zwin이 우월
- premium spread (#8 fund-prem) — single-symbol fit
- derivatives 위계 (#9 OI 2nd derivative — outlier only)
- filter mechanism (#3 corr / #4 phase / #13 joint AND) — voting POSITIVE only

### 3-H. Filter mechanism antipattern (큐 신규 lesson)
**증상**: 시드 component에 filter 적용 → trade 줄이고 alpha quality 개선 marginal
**규칙**: simple AND/correlation filter는 항상 약화. voting (joint_3signal_ensemble = POSITIVE)만 marginal value 가능.

### 3-H. Filter mechanism antipattern — STRENGTHENED (Q3 #3 신규 강화, 2026-05-06)
**3rd confirmation** (premium_oi_corr / premium_oi_joint / wick_reversal_volume): even on NEW dimension, AND-filter MONOTONICALLY degrades signal. Higher selectivity → worse sharpe. wick_reversal vt=0~2.0 sweep: 1.62 → -0.07.
**규칙 강화**: AND filter on seeded paradigm component → 95%+ degradation 확률. R-1 sweep으로 즉시 확인 가능 (3 min fail-fast). Voting (majority of 3+ signals) 만 marginal value 가능 (joint_3signal_ensemble POSITIVE/SKIP).

### 3-N. Multi-source N-way AND agreement filter degrades (Q3 #8 신규 lesson, 2026-05-06)
**증상**: 2-way seeded paradigm (cross_symbol_lead_lag DOGE 1.83σ) 에 3rd source agreement filter (BTC + ETH 둘 다 같은 방향) 추가 → R-2 alpha 10/10이지만 sharpe 3/10 (cutoff 4/10 아래), mean -0.68.
**원인**: 두 leader 모두 NEW (seeded fade 아님)이라 §3-J/§3-H 회피된다고 봤지만, 단순 N-way AND agreement도 trade 수 narrowing으로만 작동, per-trade alpha quality 개선 없음.
**규칙**: AND-agreement 구조는 §3-L wick_reversal binary AND 같은 essential discriminator일 때만 유효 (bounded asymmetric metric × heavy-tailed). 단순 N-way leader confirmation은 항상 약화. **Voting (3-of-3 majority of independent signals)**만 marginal value 가능. cross_symbol_lead_lag 같은 이미 작동하는 2-way에 3rd source 추가하지 말 것.

### 3-M. Reference-price deviation = trend artifact (Q3 #7 신규 lesson, 2026-05-06)
**증상**: VWAP/SMA/EWMA reference-price deviation z-score → R-2 alpha 10/10이지만 R-3 perm test에서 random shuffle (volume/weighting) 이 real alpha와 같거나 더 높음 (AXS sigma **-0.43σ**, random_mean > real).
**원인**: rolling 24h reference price와 close 강한 상관, deviation은 본질적으로 "price above its rolling average?" trend signal. Volume weighting의 added info 미미. Permutation이 trend signal 그대로 보존.
**규칙**: Reference-price aggregation paradigms (VWAP, EWMA, smoothed average) deviation z 는 mostly trend-following alpha이고 reference-specific orthogonal info 거의 없음. Volume info 추출하려면 **timing-dependent**: volume burst at intra-bar event, volume × price asymmetric flow, anomalous volume bursts (binary threshold).

### 3-L. Continuous-multiplicative-composite without strict gates (Q3 #6 신규 lesson, 2026-05-06)
**증상**: bounded asymmetric metric (e.g. wick_imbalance ∈ [-1, +1]) × heavy-tailed metric (e.g. prior_ret) → continuous composite z-score → R-1 catastrophic (0/36 PASS, MDD 70-85%, 5-10x trade count vs binary equivalent).
**원인**: composite은 product, wick_imbalance가 거의 0인 약한 신호도 prior_ret heavy-tail에 곱해지면 z extreme 발화. 방향 sign(wick) noise-dominated.
**규칙**: 이전 §3-H에서 "AND filter는 항상 약화"라고 했지만 정확히는 **AND filter on seeded signal은 약화**. Wick paradigm처럼 **bounded × heavy-tailed product**에서는 binary AND gate가 essential noise discriminator. Continuous composite로 binary gate 대체 시도 권장 안 됨.

### 3-K. Intra-bar MAGNITUDE-only directional fail (Q3 #5 lesson, 2026-05-06)
**증상**: 5m HIGH-LOW range (vol shock magnitude) + prior_ret 방향 logic → R-2 alpha pos 8/10이지만 **MDD catastrophic 50-77%**, sharpe Q3 #2 wick 대비 4-5x 약함.
**원인**: intra-bar MAGNITUDE는 vol shock 일어났음을 표시하지만, direction은 prior_ret에 100% 의존 → noise-driven prior_ret signal에 weakness 그대로 노출, MDD wipe out.
**규칙**: intra-bar dimension에서 directional info 추출하려면 **SHAPE asymmetry 필요** (wick_reversal Q3 #2 POSITIVE 3σ). Pure magnitude shock paradigm 시도 권장 안 됨.

### 3-J. Two-seeded-fade-joint antipattern (Q3 #1 신규 lesson, 2026-05-06)
**증상**: 시드된 두 fade signal (e.g. funding_carry × oi_price_decoupling) 결합 → R-2 매우 강함 (10/10 alpha pos), R-3 perm test에서 random_mean이 real의 55-85% → §3-D 결정적 FAIL.
**원인**: 두 fade가 모두 자체적으로 trade-able이면, 결합은 단지 trade 수 narrowing이지 orthogonal alpha 추가 아님. permutation 한 컴포넌트 부수면 다른 컴포넌트가 alpha 대부분 회수.
**예시**: oi_funding_corr_regime (Q3 #1, R-3 0.73~-0.23σ).
**규칙**: 시드된 두 fade signal joint/corr filter 시도 권장 안 됨. 적어도 한 컴포넌트는 NEW (시드 안 됨) 이어야 의미 있는 interaction term.

### 3-I. Derivatives 위계 (큐 신규 lesson)
- 0차 (level): premium_index_zscore DOGE **9.0σ** 시드
- 1차 (velocity): premium_velocity_zscore AVAX **6.86σ** 시드 ✓
- 1차 (decoupling): oi_price_decoupling AVAX **6.7σ** 시드 ✓
- 2차 (acceleration): oi_change_acceleration ETC **3.98σ outlier** graveyard ✗
**규칙**: 2차 이상 derivative 시도 권장 안 됨

---

## 4. fail-fast 결정 트리 (큐에서 검증된 fast path)

```
R-1 SOL alpha+sharpe ≥ 0?
├─ NO → graveyard 즉시
└─ YES → R-2 multi-symbol (10 paper-pool 종)
        ├─ alpha pos < 6/10 OR sharpe pos < 4/10 → graveyard (§3-E weak)
        └─ alpha pos ≥ 6/10 → R-3 perm n=200 top 4 candidates
                ├─ random_mean이 real의 50%+ → §3-D 의심, R-3 fail probable
                ├─ best perm σ < 2σ → graveyard
                ├─ 2-4σ → §3-G note + graveyard
                └─ ≥ 4σ AND multi-symbol consistency → R-5 candidate (사용자 승인 게이트)
```

**Diversity check before R-5**:
- 4σ+ PASS 종목이 이미 다른 paradigm으로 시드됐다면 §3-G family 의심
- 같은 도메인 시드 → §3-G strong (보통 R-5 SKIP)
- 다른 도메인 시드 → R-5 후보 가치 (premium_velocity AVAX 6.86σ + HBAR 5.25σ 패턴)

---

## 5. 현재 paper sessions 상태 (2026-05-06)

### 시드된 13 paper sessions (7 paradigms)

| Paradigm | Session | Symbol | baseline | Day 7 milestone | Day 30 milestone |
|---|---|---|---|---|---|
| funding_carry | 472fafc0-65a | HBAR | alpha 107.7/sharpe 1.87 | 2026-05-11 | 2026-06-03 |
| funding_carry | accc65a5-e27 | AXS | alpha 148.6/sharpe 1.48 | 2026-05-11 | 2026-06-03 |
| funding_carry | f4c8ee87-a76 | COMP | alpha 118.4/sharpe 1.67 | 2026-05-11 | 2026-06-03 |
| autocorr_regime | 694e4f47-369 | LINK | alpha 116.2/sharpe 1.25 | 2026-05-11 | 2026-06-03 |
| autocorr_regime | 469a7a29-9be | UNI | alpha 120.3/sharpe 1.10 | 2026-05-11 | 2026-06-03 |
| funding_dispersion | d2640960-52b | ETC | alpha 138.0/sharpe 3.50 | 2026-05-12 | 2026-06-04 |
| cross_symbol_lead_lag | b5041367-5a6 | DOGE | alpha 69.8/sharpe 1.83 | 2026-05-12 | 2026-06-04 |
| oi_price_decoupling | 2555033d-308 | AVAX | alpha 145.7/sharpe 1.73 | 2026-05-13 | 2026-06-05 |
| premium_index_zscore | 07934d53-b9d | DOGE | alpha **348.2**/sharpe **3.15** track 최강 | 2026-05-13 | 2026-06-05 |
| premium_index_zscore | f99ca950-931 | SOL | alpha 166.5/sharpe 2.62 | 2026-05-13 | 2026-06-05 |
| premium_index_zscore | a2f423ae-2ce | LDO | alpha 290.1/sharpe 2.66 | 2026-05-13 | 2026-06-05 |
| **premium_velocity_zscore** | **e4bff252-84a** | **AVAX** | **alpha 365.9/sharpe 2.42** 큐 첫 break-through | **2026-05-13** | **2026-06-05** |
| **premium_velocity_zscore** | **8d70b971-0ec** | **HBAR** | **alpha 279.3/sharpe 2.14** | **2026-05-13** | **2026-06-05** |
| **wick_reversal_multibar** ⭐ | **99107ad5-edd** | **SOL** | **alpha 61.94/sharpe 1.41/perm 4.49σ** Q3 첫 4σ+ POSITIVE NEW dim, single-symbol exception | **2026-05-13** | **2026-06-05** |

---

## 6. 새 paradigm 시도 절차

```bash
# 0. 사용자 의도 확인
# - "다음 paradigm 진행" → §2 후보 중 §3-G/§3-A 위험 가장 낮은 것 자동 선택
# - "{paradigm 이름} 시도" → 명시 후보 진행

# 1. PoC 스크립트 작성 (premium_velocity_zscore 템플릿 사용)
cd /home/hcpark/antigravity/backend
cp scripts/poc_premium_velocity_zscore.py scripts/poc_<new_name>.py
cp scripts/poc_premium_velocity_zscore_r3.py scripts/poc_<new_name>_r3.py
# 가설/데이터/신호 부분만 수정 (simulate 함수 재사용)

# 2. 빠른 검증 (fail-fast)
source venv/bin/activate
python3 -m py_compile scripts/poc_<new_name>.py scripts/poc_<new_name>_r3.py

# 3. R-1 SOL sweep
python3 -m scripts.poc_<new_name> --symbols SOLUSDT --tag r1_sol_sweep
# alpha+sharpe ≥ 0 확인 → R-2, 음수면 graveyard

# 4. R-2 10 paper-pool 종
python3 -m scripts.poc_<new_name> --symbols HBARUSDT AXSUSDT COMPUSDT LINKUSDT UNIUSDT ETCUSDT LDOUSDT AVAXUSDT SOLUSDT DOGEUSDT --tag r2

# 5. R-3 perm n=200 top 4 candidates
python3 -m scripts.poc_<new_name>_r3 --symbols TOP1 TOP2 TOP3 TOP4 --n-iter-perm 200

# 6. 결과 처리:
#    - 4σ+ AND diversity OK → R-5 candidate, 사용자 승인 대기
#    - 2-4σ → §3-G note + graveyard
#    - <2σ → graveyard
#    - 결과 _graveyard/<paradigm>/ 으로 이동

# 7. 모든 tracking docs 동기화:
#    - INDEX.md (마지막 갱신 + graveyard table 행 추가)
#    - 메모리 project_paradigm_queue_2026q2.md (또는 새 q3 큐 만들 때 새 메모리)
```

---

## 7. R-5 시드 절차 (4σ+ + diversity OK 시)

```bash
# 1. composer source 작성 (premium_velocity_zscore_source 템플릿)
# app/composer_framework/sources/binance_<new>_source.py

# 2. pipeline_spec 등록
# app/composer_framework/pipeline_spec.py @register_source 추가

# 3. sources/__init__.py export 추가

# 4. paper_session_cli premium_df load condition 확장 (해당하는 경우)

# 5. session JSON 작성
# configs/paper_sessions/{SYMBOL}_<paradigm>.json

# 6. session 생성
python3 -m scripts.paper_session_cli create --spec configs/paper_sessions/{SYMBOL}_<paradigm>.json

# 7. dry-run validate
python3 -m scripts.paper_session_cli run --id <session_id>

# 8. milestone_check 등록
# scripts/milestone_check.py: RESEARCH_TRACK_SEEDS + BASELINE_METRICS

# 9. INDEX.md 시드 sessions table 업데이트
```

---

## 8. References

- **Master plan**: `.claude/plans/research_track_master.md`
- **이전 큐 완료 결과**: `backend/runs/research_track/PARADIGM_QUEUE_2026Q2.md`
- **인덱스**: `backend/runs/research_track/INDEX.md`
- **시드 PoC scripts (template)**: `backend/scripts/poc_premium_velocity_zscore.py` (+ r3)
- **시드 source (template)**: `backend/app/composer_framework/sources/binance_premium_velocity_zscore_source.py`

---

**END** — 본 runbook으로 새 세션은 Round 2 paradigm 발굴 (큐 Q3) 진행 가능.
