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
| ~~10~~ | ~~`kalman_filter_premium_innovation`~~ | ~~Kalman filter residual extreme~~ | ✗ **RETIRED via paradigm 227 R-0 HALT 2026-07-15** (Lesson #61 slug grep + #56 outcome family proxy + #62 DNA HARD FAIL + Q2 §5 premium domain saturated + Lesson #45 latent-state filter architectural break precedent paradigm 121). See §9. |
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

---

## 9. Paradigm 227 R-0 HALT log — 2026-07-15 (autonomous SELF-RECOMMEND mode)

**Proposed slug**: `alt_daily_premium_index_kalman_innovation_z_mr_bilateral_1d_to_7d`
**Proposed as**: paradigm 226 → **renumbered to 227** (226 already occupied by `alt_fear_greed_index_extreme_contrarian_bilateral_1d` GRAVEYARD_R1 2026-07-14).
**Verdict**: `R0_HALT_BY_FAMILY_PROXY_LESSON_61_SLUG_GREP_HIT_LESSON_56_OUTCOME_LEVEL_PREMIUM_DOMAIN_SATURATED_RETIRED_LESSON_69_5ITEM_TEMPLATE_LESSON_62_DNA_HARD_FAIL`

**Halt cause summary (Lesson #69 5-item template)**:
1. Lesson #61 slug grep SUCCESS 9th — `kalman_filter_premium_innovation` slug appears verbatim in this document §2-C row 10 (now marked retired) and in PARADIGM_QUEUE_2026Q3.md §Retire under "premium domain saturated" verdict.
2. Lesson #56 outcome-level family proxy SUCCESS 18th — MR direction on premium/basis substrate = paradigm 111 empirically-falsified sub-slice; paradigm 22 R-5 LIVE direction is FOLLOW opposite.
3. Lesson #62 DNA 5-dim HARD FAIL 12th — 3.5/5 overlap vs paradigm 22 R-5 LIVE; 3/5 overlap vs paradigm 121 BROAD_FALSIFIED (Kalman = latent-state filter analogous class to HMM on premium/basis cousin substrate).
4. Q2 §5 premium domain saturation ratification remains in force — proposed hypothesis violates both prongs (transformation of premium + novel-statistical-approach clause already spent on HMM paradigm 119/121).
5. Zero novelty outside retired perimeter — all 5 DNA dims inside retired zone.

**Compute saved**: ~15-20 min R-1 dispatch avoided.

**Substrate note**: 14 alts × 2.0yr premium 5m joblib present + scipy 1.17 available (filterpy missing but MLE Kalman implementable via scipy.linalg). Halt entirely upstream family-level.

**Artifacts**:
- `backend/runs/research_track/alt_daily_premium_index_kalman_innovation_z_mr_bilateral_1d_to_7d/r0_prescreen.json`
- `backend/runs/research_track/graveyard__alt_daily_premium_index_kalman_innovation_z_mr_bilateral_1d_to_7d.md`
- INDEX.json entry `paradigm_227_alt_daily_premium_index_kalman_innovation_z_mr_bilateral_1d_to_7d`

**Next paradigm (228) recommendation for the next SELF-RECOMMEND / dispatch cycle**:

- **Option A (preferred)**: `binance_perpetual_open_interest_per_symbol_composition_shift_family` — daily rolling 7d vs 30d Herfindahl index of per-symbol OI-share concentration change × BTC vol regime overlay. OI aggregate substrate (not premium/basis); mechanism is concentration structural change (not level MR/FOLLOW). Fresh substrate + fresh mechanism outside retired perimeters.
- **Option B (preferred)**: `binance_futures_maintenance_margin_tier_change_event_anchored_alt_directional_3d_bilateral` — MM tier hike/cut event class (Binance publishes ~monthly); each tier change is structural risk-limit shift on a specific symbol; test alt directional 3d MR/FOLLOW. Non-microstructure, regulatory/exchange event class — fresh dimension not tested to date.
- **Option C (deferred; explicit user greenlight required)**: `orderflow_via_aggTrades_taker_flow_1m_intraday_persistence_family` — requires >30min ETA aggTrades archive backfill + Lesson #21 advisory caution family risk.

**Explicitly REJECTED for 228+**:
- any premium/basis/funding derivative or novel-statistic-on-same-substrate (Q2 §5 retired);
- any HMM/Kalman/BOCPD/CUSUM/wavelet on saturated substrate (Lesson #45 architectural break paradigm 121 precedent);
- any latent-state filter (Kalman/HMM/particle filter/state-space) on premium/basis/funding substrate.

**Meta-observation**: SELF-RECOMMEND agent proposed hypothesis whose slug appears verbatim in this document's retire table. Reinforces that Lesson #61 slug grep prescreen against §2-E + PARADIGM_QUEUE §Retire + this §9 halt log MUST be Step 1 of every SELF-RECOMMEND cycle before hypothesis dispatch.


## 10. Paradigm 228 R-1 GRAVEYARD log — 2026-07-16 (autonomous dispatch)

**Slug**: `paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h`
**Executed as**: paradigm 228 (Option A from §9 recommendation — cross-sym OI-fraction composition family, reformulated as per-sym 30d rolling z-score of OI-value share instead of universe-level Herfindahl).
**Verdict**: `CONCENTRATED_R1_PASS_NARROW_SCOPE_LIFE_CHANGING_STRUCTURAL_FAIL_LESSON_74_CANDIDATE_4TH_DOGFOOD`
**Phase halted at**: R-1 (Lesson #37 full sweep completed; R-2 NOT dispatched)

### R-0 Prescreen (all 9 items PASS, including Lesson #40 empirical z range verification)

- Universe reduced 14 → 7 syms (HBAR/LINK/AVAX/SOL/DOGE/ETH/NEAR) per OI + OHLCV joint coverage; ADA excluded per Lesson #30.
- Empirical z distribution [-5.13, +5.28] confirms bilateral feasibility.
- Item 9 pre-flagged util risk (11% at z=1.5 h=1 projected → 3% at z=2.0 h=2) — flagged but not R-0 hard halt, per PoC allowed.

### R-1 Full Sweep (Lesson #37 mandatory, 36 cells)

Sweep z ∈ {1.0, 1.5, 2.0} × hold ∈ {1, 2, 3} × 4 quadrants (A_focus/A_mirror/B_focus/B_mirror).

**1/36 cells clears Concentration Gate**: z=2.0 h=2 B_focus (SHORT on share-exit + bar-DOWN)
- 3/7 syms ci_pos (HBAR n=12 mean=329bp t=2.06; AVAX n=12 mean=302bp t=2.20; NEAR n=26 mean=232bp t=2.14)
- quarter_pos_t=0.90 (highly consistent across time)
- 0/7 syms clear individual 3-gate (perm_p threshold too strict at n=12-26)

### Lesson #39 mirror antipattern check

Perfect fee-symmetric mirror across all 7 syms (B_focus + B_mirror = -16bp = -2×fee for every sym). Sub-class B mixed direction: 3/7 syms (HBAR/AVAX/NEAR/SOL) B_focus positive; 2/7 (DOGE/ETH) B_focus negative — partial info trigger.

### Life-changing 4-dim STRUCTURAL FAIL

Best cell (z=2.0 h=2 B_focus, 3 syms):
- edge/trade ~2.5% (mean 288bp of 3 pos syms) → PASS ≥2%
- trades/yr/sym ~5 (12-26 total / 2.4yr) → **FAIL 10x vs ≥50 target**
- capital util ~2.7% (5 × 2d / 365) → **FAIL 11x vs ≥30% target**
- sharpe (annual) ~1.5-2.0 (noisy at n=12-26) → marginal

**Sparse-trigger DNA (z=2.0 × 2d hold) creates util ceiling ~3% — unrecoverable within DNA per paradigm 213 exhaustive scoping precedent.**

### 4th NARROW_SCOPE_LIFE_CHANGING_FAIL dogfood

Precedents:
1. paradigm 95 — NARROW_SCOPE_LIFE_CHANGING_FAIL
2. paradigm 212 — NARROW_SCOPE_LIFE_CHANGING_FAIL
3. paradigm 213 — NARROW_SCOPE_LIFE_CHANGING_FAIL_STRUCTURAL (Lesson #74 candidate promoted)
4. **paradigm 228 — NARROW_SCOPE_LIFE_CHANGING_FAIL_STRUCTURAL** (4th dogfood; recommend promote Lesson #74 to CONFIRMED at 5th)

### NEW Lesson candidate

**Cross-sym FRACTION on cap-dominated universe**: When universe includes mega-caps (ETH 71% mean share, SOL 22% mean share in this cohort), z-score of the mega-cap's own share change is structurally weak because the denominator is dominated by itself. Real edge appears in the mid-cap syms (HBAR/AVAX/NEAR) whose share is more volatile in relative terms but too sparse in absolute triggers to support util targets.

**Prescription for future cross-sym composition paradigms**:
- Use equal-weighted rank-based composition (percentile of share change) instead of raw z-score, OR
- Restrict universe to same-tier syms (exclude BTC/ETH mega-cap), OR
- Demean by cap-tier before z-scoring.

### Compute cost

- 7 R-1 sweep runs × ~4s each = ~30s total wall-clock
- No backfill needed (existing microstructure OI cache + monthly klines cache reused)

### Artifacts

- Script: `backend/scripts/research/paradigm_228_oi_share_composition_r1.py`
- Metrics (7 files): `backend/runs/research_track/paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h/r1_*.json`
- Graveyard report: `backend/runs/research_track/graveyard__paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h.md`
- INDEX.json entry `paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h`

### Next paradigm (229) recommendation

- **Option A (preferred)**: apply NEW Lesson candidate prescription — reformulate paradigm 228 as `alt_cross_sym_oi_share_rank_percentile_change_bilateral_directional_MID_CAP_ONLY` (exclude ETH/SOL; use rank-percentile of 7d change instead of z-score; universe = 7 mid-caps HBAR/AXS/COMP/LINK/UNI/ETC/LDO/AVAX/DOGE/NEAR/DOT/AXS with OI coverage ≥ 700 days). Fresh reformulation preserving cross-sym composition DNA class while addressing mega-cap normalization noise.
- **Option B**: `binance_futures_maintenance_margin_tier_change_event_anchored_alt_directional_3d_bilateral` — MM tier change event class per §9 Option B (regulatory/exchange event class; requires exchange announcement history backfill ~10 events/yr).
- **Option C (deferred)**: any orderflow/aggTrades family (Lesson #21 caution + >30min ETA backfill).

### Meta-observation

Paradigm 228 was the FIRST paradigm executed from §9 forward recommendation queue (Option A). The reformulated OI-share z-score (vs original Herfindahl proposal) preserves the substrate + mechanism intent but tests per-sym composition shift. Result validates §9 recommendation direction (fresh substrate + fresh mechanism outside retired perimeters) but exposes a NEW antipattern (cap-weighted normalization noise) not yet in Q3 lessons. Continue autonomous SELF-RECOMMEND cycle with Option A reformulation for paradigm 229.

---

**END** — 본 runbook으로 새 세션은 Round 2 paradigm 발굴 (큐 Q3) + paradigm 229 자동 dispatch 진행 가능.

## 11. Paradigm 229 R-1 GRAVEYARD log — 2026-07-17 (autonomous dispatch)

**Slug**: `paradigm_229_alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h`
**Executed as**: paradigm 229 (Option A from §10 recommendation — mid-cap-only universe + pct_rank fix for paradigm 228 mega-cap normalization + Lesson #40 concerns).
**Verdict**: `BROAD_FALSIFIED_LESSON_39_SUB_CLASS_A_MIRROR_SYMMETRIC_MID_CAP_UNIVERSE_FIX_INSUFFICIENT_PCT_RANK_DESTROYS_PARTIAL_INFO`
**Phase halted at**: R-1 (Lesson #37 full sweep completed; R-2 NOT dispatched)

### R-0 Prescreen (all 9 items PASS)

- Universe: 5 mid-cap syms (HBAR/LINK/AVAX/DOGE/NEAR) intersected with kline_cache availability (LDO/AXS/COMP/ETC lacking klines_cache substrate — dropped from originally-proposed 10 mid-caps).
- pct_rank statistic bounded [0,1] → Lesson #40 structural threshold feasibility PASS trivially.
- Empirical trigger density 4.5-6.7% per sym per side (target 5%) → Lesson #11 sample density PASS.
- DNA distinct 5/5 vs paradigm 228 (z-score composition), 127/128 (OI-price decoupling), 196 (OI velocity).

### R-1 Full Sweep (Lesson #37 mandatory, 7 cells)

Sweep p_hi/p_lo ∈ {(0.90, 0.10), (0.95, 0.05), (0.97, 0.03), (0.98, 0.02)} × hold ∈ {1d, 2d, 3d} × 4 quadrants.

**Aggregate: 0/140 sym×quadrant×cell tests three_gate PASS**.

**Only 1/28 quadrant-cell concentration_gate PASS**: p95_h3 B_focus (SHORT 3-day hold on share-exit + bar-DOWN)
- n_ci_pos=2/5 (AVAX ci_lower=+26bp, NEAR ci_lower=+2bp)
- quarter_pos_t_ratio_avg=0.67
- BUT: AVAX/NEAR signal_t_excess = 1.87 / 1.77 (both <2.0) AND perm_p_below = 0.95 / 0.946 (observation indistinguishable from generic bearish drift null)
- → three_gate FAIL despite concentration PASS

### Lesson #39 sub-class A CONFIRMED

Every cell shows perfect fee-symmetric A_focus ↔ A_mirror pairing across all 5 syms:

| p95_h1 sym | A_focus mean_bp | A_mirror mean_bp | Sum |
|---|---|---|---|
| HBAR | +567.6 | -583.6 | -16.0 |
| LINK | -178.9 | +162.9 | -16.0 |
| AVAX | +47.2 | -63.2 | -16.0 |
| DOGE | +86.8 | -102.8 | -16.0 |
| NEAR | +33.0 | -49.0 | -16.0 |

Sum = -16bp = -2×fee (round-trip 8bp × 2 sides). Bar-direction filter provides ZERO directional information beyond a coin-flip on the trigger day.

**8th confirmed Lesson #39 sub-class A dogfood, 7th confirmed Lesson #37 dogfood.**

### Root-cause finding

Mid-cap universe fix (paradigm 228 lesson prescription) SUCCEEDED at removing mega-cap normalization noise — density is healthy 4.5-6.7% per sym (vs paradigm 228 where ETH mean share 71% dominated denominator). But paradigm 229 reveals a DEEPER issue:

**pct_rank normalization DESTROYS the partial-info fragment that existed in paradigm 228 raw z-space.** Paradigm 228 z=2.0 h=2 B_focus showed 3/7 syms (HBAR/AVAX/NEAR) with real (fee-limited) short-side edge. Paradigm 229 pct_rank version loses that fragment because percentile rank compression discards the raw magnitude of the underlying share-composition shift. Rank normalization is strictly weaker for share-composition signals than raw z-score.

### NEW Lesson candidate

**`pct_rank_normalization_destroys_partial_info_signals`** — When considering pct_rank as a fix for z-score's structural threshold feasibility concern (Lesson #40), DO NOT substitute if the raw z version already shows Lesson #74 partial-info concentration. Percentile rank discards magnitude of the underlying shift. Prescription:

1. Prefer **log-ratio** transform (bounded but preserves magnitude ordering)
2. Or add **shift-magnitude filter** (e.g., only trigger if |share_change| > 0.5% absolute)
3. Or move to **cross-family combination** (pair share-signal with independent axis-synthesizing signal like funding direction)

### Compute cost

- 7 R-1 sweep runs × ~8s each = ~1min total wall-clock
- No backfill needed (existing microstructure OI cache + monthly klines cache reused)

### Artifacts

- Script: `backend/scripts/research/paradigm_229_oi_share_rank_pct_mid_cap_r1.py`
- Metrics (7 files): `backend/runs/research_track/paradigm_229_alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h/r1_*.json`
- Graveyard report: `backend/runs/research_track/graveyard__paradigm_229_alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h.md`
- INDEX.json entry `paradigm_229_alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h`

### Next paradigm (230) recommendation

The 228 → 229 sequence has now EXHAUSTED the naive substitution-transform variants of cross-sym OI-share composition. Family retirement candidate. Recommended next paths:

- **Option A (preferred)**: SWITCH FAMILY entirely — do NOT attempt another OI-share reformulation. Route to `binance_futures_maintenance_margin_tier_change_event_anchored_alt_directional_3d_bilateral` (§10 Option B) — event-anchored regulatory class, currently untested in Q3.
- **Option B (composition family last-attempt)**: `alt_cross_sym_oi_share_log_ratio_absolute_magnitude_conditional_directional_2d` — apply NEW lesson candidate prescription. Use log(share_t / share_{t-7}) + magnitude filter |Δshare| > 0.5% absolute. Deferred until Option A concludes (avoid family compounding failures).
- **Option C (non-substrate escape)**: any alternative non-OHLCV substrate not yet explored (BVOL term structure, funding+premium cross-lag, etc.) per Lesson #77 informational cycling.

### Meta-observation

Paradigms 228 + 229 are the 4th and 5th consecutive graveyards in the cross-sym-composition adjacent family. This exceeds the paradigm 178/199/200/201/202 5-consecutive-non-PASS threshold from agent SELF-RECOMMEND saturation guidance (paradigm 203 MEMORIAL precedent). The autonomous dispatcher should switch to user-provided hypothesis mode OR escalate family retirement per Lesson #56 family proxy rules. Do NOT dispatch a 3rd OI-share reformulation without external hypothesis input.

---

**END v2** — 본 runbook으로 새 세션은 Round 2 paradigm 발굴 (큐 Q3) + paradigm 230 dispatch 진행 가능. Family retirement flag set on `oi_share_composition` — recommend event-anchored or non-OHLCV escape for 230.

## 12. Paradigm 230 R-0 GRAVEYARD log — 2026-07-18 (autonomous SELF-RECOMMEND dispatch)

**Slug**: `binance_futures_mm_tier_change_event_alt_directional_3d`
**Proposed as**: paradigm 230 (NEXT_PARADIGM_RUNBOOK §11 Option A)
**Verdict**: `R0_HALT_COMPOUND_DNA_DUPLICATE_LESSON_56_OUTCOME_PROXY_LESSON_40_INFEASIBLE_LESSON_11_SAMPLE_INSUFFICIENT`
**Phase halted at**: R-0 (R-1 NOT dispatched)

### Halt cause summary (Lesson #69 5-item template):
1. Lesson #61 slug grep → PASS (new slug)
2. Lesson #56 outcome proxy → HARD FAIL — delisting/lifecycle family proxy (paradigm 87 R-2 FRAGILE, paradigm 191 R-0 HALT)
3. Lesson #62 DNA 5-dim → HARD FAIL — 4.5/5 overlap with delisting family (substrate=exchange-announcement, statistic=announce_ts-event, universe=USDS-M perps, mechanism=forced-exit analogue)
4. Lesson #28 substrate → PASS (1079 rows scraped from 112 batch announcements)
5. Lesson #11 sample density → HARD FAIL — batch clustering (avg 9.6 syms/announce_ts) → 112 independent obs → per-cell 6.2 ≪ 30
   + Lesson #40 direction feasibility → HARD FAIL — MM cut events 0/1079 (0%); only HIKE direction observed → 4-quadrant SNT structurally infeasible

### NEW lesson candidate (batch-clustering IID):
For announcement-event substrates: Lesson #11 prescreen must use `count(unique announce_ts)` NOT `count(symbol × event)`. First dogfood in paradigm 230 — confirmed eligible at 5th instance.

### Artifacts:
- Graveyard: `backend/runs/research_track/graveyard__binance_futures_mm_tier_change_event_alt_directional_3d.md`
- Events CSV: `backend/runs/research_track/binance_futures_mm_tier_change_event_alt_directional_3d/mm_tier_events.csv` (1079 rows, reusable)
- INDEX.json: paradigm_230 entry added

### Next paradigm (231) direction:
- **Option A (preferred)**: Non-OHLCV substrate that is bilateral by nature — NOT exchange policy (PERMANENT_GRAVEYARD for MM/risk-limit changes). Candidates: Binance Launchpool announcement → BNB demand (entry-side, bilateral possible via farming-start/farming-end triggers), or DEX liquidity pool creation event (if public event log available).
- **Option B**: Return to microstructure but with fresh aggregation — e.g., Binance aggTrades archive (not raw taker_buy_vol which is retired) with minute-level block-trade detection (>$100k single trade → informed-flow signal). Lesson #21 caution advisory applies.
- **BANNED for 231+**: Any further exchange-policy/regulatory-event class (MM tier, max leverage, circuit breaker) — unilateral by nature, sample sparse, delisting family proxy.

---

## 13. Paradigm 231 R-1 GRAVEYARD log — 2026-07-19 (autonomous SELF-RECOMMEND dispatch)

**Slug**: `binance_launchpool_bnb_demand_event_anchored_bilateral_1d_to_7d`
**Proposed as**: paradigm 231 (NEXT_PARADIGM_RUNBOOK §12 Option A — Launchpool BNB demand event-anchored)
**Verdict**: `BROAD_FALSIFIED_LESSON_39_SUB_CLASS_A_FEE_SYMMETRIC_MIRROR_9TH_DOGFOOD_PLUS_NEW_LESSON_CANDIDATE_EVENT_WINDOW_BAR_LEVEL_IID_INFLATION_FIRST_DOGFOOD`
**Phase halted at**: R-1 (Lesson #37 full sweep completed 27 cells; R-2 NOT dispatched)

### R-0 Prescreen (all 7 items PASS)

1. Lesson #61 slug grep → PASS (no launchpool/bnb_demand precedent)
2. Lesson #28 substrate → PASS (BNBUSDT 1m joblib 2024-01-02..2026-05-12, 1.24M rows + 34 events compiled from training-data knowledge Jan 2024 - Jan 2025)
3. Lesson #11 sample density (paradigm 230 batch-clustering IID amendment applied) → PASS (34 unique events ≥ 30 threshold at event-IID unit)
4. Lesson #62 DNA 5-dim novelty → PASS (2-3/5 NOVEL: substrate+mechanism new; universe single-symbol adm; direction+statistic standard)
5. Lesson #56 outcome family proxy → PASS (Launchpool entry-side ≠ delisting/unlock/MM_tier exit-side family)
6. Lesson #40 structural threshold feasibility → PASS (bounded temporal-proximity mask, not z-score aggregate)
7. Lesson #77 non-OHLCV escape → applied (result confirms LIMITED — see §13.4)

### R-1 Full Sweep (Lesson #37 mandatory, 27 cells × 4 quadrants = 108 tests)

Sweep pre_window ∈ {(1,3), (2,5), (3,7)} × post_window ∈ {(0,3), (1,5), (1,7)} × hold ∈ {1d, 2d, 3d} × 4 quadrants.

**Aggregate: 0/108 cells three_gate_bar PASS AND 0/108 three_gate_event PASS**.

Best cell (A_focus pre1_3_h3): signal_t_excess=1.65 (<2.0), ci_lo_bar=+16.2bp, **ci_lo_event=-58.9bp** (decisively negative), perm_p=0.054, q_pos_t_ratio=0.75.

### 13.1 Lesson #39 sub-class A signature — 9th confirmed dogfood

A_focus + A_mirror perfect fee-symmetric mirror across ALL 27 cells (sum = -16bp = -2×fee exactly):

| Cell | A_focus | A_mirror | Sum |
|---|---|---|---|
| pre1_3_h3 | +134.4 | -150.4 | -16.0 |
| pre1_3_h2 | +91.6 | -107.6 | -16.0 |
| pre2_5_h3 | +111.6 | -127.6 | -16.0 |
| pre3_7_h1 | -5.2 | -10.8 | -16.0 |

Bar-direction filter provides ZERO directional information beyond a coin-flip on the trigger day. The "positive" A_focus edge is BNB's raw positive drift during 2024 Launchpool era (bull market), not accumulation-mechanism alpha.

**FIRST non-OHLCV substrate instance of Lesson #39 sub-class A**. The antipattern lives in the SECOND axis (bar_direction), not the substrate axis. Lesson #77 escape condition needs amendment.

### 13.2 NEW Lesson candidate — event_window_bar_level_bootstrap_ci_inflation

Dual bar-level vs event-level bootstrap revealed critical antipattern for event-anchored paradigms:

| Cell | ci_lower_bar (bar-IID) | ci_lower_event (event-IID) | Delta |
|---|---|---|---|
| pre1_3_h3 A_focus | +16.2 (positive) | -58.9 (negative) | 75bp |
| pre2_5_h3 A_focus | +7.0 (positive) | -48.3 (negative) | 55bp |

For event-anchored paradigms with multi-day windows (>1 bar per event), bar-level bootstrap treats correlated within-window bars as independent → systematically overstates significance. Event-level aggregation reveals true IID structure. **Dual bar+event bootstrap MANDATORY** going forward; event-level CI is authoritative IID gate. First dogfood at paradigm 231; awaiting 2nd for full confirmation.

### 13.3 B_focus (post-farm SHORT distribution) — decisively falsified

All 27 B_focus cells fail decisively: mean_bp -32 to -87, ci_lo_event -142 to -329, signal_t_excess -0.90 to +0.11. Quarter breakdown coin-flip 0.20-0.50. Post-farm unstake supply overhang hypothesis NOT supported. Launchpool participants tend to be BNB long-term holders; distribution flow is structurally small vs BNB total supply.

### 13.4 Lesson #77 escape hypothesis — first NEGATIVE dogfood

Non-OHLCV substrate (event calendar) does NOT protect against Lesson #39 fee-symmetric mirror when the joint trigger's SECOND axis is a bar-direction filter. **Corollary amendment**: for genuine Lesson #77 escape from OHLCV-derived antipatterns, BOTH trigger axes must be non-OHLCV (e.g., event calendar × event-magnitude like BNB_pool_allocation percentile).

### 13.5 Family retire flag SET

`exogenous_event_anchored × bar_direction joint trigger` = 4 confirmed graveyards:
- paradigm 87 delisting (R-2 FRAGILE)
- paradigm 88 token_unlock (Phase 1 FAIL_SCOPE)
- paradigm 230 MM_tier (R-0 HALT)
- paradigm 231 launchpool (R-1 BROAD_FALSIFIED)

BANNED for 232+: any new event_anchored paradigm using bar_direction as second axis.

### Compute cost

- 27 R-1 sweep runs × ~1.5s each = ~45s wall-clock
- Event calendar compiled from prior knowledge, no web scrape (~5 min)
- No backfill needed (BNBUSDT 1m joblib reused)
- Total: ~1 min

### Artifacts

- Script: `backend/scripts/research/paradigm_231_launchpool_bnb_r1.py`
- Event CSV: `backend/runs/research_track/paradigm_231_binance_launchpool_bnb_demand_event_anchored_bilateral_1d_to_7d/launchpool_events.csv` (34 events)
- Metrics (27 files): `backend/runs/research_track/paradigm_231_binance_launchpool_bnb_demand_event_anchored_bilateral_1d_to_7d/r1_pre*_post*_h*__metrics.json`
- Graveyard report: `backend/runs/research_track/graveyard__paradigm_231_binance_launchpool_bnb_demand_event_anchored_bilateral_1d_to_7d.md`
- INDEX.json: paradigm_231 entry (top-level, following paradigm 230 pattern)

### Next paradigm (232) direction

Paradigm 178/199/200/201/202/203/228/229/230/231 = 10 consecutive graveyards in SELF-RECOMMEND mode. Per paradigm 203 MEMORIAL precedent (5-consecutive threshold), **agent SHOULD escalate to user-provided hypothesis mode** for paradigm 232. Continuous-parallel + persistence-over-efficiency preserved.

If SELF-RECOMMEND continues:
- **Option A (preferred)**: Event-calendar × event-magnitude two-axis non-OHLCV. Candidate: `binance_launchpool_bnb_pool_size_percentile_event_anchored_directional_3d` — trigger only when BNB_pool_allocation is p90+ of trailing 90d events (magnitude proxy). Both axes non-OHLCV, genuine Lesson #77 escape test.
- **Option B**: Full event-anchored family retirement (5th consecutive event graveyard would prove retire flag correct).
- **Option C (deferred)**: DEX/CEX arb spread × funding_direction (both non-OHLCV, both fundamental).

**BANNED for 232+**: (1) any event × bar_direction joint trigger, (2) any exchange-policy event class continuation, (3) any pure single-symbol paradigm without §3-C 4σ+ pre-filter.

### Meta-observation

Paradigm 231 is the FIRST non-OHLCV substrate paradigm to hit Lesson #39 sub-class A (9th total dogfood). Also FIRST paradigm to demonstrate Lesson #77 escape condition needs bilateral non-OHLCV axes (not just substrate axis). Two informational contributions: (a) confirms bar_direction is the antipattern locus, not substrate; (b) new lesson candidate (event-window CI inflation) provides prescriptive test for any future event-anchored paradigm.

---

**END v3** — 본 runbook으로 새 세션은 paradigm 232 dispatch 진행 가능. Family retire flag SET on `event_anchored × bar_direction joint trigger` (4 confirmed graveyards). Agent should escalate to user-provided hypothesis mode per 10-consecutive SELF-RECOMMEND graveyard threshold.


---

## N. Paradigm 233 R-1 graveyard log — `alt_toptrader_position_lsr_velocity_z_bilateral_4h`

**Date**: 2026-07-22 (KST 12:58)
**Mode**: SELF-RECOMMEND autonomous (11th consecutive graveyard)
**Phase halted**: R-1 PoC
**Verdict**: `R1_FAIL_LESSON_39_SUB_CLASS_A_PERFECT_FEE_SYMMETRIC_ALL_27_CELLS`

### Hypothesis (differentiator from graveyard smart_money_lsr_contrarian)
- Column: `toptrader_position_ls_ratio` (POSITION-notional weighted) — NOT `toptrader_account_ls_ratio` (account-count) used in graveyard. Confirmed distinct: corr(SOL) = 0.189.
- Statistic: velocity (1st-derivative rolling z) — NOT level z used in graveyard.
- Direction: FOLLOW velocity sign — NOT contrarian level used in graveyard.

### R-0 prescreen: ALL 9 items PASS
Including item 8 Lesson #39 pre-check (direction axis = sign(vel_z), non-OHLCV, non-bar_direction).

### R-1 execution
- SOLUSDT single-symbol, Lesson #37 full sweep: 27 (vw ∈ {144,288,576} × ez ∈ {1.0,1.5,2.0} × hold ∈ {12,48,96}) × 4 quadrants = 108 sub-runs
- OOS: last 50% ≈ 2025-05 to 2026-07 (~440 days)
- Fee: 8bp round-trip; fixed-hold non-overlapping; no SL, no exit-signal (pure signal test)

### Results
- **0/54 focus cells** pass 3-gate (alpha>0 AND sharpe>0 AND mean_net_bp>0 AND n>=30)
- Best A_focus alpha=+0.37% sharpe=-0.69 (nominal crossing zero from fee drag, NOT real edge)
- Best B_focus alpha=+0.65% sharpe=-0.59 (same)
- **27/27 (vw,ez,hold) cells show A_sum = B_sum = EXACTLY -16.00bp = -2×fee**
- Lesson #39 sub-class A signature PERFECT and UNIVERSAL

### Root cause: vel_z of position LSR has zero predictive content
The direction axis was correctly non-OHLCV per Lesson #77 corollary. Yet Lesson #39 sub-class A still triggered perfectly. This proves the microstructure signal ITSELF lacks predictive content — position LSR is REACTIVE (mirrors price move as top-trader net-notional expands with price) rather than PREDICTIVE. Its velocity captures reaction speed, not intent.

### NEW LESSON CANDIDATE #79 (1st dogfood)
**Title**: `microstructure_direction_axis_necessary_but_not_sufficient_for_lesson_39_escape`
**Statement**: Non-OHLCV microstructure direction axis is necessary but NOT sufficient to escape Lesson #39 sub-class A. Lesson #39 sub-class A is fundamentally a **signal-quality diagnostic**, NOT merely a direction-axis-source antipattern.
**Prescription for R-0 amendments**: before R-1, measure `corr(signal, forward_return_at_target_hold)` on OOS half; halt if |corr| < 0.02.
**Dogfood roster**: paradigm 108, 110, 232, 233 (this).

### Next paradigm (234) direction

Paradigms 222/223/224/225/228/229/230/231/232/233 = 10 SELF-RECOMMEND graveyards this cycle (paradigm 226 F&G also graveyard = 11 total recent). Substrate saturation:
- Premium/basis/funding derivative velocity/level (§5 saturated)
- Position/account LSR level and velocity, contrarian and follow, both column variants
- OI composition (z, pct-rank, HHI, share-rank)
- Fear&Greed, launchpool events, cross-sym OI shift

**Per paradigm 203 MEMORIAL precedent (5-consecutive threshold + agent SELF-RECOMMEND saturation default fallback)**: Agent SELF-RECOMMEND mode has saturated on microstructure velocity/level family. **Recommendation for paradigm 234**: switch to user-provided hypothesis mode. 

If SELF-RECOMMEND continues (per persistence-over-efficiency), amend R-0 with mandatory **Lesson #79 predictive-content pretest**:
```python
# Before R-1 dispatch:
oos = df.iloc[int(len(df)*0.5):]
signal = <candidate_signal>
fwd_ret = oos['price'].pct_change(target_hold_bars).shift(-target_hold_bars)
c = signal.corr(fwd_ret)
if abs(c) < 0.02:
    return "R0_HALT_LESSON_79_ZERO_PREDICTIVE_CONTENT"
```

**Candidate substrates for paradigm 234 (if user provides)**: on-chain flow (Etherscan/Glassnode-free-tier bridge inflows), FRED macro release calendar × BTC funding, orderbook L2 depth imbalance (raw depth snapshots), cross-exchange funding spread residuals.

### Artifacts
- Code: `backend/scripts/research/paradigm_233_toptrader_position_lsr_velocity_z_r1.py`
- Metrics: `backend/runs/research_track/paradigm_233_alt_toptrader_position_lsr_velocity_z_bilateral_4h/r1__metrics.json`
- Graveyard: `backend/runs/research_track/graveyard__paradigm_233_alt_toptrader_position_lsr_velocity_z_bilateral_4h.md`
- INDEX.json: paradigm_233 entry (top-level, following paradigm 232 pattern)

### Meta-observation

Paradigm 233 is the **4th dogfood of Lesson #39 sub-class A** and the **1st dogfood of Lesson #79 candidate** (microstructure-axis insufficient without signal-quality). Combined with paradigm 232 (regime-axis) and paradigms 108/110 (bar_direction axis), the sub-class A antipattern is now confirmed across all major direction-axis types when signal lacks predictive content. This strongly promotes the "signal-quality pretest" (Lesson #79 candidate) as an R-0 mandatory item.


---

## N+1. Paradigm 234 R-0 graveyard log — `alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1`

**Date**: 2026-07-23 (KST 12:53)
**Mode**: user-provided via dispatcher brief (per paradigm 233 recommendation)
**Phase halted**: R-0 prescreen (before R-1 dispatch)
**Verdict**: `R0_HALT_LESSON_56_FAMILY_PROXY_FAIL + LESSON_55_PRESCRIPTION_OUT_OF_SCOPE + LESSON_57_FEE_FLOOR_SATURATION`

### Hypothesis (rejected at R-0)
5-minute TBS at rolling 288-bar (24h) extreme percentile p95+/p05-: exhaustion reversal (SHORT on extreme buy burst, LONG on extreme sell burst). Holds 12/48/96 bars (1h/4h/8h). Brief claimed differentiation from `_graveyard/taker_flow_zscore/` (paradigm 23) via percentile-vs-z, exhaustion-vs-momentum, and non-OHLCV axes.

### R-0 findings
1. **Lesson #56 family proxy FAIL** — Brief's differentiation claim factually incorrect. Paradigm 23 `_graveyard/taker_flow_zscore/GRAVEYARD_NOTE.md` explicitly tested BOTH `fade` (climax reversal = exhaustion) AND `follow` (momentum) modes. Fade at holds 12/24/48 bars = same family as proposed 12/48/96. Paradigm 23 R-2 10-sym collapse (3/10 alpha, 1/10 sharpe, alpha_mean −7.0) already refuted exhaustion-reversal direction at family level.
2. **Lesson #55 candidate PRESCRIPTION-OUT-OF-SCOPE** — Paradigm 143 already dogfooded the percentile-rank normalization prescription as INSUFFICIENT (vs paradigm 142 z-score). Both BROAD_FALSIFIED; percentile B_focus 12h regressed z-score B_focus 12h sigex from +3.43 → +1.01 (−2.4σ). Paradigm 234's central novelty claim repeats a formally-failed prescription.
3. **Lesson #79 pretest (mandatory per RUNBOOK line 690)** — SOL OOS (2025-04-05 to 2026-05-12, 115867 bars, 6144 p95 + 6121 p05 triggers): corr(signal, fwd) = 0.030 h1h / 0.023 h4h PASS / 0.008 h8h FAIL / 0.007 h24h FAIL. Primary target 4h-24h fails at upper horizon. Gross returns +1.7 to +3.3 bp per trade uniformly << 16 bp fee → net −12.7 to −14.8 bp at all holds. Direct reproduction of Lesson #57 taker-flow fee-floor signature.

### Lesson updates
- **Lesson #79 → 2nd dogfood** (paradigm 233 at R-1, paradigm 234 at R-0). Pretest correctly detects signal-quality issues at either stage. **Candidate → CONFIRMED-eligible**. R-0 mandatory item working as designed.
- **Lesson #57 (taker-flow fee-floor saturation) → 3rd formal family dogfood** (23 + 142 + 143 + 234). Formal family retire elevated to **TIER 4 CONFIRMED**. Future dispatch policy: TBS-family + hold ≥ 4h → R-0 HALT by default. Exceptions require novel-substrate joint or fast-frame (≤60m) design.
- **Lesson #56 positive functional dogfood** — R-0 caught misclassified brief before R-1 waste.
- **Lesson #61 positive functional dogfood** — Slug grep surfaced 3 direct-relevance graveyards.

### Next paradigm (235) direction
Substrate saturation across microstructure column families now spans: TBS/CVD/taker_buy_quote_vol (family retire), position/account LSR level+velocity (paradigm 233 dogfood), OI composition (paradigm 228/229/232), Funding/premium/basis derivative (§5 saturated), Fear&Greed (226), Launchpool events (retire).

**Option A (STRONGLY PREFERRED)**: `alt_book_depth_L2_bid_ask_imbalance_persistence_5m_directional_15m` — genuine substrate novelty. WS recorder book_depth accumulation targeted at 2026-07-15+ maturity (today 2026-07-23 → should be ≥8 days available). No prior R-1 on L2 depth. Signal design: rolling 288-bar bid_depth − ask_depth CUSUM z-score, 15m fast-frame hold (proven zone per paradigm 127/128). Fast frame + novel substrate maximizes escape from family retire zones.

**Option B (event-driven, distinct axis)**: `alt_binance_perp_daily_settlement_time_reversion_15m` — UTC 00:00 daily boundary (distinct from funding boundary paradigm 132-141), post-directional-pre-open mean reversion window. Zero substrate overlap with graveyard families.

**Option C (cross-exchange)**: `alt_bybit_binance_funding_spread_residual_carry_4h` — cross-exchange spread residual (partial bybit_funding cache available). Distinct from single-exchange funding paradigms.

**BANNED for 235+**:
- Any TBS / CVD / taker_buy_quote_vol column at hold ≥ 4h (Lesson #57 TIER 4 retire).
- Any position/account LSR velocity-z single-axis at 4h+ (paradigm 233 Lesson #79 1st dogfood).
- Any percentile-vs-z normalization swap on already-graveyarded axis (Lesson #55 candidate PRESCRIPTION-OUT-OF-SCOPE).

### Artifacts
- Graveyard doc: `backend/runs/research_track/graveyard__paradigm_234_alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1.md`
- R-0 prescreen JSON: `backend/runs/research_track/paradigm_234_alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1/r0_prescreen.json`
- INDEX.json: `paradigms.paradigm_234_alt_taker_flow_burst_extreme_quantile_reversal_5m_bilateral_h4_to_d1` entry
- No R-1 code, no metrics.json, no compute > 4 seconds. Zero backfill bytes.

### Meta-observation
Paradigm 234 is the FIRST paradigm to R-0 halt via Lesson #79 pretest at prescreen stage (paradigm 233 was 1st dogfood but at R-1 completion). This proves the RUNBOOK line 690 amendment protocol works as designed: signal-quality diagnostic at R-0 saves the full 108-cell sweep cost. Combined with Lesson #56 family-proxy catch of an incorrect brief claim and Lesson #57 TIER 4 confirmation, R-0 prescreen prevented ~15 minutes of R-1 compute for a paradigm mathematically guaranteed to graveyard. Lesson #79 CONFIRMED-eligibility promotes the pretest to universal R-0 mandatory item.


---

## N+2. Paradigm 237 R-0 graveyard log — `alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral`

**Date**: 2026-07-26
**Mode**: autonomous SELF-RECOMMEND dispatch (paradigm-architect)
**Phase halted**: R-0 prescreen (item 2 of 9 — Lesson #79 predictive-content pretest)
**Verdict**: `R0_HALT_LESSON_79_PREDICTIVE_CONTENT_FAIL_UNIVERSAL`

### Hypothesis (rejected at R-0)
Per-symbol 5m `taker_buy_sell_ratio` rolling z-score (N ∈ {48, 96, 288} bars) predicts 15m/30m directional continuation. Positive z (buying imbalance) → LONG follow, negative z → SHORT follow. Design used Lesson #57 fast-frame exception (hold ≤ 60m) to sidestep the TBS-family + hold≥4h TIER 4 retire.

### R-0 findings
1. **Lesson #61 slug grep** — PASS. No prior fast-frame TBS 15m slug in graveyards; closest neighbor is paradigm 234 (h4-d1 percentile exhaustion).
2. **Lesson #79 predictive-content pretest** — **FAIL, universal**. OOS correlation of `tbs_z` vs forward 15m/30m returns tested on 9 majors (SOL / BTC / ETH / BNB / DOGE / LINK / AVAX / LTC / XRP) × 3 windows (N=48/96/288 bars):
   - **Best |corr| = 0.0089** (BTC, N=48, 30m fwd). Threshold is 0.02.
   - **All 27 combinations negative sign** — the momentum-follow hypothesis is directionally falsified in the data (weak anti-momentum micro-drift, not continuation).
   - Even a FADE reformulation would yield |corr| ≈ 0.008, sub-fee-floor at 8bp round-trip (needs roughly |corr| ≥ 0.02 to overcome fees at 15m hold).
3. Items 3-9 (Lessons #62 DNA, #56 family proxy under fast-frame exception, #28 substrate audit, #11 sample density, #40 structural feasibility, #39 direction-axis pre-check, #57 fast-frame compliance) all PASS. The paradigm was structurally admissible but had no signal.

### Lesson updates
- **Lesson #79 → 3rd formal dogfood** (paradigm 233 R-1 1st, paradigm 234 R-0 2nd, paradigm 237 R-0 3rd). Elevated from CONFIRMED-eligible to **CONFIRMED-mandatory** R-0 item at position 2 for every signal-strategy paradigm. All three dogfoods correctly rejected paradigms that would otherwise consume R-1 compute.
- **Lesson #57 fast-frame exception dogfooded functionally** — the exception itself is valid (framework correctly admitted a 15m TBS design), but exception-admissibility does not imply signal-existence. Fast-frame TBS momentum is now empirically negative across 9 majors.
- **New candidate L83** (1st dogfood): `tbs_z_fast_frame_5m_to_15m_30m_anti_momentum_micro_drift_sub_fee_floor`. Prescription: future TBS-family fast-frame attempts should test FADE direction only, |z|≥3 extreme quantiles, hold ≤ 1 bar (5m). Awaits 2nd concordant dogfood to formalize.

### Sample-size stats
- Universe with both microstructure joblib and 1m OHLCV cache: **14 syms** (ADA/AVAX/BCH/BNB/BTC/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP).
- Distribution audit on SOL N=288: 254,299 valid bars; |z|>1.0 = 26.5%, |z|>1.5 = 9.1%, |z|>2.0 = 4.4% → sample density abundant; failure is signal-quality, not data-scarcity.
- Compute saved by R-0 halt: 72-cell R-1 sweep × 4 quadrants × 14 syms ≈ 4,032 sub-runs (est. 25-40 min compute + graveyard writeup).

### Recent halt chain (last 4 paradigms)
| Paradigm | Halt | Reason |
|---|---|---|
| 234 | R-0 | Lesson #56 TBS-family + Lesson #57 fee floor |
| 235 | R-0 | DNA duplicate (paradigm 134 semivariance) |
| 236 | R-3 | book_depth imbalance perm_sigma < 4σ (best 2.42σ LTC) |
| **237** | **R-0** | **Lesson #79 |corr|<0.02 universal across 9 majors** |

Three of last four R-0 halts. Prescreen doing exactly what it was designed for.

### Next paradigm (238) direction recommendations
Ordered by novelty and Lesson-#79-passability likelihood:

1. **`alt_global_account_ls_ratio_anomaly_directional_4h`** — untested microstructure column (`global_account_ls_ratio` in the same joblib, distinct from `toptrader_position_ls_ratio` used in paradigm 233). 4h hold avoids the Lesson #57 fast-frame narrow zone entirely. R-0 must Lesson #79 pretest at fwd_4h AND fwd_1d.
2. **`alt_oi_share_HHI_2nd_derivative_1h_bilateral`** — second derivative (acceleration) orthogonal to paradigm 232's level. Detects concentration-shifts rather than concentration-states.
3. **`alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h`** — macro-substrate (CoinGecko-free BTC dominance feed), completely orthogonal to microstructure exhaustion. Higher backfill cost — must check archive first.

**BANNED for 238+ (updated)**:
- All prior TIER 4 retires (§3-X).
- **NEW: TBS-family fast-frame momentum at 5m→15m/30m** (Lesson #79 3rd dogfood + L83 candidate). Only FADE + |z|≥3 + 5m single-bar hold if TBS fast-frame revisited.

### Artifacts
- R-0 prescreen JSON: `backend/runs/research_track/paradigm_237_alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral/r0_prescreen.json`
- Graveyard doc: `backend/runs/research_track/graveyard__paradigm_237_alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral.md`
- INDEX.json: `paradigm_237_alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral` (top-level, following paradigm 233 pattern; paradigm 236 also backfilled in same edit)
- No R-1 code, no metrics beyond pretest, ~30s compute, zero backfill bytes.

### Meta-observation
Paradigm 237 is the **3rd formal Lesson #79 dogfood** (233 R-1, 234 R-0, 237 R-0) and the **first purely quantitative universal rejection** — no structural/family-proxy issue, just empirical `|corr| < 0.02` across 9 majors × 3 windows × 2 holds. This is the clearest possible signal-quality falsification. Also the first instance where the Lesson #57 fast-frame exception was correctly invoked (design admissible) yet the signal itself was empirically null — cleanly separating the "family-ban admissibility" question from the "signal-existence" question. Future dispatch rule: **Lesson #79 pretest is item 2 of every R-0**, always run before family-proxy checks (item 4) since predictive content is a hard prerequisite regardless of family status.

---

## N+3. Paradigm 238 R-0 graveyard log — `paradigm_238_alt_global_account_ls_ratio_extreme_bilateral_follow_4h_1d`

**Date**: 2026-07-27
**Mode**: autonomous SELF-RECOMMEND dispatch (paradigm-architect)
**Phase halted**: R-0 prescreen (item 2 of 9 — Lesson #79 predictive-content pretest)
**Verdict**: `R0_HALT_LESSON_79_ZERO_PREDICTIVE_CONTENT`

### Hypothesis (rejected at R-0)
Binance Futures `global_account_ls_ratio` (ALL-accounts aggregate L/S ratio — distinct third microstructure LSR column vs paradigm 16 `toptrader_account_ls_ratio` and paradigm 233 `toptrader_position_ls_ratio`) rolling 30d z-score at |z| ≥ T predicts near-term directional (FOLLOW or CONTRARIAN bilateral 4-quadrant SNT) alpha at 4h and 1d hold. Direction axis = sign(z). Followed §N+2 runbook §"Next paradigm 238 direction recommendations" item 1.

### R-0 findings
1. **Lesson #61 slug grep** — PASS. Runbook line 804 explicitly proposed this exact candidate; no verbatim graveyard duplicate.
2. **Lesson #28 substrate audit** — PASS. 14/14 syms have the column, 155k-255k 5m bars each.
3. **Lesson #79 predictive-content pretest** — **FAIL**. OOS half (SOL + BTC) full-sample `corr(z, fwd_pct_change)`:
   - SOL h=4h: +0.00845 · SOL h=1d: +0.01188
   - BTC h=4h: −0.01527 · BTC h=1d: −0.01467
   - **max |corr| = 0.01527 < 0.02 rule threshold** across all 4 (sym × hold) cells.
   - Bonus: SOL and BTC correlations have *opposite signs* on both holds → no consistent mechanism direction to even attempt a full-sweep 4-quadrant.
4. **Supplementary non-overlap confirmation** (not part of Lesson #79 formal rule but documented for future audit): after enforcing entry cooldown = hold_bars, all `|z| ≥ T` cells produce non-overlap t < 1.5 with per-quarter sign flips (SOL thr=2.5 h=1d: 25Q4=+280bp → 26Q1=−45bp; BTC thr=2.0 h=1d: 25Q3=+86bp → 25Q4=−51bp). Naive overlapping-bar t-inflation (BTC thr=2.5 h=1d n=1334 t=11.36) collapses to n=9 non-overlap. This confirms the halt is not a false-positive over-rejection.
5. Items 4-9 (Lesson #62 DNA 3/5 novel vs paradigms 16 and 233; Lesson #56 soft warning noting LSR family precedent; Lesson #39 direction-axis clean self-signaling; Lesson #40 z-distribution feasibility; Lesson #11 naive-density abundant) all PASS. Paradigm was structurally admissible but had no signal.

### Lesson updates
- **Lesson #79 → 4th formal dogfood** (paradigm 233 R-1, 234 R-0, 237 R-0, **238 R-0**). Continues CONFIRMED-mandatory position-2 R-0 status.
- **NEW candidate L80-A (1st dogfood)**: "LSR-family universal Lesson #79 failure across substrate column variants." All three L/S ratio columns exposed by Binance microstructure (`toptrader_account_ls_ratio`, `toptrader_position_ls_ratio`, `global_account_ls_ratio`) have now failed via single-column rolling-z formulations. Family-level empirical prior: single-source LSR rolling z-score has near-zero linear predictive content for 4h-1d forward returns. Future LSR-family attempts should require either (a) joint multi-source divergence (e.g., runbook §629 divergence candidate), or (b) conditioning on external context (funding × LSR interaction, OI-change × LSR interaction). Prescription: **skip further single-column LSR level/velocity/percentile/change reformulations**. Awaits 2nd concordant dogfood to formalize.
- **NEW candidate L80-B (1st dogfood)**: "Naive overlapping-bar t-inflation for slow rolling-z signals." Rolling z-scores with long window (30d = 8640 5m bars) produce highly serially-correlated trigger streams; naive bar-level t-stats can inflate 5–10× vs non-overlapping-event t-stats. Concrete example this run: BTC |z|≥2.5 h=1d naive t=11.36 vs non-overlap n=9 (untestable), a ~150× effective-sample reduction. Prescription: any R-0 or R-1 sanity check on rolling-z triggers must apply either non-overlap event sampling (cooldown = hold_bars) or block-permutation with block size ≥ autocorrelation length. Awaits 2nd concordant dogfood.

### Sample-size stats
- Substrate coverage: 14/14 syms with 155k–255k 5m bars each (2 yr, since 2024-02-21).
- Pretest compute: <30s (2 syms × 2 holds × full OOS).
- Compute saved by R-0 halt: 24-cell R-1 sweep (3 thr × 2 hold × 4 quadrants) × 14 syms ≈ 1,344 sub-runs plus R-2 walk-forward + R-3 stratify (est. 20–35 min compute + graveyard writeup).
- Backfill bytes: 0 (used pre-existing joblib cache).

### Recent halt chain (last 4 paradigms)
| Paradigm | Halt | Reason |
|---|---|---|
| 235 | R-0 | DNA duplicate (paradigm 134 semivariance) |
| 236 | R-3 | book_depth imbalance perm_sigma < 4σ (best 2.42σ LTC) |
| 237 | R-0 | Lesson #79 \|corr\|<0.02 universal across 9 majors (TBS fast-frame) |
| **238** | **R-0** | **Lesson #79 \|corr\|<0.02 universal SOL+BTC × 4h+1d (LSR aggregate)** |

Four of last five R-0/R-3 halts, three consecutive Lesson #79 halts. Prescreen doing exactly what it was designed for; family-substrate rotation continues to expose empirical dead-ends.

### Next paradigm (239) direction recommendations
Ordered by novelty × Lesson-#79-passability × substrate-family diversification (Lesson #77):

1. **`alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h`** (was runbook §N+2 item 3) — macro substrate outside microstructure. Fetch daily BTC dominance from free feed (yfinance / CoinGecko free tier / manual archive). Complete family-family orthogonality vs the LSR/OI/TBS microstructure exhaustion series. High Lesson #79 pass odds because regime-shift signals typically produce corr(0.03-0.08) on multi-day horizons.
2. **`alt_binance_open_interest_daily_change_regime_conditional_bilateral_3d`** — OI-family attempt with a novel conditioning axis: entry only when funding-rate sign agrees with OI-change direction (joint-source instead of single-column). Sidesteps L80-A LSR-family shorthand prescription pattern by pivoting to OI × funding joint.
3. **`alt_multi_source_lsr_divergence_top_position_vs_global_account_percentile_bilateral_1d`** — direct implementation of runbook §629 joint-multi-source LSR divergence. Explicitly the family-escape path L80-A permits: uses `toptrader_position_ls_ratio` and `global_account_ls_ratio` percentile-gap rather than either column alone. Would test whether "positioning divergence between smart-money proxy and aggregate crowd" has independent predictive value.

**BANNED for 239+ (updated)**:
- All prior TIER 4 retires plus TBS-family fast-frame (§N+2).
- **NEW: any single-column LSR rolling-z level/velocity/percentile/change reformulation** on `toptrader_account_ls_ratio`, `toptrader_position_ls_ratio`, or `global_account_ls_ratio` (L80-A 1st dogfood prescription). Joint multi-source formulations (§629 divergence, or LSR × funding joint) explicitly permitted.

### Artifacts
- R-0 prescreen JSON: `backend/runs/research_track/paradigm_238_alt_global_account_ls_ratio_extreme_bilateral_follow_4h_1d/r0__prescreen_metrics.json`
- Graveyard doc: `backend/runs/research_track/graveyard__paradigm_238_alt_global_account_ls_ratio_extreme_bilateral_follow_4h_1d.md`
- INDEX.json: `paradigm_238_alt_global_account_ls_ratio_extreme_bilateral_follow_4h_1d` entry (135 total paradigms).
- No R-1 code, no downstream metrics, ~30s compute, zero backfill bytes.

### Meta-observation
Paradigm 238 is the 4th formal Lesson #79 dogfood and completes the single-column LSR-family exhaustion trilogy (paradigm 16 contrarian, paradigm 233 velocity, paradigm 238 aggregate-column). Together they establish a family-level empirical prior with three orthogonal column variants tested: single-source L/S positioning ratio z-scores do not predict 4h-1d returns in this asset class regardless of which subset of accounts is measured. This is a stronger claim than any individual paradigm could make. Structural implication: future LSR research must either (a) escape the family via joint multi-source formulation, or (b) redirect to entirely different families (macro/regime/cross-asset). L80-A codifies this. Also note that paradigm 238 continued the SELF-RECOMMEND agent behavior of picking the runbook-explicitly-suggested next candidate (§N+2 item 1) — an audit trail of paradigm-architect faithfully following its own prescription queue, not fabricating orthogonal proposals. Runbook § next-direction lists are being used as a stable dispatch backlog.


## N+4. Paradigm 239 R-1 GRAVEYARD log — `alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h`

**Date**: 2026-07-28
**Verdict**: `R1_GRAVEYARD_FEE_SYMMETRIC_BROAD_FALSIFIED` (Lesson #39 sub-A dogfood)
**Compute**: ~90 s (846-day daily-resampled OHLCV, 324-cell sweep + 4-cell fee-aware perm), zero backfill.

### Hypothesis
BTC dominance regime shifts predict alt rotation. Signal: 90d rolling z-score of
`(btc_7d_ret − alt_basket_7d_ret)` spread. Bilateral 4-quadrant SNT on 13 alts at 1-3d holds.

### R-0 all 9 items PASS (with warning)
Lesson #79 pretest: **max |corr| = 0.10113** (DOGE h=3, OOS half) — clears the 0.02
threshold cleanly. HOWEVER, all correlations were POSITIVE across (sym × hold), which is
**directionally opposite** to the hypothesis's rotation-reversal mechanism (positive corr
means "BTC outperforms → alts continue underperform NEXT" = short-term momentum
continuation, not rotation reversal). R-1's 4-quadrant SNT tested both directions.

### R-1 findings — SOLUSDT full sweep 324 cells (Lesson #37)
Grid: window {60,90,120} × spread {5,7,14} × T {1.0,1.5,2.0} × hold {1,2,3} × 4 quadrants.

- **72 / 324** cells pass weak concentration gate (mean_bp>0, t>0, sharpe>0, n≥30).
- **0 / 4 top cells pass fee-aware 3-gate** (top: signal_t_excess=1.49, perm_p_2s=0.194, ci_lower=-20.9bp).
- **Lesson #39 sub-class A confirmed**: for ALL 27 (w,sp,T,h) tuples, `A_focus_mean + A_mirror_mean = exactly -16.00 bp` (= -2 × FEE_RT floor). Direction axis `sign(dom_z)` carries zero directional information; joint signal is pure direction-bet dominated by fee drag.

### Root cause
Weak positive Lesson #79 corr (0.05-0.10 range) translates to obs_t ~1.0-1.3, which is
insufficient to clear the fee-drift null (null_mean_t ~ -0.1) by the required 2σ excess.
Cross-asset regime signals at 1-3d holds against 8bp round-trip fees require |corr| > ~0.15
to be viable.

### Next-direction (post-239)
Immediate next candidate MUST NOT be a cross-asset spread variant at 1-3d holds. If
extending: (a) push hold to ≥ 7d, (b) require Lesson #79 |corr| ≥ 0.15 pre-R-1, or
(c) pivot to structural non-fee-symmetric triggers (unlocks, listings, delistings).

### Lesson candidacy — proposed Lesson #79-follow-up (1st dogfood)
> *"Lesson #79 predictive-content pretest at corr ≥ 0.02 is NECESSARY but NOT SUFFICIENT
> for cross-asset regime paradigms at daily holds + 8bp fees. Cross-asset spread paradigms
> with corr ∈ [0.05, 0.15] on 1-3d holds will fee-symmetric BROAD_FALSIFY at R-1 because
> effect size falls below fee floor. Prescription: for cross-asset spread paradigms, either
> (a) extend hold to ≥ 7d, (b) require |corr| ≥ 0.15 on OOS half, or (c) use a fee-reduced
> execution (limit orders / longer holds with fewer trigger events)."*

Elevate to CONFIRMED-자격 upon 2nd dogfood.

### Recommended next paradigm (from BANNED-aware residual list)
Given the cross-asset macro family is now weakly-fee-bound at daily holds, and the
LSR single-column family is L80-A retired, viable next-candidates from prior sections:

1. **`alt_multi_source_lsr_divergence_top_position_vs_global_account_percentile_bilateral_1d`** — §N+3 item 3 residual; joint multi-source LSR divergence, explicitly permitted by L80-A escape clause.
2. **Extended-hold BTC dominance variant** (7d–14d hold, |z| ≥ 2.0, single-symbol per-alt regression) — the paradigm 239 mechanism at longer horizons where fee drag ratio drops proportionally.
3. **Non-fee-symmetric structural family**: exchange listings/delistings post-anchor, or unlock-cliff shorts (bn_listing / bn_delist / token_unlock families with existing infrastructure).

### Artifacts
- R-0 prescreen: `backend/runs/research_track/alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h/r0_prescreen__metrics.json`
- R-1 sweep: `backend/runs/research_track/alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h/r1__metrics.json`
- R-1 top-cell verify: `backend/runs/research_track/alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h/r1__top_cells_verify.json`
- Graveyard doc: `backend/runs/research_track/graveyard__alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h.md`
- INDEX.json: `paradigm_239_alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h` entry (total_paradigms=238).

### Meta-observation
Paradigm 239 is the 1st formal cross-asset macro-substrate dogfood at Lesson #39 sub-A. It
establishes that Lesson #79 corr-pretest ≥ 0.02 is insufficient at the 1-3d/8bp regime;
the required threshold for these paradigms is higher (≥ 0.15). This is complementary to
L80-A LSR-family exhaustion (paradigms 16/233/238 single-column LSR retire) and to the
§13.5 event × bar-direction family retire — together, the empirical priors on which axis
combinations survive fee-aware perm are becoming increasingly sharp. Notably, this paradigm
was ALSO SELF-RECOMMEND-consistent (agent chose the paradigm 239 candidate that had been
pre-queued as §N+3 item 1 — pre-recommended-by-runbook dispatch pattern continues).


## N+5. Paradigm 242 R-0 GRAVEYARD log — `alt_multi_source_lsr_divergence_top_position_vs_global_account_percentile_bilateral_1d`

### Hypothesis
`div = rolling_pct90(toptrader_position_ls_ratio) − rolling_pct90(global_account_ls_ratio)`
at |div|≥T ∈ {0.2, 0.3, 0.4} predicts 1d–4d directional alpha via information asymmetry
between smart-money (top-trader) and crowd (all-account) positioning. Standard 4-quadrant
SNT bilateral. Universe: 14-sym microstructure cohort (SOL primary). Substrate:
`backend/runs/microstructure/{SYM}_full_metrics.joblib` 5m frequency.

Dispatch brief argued novelty via L80-A escape clause ("joint multi-source formulation
explicitly permitted") and cited DNA table vs paradigms 16, 233, 238 (all ≤ 2/5 overlap).

### R-0 findings — COMPOUND HALT

**Item 1 — Lesson #61 slug grep: DIRECT HIT.**
`grep -rl "lsr_divergence\|top_global_lsr\|multi_source_lsr"` matched
`backend/runs/research_track/_graveyard/top_global_lsr_divergence/` — **paradigm 22
(2026-05-06)**, complete graveyard with 21 metrics files. Dispatch brief's DNA table
omitted this closest predecessor.

**Item 2 — Lesson #62 DNA 5/6 overlap vs paradigm 22: HARD FAIL.**

| Dim | paradigm 22 | paradigm 242 | Match |
|---|---|---|---|
| Data columns | top_pos_lsr + global_acc_lsr | Same | YES |
| Substrate | microstructure joblib 5m | Same | YES |
| Universe | 10-sym alt cohort | 14-sym superset | YES |
| Direction axis | Bilateral (follow/fade) | Bilateral 4-quadrant SNT | YES |
| Hold horizon | 12h/24h/48h | 1d/2d/4d | YES (overlap) |
| Statistic transform | z(top−global, 288-bar) | pct90(top)−pct90(global) | NO (only variation) |

5/6 = duplicate ceiling per paradigm-architect.md halt rule.

**Item 3 — Lesson #56 outcome-level family proxy: FAIL.** paradigm 22 R-2 result on the
identical 10-sym cohort (`ft_z2.5_h48` — best R-1 anchor):

| Symbol | Alpha% | Sharpe |
|---|---|---|
| AVAXUSDT | +86.7 | +0.84 |
| SOLUSDT | +30.6 | +0.11 |
| ETCUSDT | -0.8 | -1.35 |
| LINKUSDT | -12.1 | -1.13 |
| COMPUSDT | -17.1 | -1.89 |
| AXSUSDT | -27.2 | -1.68 |
| UNIUSDT | -27.7 | -1.25 |
| LDOUSDT | -32.6 | -1.18 |
| HBARUSDT | -36.9 | -2.51 |
| DOGEUSDT | -51.2 | -3.08 |

alpha_pos 2/10 (20%), alpha_mean -8.82, sharpe_pos 2/10. Prior graveyard-note explicit
conclusion: "LSR data is noisy; top vs global gap is NOT a systematic signal."
Percentile-of-each vs 288-bar-z of raw difference are monotone-equivalent
cross-stream normalizations → same outcome family.

**Item 4 — Lesson #80-A LSR-family universal L79 failure (paradigm 238 1st dogfood):
2nd dogfood.** Joint formulation combines two columns already proven L79-dead in
isolation (paradigms 16/233/238). L80-A's "escape clause" phrasing was a candidate note,
not an empirical exemption — under Lesson #56 the joint transform inherits family
retirement.

**Item 5 — Lesson #79 predictive-content pretest empirical (dispatch-brief mandatory
item 2):** mixed but insufficient.

Naïve overlapping-bar corr:
- SOL 1d: 0.0125 (FAIL 0.02 gate)
- SOL 4d: 0.0903 (nominal pass but autocorrelation-inflated per candidate L80-B)
- BTC 1d: 0.0347 (marginal)
- BTC 4d: 0.0183 (FAIL)

Non-overlap sampled corr (every 1152 bars = 4d):
- SOL 1d: n_iid=422 corr=+0.008 t=+0.16 (FAIL)
- SOL 4d: n_iid=106 corr=+0.127 t=+1.31 (nominal, IID t<2)

SOL non-overlap 4d 4-quadrant net edge at T=0.3:
- A_focus LONG: n=27 net=+60.4bp t=+0.52
- A_mirror SHORT: n=27 net=-92.4bp t=-0.79
- B_focus SHORT: n=27 net=+101.0bp t=+0.66
- B_mirror LONG: n=27 net=-133.0bp t=-0.88

All 4 quadrants signal_t_excess < 2. Per-cell n=27 fails Lesson #11 30-event floor;
further partitioning into 4 quarters yields ~1.7/cell — 18× below cutoff.

**Item 6 — Fee floor prescreen under Lesson #56 inference:** paradigm 22 R-1 anchor
(SOL ft_z2.5_h48) had *stronger* per-cell metrics (n=428 alpha=+30.6% sharpe=+0.11)
and yet R-2 collapsed to alpha_pos 2/10. paradigm 242's SOL 4d best cell is thinner
(n=27 t=+0.66) — expected R-2 outcome under Lesson #56 ≈ paradigm 22 R-2 catastrophe.

### Verdict
`R0_HALT_BY_COMPOUND_LESSON_61_56_62_80A_11_DNA_DUPLICATE_FAMILY_PROXY`. R-1 not
dispatched. Compute saved ~4-6 hr (504 sub-runs planned: 14 syms × 3 T × 3 hold × 4
quadrants) + R-2 multi-symbol expansion.

### Lessons dogfooded
- Lesson #61 slug grep — post-confirmation asset dogfood (~30th cumulative), direct
  substring hit
- Lesson #62 DNA 5-dim overlap — HARD FAIL 5/6 vs paradigm 22
- Lesson #56 outcome-level family proxy — 20th cumulative instance
- Lesson #79 predictive-content pretest — mixed empirical, superseded by #61+#56+#62
- Lesson #80-A LSR-family saturation — 2nd dogfood (paradigm 238 1st, paradigm 242 2nd);
  proposed candidate → CONFIRMED-eligible at next ratification batch
- Lesson #80-B naive overlap corr autocorrelation inflation — 2nd empirical confirmation
  (SOL 4d 0.09 overlap → 0.127 non-overlap t=1.31); CONFIRMED-eligible at next ratification
- Lesson #11 sample density — FAIL at meaningful T=0.3 (n=27 per-cell, ~1.7 per
  quarter-quadrant)
- Lesson #39 direction-axis pre-check — PASS (both axes non-OHLCV)
- Lesson #40 structural threshold feasibility — PASS (|div| spans ±1)
- Lesson #28 substrate audit — PASS (both cols present all 14 syms)

### New lesson candidate
**Lesson candidate #83 — "joint multi-source rescue of family-saturated substrate"**:
When two data columns each individually fail Lesson #79 (or belong to a family-retired
substrate under Lesson #80-A), their joint transforms (divergence, ratio, log-ratio,
percentile-difference) do NOT restore predictive content beyond the individual columns'
baseline. The joint transform preserves the underlying substrate's information ceiling.
**1st dogfood at paradigm 242**. Prescription: before proposing joint-multi-source
formulations, verify that at least ONE component column has a documented Lesson #79
PASS in isolation.

### Family status update
LSR-family substrate is now empirically exhausted across all tested formulations:
- Single-column level z (paradigm 238) → L79 FAIL
- Single-column velocity (paradigm 233) → graveyard
- Contrarian level (paradigm 16) → R-5 LIVE (grandfathered exception)
- Cross-stream difference z (paradigm 22) → R-2 collapse
- Cross-stream percentile difference (paradigm 242) → R-0 duplicate

**Recommend Tier 4 retire of LSR-family substrate at next Q3 ratification batch**
(paradigm 16 R-5 LIVE grandfathered exception only).

### Next-paradigm recommendations (ranked by novelty × Lesson #77 compliance)
1. **`alt_cross_exchange_funding_rate_dispersion_binance_okx_bybit_percentile_bilateral_4h`**
   — funding-rate dispersion across 3 CEX (Binance / OKX / Bybit via ccxt free tier);
   genuine cross-venue microstructure axis; no overlap with any tested paradigm;
   L80-A does not apply (funding rate ≠ LSR family). Substrate:
   `binance_funding_rate` + ccxt/OKX + ccxt/Bybit funding endpoints (free, rate-limited).
   PREFERRED.
2. **`alt_perp_index_price_deviation_from_spot_index_percentile_bilateral_4h`** —
   perp mark price vs spot index deviation z; untested family; distinct from LSR + funding.
3. **`alt_orderbook_liquidity_asymmetry_top10_depth_bid_ask_ratio_bilateral_1d`** —
   L2 book snapshot bid/ask depth ratio; requires book snapshot substrate audit
   (`binance_book_ticker_snapshot` table presence).

### Artifacts
- Graveyard doc: `backend/runs/research_track/graveyard__paradigm_242_alt_multi_source_lsr_divergence_top_position_vs_global_account_percentile_bilateral_1d.md`
- INDEX.json: `paradigm_242_alt_multi_source_lsr_divergence_top_position_vs_global_account_percentile_bilateral_1d` entry (total_paradigms=139)
- Prior paradigm 22 graveyard tree (referenced): `backend/runs/research_track/_graveyard/top_global_lsr_divergence/`

### Meta-observation
Paradigm 242 is the 2nd L80-A dogfood and 1st candidate #83 (joint-multi-source rescue)
dogfood. It closes out the LSR-family research question definitively: neither individual
column formulations (paradigms 16/233/238) nor joint-column transforms (paradigms 22/242)
survive Lesson #79 + Lesson #16 + Lesson #56 gates on the 10-14 sym cohort. This is the
5th consecutive LSR-adjacent paradigm to graveyard, and pattern P1 (family-exhaustion via
5+ empirical confirmations of substrate ceiling) formally triggers Tier 4 retirement
recommendation. The dispatcher's DNA-novelty argument via statistic-transform variation
was factually correct at the transform level but failed the higher-level Lesson #56
outcome-equivalence test — reinforcing paradigm-architect.md's mandate that DNA-overlap
check MUST include ALL predecessor paradigms with matching substrate + universe +
direction axes, not just the ones convenient to the novelty claim.

---

## Paradigm 248 — btc_onchain_active_address_regime_alt_bilateral_24h — GRAVEYARD (2026-08-08)

**Verdict**: `R1_GRAVEYARD_BROAD_FALSIFIED_LESSON39_SUBCLASS_A`

**Hypothesis**: BTC AdrActCnt (CoinMetrics FREE community API) 30d rolling percentile
rank → HIGH/LOW regime × BTC prior-day sign → alt continuation 24h bilateral. First
paradigm in track to use on-chain community-API substrate (Lesson #77 compliant).

**R-0**: PASS. AdrActCnt fetched 949 daily bars 2024-01 to 2026-08. Sample density
87.8 events/quadrant/quarter (3-alt pool). Fee headroom ×20-28.

**R-1 (bugfix v2)**:
- 96 cells swept (3 thresholds × 4 holds × 8 quadrants). 44 with n≥30 & mean>0.
- Only 2 of 15 top cells pass 3-gate; **neither passes Concentration Gate**.
- All A/B/C/D SNT pairs: focus+mirror = -16bp = -2×fee_RT (Lesson #39 sub-class A).
- Hypothesis-critical B_focus is NEGATIVE (-34.4bp) — contradicts continuation mechanism.

### NEW LESSON CANDIDATE #82 (documented, awaits 2nd dogfood confirmation)

**Timestamp-labelling look-ahead in `resample('1D').last()`.**

Daily bars from `resample('1D').last()` are labelled at midnight D 00:00 UTC but
contain the value of the LAST 1m close of that day (D 23:59 UTC). Therefore
`daily_close.pct_change()[D]` reflects the return from D-1 23:59 to D 23:59 — a return
ENDING at D 23:59 UTC. If the analysis assumes D 00:00 is the entry timestamp and treats
this return as "known at D 00:00", the trigger sign incorporates ~17 hours of future
price information — a subtle but catastrophic look-ahead.

**Symptom** (paradigm 248 v1 dogfood):
- Naive "yesterday's BTC sign → alt 24h continuation" baseline appeared to give
  +234 bp/trade with 79% winrate on 2,580 trades (t=32.5).
- Manual pandas cross-check gave -8 bp with 49.9% winrate (i.e., zero autocorrelation,
  as expected for a daily lag).

**Fix pattern**: for R-1 scripts requiring entry at a specific UTC instant, prefer:
```python
opens_at_midnight = df.loc[df.index.time == pd.Timestamp("00:00").time(), "open"]
opens_at_midnight.index = opens_at_midnight.index.normalize()
```
This explicitly selects the 1m OPEN at 00:00 UTC minute of each day — a price that
IS knowable at that timestamp — instead of the label-truncated daily bar.

**R-0 prescreen amendment (proposed)**: any script combining `resample('1D').last()`
+ `pct_change()` + "signal at entry time" must include an explicit timestamp-audit
assertion, e.g., compare the naive baseline result against a manual reference
computation to catch the artefact.

### Family advisory: on-chain BTC network metrics × alt returns

The two 3-gate-PASS-but-concentration-FAIL cells (A_focus, D_focus at 24h) are
consistent with fee-boundary drift, NOT with a live mechanism. Any future paradigm
proposing BTC on-chain metric (TxCnt, HashRate, MinerRev, ActiveAddresses, NVT, etc.)
× alt direction MUST:
1. Include Symmetric Negative Test 4-quadrant in R-1 (Lesson #19).
2. Enforce Concentration Gate at 3-gate threshold (per-symbol AND per-quarter).
3. Report unfiltered baseline diagnostic (same trade rule without the regime filter)
   alongside filtered results (Lesson #32 baseline-coherent drift check).
4. Use timestamp-explicit price selection (Lesson candidate #82).

Substrate is genuinely novel and API is FREE — the family door stays open — but the
R-0 checklist for this family is now stricter.

### Artifacts (paradigm 248)
- Graveyard doc: `backend/runs/research_track/graveyard__btc_onchain_active_address_regime_alt_bilateral_24h.md`
- R-0 script: `backend/scripts/research/paradigm248_btc_onchain_active_address_regime_alt_bilateral_24h_r0.py`
- R-1 script (bugfix v2): `backend/scripts/research/paradigm248_btc_onchain_active_address_regime_alt_bilateral_24h_r1.py`
- Baseline diagnostic script: `backend/scripts/research/paradigm248_baseline_diagnostic.py`
- Metrics: `backend/runs/research_track/btc_onchain_active_address_regime_alt_bilateral_24h/{r0_prescreen,r1__metrics,r1_baseline_diagnostic}.json`
- INDEX entry: `btc_onchain_active_address_regime_alt_bilateral_24h` (paradigm_number 248, current_phase graveyard, total_paradigms 144)
