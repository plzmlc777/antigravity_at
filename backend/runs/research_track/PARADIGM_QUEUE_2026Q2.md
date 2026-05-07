# Research Track Paradigm Queue — 2026-Q2 (Day 30 검증 대기 기간 활용)

> **목적**: 32 paradigm 후 saturation 도달, 시드된 11 sessions Day 30 검증(2026-06-03~05)까지 28일 동안 paradigm 발굴 지속.
> **제약**: 시간 비용 0인 paradigm만 (데이터 backfill 작업 불가능). 새 데이터 도메인 추가 불가.
> **목표**: 신규 paradigm 8-12개 추가 시도 → 추가 R-5 시드 1-2개 발굴 OR §3-G 패턴 추가 확인.

---

## 0. TL;DR — 우선순위 큐 (16 candidates)

| # | Paradigm | Category | §3 위험 | 예상 fail-fast | Day |
|---|---|---|---|---|---|
| 1 | `premium_volatility_regime` | new metric on premium | 낮음 (§3-G premium domain risk) | R-1 SOL alpha+sharpe<0 즉시 graveyard | 2026-05-07 |
| 2 | `cross_asset_premium_spread` (alt - BTC) | relative basis | 낮음 | R-1 SOL borderline | 2026-05-08 |
| 3 | `premium_oi_correlation_regime` | rolling corr regime | 중 (joint of seeded) | R-1 borderline | 2026-05-09 |
| 4 | `funding_oi_phase_lag` | cross-data leading-lagging | 중 | R-1 sweep 결정 | 2026-05-10 |
| 5 | `monthly_premium_seasonality` | calendar effect | **높음 §3-F** | R-2 alpha 6/10 미만 즉시 폐기 | 2026-05-11 |
| 6 | `cross_section_funding_rotation` | portfolio rotation | 중 | multi_symbol_portfolio graveyard 패턴 | 2026-05-12 |
| 7 | `premium_intraday_range_zscore` | new metric (premium high-low) | 낮음 | volume_absorption family check | 2026-05-13 |
| 8 | `funding_premium_spread_zscore` | joint signal | 높음 §3-G ensemble | 즉시 perm test | 2026-05-14 |
| 9 | `oi_change_acceleration_squeeze` | OI 2nd derivative | **매우 높음 §3-G** | R-1 음수면 graveyard | 2026-05-15 |
| 10 | `premium_velocity_zscore` (Δ premium) | premium 1st derivative | 높음 §3-G | R-1 결과 즉시 평가 | 2026-05-16 |
| 11 | `garman_klass_vol_premium` | OHLC vol estimator | 낮음 (premium volatility) | R-1 결과 | 2026-05-17 |
| 12 | `bid_ask_concentration_regime` | book_depth alt feature | 중 (book_depth borderline) | 6 syms only | 2026-05-18 |
| 13 | `premium_oi_joint_filter` (premium OR + OI confirmation) | confidence filter | 중 §3-G | Filter 효과 측정 | 2026-05-19 |
| 14 | `weekday_DoW_combined` (Tue+Wed+Thu+Fri pre-weekend cluster) | calendar v2 | **높음 §3-F** | R-1 결정 | 2026-05-20 |
| 15 | `multi_zwin_ensemble_premium` (15d + 30d + 60d z) | timeframe ensemble | 중 §3-G | perm test 즉시 | 2026-05-21 |
| 16 | `funding_oi_premium_3sigma_event` (3 동시 extreme) | rare-event composite | 높음 §3-A + §3-G | trade count 확인 | 2026-05-22 |

**Schedule**: 평균 1 candidate/day, 16-22 days. 2026-05-23 이후 reserve days for R-5 implementation if any candidate seeds.

**Fail-fast 정책**: R-1 SOL alpha 또는 sharpe 음수면 즉시 graveyard, 추가 sweep 금지. R-2 alpha 5/10 미만이면 R-3 SKIP.

---

## 1. Candidates 상세 (Phase R-1 시도 순서)

### #1 `premium_volatility_regime` (2026-05-07 시도)
- **데이터**: `runs/premium_index/{SYM}_premium.joblib` (high/low 컬럼) — 14종 800일
- **신호**: daily premium high-low range 30d z-score
- **가설**:
  - 가설 A: high vol regime → fade momentum (premium 변동성 큰 시기 mean-revert 강함)
  - 가설 B: low vol regime → follow trend (premium 안정 → directional 신호 신뢰도 ↑)
- **§3 위험**: premium domain saturated (premium_index_zscore 시드, premium_dispersion graveyard) → §3-G borderline. 그러나 vol-of-basis는 별도 차원 (level → volatility)
- **R-1 fail-fast**: SOL alpha+sharpe ≥ 0 → R-2; 음수면 graveyard

### #2 `cross_asset_premium_spread` (2026-05-08)
- **데이터**: 14종 + BTC premium 1d
- **신호**: (alt premium z) - (BTC premium z) → relative basis spread
- **가설**: alt vs BTC premium spread 극단값은 alt-specific over/under-positioning → mean-revert
- **§3 위험**: cross_symbol_correlation_regime graveyard와 다른 차원 (basis spread vs price corr) → 낮음
- **R-1 fail-fast**: SOL alpha+sharpe ≥ 0

### #3 `premium_oi_correlation_regime` (2026-05-09)
- **데이터**: premium 1d + OI 5m→1d aggregation
- **신호**: rolling 30d correlation(premium_z, OI_z) → high corr / low corr regime
- **가설**: high corr regime → 두 신호 confirmation, low corr → divergence opportunity
- **§3 위험**: 2 시드된 paradigm 데이터 결합 → §3-G ensemble 위험. but **correlation regime은 새 차원** (level이 아닌 dependence structure)
- **R-1 fail-fast**: 5종 quick test alpha pos 3/5 이상

### #4 `funding_oi_phase_lag` (2026-05-10)
- **데이터**: funding rate 8h + OI 5m → both daily
- **신호**: funding 변화가 OI 변화를 lead/lag하는 시기 → leader signal로 trade
- **가설**: OI 변화가 먼저 일어나면 funding이 따라옴 (smart money first); funding이 먼저면 retail driven (fade)
- **§3 위험**: 두 시드 paradigms 데이터 결합 §3-G but lead-lag은 새 dynamics
- **R-1 fail-fast**: phase 분포 분석 후 sweep 결정

### #5 `monthly_premium_seasonality` (2026-05-11) ⚠ §3-F 강함
- **데이터**: premium 1d 800일
- **신호**: 매 월말 N일 (28-31) premium z 검사 → fade or follow
- **가설**: Institutional rebalancing flows 월말 집중 → premium drift 후 월초 정상화
- **§3 위험**: time_of_day_seasonality graveyard와 동일 §3-F (calendar bias)
- **R-1 fail-fast**: 매우 sparse (12 events/year × 14 syms = 168 total samples), R-2 alpha 6/10 미만 즉시 graveyard

### #6 `cross_section_funding_rotation` (2026-05-12)
- **데이터**: 14종 funding rate 8h
- **신호**: 매주 funding rate 분포 측정 → top-K 음수 funding (long pays low) 매수, bottom-K 양수 funding (short pays high) 매도
- **가설**: funding rate 양극단의 portfolio rotation → market-neutral carry
- **§3 위험**: multi_symbol_portfolio graveyard와 family. but rule-based rotation은 ML 다른 차원
- **R-1 fail-fast**: top-K 1, 3, 5 sweep, alpha+sharpe ≥ 0

### #7 `premium_intraday_range_zscore` (2026-05-13)
- **데이터**: premium high-low 1d
- **신호**: range / median(range) 30d z-score
- **가설**: extreme range = positioning uncertainty → fade or follow regime
- **§3 위험**: volume_absorption graveyard와 family (range-based event)
- **R-1 fail-fast**: SOL alpha 음수면 즉시

### #8 `funding_premium_spread_zscore` (2026-05-14) ⚠ §3-G strong
- **데이터**: funding 8h + premium 1d
- **신호**: (funding_z - premium_z) at daily timestamp
- **가설**: funding과 premium 서로 vine관계, spread 극단값 → 둘 중 하나 mean-revert
- **§3 위험**: 두 시드 paradigm 결합 명확 §3-G
- **R-1 fail-fast**: 즉시 R-3 perm test on best, 3σ 미만이면 graveyard

### #9 `oi_change_acceleration_squeeze` (2026-05-15) ⚠ §3-G 매우 강함
- **데이터**: OI 5m → 1d aggregation
- **신호**: 2nd derivative of OI z-score (Δ²)
- **가설**: OI 변화 가속도 극단 = squeeze imminent
- **§3 위험**: oi_price_decoupling 시드의 derivative extension §3-G
- **R-1 fail-fast**: SOL 단독 sweep, 음수면 graveyard

### #10 `premium_velocity_zscore` (2026-05-16) ⚠ §3-G strong
- **데이터**: premium 1d
- **신호**: Δ premium 30d z-score (1st derivative)
- **가설**: premium 변화 속도 극단 → 추세 가속 또는 한계
- **§3 위험**: premium_index_zscore 1st derivative 명확 §3-G
- **R-1 fail-fast**: 즉시 평가

### #11 `garman_klass_vol_premium` (2026-05-17)
- **데이터**: premium OHLC 1d
- **신호**: Garman-Klass vol estimator (OHLC 사용 vol) z-score
- **가설**: vol regime 변화 → premium 신호 신뢰도 변화
- **§3 위험**: vol_regime_breakout graveyard와 family but premium-specific은 fresh
- **R-1 fail-fast**: SOL R-1 결과

### #12 `bid_ask_concentration_regime` (2026-05-18)
- **데이터**: book_depth 1d 6종 (top1_concentration_mean column)
- **신호**: top1 size concentration z-score → manipulation/retail tier 식별
- **가설**: high concentration = single-actor pressure (fade); low = distributed (follow)
- **§3 위험**: book_depth_imbalance graveyard와 family but different feature
- **R-1 fail-fast**: 6 syms only, R-2 alpha 4/6 미만 graveyard

### #13 `premium_oi_joint_filter` (2026-05-19)
- **데이터**: premium 1d + OI 5m
- **신호**: premium z fires AND OI z direction agrees → confirmation entry
- **가설**: 두 신호 동시 발화 시 conviction 상승 (joint_3signal_ensemble의 2-signal version)
- **§3 위험**: §3-G 명확 (component seeds 결합)
- **R-1 fail-fast**: joint_3signal_ensemble과 동일 패턴 → trade 빈도 낮음 우려

### #14 `weekday_DoW_combined` (2026-05-20)
- **데이터**: premium 1d
- **신호**: weekend_drift_premium graveyard에서 발견된 Thu/Fri/Sat cluster 신호 통합
- **가설**: pre-weekend cluster (Thu+Fri+Sat 3일 entry window)이 single-day Friday보다 강할 수 있음
- **§3 위험**: weekend_drift graveyard 본가설 검증 → §3-F + §3-G 합쳐짐
- **R-1 fail-fast**: weekend_drift R-2 alpha 10/10인데 perm σ 약 → 통합도 비슷할 듯, R-3 perm 즉시

### #15 `multi_zwin_ensemble_premium` (2026-05-21)
- **데이터**: premium 1d
- **신호**: 15d + 30d + 60d z-score 동시 같은 sign + 합 |sum|>5 → 멀티-timeframe confirmation
- **가설**: short/medium/long-term premium 신호 일치 시 high conviction
- **§3 위험**: premium_index_zscore의 timeframe ensemble §3-G
- **R-1 fail-fast**: 발화 빈도 낮을 듯, 즉시 측정

### #16 `funding_oi_premium_3sigma_event` (2026-05-22)
- **데이터**: 3 시드 paradigm 데이터
- **신호**: 3 paradigm 모두 ±3σ 극단 발화 시점만 entry (rare-event)
- **가설**: super-rare 3-way agreement = 매우 strong signal
- **§3 위험**: §3-A rare-event + §3-G ensemble 둘 다 강함
- **R-1 fail-fast**: trade count <10/year 면 즉시 graveyard

---

## 2. 일별 실행 가이드

### Daily 실행 protocol (15-20분/paradigm)
1. **R-1 SOL** (단일 종목 sweep, 5분): `python3 -m scripts.poc_<paradigm> --symbols SOLUSDT --tag r1_sol_sweep`
2. **alpha+sharpe ≥ 0 확인** → R-2 진행. 음수면 graveyard 즉시.
3. **R-2 multi-symbol** (10 종 또는 6 종, 5분): paper-pool 종목들
4. **alpha pos ≥ 6/10 + best symbol cutoff 3/5 이상** → R-3 진행
5. **R-3 perm n=200** (5분): top 4 candidates
6. **perm σ ≥ 4σ + cutoff 4/5+ → R-5 candidate**, σ 2-4σ → §3-G note + graveyard, σ <2 → graveyard

### 결정 트리
```
R-1 SOL alpha+sharpe ≥ 0?
├─ NO → graveyard 즉시 (1 paradigm/day)
└─ YES → R-2 multi-symbol
        ├─ alpha pos < 6/10 → graveyard (§3-E weak)
        └─ alpha pos ≥ 6/10 → R-3 perm
                ├─ best perm σ < 2σ → graveyard
                ├─ 2-4σ → §3-G note + graveyard
                └─ ≥ 4σ → R-5 candidate (사용자 승인 게이트)
```

### Day 30 검증 후 (2026-06-03+)
- 11 시드 sessions Day 30 결과 분석
- 성공한 paradigm은 추가 symbol 시드 (premium_index_zscore에 AVAX/UNI 추가 등)
- 실패한 paradigm은 demote 결정
- 새 paradigm 발굴 큐가 모두 소진되었으면 paper 풀 운영에 집중

---

## 3. 진행 추적 표

| Date | Paradigm # | Phase | Result | Decision |
|---|---|---|---|---|
| 2026-05-06 | #1 premium_volatility_regime | R-3 perm n=200 | R-1 SOL follow ez=2.5 alpha 105/sharpe 1.78 (12/12 SHORT). R-2 10종 follow ez=2.0 alpha 8/10 sharpe 6/10 mean +40.92. R-3 perm best **SOL 2.17σ borderline**, others <1σ. random_mean 31-40 → §3-D directional bias dominant + §3-G premium domain | **graveyard** (§3-G + §3-D) |
| 2026-05-06 | #2 cross_asset_premium_spread | R-3 perm n=200 | R-2 fade ez=1.5 매우 강함 alpha **9/10** sharpe **9/10** mean +125 (ETC 236/sharpe 3.08 4/5 cutoff). R-3 catastrophic: ETC 2.49σ borderline, LINK 1.46σ, AVAX/UNI **random_mean이 real 압도** (-0.59σ/-0.82σ) | **graveyard** (§3-D + §3-G strong) |
| 2026-05-06 | #3 premium_oi_correlation_regime | R-1 + R-2 quick 5종 | baseline (filter 없음) sharpe 2.155 ✅ premium_index_zscore 재현. high_corr_follow R-2 5종: sharpe **3/5** mean -0.012, 31 trades. low_corr_fade sharpe **0/5** mean -3.76. DOGE filter 12 trades vs baseline 17 trades — filter는 alpha source가 아닌 sparsifier. R-3 SKIP | **graveyard** (§3-G filter mechanism) |
| 2026-05-06 | #4 funding_oi_phase_lag | R-3 perm n=200 | R-1 SOL phase 73% positive, best `oi_leads_follow_oi` ez=1.0 pt=0.05 alpha 104.84/sharpe 3.134/PF 6.08 (5/5 cutoff). R-2 10종 alpha **9/10** sharpe **8/10** mean +49.59 매우 강함. R-3 best **SOL 1.60σ borderline**, others <0.8σ. random_mean이 real의 80% → OI direction 신호 자체가 alpha, phase filter marginal | **graveyard** (§3-G family + filter mechanism) |
| 2026-05-06 | #5 monthly_premium_seasonality | R-3 perm n=200 | fade_eom 가설 invalid. R-2 follow_eom nd=7 ez=0.5 alpha 9/10 sharpe 4/10 mean +36.77, SOL alpha 88/sharpe 1.37/PF 2.05. R-3 SOL **1.89σ borderline FAIL**/DOGE 0.74σ/UNI 0.71σ, random_mean 40 vs real 66-88 (50% noise) | **graveyard** (§3-F calendar + §3-G premium saturation) |
| 2026-05-06 | #6 cross_section_funding_rotation | R-3 perm n=200 (3 configs) | R-1 reverse mode 우월 (가설 INVERTED). best k=1 h=14 reverse alpha 168/sharpe 1.73/PF 7.87 12 rebalances. R-3: k=1 h=14 **3.01σ borderline** (큐 best), others 1.3-1.5σ | **graveyard** (§3-A small sample + §3-G family + 4σ 미달) — 2y+ funding 후 재시도 가치 |
| 2026-05-06 | #7 premium_intraday_range_zscore | R-3 perm n=200 | premium range/median ratio z, prior-return direction. fade invalid. follow R-2 alpha 10/10 sharpe 8/10 mean +55.26 SOL 4/5 cutoff. R-3 SOL **2.88σ borderline** (>#1 SOL 2.17σ), LDO 1.73σ, DOGE/UNI <1σ | **graveyard** (§3-G premium saturation + 4σ 미달) |
| 2026-05-06 | #8 funding_premium_spread_zscore | R-3 perm n=200 | spread_z = fund_z - prem_z. R-1 SOL fade ez=1.0 alpha 46/sharpe 0.59만 통과. R-2 alpha 7/10 sharpe 4/10 약함. R-3 SOL **3.10σ borderline** (큐 best 동급) but ETC **0.08σ = random** — single-symbol fit | **graveyard** (§3-G strong + §3-D ETC random) |
| 2026-05-06 | #9 oi_change_acceleration_squeeze | R-3 perm n=200 (7 syms) | OI 2nd derivative. R-2 alpha 9/10 sharpe 7/10. ETC 5/5 cutoff (alpha 161/sharpe 1.53). R-3 **ETC 3.98σ (큐 best, 4σ 1bp 미달)**, LINK 2.01σ, **5/7 random** | **graveyard** (ETC single-symbol fit + §3-G 2nd derivative weaker than 1st) |
| 2026-05-06 | #10 premium_velocity_zscore | **R-5 시드 완료** | premium 1차 derivative z. R-1 SOL alpha 184/sharpe 1.87. R-2 alpha 8/10 sharpe 6/10 mean **+121.60 (큐 최고)**. R-3 **AVAX 6.86σ / HBAR 5.25σ / SOL 4.88σ ALL PASS 4σ+** (3/10), UNI 3.54σ borderline | ✅ **R-5 SEEDED 옵션 A** (큐 첫 break-through). AVAX e4bff252-84a + HBAR 8d70b971-0ec. SOL 제외 §3-G family |
| 2026-05-06 | #11 garman_klass_vol_premium | R-3 perm n=200 (3 syms) | GK vol on premium OHLC + prior return direction. R-1 SOL alpha 190/sharpe 2.65 (5/5). R-2 alpha 10/10 sharpe 8/10 mean +71. SOL distinct from #10 (AVAX/HBAR 약함, SOL만 강함). R-3 **SOL 5.4σ PASS 단독**, UNI 3.51σ, LDO 1.31σ | **graveyard** (SOL single-symbol fit + §3-G premium saturation 5번째) |
| 2026-05-06 | #12 bid_ask_concentration_regime | R-3 perm n=200 (4 syms) | book_depth top1 conc z + prior return. R-1 SOL fade ez=2.0 alpha 47/sharpe 0.71. R-2 6종 alpha 6/6 sharpe 5/6 (BTC/ETH 5/5 cutoff but 6 trades only). R-3 ETH 1.94σ best, BTC 1.41σ, DOGE/SOL <1σ | **graveyard** (§3-A rare-event 결정적, 6-10 trades sparse) — 2y+ book_depth backfill 후 재시도 가치 |
| 2026-05-06 | #13 premium_oi_joint_filter | R-1 SOL only | premium z + OI direction agree filter. SOL: filter 없음(baseline) sharpe 1.35, 모든 OI filter 적용 sharpe ≤ 0 | **graveyard** (§3-G filter mechanism, R-2 SKIP) |
| 2026-05-06 | #14 weekday_DoW_combined ⭐ POSITIVE | R-3 perm n=200 (5 syms) | premium z + Thu/Fri/Sat 3-day cluster. R-2 alpha 10/10 sharpe 9/10 mean +143 (큐 최고). R-3 **4/5 PASS 4σ+**: DOGE 9.09σ / SOL 8.75σ / LDO 4.35σ / AVAX 4.33σ. UNI 2.02σ | **graveyard POSITIVE** (§3-G — 모든 4 PASS 종목 이미 시드됨, calendar 재라벨링 / Lesson: pre-weekend cluster premium 95% concentration) |
| 2026-05-06 | #15 multi_zwin_ensemble_premium | R-3 perm n=200 (3 syms) | premium 15/30/60d z 동시 sign + |sum|>5. R-1 SOL alpha 132/sharpe 2.07. R-2 alpha 9/10 sharpe 5/10 weak. R-3 SOL **4.03σ PASS 간신히** (premium_index 5.4σ 대비 약화), LDO 3.47σ, AVAX 2.72σ | **graveyard** (§3-G timeframe ensemble, single zwin이 우월) |
| 2026-05-06 | #16 funding_oi_premium_3sigma_event | R-1 only | 3-way ±σ 동시 발화. sigma 3.0/2.0/1.5 모두 0 trades, sigma 1.0 lenient도 9 trades total. funding 366d 한계 본질적 검증 불가 | **graveyard** (§3-A rare-event 결정적, R-2/R-3 SKIP) |
| 2026-05-23~06-02 | reserve | R-5 implementation if any seeds | — | — |
| 2026-06-03~05 | — | Day 30 검증 11+2 sessions | — | — |

---

## 🎯 큐 완료 요약 (2026-05-06)

**16/16 candidates 처리 완료** — 16일 일정 → 1일에 모두 fail-fast 결정 트리로 가속 진행.

### Outcomes
- ✅ **#10 premium_velocity_zscore → R-5 시드 (AVAX e4bff252-84a + HBAR 8d70b971-0ec)** — 큐 첫 break-through, 옵션 A 사용자 승인
- 🟡 **2 POSITIVE graveyards (§3-G but lessons valuable)**:
  - #14 weekday_DoW_combined: pre-weekend Thu/Fri/Sat이 premium 신호의 **95% 집중** 발견
  - #6 cross_section_funding_rotation: 가설 INVERTED (long high-funding 우월), 3.01σ borderline
- ❌ **13 graveyards** (대부분 §3-G family-extension 또는 §3-A rare-event):
  - **§3-G filter mechanism (4)**: #3, #4, #13 + #15 ensemble — filter는 component 정보 손실
  - **§3-G family extension (5)**: #1/#7/#11 premium-vol (3 paradigm 모두 weak), #5 calendar, #9 derivative weakening
  - **§3-D directional bias (2)**: #2, #8 single-symbol fit
  - **§3-A rare-event (2)**: #12 book_depth 365d, #16 funding 366d sample 부족

### Track 누적 통계 (2026-05-06)
- **48 paradigms 시도** (32 → 48), **7 시드 ⭐** (6 → 7), 40 graveyard, 1 데이터 누적
- 시드 비율: **14.6%** (큐는 1/16 = 6.25% — 예상 12-18%보다 낮음, saturation 확인)
- **#10 premium_velocity_zscore가 시드 가능했던 유일한 paradigm** — 기존 시드와 직교한 새 차원 (velocity vs level/decoupling/funding)

### Critical Lessons
1. **derivatives 위계**: 0차(level 9σ) > 1차(velocity 6.86σ) > 2차(acceleration 3.98σ outlier) — premium velocity가 1차 derivative 중 유일하게 robust
2. **premium 도메인 saturation**: vol(#1/#7/#11)/calendar(#5/#14)/spread(#2/#8)/ensemble(#15) 모두 weak residual
3. **filter mechanism antitpattern**: simple AND/correlation filter는 component보다 항상 약함, voting (joint_3signal_ensemble)만 marginal value
4. **funding/book_depth 데이터 한계**: 1y data는 cross-section/rare-event paradigm 검증 부족 (2y+ 후 재시도)

### Next Steps
- **2026-05-13**: Day 7 점검 (premium_velocity AVAX/HBAR + 기존 5 paradigm 시드 sessions)
- **2026-06-05**: Day 30 검증 (premium_velocity_zscore 2 sessions + premium_index 3 + oi_decoupling 1)
- **2026-07-03**: positioning_dynamics R-1 시작 (60d 누적 후)
- **추가 paradigm**: 데이터 누적 후 #6 funding_rotation 2y+, #12 book_depth 2y+, #16 funding_3sigma_event 2y+ 재시도 가치

---

## 4. 예상 결과 분포 (32 paradigms 통계 기반)

기존 통계: 32 시도 → 6 시드 (19%), 26 graveyard (81%).

다음 16개 시도 예상:
- **2-3 R-5 candidates** (12-18% 비율 가정) — 시간 비용 0 후보들은 saturation 상태라 actual 비율 더 낮을 수 있음
- **8-10 §3-G/§3-F graveyard** — 명확한 family-extension 패턴
- **3-5 R-1 fail-fast** — paradigm 자체 약함

**Realistic outcome**: 0-1 strong R-5 candidate (positioning_dynamics 같은 진짜 새 도메인 없으니 기대 낮음). 그러나 §3-G 패턴 추가 confirm + lessons 기록 가치.

---

## 5. 새 세션 시작 시 명령

```bash
# 1. 본 큐 문서 확인
Read backend/runs/research_track/PARADIGM_QUEUE_2026Q2.md

# 2. 가장 가까운 미완료 candidate 식별 (위 §3 표)
# 3. paradigm template 사용:
cp scripts/poc_premium_index_zscore.py scripts/poc_<new_name>.py
cp scripts/poc_premium_index_zscore_r3.py scripts/poc_<new_name>_r3.py
# 4. 가설/데이터/신호 부분만 수정 (simulate 함수 재사용)
# 5. R-1 → R-2 → R-3 빠른 진행
# 6. 결과를 §3 추적 표에 기록
# 7. graveyard or seed 결정
# 8. INDEX.md + runbook + 본 큐 문서 update
```

---

## 6. 큐 종료 후 다음 단계

본 큐 16개 모두 시도 후:
1. **2026-07-03 positioning_dynamics R-1** 대기 (60일 누적 후 새 도메인)
2. **Live confidence filter 통합** (joint_3signal_ensemble 코드 → paper session entry filter)
3. **시드된 11 sessions 추가 multi-symbol 확장** (Day 30 검증 후 성공 paradigm을 다른 symbol로)
4. **Portfolio-level paradigms** (여러 시드 paradigm signals 결합한 dynamic asset allocation)

---

**END** — 본 큐로 28일 동안 paradigm 발굴 활동 자율적으로 진행 가능. 매일 1-2 candidates 처리, 시간 비용 0 유지.
