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

### #1 `liquidation_cascade_event` ⭐⭐⭐ (최강 후보, ~~데이터 backfill 필요~~ → **substrate-blocked R-0 2026-05-19**)
- ~~**데이터**: Binance liquidation REST API (`/fapi/v1/forceOrders` archive 또는 `data.binance.vision/futures/um/daily/liquidationSnapshot/`)~~
- **substrate verification 결과 (2026-05-19 ad-hoc R-1 dispatch attempt, paradigm-architect agent `a24a663f7f0416aad`)**: **4 independent fail modes** — (1) `data.binance.vision/.../liquidationSnapshot/` 트리 부재 (HTML cache만, 실제 S3 prefix `<IsTruncated>false</IsTruncated>` empty), (2) `metrics/` csv 8칼럼 (OI + 4 L/S + taker buy/sell) liquidation 미포함, (3) REST `allForceOrders` 영구 폐기 ("out of maintenance"), `/fapi/v1/forceOrders` 계정 scoped, WS `!forceOrder@arr` live-only, (4) Mint forceOrder/liquidation recorder 사전 누적 0건
- **Verdict**: `DISPATCH_IMPOSSIBLE` — **Lesson #28 5번째 effective dogfood** (paradigm 89 listing_pre_announce + 90 stablecoin_mint sub-mode + 100 candidate dart_treasury_buyback #27 + 100 candidate liquidation_cascade #28 + implicit 84/85)
- **재시도 경로 (deferred to Day 30 후)**: (a) Mint PM2 `!forceOrder@arr` WS recorder service stand-up → 60-90d forward collection → 2026-07-15+ 재시도 가능, (b) paid feed (Coinglass/Hyblock/Laevitas) **차단** ([[feedback_no_freemium_trial]] 위반)
- **Tier 변경**: ⭐⭐⭐ 최강 후보 → **R-0 substrate-blocked, R-1 dispatch 불가** (2026-Q2/Q3 후보 아님). 산출물: `backend/runs/research_track/graveyard__binance_perp_liquidation_cascade_event_alt_intraday.md`
- **메타 함의**: Q3 큐 §1 top candidate 중 가장 강한 claim이 public 인프라에서 구조적 undispatchable

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
9. **Trigger swap antipattern** (71번째 graveyard 2026-05-15) — 시드 paradigm의 mechanism (filter + universe + hold)를 유지하고 trigger만 다른 도메인(가격→OI/funding/LSR)으로 교체할 때, 새 trigger의 정보 운반 차원 사전 검토 필수. precedent: paradigm 69 RV trigger +112.9bp UP×LONG vs paradigm 71 OI velocity trigger -12.62bp z=2.5 = mechanism 동일하지만 trigger 호환 부재. OI/funding/LSR 같은 microstructure-only trigger는 가격 기반 vol-cascade mechanism filter와 결합 시 alpha 부재 전제. mirror antipattern과 함께 자동 시도 금지.
10. **Taker-side aggressive volume family graveyard** (72번째 graveyard 2026-05-15) — implied/raw taker_buy_volume z-spike (5m trigger + 60m hold) 패밀리 전체가 fee floor 미달. graveyard 23 (taker_buy_sell_ratio raw) + 60 (LSR contrarian) + 72 (taker_buy_vol z signed) **3개 누적**. mechanism: buyer-imbalance overshoot가 60m forward에 mean-revert (anti-momentum) — z=1.5 signed -8.47bp **t=-21.10** 강력 부호 일관, BTC-up sign filter 부호 반전 무력. NET≈-8bp / gross≈0bp으로 **mirror SHORT도 fee saturation 본질로 비추**. 향후 taker/buyer-imbalance 변형 5m+60m hold 발의 보류. Longer hold (240m+) momentum continuation은 별개 검증 가치 있음.
11. **Sample-density prescreen rule** (73번째 graveyard 2026-05-15, funding_oi_bipolar_squeeze_event) — fee_floor_prescreen (16bp gross) 통과해도 universe × sample × trigger_rate 부족하면 strict threshold cells가 n<30으로 측정 불가. R-1 발의 전 `expected_n_per_cell = total_windows × universe_size × trigger_rate` 추정 후 30 미만이면 발의 보류 또는 sample 확장 (universe 확장 / DB 백필) 우선. precedent: paradigm 73 funding DB 1y 한계 + 6-sym intersection (funding ∩ microstructure ∩ ohlcv) → strict cells 모두 skip, lower threshold 완화 시 noise 압도 + perm test 미생존. 특히 **funding-기반 joint event paradigm은 funding DB 백필 우선**.
12. **Cross-asset correlation regime 자체는 directional signal 아님** (74번째 graveyard 2026-05-15, btc_eth_correlation_breakdown_5m_event_alt_directional) — BTC↔ETH 5m corr 1d-rolling z-score breakdown은 cross-asset stress regime을 정확히 표지 (p10=0.705 vs 평소 0.81)하나 unsigned single-direction (LONG)은 alpha 부재. paradigm 62 BTC RV contagion unsigned LONG와 동질 — regime detection ≠ directional bias. corr/vol regime trigger는 sign-conditional split (lesson #3) 필수, unsigned single-direction는 ex ante 폐기 권고.
13. **Aggregate-real-but-fragile graveyard pattern** (75번째 graveyard 2026-05-15, btc_eth_corr_breakdown_signcond_btcdn_altup_240m_long) — signal_t_excess 1.5~2σ + diversity gate PASS (7/12) + CI cross 0 (-0.001) + gross +19bp의 패턴은 alt-class universal mechanism 가설의 실패 (heterogeneity dominates). z=-2.0 focus aggregate +11bp는 4-alt 클러스터 (DOGE/SOL/NEAR/AVAX) + 8-alt 음수 분산의 우연한 합산. graveyard 확정하되 mirror/regime-stratify 변형 후보로 남김.
14. **Single-symbol H5 sub-cell evidence는 cross-symbol generalize 보장 X** (76번째 graveyard 2026-05-15, btc_eth_corr_breakdown_signcond_btcdn_altdn_240m_short) — paradigm 74 H5 SOL-only sub-cell SHORT |t|=1.60 > LONG |t|=1.42 사전 evidence가 12-alt aggregate에 generalize 안 됨 (SHORT +0.42bp/sigex +0.83 < LONG +11bp/sigex +1.78). 단일 종목 H5 evidence를 cross-symbol promotion 정당화로 사용 시 사전 cross-symbol mini-validation 의무화. 단 paradigm 70 13σ 격차 mirror antipattern은 약함 (76 격차는 0.95σ 수준).
15. **Non-focus PASS 격상 4-조건 정책** (77번째 R-1 PASS 2026-05-15, btc_eth_corr_severe_breakdown_signcond_btcdn_altdn_240m_short) — focus FAIL이지만 sweep 비-focus threshold에서 strict 4-gate PASS 시 separate paradigm 격상 정당 조건: (a) 모든 4 gate 통과 (3-gate + diversity), (b) separate R-1 replication ±10% 일치, (c) Bonferroni adj_p (prior 9 tests 보수적) ≤ 0.10, (d) hold sweep 부호 일치. 동시 충족 시 sampling fluke 가능성 낮음, R-2 진행 권고. 단 R-1 PASS는 충분조건이 아니며 R-2 robustness가 진짜 검증 (paradigm 77이 R-1 PASS 후 R-2 1/4 FAIL).
16. **Aggregate stat은 quarter/symbol 집중도 사전 검증 필수** (77번째 R-2 FAIL 2026-05-15) — R-1 단계에서 per-quarter t-stat distribution + per-alt ci_lower bootstrap 자동 포함 의무. Cherry-pick artifact 사전 차단. paradigm 77 aggregate +33.6bp/perm_p 0.005가 BNB+WIF 2종 + 4 quarter 우연한 합산 (10 alt 중 ci_lower>0인 alt = 2/10 / 2025Q3 t=-3.03 + 2025Q4 t=-1.73 반년 regime 단절). lesson #15 보완: non-focus PASS 격상 시 quarter homogeneity + per-alt ci_lower diagnostic 추가 검증 후에만 격상 자격.
17. **Geometric path metrics alone fee-floor 미달** (78번째 graveyard 2026-05-15 turn 3, `range_compression_directional_break_alt_30m_240m`) — 12h rolling 30m bars 의 path tortuosity (= Σ|H-L| / |net_move|) 의 30일 z-score top-decile compression + next-bar break-direction-following 240m hold 가설. focus aggregate net -14.37bp / sigex -0.44 / ci=[-25.5,-3.6]bp three-gate FAIL/FAIL/FAIL. UP-LONG -13.14bp + DOWN-SHORT -15.52bp **대칭 음수** (mirror antipattern 아닌 진성 dud). Concentration Gate dogfood 첫 적용: quarter_pos_t_ratio=0.20 / symbol_ci_pos_ratio=0.00 → 균질 음수 (cherry-pick X). Hold sweep monotonic worsening (480m sigex=-1.70 perm_p=0.058 anti-momentum 근접). **메시지**: skewness family (65-66) 와 동일하게, return distribution moments 외 geometric path metrics (tortuosity / fractality / Hurst exponent 등) 단독은 directional alpha 운반 X. paradigm-architect spec Lesson #16 Concentration Gate가 첫 dogfood에서 정상 작동 확인 (verdict CONCENTRATED_R1_PASS 가능성 사전 차단 — three-gate 자체 FAIL이라 concentration까지 도달 안 함). Tier 4 영구 제거: `geometric_path_metrics_family` (tortuosity / fractality / Hurst 등 alone).
18. **Sample-density boost는 mechanism 부재를 보상하지 않는다** (79번째 graveyard 2026-05-15 turn 3, `funding_oi_bipolar_squeeze_event_retry_2025_2026`) — paradigm 73 graveyard 사유(Lesson #11 sample-density)를 정확히 해결 (funding DB 1y→2.5yr backfill + universe 6→14 syms, 실측 boost A n=10→69 / B n=30→137 = 5.1x — prescreen 추정 5.8x microstructure 1.5yr binding 보정 후 일치). **그러나 mechanism 자체 falsified**: focus A SHORT mean +4.94bp sigex 0.52 perm_p 0.82 noise, B LONG mean **-53.04bp sigex -1.21 방향 반대** (12/14 syms 음수 / 7/9 quarters 음수 / textbook short-squeeze → LONG 직관 cross-symbol universal에서 실패). 36-cell sweep 어느 셀도 3-gate PASS 없음 (max sigex +1.80 A f=2.0 oi=1.0). **메시지**: Lesson #11 prescreen mechanic은 정상 작동하나 sample-density는 mechanism의 필요조건이지 충분조건이 아님. retry 결정 트리: (a) 기존 graveyard 사유가 *오직* sample-density뿐이고 mechanism aggregate stat이 marginal-positive였으면 retry 정당화, (b) mechanism이 noise-level 또는 directionally wrong이었으면 sample 확장해도 fail. Tier 4 영구 제거: `funding_oi_joint_squeeze_family` (paradigm 73 sample-bottleneck + 79 mechanism-falsified 2회 일관 fail).
19. **Symmetric Negative Test을 R-1 본체에 통합** (80번째 graveyard 2026-05-15 turn 4, `oi_premium_5m_decoupling`) — 5m OI z × 5m premium z joint event detector 4-quadrant (A focus + mirror A + B same-sign + mirror B) **모두 음수**, 14-sym × 1.48-yr panel n=5859 (paradigm-architect 통산 최대 sample), expected_n_per_cell 325 (Lesson #11 floor 30 대비 10배 초과, prescreen 통과). focus mean −8.11bp / sigex +3.83 / ci_lower −13.04 / perm_p 1.000 three-gate B+C FAIL. Concentration **broad-negative** 14/14 syms ci_neg + 1/9 quarters pos_t — broad-falsified mechanism case (Lesson #18의 sample-falsified 대비). **메시지**: (a) mechanism A focus 검증 후 mirror direction을 별도 R-1 dispatch로 시도하면 시간 낭비 — 한 batch에서 4-quadrant 측정하여 broad-falsified vs sample-issue 즉시 구분 가능. (b) signal_t_excess > 2.0이어도 observed 자체가 음수 (fee floor 미초과) 이면 3-gate B/C에서 자동 차단. (c) premium 5m × OI 5m joint z-score level의 4-quadrant 어느 cell도 directional alpha 부재 — 향후 동일 (signal × granularity × combination) 변형 시도는 duplicate fishing으로 간주, 새 feature transform (premium acceleration / OI dispersion / mark-index separate legs 등) 만 허용. **No family retire** — premium 단독 또는 OI 단독은 여전히 유효 가설 공간 (paradigm 21 oi_price_decoupling 1d seed 참조). paradigm-architect spec Step 3에 "Mandatory Symmetric Negative Test" 의무 격상 (mirror direction + alternative mechanism 4-quadrant 한 batch 측정).
20. **Sign-conditional 4-cell partial-PASS narrow-scope 자격 정책** (81번째 graveyard 2026-05-15 turn 5, `rolling_beta_regime_breakdown`) — 30d rolling β z-score × BTC 1d sign 4-cell. focus cell 1 (high-β-z × BTC up × LONG) mean −196.5bp 강하게 falsified, BUT **cell 4** (low-β-z × BTC down × LONG, "trade-the-decoupling") isolated three-gate ALL PASS (sigex +2.52 / ci_lower +3.19bp / perm_p 0.003) + hold sweep monotonic positive +44~+368bp. 그러나 **Concentration FAIL**: 3/13 alts ci_pos (AVAX/BCH/BNB만, LTCUSDT 정반대 −675bp) → symbol_ci_pos_ratio 0.23 < 0.30 floor. Bonferroni adj_p 0.003 × 60 sweep tests = 0.18 > 0.10. **Lesson #15 4-cond (a)+(c) FAIL → promotion 자격 없음, R-1 graveyard 확정**. paradigm 70 mirror antipattern 13σ vs paradigm 76 0.95σ 비교: 본 paradigm 1↔4 cell 격차 361bp = paradigm 70보다 약함, 76보다 강함. **메시지**: (a) Lesson #16 Concentration Gate가 cell 4 isolated PASS evidence를 cherry-pick으로 정확히 진단 (3/13 syms = symbol-concentrated). (b) narrow scope variant ("AVAX/BCH/BNB only low-β decoupling LONG 10d") 발의는 Lesson #14 single-sym H5 generalize 약함 + paradigm 77 R-2 quarterly FAIL precedent (lesson #13 fragile-real) 적용 → ROI 낮음. (c) sign-cond 4-cell 모두 broad-falsified가 아니더라도 **focus FAIL + 단일 cell partial-PASS + concentration FAIL** 패턴은 narrow scope 자격 자동 부여 아님. 4-cond (a)~(d) 모두 통과 시에만 narrow scope R-1 정당화. (d) β statistic vs ρ correlation 차이 명시 (paradigm 81 graveyard note 참조) — cross-asset corr family retired는 직접 적용 안 됨, 단 결과는 비슷한 fragile-real 패턴 노출. **No family retire** — rolling beta DNA는 narrow scope (3 syms cluster) 단독으로는 살아있을 수 있으나 cross-symbol universal mechanism에서는 falsified.
21. **Axis stacking does not synthesize alpha; 5m microstructure single-domain alpha 한계 신호 advisory** (83번째 graveyard 2026-05-15 turn 7, `oi_5m_latent_regime_per_symbol_alt_60m`, /new-paradigm-frontier 2번째 dispatch) — 13 alts × 5m OI multi-feature (level z / velocity z / acceleration z / 60m std z) × per-sym k-means k=4 unsupervised latent regime → cluster-conditional 60m forward return. **3/5 NOVEL ex ante** (statistic = unsupervised k-means / universe = per-symbol model fit / mechanism = latent regime-conditional, paradigm 82 동급 또는 더 강한 novelty 점수). 그러나 **4/4 cluster BROAD_FALSIFIED_FEE_FLOOR**: obs_t -27.07σ~-58.11σ 깊은 음수 (n cluster-bar OOS 220K~482K, 합산 1.31M labels), 모든 cluster CI fully negative [-8.19, -5.03]bp, 모든 cluster `q_pos_t_ratio=0.00` + `n_symbols_ci_pos=0/13`, 52 cells (13 syms × 4 clusters) 중 최대 |gross mean| **5.23bp (BCH cluster 3) ≪ 16bp fee floor**. fee_aware_perm_test는 n_obs > n_pool 2배 도달로 null_mean_t NaN early return (diagnostic 한계, CI 압도 negative로 결론 robust). **메시지**: (a) **Axis stacking does not synthesize alpha** — paradigm 82 (3/5 NOVEL ex ante divergence statistic + event-relative pre-window + pre-event flow timing) + paradigm 83 (3/5 NOVEL ex ante k-means + per-sym + latent regime) 두 frontier scout dispatch 모두 broad-falsified로 5-axis novelty matrix는 retired family 회피 정도의 안전망일 뿐, mechanism level alpha 발견 보장 아님 재확인 강화. (b) **5m microstructure single-domain alpha-extraction 광범위 limit signal**: paradigm 80 (5m OI z × premium z joint level broad-falsified) + paradigm 82 (5m premium velocity × OI direction at pre-funding event broad-falsified) + paradigm 83 (5m OI multi-feature latent k-means broad-falsified) — 3개 연속 paradigm 모두 5m microstructure single-domain (premium 또는 OI, joint or single, threshold or latent) → fee floor 미달 또는 broad-negative. (c) **Family-level retire는 prematurely** — 5m microstructure에 새 transform class (cross-exchange dispersion / 시간 lagged cross-feature / aggTrades event detection 등) 가능성 살아있음, 그러나 단순 z/velocity/divergence/latent-clustering 4가지 sub-class는 advisory caution 격상 (Tier 4 retire 직전 단계). (d) **fee_aware_perm_test n_pool 제약 한계 문서화**: n_obs > n_pool 도달 시 null_mean_t NaN early return, CI 자체로 결론 derive 의무. paradigm-architect spec 추가 hook 권고 (n_pool 사전 estimate + downsample 또는 strict pool 확장 분기). (e) **결정 권고**: Day 7 baseline (2026-05-21, 6일 남음) 우선 모드 진입, 추가 5m microstructure single-domain R-1 dispatch는 advisory caution 적용 (별도 사용자 명시 승인 시에만 진행).
22. **Stateful change-point detectors require frame-grade source frequency** (84번째 graveyard 2026-05-15 turn 9, `book_depth_concentration_cusum_breakout_alt_12h`, /new-paradigm-frontier 3번째 dispatch) — book_depth top1_concentration_mean × CUSUM Page-Hinkley structural change-point detector × 1h trigger + 12h hold 가설. **3/5 NOVEL ex ante** (data source = book_depth class, statistic = CUSUM Page-Hinkley Class A stateful change-point, mechanism = structural change detection). 그러나 **SAMPLE_INSUFFICIENT at Lesson #11 prescreen halt** (three-gate stat suite 미실행): book_depth joblib 인프라는 **daily aggregates only** (365 rows/sym × 14 syms), 가설의 1h frame + 12h forward return은 daily index에서 정의 불가. BTCUSDT 1년 daily top1_concentration_mean에 Page-Hinkley 직접 적용 시 trigger-rate 측정: lambda 5×std 25 breaks → 350 universe-est → 22 per-cell (cutoff 30 미달) / 10×std 16 / 20×std 6 / 50×std 3 → all 합리적 lambda에서 per-cell (4 quadrants × 4 quarters) ≥ 30 cutoff 불충족. **메시지**: (a) **Class A stateful statistics (CUSUM / Page-Hinkley / BOCPD / Bayesian online change-point) require source signal at frame-grade frequency (minute/hour-level)** — daily 또는 그 이상 aggregation은 per-day collapse가 이미 structural break를 평활화하여 detector가 발견할 "전환점"이 사전적으로 사라짐. statelessness가 paradigm class novelty의 본질이라면 statefulness compatible source frequency가 필수 전제조건. (b) **paradigm-architect spec failure protocols hook 권고**: "stateful statistic + non-frame source frequency = `SAMPLE_INSUFFICIENT` 자동 halt at prescreen". Lesson #11 sample-density prescreen에 source-frequency-vs-statistic-class 호환성 사전 점검 추가 (Class A stateful Y/N, source frequency 1m/5m/1h/1d/weekly 측정 후 호환 매트릭스 적용). (c) **book_depth_family (paradigm 12 + 23 + 61 + 84) 4번째 일관 fail** — daily aggregation 차원 영구 폐기 재확인. 새 인프라 (1h book_depth joblib backfill ETA 90d × 14 syms × 24h ≈ 30,240 hourly rows/sym) 없이는 family 전체 막혀 있음 입증. WS recorder 60+일 누적 (2026-07-15) 또는 별도 book_depth REST API 1h backfill 시 family 재시도 가능. (d) **/new-paradigm-frontier 3 consecutive dispatches 모두 halt/falsified** — paradigm 82 BROAD_FALSIFIED (lesson #19) + paradigm 83 BROAD_FALSIFIED_FEE_FLOOR (lesson #21) + paradigm 84 SAMPLE_INSUFFICIENT (lesson #22) = frontier scout 명령 메타 한계 명시적 입증 강화. 5-axis NOVEL ex ante 3/5 통과가 mechanism alpha 보장 아닐 뿐 아니라 **data infrastructure feasibility도 보장 안 됨** (data feasibility prescreen은 별개 차원). Day 7 baseline 2026-05-21 우선 모드 강력 재확인.
23. **Event-anchored low-frequency cycle × strict |z|>2 sample-density antipattern** (85번째 graveyard 2026-05-15 turn 10, `pre_session_open_oi_ramp_alt_4h`, /new-paradigm-frontier 4번째 dispatch) — daily 00:00 UTC session open cycle × (-60..-30min) window × 5m OI velocity z>+2 LONG / z<-2 SHORT × 4h hold (00:00~04:00 UTC) 가설. **3/5 NOVEL ex ante** (time scale = daily session cycle anchored, mechanism = pre-session positioning ramp event detection, statistic = event-anchored OI velocity transform). 그러나 **SAMPLE_INSUFFICIENT at Lesson #11 prescreen halt** (three-gate stat suite 미실행): 13 alts × 2.22yr × 365 daily anchors = 8158 total events, z>+2 LONG empirical rate **1.16%** (가정 5% 대비 4.3x lower), z<-2 SHORT 0.80%. total 95 + 65 = 160 triggers, 4 quadrants × 4 quarters split 후 A focus/mirror 23.8/cell, B same-sign/mirror 16.2/cell → all per-cell < 30 cutoff. **메시지**: (a) **Empirical trigger rate 5% 가정 ex ante overconfidence pattern**: per-symbol rolling-30d z-score on 5m OI velocity의 strict |z|>2 empirical rate는 1.0-1.5% 수준 (가정 5%의 1/3~1/5). 사전 추정 시 분포 stationarity 가정 + parametric tails 가정이 noise/microstructure에서 fails. (b) **Daily cycle anchor + always-on z-score 분포 mismatch**: daily 00:00 UTC anchor가 z-score reset 없는 always-on rolling z 적용 시 ~288x 데이터 압축 (1440min/5min frame), trigger sparsity 누적. paradigm 71 OI velocity (always-on 5m z) 회피 전략 (event-anchored mechanism + 4h hold)이 sample 차원에서 무력화됨. (c) **사전 검증 의무**: cycle frequency × universe × empirical |z|>2 rate (~1-1.5%) × n_quarters 계산하여 per-cell expected < 30이면 forward-return 계산 전 SAMPLE_INSUFFICIENT halt. 완화 옵션: (i) |z|>1.5 + Bonferroni adj (rate ~5%로 회복), (ii) universe 확장 (현 13 alts × 2.2yr 풀 한계, 신규 backfill 필요), (iii) 8h funding boundary 등 더 빈번한 cycle (anchor 3×; paradigm 82가 이미 시도, fee floor 모드로 실패). (d) **5m microstructure single-domain advisory caution family 4번째 누적 fail** (paradigm 80 broad-falsified + 82 broad-falsified-fee-floor + 83 broad-falsified-fee-floor + 85 sample-insufficient). Tier 4 formal retire 보류 (fail mode 갈라짐: 3 broad-falsified + 1 sample-insufficient, family-grade strict retire 조건 미충족) but **advisory caution 등급 상향**. (e) **/new-paradigm-frontier 4 consecutive dispatches 모두 halt/falsified** — frontier scout 명령 메타 한계 4번째 입증 강화. paradigm-architect spec failure protocols hook 권고: event-anchored cycle paradigm dispatch 시 empirical trigger rate prescreen (architect가 source data sample로 직접 측정 후 expected_n_per_cell 보고) 의무.
24. **Boundary-event statistic class is horizon-bound density in cryptocurrency 2-3yr horizons** (86번째 graveyard 2026-05-15 turn 11, `multi_day_vol_persistence_3d_alt_long_1d`, /new-paradigm-frontier 5번째 dispatch) — BTC 30d realized vol p80+ HIGH regime ≥3 consecutive days streak end + BTC sign-aligned 13 alts directional 1d hold 가설. **3/5 NOVEL ex ante** (statistic = persistence count sequence streak length, time scale = multi-day 3-day, mechanism = persistence-conditioned momentum cascade). 그러나 **SAMPLE_INSUFFICIENT pre-execution halt at Lesson #11+23 prescreen** (three-gate stat suite 미실행 + R-1 본체 진입 안 함): BTC 2.4yr daily series에서 30d realized vol HIGH regime streak length 분포 mean **12.5d / std 11.7 / max 31d** — vol regime phase는 한번 시작되면 매우 길게 지속, 2.4yr admits only **6개 streak boundaries** regardless of threshold/length tuning. 8 relaxation variants (p80/p75/p70/p60 × s≥3/s≥2) all q_measurable=0/9 quarters. Original p80_s3 A focus pool 26 < 30 floor. **메시지**: (a) **Boundary-event statistic class (streak/regime-transition/level-crossing/duration-summarized event boundary) 는 cryptocurrency 2-3yr horizon에서 measurement-density-bound**: single boundary가 multi-day persistence를 compress한 결과 2.4yr에서 N≈5-10 수준 본질적 sparse, threshold/length relaxation으로도 회복 불가. (b) **Spike/jump trigger (paradigm 69 RV spike instantaneous event n=767) vs persistence boundary (n=6 sparse) = 1-2 orders magnitude 차이**. statistic class에서 sample density는 trigger 본질에 종속, spike trigger는 horizon-bound density 회피. (c) **paradigm-architect spec failure protocols hook 권고**: frontier 5-axis NOVEL timescale axis "multi-day" 또는 statistic axis "boundary-event"인 경우 sample-density prescreen이 trigger 정의에 boundary statistic 포함 여부 사전 체크 의무. (d) **Boundary-event statistic class family advisory caution 후보**: 단일 instance (paradigm 86 only) 이나 향후 streak/duration/regime-transition paradigm 후보는 사전 prescreen 의무화 + 백테스트 horizon 5yr+ 필수 검토. (e) **/new-paradigm-frontier 5 consecutive dispatches 모두 halt/falsified** — frontier scout 명령 메타 한계 5번째 입증. 5-axis NOVEL ex ante 3/5 통과 prescreen 한계 **4차원**: lesson #21 mechanism alpha + lesson #22 data infrastructure feasibility + lesson #23 empirical trigger rate ex ante 추정 + lesson #24 boundary-event horizon density. 모두 독립 사전 prescreen 필요. Day 7 baseline 2026-05-21 (6일 남음) 우선 모드 강력 재확인.
28. **Entry-side external event paradigm은 measurement substrate (target instrument price history) 시간 차원 존재 prescreen 의무** (89번째 graveyard 2026-05-18, `listing_pre_announce_leak_long_alt`, life-changing campaign 2차 세션 third dispatch, **DISPATCH_IMPOSSIBLE Phase 0 fundamental verification halt** — R-1 dispatch 미실행) — Binance Futures USDS-M perp listing announcement T-48h → T+5min LONG pre-announce informed leak 가설. Phase 0 verification 결정적 진단: Binance Futures USDS-M perp는 **`onboardDate`부터만 거래 시작** → pre-announce window는 listed symbol의 measurement substrate (가격 history) 자체가 시간 차원에서 **부재**. Independent verification: BILLUSDT pre-onboard 2026-04-01 archive HTTP 404 (절대 부재) + post-onboard 2026-05-15 archive HTTP 200 (가용), 5/5 youngest listings 일관 확인. paradigm 87 delisting (pre-delist substrate 가용)과 dual하지만 **더 깊은 인프라 한계**. 정량: 388 listing events 2024-01~2026-05 (paradigm 87 delisting 57건의 6.8x), spot pre-existence random 30 = 7/30 = 23.3% → ~90 effective events, 2-quadrant × 5 quarters per-cell 22.5 < 30 cutoff (variant i SAMPLE_INSUFFICIENT 예측), 4-quadrant per-cell 4.5 절대 미달. 4 변형 evaluation 모두 폐기 (i spot pre-existence 동형 SAMPLE_INSUFFICIENT 자원 낭비 / ii cross-exchange universe 위반 / iii BTC macro proxy substrate 변경 = 별도 paradigm / iv post-only lifecycle 중복). **메시지**: (a) **Entry-side external event paradigm 발의 시 substrate availability prescreen 의무**: paradigm 발의 (1) entry/exit_window 정의 → (2) substrate (target instrument) 가용 시간 범위 verify → (3) entry/exit window ⊆ substrate availability window prescreen → (4) 부재 시 `DATA_INFRASTRUCTURE_IMPOSSIBLE` 자동 halt. lifecycle (post-onboard substrate 가용) vs paradigm 89 (pre-onboard substrate 부재) = Category A entry-side 안에서도 substrate availability 차원이 결정적. (b) **paradigm-architect spec failure protocols hook 권고**: 가설 spec parser에 entry/exit window 자동 추출 + substrate availability cross-check (Binance Futures perp = onboardDate~deliveryDate, spot = listing date 등) 사전 prescreen 의무 추가. (c) **Category A sub-mechanism asymmetry taxonomy 결정적 확장**: lesson #27 1st-dim (entry/exit) + lesson #28 (substrate availability) 차원 추가. lifecycle uniqueness = entry-side + post-event substrate 가용 + immediate market demand (lesson #27 amendment 후속 도출) + sample density 4-dim 모두 충족하는 **유일** mechanism class confirmed. (d) **재시도 차단 룰**: Binance Futures perp pre-onboard window paradigm은 substrate 본질 부재로 영구 차단. spot pre-existence subset (variant i, ~90 events) 또는 cross-exchange (variant ii) 시도는 동형 SAMPLE_INSUFFICIENT 또는 universe binding 위반 — 자원 낭비. (e) **life-changing campaign 2차 세션 third dispatch** = 90 dispatch와 동시 진행 (paradigm-architect agent 2 parallel background, Phase 0 4분 실측 효율). Phase 0 fundamental limitation report only — Mint commit 없음 (dispatch 미실행, paradigm_index graveyard 등록만).

27. **Category A external event injection은 entry-side vs exit-side 사전 분류 필수 prescreen** (88번째 graveyard 2026-05-18, `token_unlock_cliff_short_alt`, life-changing campaign 2차 세션 second dispatch, Phase 1 compilation FAIL_SCOPE prescreen halt — R-1 dispatch 미실행) — paradigm 87 (delisting forced-exit, R-2 FRAGILE_TEMPORAL_WF_FAIL) + paradigm 88 (token unlock cliff, exit-side dominant assessed at Phase 1 compilation) = **2 consecutive Category A exit-side graveyards 누적** family-level pattern 입증. token unlock manual compilation 결과 (general-purpose agent 25분 실측, [[feedback_no_freemium_trial]] 신규 룰 준수 — DropsTab Builders 3-month trial-to-paid 패턴 폐기, CryptoRank/Tokenomist public web scrape only): Universe 26 tokens × 206 events × 2.4yr × cliff filter ≥0.5%, broad scope에서도 per-cell <30 (lesson #11 FAIL) + n_measurable_quarters 2/7 < 4 (lesson #26 패치 FAIL). cliff_or_linear 분포 195 linear : 9 cliff (95:5) → cliff event 자체 sparse 본질 (linear는 always-on flow로 event-anchored 가설 정의 불가). 데이터 품질: cross-validation rate 0% (tokenomist URL archive만) + cryptorank isAuthProtected 일부 allocation 가려짐 50-75% 누락 가능. **메시지**: (a) **Category A 안에서도 entry-side (new demand entry from external trigger, lifecycle listing seed = 신규 buyers/demand creation) vs exit-side (existing holder cohort 유동성 status 전환 또는 forced exit, paradigm 87 delisting + paradigm 88 token unlock = 기존 cohort 거래 종료 또는 supply increase) 사전 분류는 결정적 prescreen**. entry-side = temporal robust 가능성 (lifecycle live mode 2026-05-29+ 검증 진행), exit-side = sample-density 통과해도 temporal fragility 예상 (priced-in efficient 본질). (b) **paradigm-architect spec failure protocols hook 권고**: Category A 가설 발의 시 mechanism이 (1) creates new buyers/demand entry vs (2) forces existing holders to transition/exit 사전 분류 의무, exit-side는 R-1 dispatch 전 사용자 명시 승인 + 추가 robustness prescreen (paradigm 87 + 88 동형 risk 명시) 의무. (c) **entry-side 잠재 후보 priority** (lifecycle 외 발의 가치 있음): CEX Listing pre-announce leak (announcement T-24h 가격 anomaly detection, lifecycle pre-stage) + Network Upgrade/Hard Fork pre-event (ETH Pectra / SOL Firedancer 등) + ETF Approval/AUM Inflow Cascade. **exit-side 잠재 후보 (자동 차단)**: delisting (paradigm 87 graveyard), token unlock (paradigm 88 graveyard), staking unlock continuous flow (1차 brainstorm C2 mechanism mismatch 폐기). (d) **life-changing campaign 1+2차 통산 결과 갱신**: new paradigm 발의 3건 (1차 0건 + 2차 2건 dispatch attempts: paradigm 87 + 88) / graveyards 2건 (87 R-2 FRAGILE + 88 Phase 1 FAIL_SCOPE) / lessons 추가 3건 (#25 + #26 + #27) / family retire 권고 1건 (OHLCV magnitude-confluence) + Category A sub-mechanism taxonomy 정식 등록 (entry-side vs exit-side 2회 입증 family-level pattern). external event injection 검증된 sub-mechanism은 여전히 lifecycle (listing entry-side) 단독. (e) **다음 priority**: entry-side 다른 후보 brainstorm 또는 lifecycle live mode 결과 (2026-05-29+) 대기 + paper Day 30 (2026-06-03+). 추가 exit-side 발의 자동 차단. (f) **lesson #26 + #27 prescreen 메커니즘 dogfood 성공**: paradigm 88 Phase 1 compilation 단계에서 lesson #26 패치 (n_measurable_quarters ≥ 4 cutoff) + lesson #27 (sub-mechanism asymmetry assessment) 모두 정확 작동하여 R-1 자원 사전 차단 — paradigm 87 graveyard 직후 도출된 두 lesson의 즉시 적용 효과 입증. Commit 251a5d0f compilation + (this commit) graveyard.

**Lesson #27 정밀화 amendment** (90번째 graveyard 2026-05-18, `stablecoin_mint_event_long_alt_24h`, life-changing campaign 2차 세션 fourth dispatch, **HALT R-1 미실행** 3 independent fail modes) — USDT/USDC large mint event (≥$100M) → 24-48h BTC/ETH/13 alts cascade LONG 가설. 표면적 entry-side claim이지만 Phase 1 사전 검토 결과 3 independent fail mode: (1) **SAMPLE_INSUFFICIENT** Ethereum-only (publicnode RPC verified, USDT 90일 sample 3 events $1B each, 연간 12-20 / 2.4yr 30-50 events × 4-quadrant × 4 quarters per-cell 1.9-3.1 catastrophic FAIL, cross-asset cascade = portfolio event n_effective = n_events not n_events × 15 syms), (2) **[[feedback_no_freemium_trial]] 위반** multi-chain expansion 차단 (Etherscan V2 chainid+signup verified "Missing chainid parameter" + Solana paid RPC + Tron historical paid scrape), (3) **lesson #27 sub-mechanism re-classification (CRITICAL)** — claimed entry-side이지만 first-principle 분해 시 paradigm 87 forced-exit 동형 fragility risk: (a) mint = issuance ≠ immediate market demand, (b) OTC settlement lag 수시간-수일 vs 5min entry timing mismatch, (c) priced-in HIGH (CT real-time tracking, $100M mint 즉시 알려짐), (d) forced-flow direction AMBIGUOUS (supply potential ≠ immediate buy). **NEW lesson #27 정밀화**: "entry-side" 1st-dimensional 분류만으로 부족 — **immediate market demand entry** (lifecycle listing 동형, 즉시 신규 거래자 cohort 발생) vs **delayed/indirect entry** (mint → OTC → CEX lag, supply potential ≠ demand 즉시성, priced-in efficient) sub-classification 추가 의무. 후자는 entry-side claim에도 불구하고 paradigm 87 forced-exit 동형 fragility risk. 추가 검증 기준: (i) event_ts → market_signal_ts lag < 5min, (ii) event 자체가 priced-in candidate가 아닌 surprise component 포함, (iii) forced-flow direction이 mechanism 1차 effect (supply potential 같은 2차 effect 아님). **paradigm-architect spec failure protocols hook 권고**: Category A entry-side 가설 발의 시 immediate vs delayed/indirect sub-classification 의무, delayed/indirect는 R-1 dispatch 사전 차단 또는 사용자 명시 승인 + 추가 robustness prescreen.

26. **Small-sample (n<100) R-1 PASS_R1_FULL은 walk-forward + 5-fold TS-CV 의무 + Concentration Gate per-quarter ratio blind spot 패치** (87번째 graveyard 2026-05-18, `binance_delisting_announce_short_alt`, life-changing campaign 2차 세션 첫 dispatch + 캠페인 1+2차 통산 첫 4-dim Frequency-First Gate 전면 통과 paradigm) — Binance Futures USDS-M perp delisting announcement → forced-exit liquidity drift SHORT 가설 (Category A external event injection, lifecycle_pump_decay analog forced-exit side). 데이터 인프라 즉시 가용: Binance announcements scrape 17초 (57 USDS-M perp delisting events 2024-11~2026-04) + data.binance.vision OHLCV 1m 백필 2분 (57/57 syms × 5-13d window). **R-1 결과 PASS_R1_FULL**: 3-gate fee_baseline 16bp sigex +2.23 / ci_lower +782bp / perm_p 0.062 + 3-gate fee_stress 50bp sigex +2.23 / ci_lower +765bp (fee-fragility 없음) + Concentration Gate quarter_pos_t_ratio 1.0 (3/3) + sign_ratio 71.9% (41/57 win) + top3_blowup 14.8% + 4-dim Frequency-First Gate ALL PASS (trades/yr 40.5 / edge 14.6% / util 36.7% / sharpe 6.49). **R-2 결과 FRAGILE_TEMPORAL_WF_FAIL graveyard**: walk-forward 70/30 IS sigex +2.09 PASS / OOS sigex +0.18 FAIL drift_ratio 0.47 < 0.50 cutoff + 5-fold TS-CV **1/5 fold PASS** (k=3 2025Q4 sigex +5.05 perm_p 0.000 단일 outlier, k=0/1/2/4 sigex -0.43~+0.95 모두 FAIL) + Symmetric Negative Test 4-quadrant 완성 (A focus 단독 PASS, A mirror -2.24 대칭 FAIL, B same-sign LONG -0.26 noise FAIL, B mirror SHORT +0.28 borderline fee saturation FAIL — SPLIT_PARADIGM/broad-falsified 아님). **메시지**: (a) **R-1 PASS_R1_FULL은 2025Q4 single-quarter cluster artifact**였음. R-1 Concentration Gate "per-quarter ratio 3/3 PASS"는 measurable quarters 3개뿐 (2024Q4=6 + 2025Q3=8 모두 n<10 cutoff 제외, denominator=3) 이라는 small-denominator blind spot. 단일 outlier quarter (2025Q4 n=18) dominance가 ratio 1.0 만들어냄. (b) **paradigm-architect spec Lesson #16 본질적 blind spot 발견 + 패치 권고**: (i) n_events < 100 paradigm은 R-1 PASS 후 즉시 walk-forward + 5-fold TS-CV 의무 등록 (R-2의 별도 step이 아닌 R-1 본체 통합), (ii) Concentration Gate 보강 — n_measurable_quarters ≥ 4 미달 시 quarter_pos_t_ratio 자동 GATE FAIL 처리, (iii) 5-fold TS-CV fold_pass_count ≥ 3/5 cutoff R-1/R-2 통합 의무. (c) **Category A external event injection sub-mechanism asymmetry hypothesis 등록 (가설)**: lifecycle_pump_decay (R-4 seeded, listing-side forced-entry, temporal robust 입증) vs paradigm 87 (delisting-side forced-exit, temporal fragile 입증) — **forced-entry liquidity > forced-exit liquidity** 시간 robustness 격차 가능성. 향후 Category A 발의 시 entry-side mechanism 우선. 검증은 lifecycle live mode 2026-05-29+ 결과 + 추가 Category A paradigm 누적으로. (d) **2026 alpha 감쇠 메커니즘 가설** (academic interest, R-1 변형 자원 낭비): market-learning (delisting algorithm front-run 증가) / informed-leak (announcement timing predictability 상승) / structural shift (Binance delisting cadence 변화) — 검증 불가능 (forward data 부재). (e) **재시도 차단 룰**: 동일 mechanism (Binance USDS-M perp delisting announcement SHORT) 변형은 별도 R-1 dispatch 자원 낭비. pre-announce leak hypothesis는 announce_ts unknown future 본질로 실거래 적용 불가 (backtest-only paradigm 폐기). (f) **life-changing campaign 2차 세션 결과**: 1+2차 통산 new paradigm 발의 2건 (1차 0건 + 2차 1건) / graveyards 1건 (paradigm 87) / lessons 추가 2건 (#25 + #26) / family retire 권고 1건 (OHLCV magnitude-confluence). external event injection 검증된 sub-mechanism은 여전히 lifecycle (listing-side) 단독. Mint commits `6d6f7050` (scrape) + `65e78ec2` (OHLCV backfill) + `925c5c04` (R-1 PASS) + `d29afd5b` (R-2 graveyard).

25. **4-dim frequency-first gate × intraday signal systematic incompatibility + OHLCV magnitude-confluence family Tier 4 retire 권고** (2026-05-18 life-changing paradigm 발굴 캠페인 1차 세션 보류 결정) — 새 paradigm graveyard 추가 없이 사전 평가 단계에서 13 candidates 모두 탈락 (5 archetype A-E + 4 brainstorm N1-N4 + 2 hidden state U1+U2 + 2 sub-evaluation). 결정적 reproducible evidence: U2 (Retail-vs-Smart LSR Divergence, `global_long_short_account` vs `top_long_short_position` 5m z-score divergence) 14 variants × 4 hypotheses 측정, **gross edge consistently +2~+3bp (statistical signal 존재 obs_t +1.0~+1.5)**, fee 16bp round-trip 차감 후 **net −12~−18bp 모두 음수**. mean |fwd_return_60m| baseline = 54bp → **+2% net edge cutoff (216bp gross)은 4x baseline = top p99 tail events만 통과 = sparse-trigger 자기모순**. **메시지**: (a) **lifecycle_pump_decay paradigm (median +21.6%/trade × 50+ listings/yr external event injection)이 4-dim frequency-first gate를 통과하는 유일 mechanism class**임이 14+11 universe × 5-15m frame × ≤60min hold 공간에서 입증. 14+11 universe + intraday signal + 4-dim gate 조합 = **systematically incompatible**. (b) **OHLCV magnitude-confluence × directional-follow family Tier 4 formal retire 권고**: paradigm 84 `range_compression_directional_break_alt_30m_240m` + `range_expansion` + `vol_regime_breakout` + `wick_reversal_volume` + `volume_absorption` 5+ 일관 fail (R-1 ALL FAIL 또는 perm test fail 또는 single-symbol noise). 동일 mechanism class의 5m frame 변경 또는 feature swap은 substantive 차이 없음 — paradigm-architect spec Step 3 prescreen에 자동 차단 룰 추가 검토. (c) **U1 (trading-signal skill, on-chain smart money signal)** universe 제약 위반 (Solana/BSC DEX, 본 캠페인 Binance perp universe와 분리) — cross-chain proxy 변형은 사변적 mechanism + historical feed 부재로 별도 R-1 의무. 본 세션 폐기. (d) **U2 (Retail-vs-Smart LSR)** 통계 신호 존재하나 fee floor 미만 — paradigm 23/60/72 fee-saturated family와 동일 mechanism (positioning intraday signal은 fee 8-16bp round-trip 대비 magnitude 불충분). (e) **본 lesson 위반 즉시 차단 룰 권고**: 새 paradigm spec dispatch 시 (i) frame ≤ 15m + hold ≤ 60min + perp universe 조합 시 mean |fwd_return_hold| baseline 측정 후 expected gross edge가 fee floor 16bp + cutoff (+200bp net = +216bp gross) 도달 mechanism 사전 explanation 의무, (ii) external event injection mechanism (listings / delistings / token unlocks / ETF flows / macroeconomic releases) 또는 lifecycle-class external trigger가 아니면 4-dim gate 통과 가능 magnitude prescreen FAIL 자동 처리. (f) **next productive 방향**: external event domain 확장 + lifecycle paradigm meta-learning (2026-05-29+ live mode 결과) + 4-dim gate 사용자 재검토 (alternative gate "edge≥+1% net OR (trades/yr≥100 AND edge≥+0.5% AND Sharpe≥3.0)" 등 의향 확인). (g) **universe reframe 적용**: 14+11 sym pool → Binance Futures USDS perp 전체 (~250 active). 본 reframe은 본 lesson 영향 안 받음 (universe 확장해도 intraday × 4-dim gate fundamental incompatibility 동일).

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
| (NEW) | `btc_eth_5m_corr_breakdown_family` (74-77) | 4 paradigms 동일 family DNA (BTC↔ETH 5m corr 1d-rolling z-score) — unsigned LONG/sign-cond LONG/sign-cond SHORT/severe SHORT 모두 R-1 또는 R-2 graveyard. taker_buy family와 동일 family-level retire. cross-asset corr regime trigger 변형 추가 시도 권장 안 됨 |
| (NEW 2026-05-15 turn3) | `geometric_path_metrics_family` (78 range tortuosity) | path geometric metrics (tortuosity / fractality / Hurst exponent / box-counting fractal dim 등) alone — return distribution moments family (skewness 65-66) 와 동일하게 fee-floor 미달. 78 paradigm UP-LONG/DOWN-SHORT 양 방향 대칭 음수로 mirror sub-paradigm 잠재력 X. lesson #17 |
| (NEW 2026-05-15 turn3) | `funding_oi_joint_squeeze_family` (73 + 79) | funding × OI joint squeeze event detection (paradigm 73 + paradigm 79 retry 2회 일관 fail). 73은 sample-density bottleneck, 79는 sample 5.1x 확장 후에도 mechanism falsified (B short-crowded LONG = -53bp 방향 반대, 12/14 syms 음수). textbook short-squeeze 직관 cross-symbol universal에서 작동 X. lesson #18 |
| (NEW 2026-05-15 turn7 **advisory caution**) | `5m_microstructure_single_domain_alpha_family` (80 + 82 + 83) | 5m microstructure (premium or OI, joint or single, threshold or latent) single-domain → directional alpha 광범위 한계 신호. paradigm 80 (5m OI z × premium z joint level broad-falsified) + paradigm 82 (5m premium velocity × OI direction at pre-funding event broad-falsified) + paradigm 83 (5m OI multi-feature per-sym k-means latent broad-falsified) 3개 연속. **Tier 4 formal retire 직전 advisory caution** — 새 transform class (cross-exchange dispersion / 시간 lagged cross-feature / aggTrades event detection 등) 가능성은 살아있으나 단순 z/velocity/divergence/latent-clustering 4가지 sub-class는 사용자 명시 승인 시에만 진행. lesson #21 |

### 6.5 Updated Schedule (2026-05-14 ~ 2026-06-13 Day 30 검증 전)

Day 30 검증까지 30일. 일일 1-2 candidate fail-fast:

| 우선순위 | candidate | 데이터 백필 필요? | ETA | 상태 |
|---|---|---|---|---|
| ~~1~~ | ~~A `btc_rv_HIGHVOL_down_alt_short_240m`~~ (mirror SHORT) | 없음 | R-1 5-10분 | **GRAVEYARD 2026-05-14** ❌ |
| ~~1~~ | ~~D `btc_oi_velocity_regime_alt_long_240m`~~ | 없음 (microstructure 보유) | R-1 0.56분 실측 | **GRAVEYARD 2026-05-15** ❌ (71번째, 0/3 z three-gate FAIL, trigger swap antipattern 입증) |
| ~~1~~ | ~~#1 `liquidation_cascade_event`~~ | **Binance archive 전체 제거 확인 2026-05-15** | — | **BLOCKED ❌** — listing 빈 상태 (issue #337 미해결). 대안: CoinGlass 유료 (사용자 승인) / WS 자체 기록 60일+ / skip |
| ~~1~~ | ~~#2 `taker_buy_volume_5m_zscore_signcond`~~ | 없음 (microstructure) | R-1 ~13분 실측 | **GRAVEYARD 2026-05-15** ❌ (72번째, z=1.5 signed -8.47bp t=-21.10, 0/3 z gates FAIL, taker-side family retire lesson #10) |
| ~~1~~ | ~~F1 `funding_oi_bipolar_squeeze_event`~~ | 없음 (funding DB 1y) | R-1 ~5분 실측 | **GRAVEYARD 2026-05-15** ❌ (73번째, sample density 부족, lesson #11 sample-density prescreen) |
| ~~1~~ | ~~B1 `btc_eth_correlation_breakdown_5m_event_alt_directional`~~ (74) | 없음 (OHLCV joblib) | R-1 ~7분 실측 | **GRAVEYARD 2026-05-15 turn 2** ❌ (74번째, unsigned LONG 0/3 z FAIL, lesson #12 cross-asset corr regime ≠ directional) |
| ~~1~~ | ~~B1.1 `btc_eth_corr_breakdown_signcond_btcdn_altup_240m_long`~~ (75) | 없음 | R-1 ~6분 실측 | **GRAVEYARD 2026-05-15 turn 2** ❌ (75번째, signal_excess +1.78 cutoff 0.22σ 미달, lesson #13 fragile-real heterogeneity) |
| ~~1~~ | ~~B1.2 `btc_eth_corr_breakdown_signcond_btcdn_altdn_240m_short`~~ (76) | 없음 | R-1 ~6분 실측 | **GRAVEYARD 2026-05-15 turn 2** ❌ (76번째, focus z=-2.0 FAIL, z=-2.5 non-focus PASS — 77로 격상, lesson #14 single-symbol H5 generalize 보장 X) |
| ~~1~~ | ~~B1.3 `btc_eth_corr_severe_breakdown_signcond_btcdn_altdn_240m_short`~~ (77) | 없음 | R-1 PASS + R-2 FAIL ~33s + 26s 실측 | **GRAVEYARD 2026-05-15 turn 2** ❌ (77번째, R-1 4-gate ALL PASS — sigex +3.69σ perm_p 0.005, R-2 1/4 robustness PASS — quarter 2025Q3 t=-3.03 / per-symbol bootstrap 2/10 ci_lower>0, lesson #15 non-focus PASS 정책 + lesson #16 quarter/symbol 집중도 검증) |
| ~~1~~ | ~~G1 `range_compression_directional_break_alt_30m_240m`~~ (78) | 없음 (OHLCV joblib 2.4yr) | R-1 ~6분 실측 | **GRAVEYARD 2026-05-15 turn 3** ❌ (78번째, path tortuosity 12h compression + break direction-following 240m, three-gate ALL FAIL, sign-split 대칭 음수, Concentration Gate dogfood 정상 작동, lesson #17 geometric path metrics family retire) |
| ~~1~~ | ~~F1' `funding_oi_bipolar_squeeze_event_retry_2025_2026`~~ (79) | **funding DB 백필 17초 실측** (14 syms × 911일 + WIFUSDT 847일, +33,950 rows) | R-1 ~5분 실측 | **GRAVEYARD 2026-05-15 turn 3** ❌ (79번째, sample 5.1x boost 후에도 mechanism falsified — A SHORT noise +4.94bp, B LONG -53.04bp 방향 반대, 12/14 syms 음수, lesson #18 sample boost ≠ mechanism 보상, funding × OI joint squeeze family retire) |
| ~~1~~ | ~~#4 `oi_premium_5m_decoupling`~~ (80) | **premium 5m 백필 98초 실측** (14 syms × 730일, 209,952 rows/sym, ~84MB, ETA 7-10분 vs 실측 1.6분) | R-1 ~5분 실측 (Symmetric Negative Test 4-quadrant 통합) | **GRAVEYARD 2026-05-15 turn 4** ❌ (80번째, broad-falsified, n=5859 paradigm-architect 통산 최대 sample but 14/14 syms ci_neg + 1/9 quarters pos_t + 4-quadrant 모두 음수, lesson #19 symmetric negative test R-1 본체 통합 의무) |
| ~~1~~ | ~~`rolling_beta_regime_breakdown`~~ (81) | OHLCV 1d (1m joblib resample) | R-1 ~6초 실측 (4-cell sign-conditional + Concentration + z/hold sweep) | **GRAVEYARD 2026-05-15 turn 5** ❌ (81번째, focus FAIL −196.5bp, cell 4 "trade-the-decoupling" isolated three-gate PASS sigex +2.52 ci_lower +3.19bp BUT Concentration FAIL 3/13 alts AVAX/BCH/BNB 만 + Bonferroni adj_p 0.18, narrow scope 자격 4-cond (a)+(c) 실패, lesson #20 sign-cond 4-cell partial-PASS narrow-scope 자격 정책. No family retire — narrow scope DNA 가능성은 살아있으나 cross-symbol universal mechanism에서 falsified) |
| ~~1~~ | ~~`pre_funding_window_divergence_5m_alt_240m`~~ (82) | 없음 (premium 5m 730d joblib + microstructure 5m OI + OHLCV 1m joblib 모두 보유) | R-1 ~8초 실측 (4-quadrant single batch, /new-paradigm-frontier 첫 dispatch, 3/5 axes NOVEL ex ante: divergence statistic + event-relative pre-window + pre-event flow timing mechanism) | **GRAVEYARD 2026-05-15 turn 6** ❌ (82번째, 4-quadrant Symmetric Negative Test broad-falsified, A focus pv↓oi↑ LONG mean -4.42bp sigex +1.06 ci_lower -11.03 perm_p 0.883 / B same-sign pv↑oi↓ SHORT -4.85bp sigex +0.74 ci_lower -12.28 perm_p 0.784 / mirrors 정확히 fee 8bp 더 낮음 = direction-bet 자체 noise. Concentration Gate 0/13 alts ci_pos in both quadrants (paradigm 81 cell 4 cherry-pick 3/13와 본질적으로 다른 완전 균질 음수 failure). gross median 84.78bp fee floor 통과 + n/cell 2,625-2,692 sample density 충분 — mechanism broad-falsified confirmed. lesson #19 정확 적용 — 1-batch로 결판, mirror dispatch 시간 낭비 회피. 5m premium × OI joint event 차원 paradigm 80 + 82 모두 broad-falsified로 family extension caution 신호 — single-domain premium/OI는 유효 paradigm 21 + premium_index seed 참조) |
| ~~1~~ | ~~`oi_5m_latent_regime_per_symbol_alt_60m`~~ (83) | 없음 (microstructure 5m × 1.5yr joblib 14 alts 보유) | R-1 555.2초 실측 (9.3분, foreground, /new-paradigm-frontier 2번째 dispatch, 3/5 axes NOVEL ex ante: unsupervised k-means statistic + per-symbol model universe + latent regime-conditional mechanism, paradigm 82 동급 또는 더 강한 novelty 점수) | **GRAVEYARD 2026-05-15 turn 7** ❌ (83번째, BROAD_FALSIFIED_FEE_FLOOR, 4/4 cluster obs_t -27.07σ~-58.11σ 깊은 음수, CI fully negative [-8.19, -5.03]bp, 모든 cluster q_pos_t_ratio=0.00 + n_symbols_ci_pos=0/13 균질 음수, 52 cells (13 syms × 4 clusters) 중 최대 \|gross mean\| 5.23bp (BCH c3) ≪ 16bp fee floor. fee_aware_perm_test null_mean_t NaN (n_obs > n_pool 2배 early return, diagnostic 한계 — CI로 결론 robust). lesson #21 (axis stacking does not synthesize alpha + 5m microstructure single-domain alpha 한계 advisory + n_pool 제약 한계 문서화). 5m microstructure single-domain (premium 또는 OI, joint or single, threshold or latent) paradigm 80+82+83 3개 연속 broad-falsified로 family-level advisory caution 격상 — formal retire 직전 단계 (다른 transform class 가능성 살아있음). Concentration Gate dogfood 3번째 정상 작동) |
| ~~(open)~~ | ~~새 mechanism candidate 발의~~ | — | — | **2026-05-15 turn 8 결정: Day 7 baseline 우선 모드 정식 진입 (사용자 옵션 0 채택)** — /new-paradigm-frontier 3번째 dogfood에서 사용자가 메타 경고 (53 graveyards / 5% PASS / 2회 연속 BROAD_FALSIFIED / lesson #21 axis stacking does not synthesize alpha) 수용하여 R-1 dispatch 보류. 3 candidates 분석 archive (Candidate A multi_day_vol_persistence_3d_alt_long_1d 3/5 NOVEL OHLCV-only / Candidate B book_depth_concentration_cusum_breakout_alt_12h 3/5 NOVEL 새 도메인 / Candidate C weekly_oi_imbalance_alt_3d_hold 3/5 NOVEL weekly granularity 미탐색). **frontier scout 명령 자체의 메타 한계 추가 입증**: 2 dispatch BROAD_FALSIFIED + 1 dispatch user-declined → strict novelty enforcement만으로는 5% PASS rate 메타 극복 못함. |
| ~~1~~ | ~~`book_depth_concentration_cusum_breakout_alt_12h`~~ (84) | 없음 (book_depth daily aggregates joblib 365d × 14 syms 보유) | R-1 ~1분 실측 (sample-density prescreen halt at Page-Hinkley trigger-rate measurement, /new-paradigm-frontier 3번째 dispatch turn 8 후속 — 사용자 옵션 0 채택 후 옵션 2 변경 결정. 3/5 axes NOVEL ex ante: book_depth domain class + CUSUM Page-Hinkley stateful change-point statistic + structural change Class A mechanism) | **GRAVEYARD 2026-05-15 turn 9** ❌ (84번째, **SAMPLE_INSUFFICIENT** at Lesson #11 prescreen halt 단계 — three-gate stat suite 미실행. **데이터 인프라 한계 발견**: book_depth joblib는 daily aggregates only (365 rows/sym × 14 syms), 가설의 1h frame + 12h forward return은 daily index에서 정의 불가. BTCUSDT 1년 daily top1_concentration_mean에 Page-Hinkley 직접 적용 시 trigger-rate 측정: lambda 5×std 25 breaks / 10×std 16 / 20×std 6 / 50×std 3 → all 합리적 lambda에서 per-cell (4 quadrants × 4 quarters) ≥ 30 cutoff 불충족 (best 22). **NEW lesson #22 후보 (정식 채택)**: Stateful change-point detectors (CUSUM/Page-Hinkley/BOCPD) require frame-grade source frequency — daily 또는 그 이상 aggregation은 per-day collapse가 이미 structural break를 평활화하여 detector가 발견할 전환점이 사전적으로 사라짐. Class A stateful statistic 발의 시 source data sampling frequency 호환성 dispatch 사전 점검 의무. paradigm-architect spec failure protocols hook 권고 (stateful statistic + non-frame source frequency = SAMPLE_INSUFFICIENT 자동 halt). book_depth_family (paradigm 12 + 23 + 61 + 84) 4번째 일관 fail — daily aggregation 차원 영구 폐기 재확인. 새 인프라 (1h book_depth joblib backfill ETA 90d × 14 syms × 24h ≈ 30,240 hourly rows/sym) 없이는 family 전체 막혀 있음 입증. /new-paradigm-frontier 3 consecutive dispatches 모두 halt/falsified — Day 7 baseline 2026-05-21 우선 모드 강력 재확인. Mint architect commit a30d1b56) |
| ~~1~~ | ~~`pre_session_open_oi_ramp_alt_4h`~~ (85) | 없음 (microstructure 5m OI 1.5yr × 13 alts joblib 보유) | R-1 ~3분 실측 (sample-density prescreen halt at empirical trigger-rate measurement, /new-paradigm-frontier 4번째 dispatch turn 10 — 사용자 옵션 D new brainstorm 채택, Day 7 baseline 우선 모드와 병행 진행 의지. 3/5 axes NOVEL ex ante: daily 00:00 UTC session cycle anchored time scale + pre-session positioning ramp mechanism + event-anchored OI velocity transform statistic) | **GRAVEYARD 2026-05-15 turn 10** ❌ (85번째, **SAMPLE_INSUFFICIENT** at Lesson #11 prescreen halt 단계 — three-gate stat suite 미실행. **trigger-rate 실측 vs 가정 4.3x 과대 추정 진단**: 13 alts × 2.22yr × 365 daily anchors = 8158 total events, z>+2 LONG empirical rate **1.16%** (가정 5% 대비 4.3x lower), z<-2 SHORT 0.80%. z>+2 total 95 triggers / z<-2 total 65 triggers. 4 quadrants × 4 quarters split: A focus/mirror 23.8/cell, B same-sign/mirror 16.2/cell → all per-cell < 30 cutoff. paradigm 71 OI velocity trigger swap antipattern 회피 (event-anchored mechanism + 4h hold) 그러나 daily cycle anchor가 always-on 대비 ~288x 데이터 압축 (1440min/5min) → 통계 충분량 부재로 paradigm 71 회피 전략 무력화. **NEW lesson #23 후보**: event-anchored low-frequency cycle × strict z>2 sample-density antipattern — empirical trigger rate 1-2% (5% 가정 대비 1/3~1/10), daily 또는 그 이상 cycle anchor + strict |z|>2 + 13-sym × 1-2yr universe ≤ 60-150 events/direction, 4-quarter × multi-quadrant split 후 30/cell floor 미달. 완화 옵션: (a) |z|>1.5 + Bonferroni adj, (b) universe 확장, (c) 8h funding boundary 더 빈번한 cycle (paradigm 82 시도, fee floor mode fail). **5m microstructure single-domain advisory caution family 4번째 누적 fail** (paradigm 80 broad-falsified + 82 broad-falsified-fee-floor + 83 broad-falsified-fee-floor + 85 sample-insufficient). Tier 4 formal retire 보류 (fail mode 갈라짐: 3 broad-falsified + 1 sample-insufficient, family-grade strict retire 조건 미충족) but **advisory caution 등급 상향**. Mint architect commit eacbded2. /new-paradigm-frontier 4 consecutive dispatches 모두 halt/falsified — frontier scout 명령 메타 한계 4번째 입증 강화) |
| ~~1~~ | ~~`multi_day_vol_persistence_3d_alt_long_1d`~~ (86) | 없음 (OHLCV 1m joblib cache 2.4yr × 14 syms 보유) | R-1 ~2분 실측 (sample-density prescreen pre-execution halt at streak boundary count measurement, /new-paradigm-frontier 5번째 dispatch turn 11 — 사용자 옵션 A 채택, 1순위 권장 후보. 3/5 axes NOVEL ex ante: persistence count sequence streak length statistic + multi-day 3-day timescale + persistence-conditioned momentum cascade mechanism. paradigm 69 vol cascade seed 도메인 leverage 의도) | **GRAVEYARD 2026-05-15 turn 11** ❌ (86번째, **SAMPLE_INSUFFICIENT pre-execution halt** at Lesson #11+23 prescreen — three-gate stat suite 미실행. **streak boundary event는 horizon-bound density 발견**: BTC 2.4yr daily series에서 30d realized vol p80+ HIGH regime streak length distribution mean **12.5d, std 11.7, max 31d** → 2.4yr admits only **6개 streak boundaries** regardless of threshold/length tuning. 8 relaxation variants (p80/p75/p70/p60 × s≥3/s≥2) all q_measurable=0/9 quarters (no quarter reaches ≥10 trigger days). Original p80_s3: A focus pool 26 < 30 floor, B pool 52 < 30 (split per BTC sign × quarter cell < 10). **NEW lesson #24 후보**: Boundary-event statistic class (streak/regime-transition/level-crossing/duration-summarized event boundary)는 cryptocurrency 2-3yr horizon에서 measurement-density-bound. single boundary가 multi-day persistence를 compress한 결과 2.4yr에서 N≈5-10 수준 본질적 sparse, threshold/length relaxation으로도 회복 불가. frontier 5-axis NOVEL timescale axis가 "multi-day" 또는 statistic이 "boundary-event"인 경우 sample-density prescreen이 trigger 정의에 boundary statistic 포함 여부 사전 체크 권고. spike/jump trigger (paradigm 69 spike instantaneous event)는 boundary가 아니라 density 보존. **/new-paradigm-frontier 5 consecutive dispatches 모두 halt/falsified** (82+83+84+85+86): frontier scout 명령 메타 한계 5번째 입증 + 5-axis NOVEL prescreen 한계 4차원 (lesson #21 mechanism alpha + #22 data infrastructure + #23 empirical trigger rate + #24 boundary-event horizon density). Mint architect commit c40040a8. paradigm 69 vol cascade seed와 차별점 명확화: spike (n=767 풍부) vs persistence boundary (n=6 sparse), 1-2 orders magnitude 차이. Day 7 baseline 2026-05-21 우선 모드 강력 재확인 + boundary-event statistic class family advisory caution 검토) |
| ~~life-changing 2차~~ | ~~`binance_delisting_announce_short_alt`~~ (87) | Binance announcements scrape 17초 (57 USDS-M perp delisting events 2024-11~2026-04, cat 161) + data.binance.vision OHLCV 1m 백필 2분 (57/57 syms × 5-13d window, ~30MB joblib Mint) | R-1 PASS_R1_FULL ~30분 실측 (sigex +2.23 ci_lower +782bp perm_p 0.062 + 4-dim freq gate ALL PASS trades/yr=40.5 edge=14.6% util=36.7% sharpe=6.49 + fee_stress 50bp 통과 + concentration 3/3 quarter pos_t + win 71.9% 41/57) → R-2 FRAGILE_TEMPORAL_WF_FAIL ~1.4초 실측 (walk-forward IS sigex +2.09 PASS / OOS sigex +0.18 FAIL drift=0.47 + 5-fold TS-CV **1/5 fold PASS** k=3 2025Q4 sigex +5.05 single outlier dominance / k=0/1/2/4 sigex -0.43~+0.95 모두 FAIL + B same-sign LONG -0.26 noise FAIL + B mirror SHORT +0.28 borderline FAIL) | **GRAVEYARD 2026-05-18** ❌ (87번째, life-changing campaign 2차 세션 첫 dispatch + 캠페인 1+2차 통산 첫 4-dim freq gate 전면 통과 paradigm, **NEW lesson #26** small-sample R-1 PASS walk-forward 의무 + Concentration Gate per-quarter blind spot 패치 (n_measurable_quarters ≥ 4 미달 시 auto-FAIL) + Category A external event injection sub-mechanism asymmetry hypothesis (listing-side forced-entry > delisting-side forced-exit temporal robust 가능성). Mint commits 6d6f7050 + 65e78ec2 + 925c5c04 + d29afd5b) |
| ~~life-changing 2차~~ | ~~`token_unlock_cliff_short_alt`~~ (88) | Manual compilation general-purpose agent 25분 실측 (1.5-2.5h ETA 사용자 명시 승인 30min ETA 초과, [[feedback_no_freemium_trial]] 신규 룰 적용 — DropsTab Builders 3-month trial-to-paid 폐기, CryptoRank/Tokenomist public web scrape no API key no signup, 36 raw HTML cache) | Phase 1 compilation **FAIL_SCOPE at Lesson #11+#26 prescreen halt** (R-1 dispatch 미실행) — Universe 26 tokens (38 시도 13 drop) × 206 events × 2.4yr × cliff filter ≥0.5%, 분포 2024 55/2025 102/2026 49, cliff_or_linear 195 linear+9 cliff+2 unknown (95:5 cliff sparse 본질 — linear는 always-on flow event-anchored 가설 정의 불가), broad scope per-cell <30 + n_measurable_quarters 2/7 < 4 cutoff (lesson #26 패치 paradigm 87 도출 정확 작동), cross-validation rate 0% + cryptorank isAuthProtected 일부 allocation 50-75% 누락 가능 | **GRAVEYARD 2026-05-18** ❌ (88번째, life-changing campaign 2차 세션 second dispatch + Category A exit-side 2회 누적 입증 paradigm 87 동형, **NEW lesson #27** entry-side vs exit-side 사전 분류 필수 prescreen + paradigm-architect spec failure protocols hook 권고 + lifecycle 외 entry-side mechanism (CEX listing pre-announce / Network Upgrade pre-event / ETF Approval) 우선 권고 + exit-side 자동 차단 + lesson #26+#27 prescreen 메커니즘 dogfood 성공 (Phase 1 단계 R-1 자원 사전 절약). Commit 251a5d0f compilation) |
| ~~life-changing 2차~~ | ~~`listing_pre_announce_leak_long_alt`~~ (89) | Phase 0 fundamental verification 4분 (Mint paradigm-architect agent, no Mint commit dispatch 미실행) | Phase 0 **DISPATCH_IMPOSSIBLE Binance Futures USDS-M perp onboardDate 이전 substrate 부재** — listed symbol pre-announce window 가격 history 자체 시간 차원 부재. Independent verification: BILLUSDT pre-onboard archive HTTP 404 + post-onboard HTTP 200. 388 listing events 2024-01~2026-05, spot pre-existence 7/30 random = 23.3% → ~90 effective events, 2-quadrant × 5 quarters per-cell 22.5 < 30 cutoff. 4 변형 (spot pre-existence / cross-exchange / BTC macro proxy / post-only) 모두 폐기 | **GRAVEYARD 2026-05-18** ❌ (89번째, life-changing campaign 2차 세션 third dispatch + paradigm 90 parallel dispatch, **NEW lesson #28** Entry-side external event paradigm substrate availability prescreen 의무 + paradigm-architect spec failure protocols hook 권고 + Category A sub-mechanism asymmetry taxonomy 4-dim 결정적 확장 (entry/exit + immediate/delayed + substrate availability + sample density)) |
| ~~life-changing 2차~~ | ~~`stablecoin_mint_event_long_alt_24h`~~ (90) | Phase 1 사전 검토 8분 (Mint paradigm-architect agent, no commit dispatch 미실행, [[feedback_no_freemium_trial]] 룰 strict 적용) | Phase 1 **HALT R-1 미실행 3 independent fail modes**: (1) SAMPLE_INSUFFICIENT Ethereum-only (publicnode RPC verified, USDT 90일 3 events, 연간 12-20 → 2.4yr 30-50 events × 4-quadrant × 4 quarters per-cell 1.9-3.1 catastrophic FAIL, cross-asset cascade portfolio event), (2) [[feedback_no_freemium_trial]] 위반 multi-chain (Etherscan V2 chainid+signup verified + Solana paid + Tron paid), (3) lesson #27 sub-mechanism re-classification claimed entry-side but delayed/indirect (OTC settlement lag) = paradigm 87 forced-exit 동형 fragility risk | **GRAVEYARD 2026-05-18** ❌ (90번째, life-changing campaign 2차 세션 fourth dispatch + paradigm 89 parallel dispatch, **NEW lesson #27 amendment** immediate vs delayed/indirect entry 정밀화 + paradigm-architect spec failure protocols hook 권고 + **lifecycle paradigm uniqueness 4-dim 결정적 입증** (entry-side + immediate market demand + post-event substrate availability + sample density 모두 충족하는 유일 mechanism class confirmed)) |
| (deferred) | Day 7/Day 30 baseline 측정 후 재평가 | — | — | **Day 7 baseline (2026-05-21) + Day 30 baseline (2026-06-13)** paradigm 69 13 sessions + R-5 시드 8개 실측 우선. measured alpha < predicted 50% 시 demote 결정. baseline 측정 완료 후 (a) 3 candidates archive (A/B/C) 재평가 또는 (b) 진짜 새 데이터 도메인 발굴 (WS recorder accumulation 60+일 누적 후 2026-07-15 가능) 재개. **추가 R-1 dispatch는 사용자 명시 승인 시에만**. |

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

### 6.7 2026-05-18 Track 3 DART KR equity earnings/guidance family update

**Track 3 (DART OpenAPI pipeline)** Sub-task 3A design + 3B 구현 + 2 R-1 dispatch 완료, KR equity post-earnings/guidance directional momentum family **Tier 4 formal retire**.

**Paradigm 92 — `dart_h1_earnings_gap_proxy_kr_equity_long_5d`** (Track 3 Sub-task 3B 첫 dispatch, 2026-05-18)
- 가설: KOSPI200+KOSDAQ150 잠정실적 공시 후 시초가 gap ≥ +3% → +1d open 매수 → +5d hold (LONG)
- R-1 gap proxy PASS_R1: n=156 / sigex +3.67 / 3-gate ALL PASS / Concentration PASS
- R-2 wf TEST PASS but TS-CV **1/5** (fold k=5 2026Q1+Q2 단독 견인)
- R-2c true YoY OP ≥+30% surprise n=706: **0/5 folds PASS** (5 fold 3 양수 / 2 유의 음수 temporal alternating)
- **NEW lesson #29 candidate**: gap proxy ≠ true surprise direction (sentiment-driven gap ≈ continuation vs fundamental YoY ≈ mean reversion in KR equity, US PEAD strong but KR retail over-reaction)
- Side discovery: neg surprise × LONG t=-2.28 sig_t_ex -3.25 강한 하방 continuation but reverse (neg×SHORT) net -23bp sub-fee
- 산출물: dart_adapter.py + disclosure_parser.py + _naver_kr_equity.py + dart_earnings_signal_r1.py + r2.py + r2c.py (6 files ~1,000 lines) + cache (universe + 197 stock OHLCV 2.4yr + 2,000 fnltt + 1,996 events_ret joblib)
- [[project_paradigm_dart_h1_earnings_gap]] 참조

**Paradigm 93 — `dart_h2_guidance_amend_30pct_kr_equity_directional_5d`** (Track 3 Sub-task 3B 두번째 dispatch, 2026-05-18)
- 가설: EARNINGS_GUIDANCE_AMEND 공시 ("매출액또는손익구조30%이상변경") + DART fnltt YoY OP growth direction → +1d open / +5d hold, lesson #29 cross-proxy 강제 (observable pre_ret_5d + fundamental YoY OP 두 트랙 독립 측정)
- R-1 4-quadrant + cross-proxy: n=1,106 events / 350 pos / 327 neg
  - Fund pos×LONG: gross +50.7bp (정확 fee floor) / net +0.7bp / sigex **-0.97** / ci_lo -98bp
  - Obs pos_pre×LONG: gross +175.4bp / t **+2.47** / sigex **+1.34 < 2.0** / ci_lo +25.8bp (traditional t PASS but fee-aware strict 차단)
  - 두 트랙 모두 strict 3-gate FAIL → `BROAD_FALSIFIED` cross_proxy_verdict
- **Lesson #29 dogfood 2번째 성공 + 정식 승급 candidate → confirmed**: cross-proxy strict gate가 single-proxy marginal artifact 정확 차단 (paradigm 92 동형 trap 방지 입증)
- Side discovery: B mirror neg×LONG gross +74~110bp / prob_pos 94.2% / mean reversion pattern but sigex<2.0 paradigm-grade 미달
- TS-CV degenerate 1 fold (가이던스 ≥30% pos events Q1 entry agglomeration, 별도 lesson candidate 본 paradigm BROAD_FALSIFIED로 보류)
- 산출물: dart_guidance_signal_r1.py (~550 lines) + h2_guidance_r1_metrics.json + h2_guidance_events_cache.joblib (1,107 events) + h2_guidance_events_ret_cache.joblib (1,106 enriched) + fnltt_cache +150 entries
- [[project_paradigm_dart_h2_guidance]] 참조

**Lesson #29 정식 (candidate → confirmed via dual dogfood)**:
**Cross-proxy strict (observable + fundamental both PASS)**. Trigger: R-1 paradigm 발의 시 trigger가 관측 가능한 sentiment-driven proxy 또는 fundamental signal 단일 차원. Check: 동일 mechanism family에서 두 트랙 (observable + fundamental) 독립 측정 가능한가? 두 트랙 모두 R-1 본체에 4-quadrant Symmetric Negative Test 한 batch 측정 의무. Action: 두 트랙 모두 PASS → PROMOTE_R2 / 한 트랙만 PASS → SINGLE_PROXY_TRAP halt / 두 트랙 모두 FAIL → BROAD_FALSIFIED / opposite alignment → mean-reversion regime 진단. paradigm-architect r1_protocol.md spec 통합 권고.

**Family retire — KR equity post-earnings/guidance directional momentum** (Tier 4 formal retire 5번째, 2026-05-18):
- paradigm 92 (잠정실적 gap proxy R-1 PASS → R-2c 0/5) + paradigm 93 (가이던스 ±30% cross-proxy R-1 BROAD_FALSIFIED) 이중 graveyard 누적 입증
- 사전 차단 sub-mechanism: 잠정실적 directional momentum / 가이던스 변경 directional momentum / 사업/반기/분기 보고서 directional momentum / 컨센서스 surprise momentum / 모든 hold period × universe size 변형
- Family-distinct hypothesis만 R-1 dispatch 가능: mean-reversion 방향 (단 fee floor / sigex 2.0 사전 통과) / 비-directional event / 외부 event (lesson #27 amendment 추가 prescreen)
- 재검토 2026-11-18
- [[feedback_family_retire_kr_post_earnings]] 참조

**Track 3 DART OpenAPI 인프라 영구 자산** (재사용 가능, ~250MB):
- `backend/app/services/dart_adapter.py` (DART HTTP client + crtfc_key + paging)
- `backend/app/services/disclosure_parser.py` (Tier S/A/B/C classifier)
- `backend/scripts/research/_naver_kr_equity.py` (universe + OHLCV)
- `backend/runs/dart_track/ohlcv_cache/` (197 KR stocks × 2.4yr 일봉)
- `backend/runs/dart_track/fnltt_cache/` (~2,150 DART fnltt entries)
- `backend/runs/dart_track/events_ret_cache.joblib` (1,996 잠정실적 events)
- `backend/runs/dart_track/h2_guidance_events_ret_cache.joblib` (1,106 가이던스 events)

**Tier 4 family retire 표 update** (§6.4):

| Family | 누적 paradigm graveyard | 사유 |
|---|---|---|
| btc_eth_5m_corr_breakdown_family | 74+75+76+77 | cross-asset corr regime trigger 변형 모두 fail, lesson #15+16 적용 |
| geometric_path_metrics_family | 78 | path tortuosity/fractality/Hurst alone fee-floor 미달, lesson #17 |
| funding_oi_joint_squeeze_family | 73+79 | sample-density bottleneck → 5.1x boost 후에도 mechanism falsified, lesson #18 |
| 5m_microstructure_single_domain_alpha_family (advisory caution) | 80+82+83+85 | 5m premium/OI single-domain 4번 누적 fail, formal retire 직전 단계 |
| **kr_equity_post_earnings_guidance_directional_momentum_family** (NEW 2026-05-18) | **92+93** | **KR PEAD weak + retail over-reaction, sub-mechanism 모두 사전 차단, lesson #29 confirmed** |

**Paradigm campaign 진행 상태** (2026-05-18 22:13 KST):
- 누적 graveyards: 93 (paradigm 86~93 9개 graveyard 8개 + R-1 PASS 가지 변형 0개)
- R-5 시드: 8개 (unchanged)
- Family retire (formal): 5 + advisory caution 1
- Lessons: 29 (lesson #29 정식 승급)
- Day 30 baseline 검증: 2026-06-03~13 (10-20일 남음)
- Campaign 휴면 유지: paradigm-architect 정식 dispatch 금지 2026-05-29까지 (lifecycle live mode 재개), ad-hoc R-1 검증은 허용
- 다음 entry point: Day 30 baseline 측정 완료 + lifecycle live mode 결과 누적, family-distinct mechanism만 발의 가능

---

### 6.8 2026-05-19 paradigm 97 candidate R-0 inventory halt + lesson #31 candidate

**paradigm 97 candidate — `funding_term_structure_cross_sym_dispersion`** (ad-hoc R-1 dispatch attempt, R-0 inventory halt 적용, R-1 미실행)

- **가설**: 같은 거래소(Binance USDS-M) 14-sym universe 8h funding cycle 시점 cross-section z-score (sym i funding rate vs universe median/std) outlier (|cs_z|>2) → mean-reversion fade
- **Family-distinct claim**: paradigm 96 graveyard memory §family-distinct exception path 2 "funding term structure cross-sym (8h cycle differential between syms)" 매칭 시도
- **r0_inventory_check 결과 (paradigm-architect agent `a5ab76e84652d8a3d`, 2026-05-19 11:25 KST)**: 기존 `funding_dispersion` paradigm (R-5 paper seeded 2026-05-05, ETCUSDT `d2640960-52b` active) 와 **DNA 5/6 차원 정확 일치**:

| 차원 | funding_dispersion (R-5 seeded) | paradigm 97 candidate |
|---|---|---|
| Substrate | Binance USDS perp 14-sym universe | 동일 ✅ |
| Statistic | cross-section z-score of funding vs universe mean/std | 동일 ✅ |
| Direction | mean-reversion fade (FundingReversalPolicy + NegationPassthrough) | 동일 ✅ |
| Mechanism | universe-level cross-section dispersion | 동일 ✅ |
| Universe scope | R-1 ETC focus + R-2 14-sym 전체 측정 완료 | 14-sym 동일 ✅ |
| Threshold | entry_z = 0.8 (+ z=2.0 SOL sweep 측정 완료) | \|z\| > 2.0 ⚠️ parametric variant |

- **R-2 14-sym universe-wide 측정 (2026-05-05) 결과적 부분 falsified**: ETC alpha 138 sharpe 3.50 R-5 paper seed / **non-ETC 13 sym 평균 alpha +37 sharpe -0.07 sharpe_pos 5/13** → universe-wide mean-reversion 가설 R-2 단계에서 이미 falsified, per-symbol 1:1 paradigm (ETC outlier)
- **paradigm 96 §family-distinct path 2 정의 모호성 노출**: "funding term structure"는 funding_dispersion (cross-section dispersion)이 **아님**. 진정한 family-distinct term structure = (a) multi-tenor funding curve slope (Binance 단일 8h tenor → 불가능) 또는 (b) funding cycle 시점 간 differential / velocity (8h-to-8h delta velocity, 미측정). [[project_paradigm_96_funding_sign_flip_family_retire]] §family-distinct amendment 적용
- **Verdict**: `FAIL_FAMILY_SUBSUMED` (R-0 inventory halt, R-1 dispatch 미실행, graveyard 카운터 96 유지, paradigm_index register skip — INDEX.md 부정확성 회피)
- **산출물**: 본 큐 §6.8 인라인 보고만 (R-1 코드/metrics/gate_eval 없음). Inventory 증거: `backend/runs/research_track/funding_dispersion/gate_eval__ETCUSDT.md` (2026-05-05 5/6 DNA overlap 명시), 본 INDEX.md line 70 (`funding_dispersion` R-5 paper seeded), 181-195 (시드 산출물 + R-1 spec)
- **연결**: [[project_paradigm_97_funding_dispersion_inventory_halt]]

**NEW Lesson #31 candidate (1 dogfood 2026-05-19) — Cross-section dispersion family R-5 점유 inventory prescreen**

**Trigger**: R-1 paradigm 발의 시 statistic axis = cross-section dispersion (sym i feature vs universe mean/std/median z-score) family
**Check**: paradigm_index에서 기존 seeded paradigm DNA 차원 6개 cross-check — substrate / statistic / direction / mechanism / universe / threshold-or-hold
**Action**:
- DNA cutoff ≥ 5/6 일치 (parametric variant only) → `FAIL_FAMILY_SUBSUMED` R-0 inventory halt, R-1 dispatch 차단
- DNA 4/6 이하 → 다음 차원 (시간 frame / event anchor / regime conditioning) 새 dimension 결합 시 valid family-distinct, R-1 dispatch 가능
- **Why**: paradigm 97 candidate dogfood (DNA 5/6 with funding_dispersion R-5 seeded ETCUSDT, parametric variant only) → inventory halt 사전 차단으로 R-1 자원 + paper pool noise 회피. paradigm-architect r0_inventory_check skill의 정상 작동 입증
- **Implementation**: paradigm-architect agent skill spec에 `r0_inventory_check` cross-section dispersion family-aware DNA 6-dim cross-check 의무 추가, paradigm 96 graveyard memory §family-distinct path 정의 모호성 해소 후속 dispatch 의무

**campaign 진행 상태 갱신 (2026-05-19 11:30 KST, 후속 batch 전)**:
- 누적 graveyards: 96 (paradigm 97 candidate inventory halt는 graveyard 카운터 미증가)
- Inventory-halt 사례: 1건 NEW (paradigm 97 candidate `funding_term_structure_cross_sym_dispersion`)
- Lessons: 29 confirmed + Lesson #30 candidate + Lesson #31 candidate + NARROW_SCOPE_LIFE_CHANGING_FAIL verdict candidate

### 6.9 2026-05-19 12:00 KST batch ad-hoc R-1 — paradigm 97/98/99 정식 graveyard (funding family 완전 소진)

**Batch dispatch context**: Day 7 baseline 우선 모드 binding 상태에서 사용자 명시 P1/P2/P3 batch ad-hoc R-1 dispatch. paradigm 97 candidate inventory halt 후속 agent 권고 3 진정한 funding family-distinct 후보 동시 검증. paradigm-architect agent `a4f7454c52e17debf` Mint full-window sequential execution (P1→P2→P3), batch 단일 message 종료 보고.

> **명명 명확화**: paradigm 97 candidate `funding_term_structure_cross_sym_dispersion` §6.8 inventory halt (counter 미증가)와 본 §6.9 paradigm 97/98/99는 별개. 본 batch P1이 정식 paradigm 97 카운터 차지.

| # | Paradigm | Sample | Focus 결과 | Verdict |
|---|---|---|---|---|
| **97** | `funding_velocity_cross_section_dispersion` (P1) | 14×2.37yr 36,211 | A LONG -8.62bp sigex -0.20 (4-quadrant fee floor -7.4~-8.6bp) | **BROAD_FALSIFIED** |
| **98** | `funding_regime_stratify_dispersion` (P2) | 14×2.37yr 36,252 | HIGH-A LONG +15.72bp ci -76.71 (sample variance) / MID-B opposite sigex -1.51 | **BROAD_FALSIFIED** |
| **99** | `funding_cycle_8h_differential_velocity_per_sym` (P3) | 14×2.38yr 38,618 | A focus sigex +2.03 ci -4.31 FAIL / B mirror PASS sigex +3.19 / Concentration 0/13 ci_pos / edge 0.24% (8x deficit) | **BROAD_FALSIFIED_MIRROR_ONLY** |

**Funding family Tier 4 retire 결정적 강화** (6 sub-class 6 graveyards):
- 73 funding_oi_bipolar (joint event) / 79 funding_oi_bipolar_retry (extreme level) / 96 funding_rate_sign_flip (categorical) / **97 cs velocity** / **98 regime stratify** / **99 per-sym velocity**
- **Exception**: paradigm 22 funding_carry R-5 seeded (3-sym narrow carry) + funding_dispersion R-5 seeded ETCUSDT (cs level z, per-symbol 1:1, R-2 non-ETC sharpe_pos 5/13 부분 falsified)
- HALT_BEFORE_R1 sub-mechanism 8개로 확장 ([[project_paradigm_96_funding_sign_flip_family_retire]] §HALT_BEFORE_R1 sub-mechanism 5-8 추가)

**Lesson dogfood 동시 통과 (3개)**:

### NARROW_SCOPE_LIFE_CHANGING_FAIL verdict [CANDIDATE → CONFIRMED 2026-05-19 dogfood 2회 누적]
- dogfood 1: paradigm 95 cross_asset_volume_concentration (edge 0.47% 4.3x deficit)
- dogfood 2: paradigm 99 funding_cycle_8h_differential_velocity B mirror (edge 0.24% **8x deficit**, 3/4 dim PASS only)
- **정식 승급 자격 충족** → lesson_prescreen_checklist.md `NEW verdict — NARROW_SCOPE_LIFE_CHANGING_FAIL` 항목 [CONFIRMED] 격상

### Lesson #31 — Cross-section dispersion family R-5 점유 inventory prescreen [CANDIDATE → CONFIRMED 2026-05-19 dogfood 2회 양방향]
- dogfood 1: paradigm 97 candidate inventory halt (DNA 5/6 with funding_dispersion R-5, FAIL_FAMILY_SUBSUMED)
- dogfood 2: batch P1/P2/P3 (DNA ≤4/6 cross-check 통과 → dispatch 정상)
- **정식 승급 자격 충족** → lesson_prescreen_checklist.md `Lesson #31 candidate` 항목 [CONFIRMED] 격상

### Lesson #8 Mirror antipattern symmetric LONG bias amendment candidate (paradigm 99 발견)
- A focus high LONG +12.44bp AND B mirror low LONG +24.00bp **둘 다 양수**
- "leverage shock magnitude → general upward bias" 패턴 (directional MR 아님)
- 향후 mirror-only PASS 판정 시 (a) 정통 mirror antipattern vs (b) symmetric magnitude bias 사전 분류 의무 추가 candidate

### Campaign 진행 상태 갱신 (2026-05-19 12:00 KST 본 batch 후)
- 누적 graveyards: **99** (96→99, +3 신규 정식)
- Inventory-halt 사례: 1 (paradigm 97 candidate, counter 미증가)
- R-5 시드: 8개 unchanged
- Family retire (formal Tier 4): 7 + 1 advisory caution (funding sub-class 결정적 강화, entry 변경 없음)
- Lessons: **29 confirmed + Lesson #30 candidate + Lesson #31 confirmed + NARROW_SCOPE_LIFE_CHANGING_FAIL confirmed** + Lesson #8 amendment candidate
- Campaign 모드: **Day 7 baseline 우선 모드 유지** (2026-05-21 도래까지 2일, 본 batch는 ad-hoc 사용자 명시 승인으로 모드 위반 아님)

---

### 6.10 2026-05-19 12:35 KST paradigm 100 candidates 2x halt + 메타 회고 + Day 7~Day 30 plan revision

**Context**: §6.9 batch P1+P2+P3 → paradigm 97/98/99 graveyards 직후 추가 ad-hoc R-1 2건 attempt. 둘 다 R-0 halt (paradigm 100 ID 미확정, candidate halt 사례).

#### paradigm 100 candidate `dart_treasury_share_repurchase_announce_kr_equity_long_5d`
- KR equity 자기주식 취득 결정 공시 +1d open / +5d hold LONG
- **Verdict**: `HALT_BEFORE_R1_LESSON27_AMENDMENT_DELAYED_INDIRECT` (R-1 미실행, compute 0)
- **차단 근거 3 independent evidences**:
  1. `backend/app/services/disclosure_parser.py:60-62` 자기주식취득결정 `Side.ENTRY_DELAYED` 사전 분류 (Track 3 paradigm 92/93 작업 시 이미 명시)
  2. `.claude/plans/track3_dart_pipeline_design.md` §11.4 H3 차단 결정 명시
  3. Mechanism 동형 paradigm 87/88/90 fragility (announcement vs execution 시간 분리, VWAP 분할)
- **Lesson #27 amendment 4번째 dogfood** (paradigm 87 + 88 + 90 + 본 100 candidate)
- agent ID: `a014bd5d7e0d416f8`

#### paradigm 100 candidate `binance_perp_liquidation_cascade_event_alt_intraday`
- Binance USDS-M perp 14-sym 5min liquidation notional volume top decile cascade → 4-quadrant direction (Q3 큐 §1 #1 ⭐⭐⭐ 최강 후보)
- **Verdict**: `DISPATCH_IMPOSSIBLE` (R-0 substrate halt, compute 0)
- **차단 근거 4 independent fail modes**:
  1. `data.binance.vision/.../liquidationSnapshot/` 트리 부재 (HTML cache only, S3 prefix `<IsTruncated>false</IsTruncated>` empty)
  2. `metrics/` csv 8칼럼 (OI + 4 L/S ratio + taker buy/sell ratio) liquidation 미포함
  3. REST `allForceOrders` 영구 폐기 ("out of maintenance"), `/fapi/v1/forceOrders` 계정 scoped only, WS `!forceOrder@arr` live-only
  4. Mint 인프라 forceOrder/liquidation recorder 사전 누적 0건
- **Lesson #28 5번째 effective dogfood** (paradigm 89 + 90 sub-mode + 100 candidate dart_treasury + 100 candidate liquidation + implicit 84/85)
- 재시도 경로 (deferred to Day 30 후): Mint PM2 `!forceOrder@arr` WS recorder service stand-up → 60-90d forward collection → 2026-07-15+
- 산출물: `backend/runs/research_track/graveyard__binance_perp_liquidation_cascade_event_alt_intraday.md`
- agent ID: `a24a663f7f0416aad`
- **§1 #1 annotation 갱신** (위 §1 #1 entry strikethrough + substrate-blocked R-0 표기)

#### 메타 회고 (정량)

**누적 통계 (2026-05-19 12:35 KST)**:
- graveyards counter: **99**
- Inventory-halt 사례: 2 (paradigm 97 candidate funding_term_structure + paradigm 100 candidate dart_treasury)
- Substrate-halt 사례: 1 (paradigm 100 candidate liquidation_cascade)
- R-5 paper seeded: 8 (unchanged)
- Family retire formal Tier 4: 7 + 1 advisory caution
- Lessons confirmed: 30 (29 prior + #31 NEW) + 1 amendment (#27 4 dogfoods)
- Lessons candidate: 2 (#30 short-data + #8 symmetric LONG bias amendment)
- Verdict confirmed: 2 (#29 cross-proxy + NARROW_SCOPE_LIFE_CHANGING_FAIL)

**Closing rate 정량 분석**:
- Q2 (2026-04~2026-05-13): R-5 시드 비율 ~10%, family retire 0건
- mid-Q3 (2026-05-14~2026-05-19): R-5 시드 비율 ~3% (1/35), **family retire 7건** + advisory 1건
- **3.3x closing rate 가속**
- 최근 14 R-1 dispatches (paradigm 86~99) + 3 candidate halts (97 candidate + 100×2): **0% R-5 pass rate in last 5 days**

#### Day 7 ~ Day 30 plan revision

| 기간 | 일정 | 모드 |
|---|---|---|
| 2026-05-19 ~ 05-21 (~1.5d) | Day 7 도래까지 | Day 7 baseline 우선 모드 유지, ad-hoc R-1 가능하나 ROI 낮음. 인프라 prep / 다른 트랙 권장 |
| 2026-05-21 (Day 7) | paradigm 69 13 sessions 실측 alpha 측정 | baseline 비교 + lifecycle live mode 재개 prep |
| 2026-05-22 ~ 05-28 (~7d) | Day 7 → lifecycle live mode 재개 전 | Day 7 결과 메타-학습, WS recorder stand-up 결정 사용자 게이트 |
| 2026-05-29 (lifecycle live mode 재개) | live mode 재개 + paper Day 30 baseline prep | 정식 dispatch 보류 유지 |
| 2026-06-03 ~ 06-13 (Day 30) | paper Day 30 baseline 측정 | 정식 dispatch 재개 가능 시점, family-distinct 새 axis만 발의 |
| 2026-07-15 (WS recorder 60-90d) | frontier scout 재실행 가능 | liquidation cascade event 재시도 가능, 5m microstructure family advisory 재시도 검토 |
| 2026-11-18 (6개월) | KR equity family retire 재검토 | regime 변화 trigger 시 |

#### Campaign 진행 상태 갱신 (2026-05-19 12:35 KST 본 §6.10 후)

- 누적 graveyards: 99 (96→99, +3 신규)
- Inventory-halt 사례: 2 (paradigm 97 candidate + paradigm 100 candidate dart_treasury)
- Substrate-halt 사례: 1 (paradigm 100 candidate liquidation_cascade)
- Lessons: 30 confirmed + 2 candidates + 2 verdict confirmed
- Campaign 모드: Day 7 baseline 우선 모드 유지 (2026-05-21 도래까지 ~1.5일), 추가 ad-hoc R-1 ROI 낮음
- **paradigm 발의 공간 사실상 closing 입증** — 정식 dispatch 재개는 2026-05-29 또는 Day 30 결과 후, family-distinct 새 axis (WS recorder substrate / paid feed user decision / DART/KIND/FRED/ECOS 정부 source / cross-exchange) 만 발의 가능
- [[project_paradigm_campaign_closing_rate_snapshot_2026_05_19]] 정량 회고 메모리

---

### 6.11 2026-05-19 13:27 KST paradigm 100 정식 graveyard — DART 가이던스 family 양방향 결정적 폐기

**Context**: agent 권고 "family-distinct mean-reversion direction" 정식화 시도. paradigm-architect ad-hoc R-1 분리 모드 dispatch (`a472b837b91df3400`). paradigm 93 cache audit으로 R-0 prescreen halt, 자원 0 소모.

#### paradigm 100 `dart_h2_guidance_amend_30pct_kr_equity_mean_reversion_neg_long_20d`
- 가설: KR equity EARNINGS_GUIDANCE_AMEND × NEG surprise (YoY OP ≤ -30% OR pre_ret_5d ≤ -3%) × LONG mean-reversion (oversold bounce) × hold 5d→20d 확장
- Family-distinct path 정확 통과 — [[feedback_family_retire_kr_post_earnings]] §"mean-reversion direction 허용" 첫 항목
- **Verdict**: `SAMPLE_INSUFFICIENT_TEMPORAL_CONCENTRATION` (R-0 prescreen halt, paradigm_index 정식 register, **graveyard counter 99 → 100**)

#### R-0 prescreen 차단 evidence (paradigm 93 cache audit)

| Track | n_neg | Quarter distribution | n_measurable_quarters |
|---|---|---|---|
| FUND (op_growth ≤ -30%) | 327 | 2024Q1=134 / 2025Q1=120 / 2026Q1=73 (100.0%) | **3** |
| OBS (pre_ret_5d ≤ -3%) | 259 | 2024Q1=75 / 2025Q1=88 / 2025Q2=1 / 2026Q1=95 (99.6%) | **3** |
| All events | 1106 | 99.5% Q1-clustered | **3** |

Lesson #26 amendment `n_measurable_quarters ≥ 4` 의무 → 실측 **3** (양 트랙). EARNINGS_GUIDANCE_AMEND substrate Q1-clustered 99.5% (KR annual-results disclosure cycle 본질). hold-extension/direction-flip/threshold-tweak 무력.

#### DART 가이던스 family 양방향 결정적 폐기 입증

| # | Paradigm | Direction | Verdict |
|---|---|---|---|
| 92 | dart_h1_earnings_gap_proxy_long_5d | directional momentum LONG | R-2c 0/5 graveyard |
| 93 | dart_h2_guidance_amend_directional_5d | cross-proxy directional | BROAD_FALSIFIED |
| **100** | **dart_h2_guidance_amend_mean_reversion_neg_long_20d** | **mean-reversion NEG×LONG** | **SAMPLE_INSUFFICIENT_TEMPORAL_CONCENTRATION** |

**Track 3 DART 가이던스-기반 paradigm 영구 폐기** (directional + mean-reversion 양방향). Family retire 강화 — [[feedback_family_retire_kr_post_earnings]] amendment 의무 적용 ("mean-reversion direction 허용" path 차단).

#### Lesson dogfood 누적

##### Lesson #26 amendment — 3번째 dogfood 강력 누적
- dogfood 1: paradigm 87 R-2 적발 FRAGILE_TEMPORAL_WF_FAIL
- dogfood 2: paradigm 88 + 90 Phase 1 prescreen halt
- dogfood 3: **paradigm 100 R-0 prescreen halt** (paradigm 93 cache audit, 자원 0)

##### NEW lesson candidate — R-0 substrate quarterly distribution audit 의무
**Trigger**: paradigm 발의 시 prior-paradigm cache 있을 때 R-1 실행 전 substrate quarter distribution 사전 audit
**Check**: n_measurable_quarters 측정 → lesson #26 amendment auto-FAIL precondition cross-check
**Action**: < 4 시 SAMPLE_INSUFFICIENT_TEMPORAL_CONCENTRATION halt before R-1
**Why CANDIDATE (1 dogfood)**: paradigm 100 R-0에서 paradigm 93 cache 직접 audit으로 R-1 자원 사전 차단. paradigm-architect r0_inventory_check skill spec amendment 제안.

#### Family-distinct path 사실상 close

KR equity post-earnings/guidance family 남은 path:
- ~~mean-reversion 방향~~ (paradigm 100 차단)
- 비-directional event (vol expansion, pair trade, sector rotation)
- ~~외부 event delayed/indirect~~ (paradigm 100 candidate dart_treasury 4th dogfood 차단)
- **DART year-round filing (NEW agent 권고)**: 분기보고서 4x/yr / 단일판매·공급계약 — lesson #26+27+28 amendment 3중 prescreen 통과 필수

#### Agent 권고
1. 재시도 금지 (EARNINGS_GUIDANCE_AMEND hold/direction/threshold 모두 동일 temporal defect)
2. Day 7 baseline 우선 모드 유지 (2026-05-21 ~1.5일)
3. 후속 family-distinct 발의 시 R-0 substrate quarterly distribution audit 의무
4. paradigm-architect spec amendment: `r0_inventory_check`에 "substrate quarterly distribution audit" sub-step 추가
5. 후속 family-distinct 가능 후보: (a) 분기보고서 4x/yr / (b) 단일판매·공급계약 year-round filing / (c) 비-directional volatility event

#### Campaign 진행 상태 갱신 (2026-05-19 13:30 KST)
- 누적 graveyards counter: **100** milestone (+1 정식)
- Inventory-halt 사례: 2 (97 candidate funding_term + 100 candidate dart_treasury)
- Substrate-halt 사례: 1 (100 candidate liquidation_cascade)
- R-5 시드: 8 unchanged
- Family retire (formal Tier 4): 7 + 1 advisory caution (KR post-earnings family **mean-reversion path 차단 추가 강화**)
- Lessons: 30 confirmed + Lesson #26 amendment 3 dogfoods + **NEW candidate "substrate quarterly distribution audit"** + #30 candidate + NARROW_SCOPE_LIFE_CHANGING_FAIL confirmed
- [[project_paradigm_100_dart_guidance_mean_reversion_milestone]] 신설

---

### 6.12 2026-05-19 14:56 KST paradigm 101 정식 graveyard — DART entry-side immediate family 결정적 폐기 (4 graveyards)

**Context**: agent paradigm 100 §Next-step §5 권고 path (b) **DART year-round filing** 정식화 시도. paradigm-architect ad-hoc R-1 분리 모드 dispatch (`a26dae8c84f89483b`). DART scan 54분 + R-1 1분 = ~55분 cumulative cost.

#### paradigm 101 `dart_supply_contract_announce_kr_equity_long_5d`
- 가설: 단일판매·공급계약 공시 → +1d open / +5d hold LONG (immediate market attention information event)
- **R-0 prescreen GO_R1 통과**: 2,421 events / 350 universe / 127 stocks, 10/10 quarters year-round PASS (≥88 events/quarter, paradigm 100 Q1-clustering trap 정확 회피)
- disclosure_parser.py 단일판매·공급계약 type entry 부재 → agent inference `Side.ENTRY_IMMEDIATE` (lesson #27 amendment dogfood 5번째)
- 측면 발견: DART pblntf_ty=I (거래소공시) 카테고리

#### R-1 정식 실행 결과 — 3중 fail mode

| Cell (5d) | n | net_bp | t_obs | sigex | gate |
|---|---|---|---|---|---|
| A focus announce × LONG | 2,009 | +52.9 | +2.49 | **-0.75** | FAIL |
| A mirror announce × SHORT | 2,009 | -152.9 | -7.18 | +0.82 | FAIL |
| **B baseline non_announce × LONG** | 14,886 | **+68.4** | +8.83 | — | FAIL |
| B baseline × SHORT | 14,886 | -168.4 | -21.75 | — | FAIL |

**3중 fail mode**:
1. **Universe-drift dominance**: A focus +52.9bp < B baseline +68.4bp (15bp/5d under-perform, signal_t_excess -0.75)
2. **Cross-proxy inverse**: freq_high +121.9bp > freq_low +57.4bp = company-quality selection bias (information event 가설 reject)
3. **Per-symbol concentration FAIL**: 4-15/61 ci_pos (6.6-24.6% < 30% cutoff)

**Life-changing 4-dim trap**: 10d edge +2.65% / sharpe +5.48 4-dim PASS — 그러나 A focus +265bp vs B baseline +230bp = 35bp/10d edge ≪ 50bp fee margin = universe drift artifact false-positive (paradigm 95 narrow-scope life-changing FAIL 동형).

#### Verdict
**`CONCENTRATION_FAIL` (R-1 primary) + `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` (auxiliary)** — counter 100 → **101** (정식 등록).

#### KR equity DART entry-side family retire 4 graveyards 누적 결정적 강화

| # | Paradigm | Mechanism class | Verdict |
|---|---|---|---|
| 92 | dart_h1_earnings_gap_proxy_long_5d | directional momentum | R-2c 0/5 graveyard |
| 93 | dart_h2_guidance_amend_directional_5d | cross-proxy directional | BROAD_FALSIFIED |
| 100 | dart_h2_guidance_amend_mean_reversion_neg_long_20d | mean-reversion | SAMPLE_INSUFFICIENT_TEMPORAL |
| **101** | **dart_supply_contract_announce_long_5d** | **entry-side immediate information event** | **BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT** |

#### NEW 자산 3건 정식 등록

**Lesson — R-0 substrate quarterly distribution audit [CONFIRMED 자격 충족 2 dogfoods]**:
- dogfood 1: paradigm 100 cache audit halt
- dogfood 2: paradigm 101 신규 scan GO_R1 (양방향 입증)

**NEW Lesson #32 candidate — Universe-baseline-coherent A_focus trap** (1 dogfood paradigm 101):
- Trigger: A focus three-gate t_obs PASS but signal_t_excess < 2.0 AND B baseline net ≥ A focus net
- Action: `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` verdict 발급

**NEW verdict `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` 정식 추가**:
- A_focus signal positive but B_baseline outperforms or ≥
- 4-dim PASS는 universe drift artifact false-positive (paradigm 95 동형)
- cross-proxy inverse 동반 시 mechanism reject

**Lesson #27 amendment dogfood 5번째 성공**: agent 자체 inference `Side.ENTRY_IMMEDIATE` 분류 (disclosure_parser.py entry 부재 케이스)

#### Agent 권고
1. DO NOT retry single sales/supply contracts (3중 fail)
2. KR equity DART entry-side family Tier 4 retire 결정적 강화 ([[feedback_family_retire_kr_post_earnings]] amendment)
3. **다음 우선**: agent path (c) **non-directional volatility event paradigm** — paradigm 101 events cache + OHLCV 재사용 (Phase 0 ~5min)
4. Lesson #32 candidate Q3 §6.2 정식 등록
5. paradigm-architect R-1 verdict tree에 `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` 정식 추가
6. Day 7 baseline 우선 모드 유지

#### Campaign 진행 상태 갱신 (2026-05-19 15:00 KST)
- 누적 graveyards: **101** (+1 정식)
- Inventory-halt 사례: 2 / Substrate-halt 사례: 1
- R-5 시드: 8 unchanged
- Family retire (formal Tier 4): 7 + 1 advisory caution (KR post-earnings/guidance/contract family **4 graveyards 누적 결정적 강화**)
- Lessons: 30 confirmed + Lesson #26 amendment 3 dogfoods + Lesson #27 amendment 5 dogfoods + Lesson #28 5 dogfoods + Lesson #31 confirmed 2 dogfoods + **NEW substrate quarterly distribution audit confirmed 2 dogfoods** + **NEW Lesson #32 candidate 1 dogfood** + Lesson #30 candidate + Lesson #8 amendment candidate
- Verdicts: 2 confirmed + **NEW BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT 정식**
- [[project_paradigm_101_dart_supply_contract_universe_drift]] 신설

---

### 6.13 2026-05-19 15:40 KST paradigm 102 정식 graveyard — non-directional vol expansion conditioning trap + NEW Lesson #33 candidate

**Context**: agent paradigm 101 §Next-step §3 권고 path (c) **non-directional volatility event paradigm** 정식화. paradigm-architect ad-hoc R-1 분리 모드 dispatch (`a174676849b10ac09`). paradigm 101 cache 재사용 (ETA ~3초).

#### paradigm 102 `dart_supply_contract_announce_kr_equity_vol_expansion_5d`
- 가설: 단일판매·공급계약 공시 후 +1d ~ +5d realized vol expansion magnitude (vol_post_5d / vol_pre_30d ≥ 1.5) trigger, **direction-blind univariate magnitude**
- Family-distinct path 정확 통과 — paradigm 101 directional 4 axes 외 magnitude axis
- **Verdict**: `BROAD_FALSIFIED` (conditioning trap, R-1 primary) — counter 101 → **102**

#### R-1 결과

| Cell | n | net_bp | sig_t_ex | mean_vol_ratio | 3-gate |
|---|---|---|---|---|---|
| A focus announce × vr≥1.5 | 311 | +987.1 | **1.95** | 1.99 | **FAIL** (sig_t_ex<2.0) |
| A mirror announce × vr<1.0 | 1,211 | +424.6 | 5.63 | 0.64 | PASS |
| **B baseline non_announce × vr≥1.5** | 4,118 | **+1,073.1** | **6.52** | 2.15 | PASS |
| B baseline × vr<1.0 | 19,058 | +400.2 | nan | 0.62 | n/a |

#### Conditioning trap 결정적 발견

**vol_ratio≥1.5 filter가 |fwd_ret_5d| outcome과 수학적 상관** — A focus 987bp < B baseline_expand 1,073bp = universe baseline mechanics. A mirror도 +424bp positive (universe |return| floor). threshold tweak 복구 불가.

#### NEW Lesson #33 candidate (agent 권고 정식 도출)

**"Magnitude-as-outcome equals conditioning trap"**:
- **Trigger**: trigger filter (magnitude-based) × outcome metric (magnitude-based) 수학적 상관
- **Check**: R-1 4-quadrant에 5번째 cell `B_baseline_same_filter` 추가 의무
- **Verdict**: A_focus_sig_t_excess ≥ B_baseline_same_filter_sig_t_excess + delta(≥1.0) 충족 시 valid / 미충족 시 `BROAD_FALSIFIED_CONDITIONING_TRAP`
- **Distinct from #32**: #32 LEVEL coherence (trigger metric) vs #33 POST-CONDITIONING payoff coherence (outcome metric)
- paradigm 102가 #32 PASS (vol_ratio 1.99 vs 0.96 20×) + #33 FAIL (payoff 987 vs 1,073) **양면 trap 입증**

#### NEW verdict `BROAD_FALSIFIED_CONDITIONING_TRAP` candidate

paradigm-architect R-1 verdict tree에 추가 — magnitude-based trigger × magnitude-based outcome conditioning trap halt.

#### KR equity DART entry-side family retire 5 graveyards 누적 — 4 axes exhausted

| # | Paradigm | Axis | Verdict |
|---|---|---|---|
| 92 | dart_h1_earnings_gap_proxy_long_5d | directional momentum | R-2c 0/5 |
| 93 | dart_h2_guidance_amend_directional_5d | cross-proxy directional | BROAD_FALSIFIED |
| 100 | dart_h2_guidance_amend_mean_reversion_neg_long_20d | mean-reversion | SAMPLE_INSUFFICIENT_TEMPORAL |
| 101 | dart_supply_contract_announce_long_5d | entry-side immediate directional | BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT |
| **102** | **dart_supply_contract_announce_vol_expansion_5d** | **non-directional magnitude** | **BROAD_FALSIFIED (conditioning trap)** |

→ **4 axes exhausted**: directional / mean-reversion / entry-side immediate / non-directional magnitude. **공시 announcing stock 자체에 대한 모든 axis = 영구 retire**.

#### 잔존 family-distinct path (agent 권고)
- (a) external-event non-DART (KIND / FRED / ECOS 정부 source)
- (b) DART event + decorrelated outcome (cross-stock spillover / 섹터 rotation, announce stock 자체가 아닌 영향받는 다른 stocks)
- (c) non-announcement event types (volume shock / 외국인 매수 비율 변화)

#### Cross-proxy (Lesson #29) — inverted (paradigm 101 동형)
- Observable |gap| top33 +1,367bp > bot33 +813bp ✓
- Fundamental freq_6m top33 +1,114bp > bot33 +994bp ✗ inverted (frequent announcer = high-beta company-quality bias)

#### Life-changing 4-dim trap (paradigm 101 동형 false-positive)

| Metric | Value | 4-dim |
|---|---|---|
| trades/yr | 137.4 | PASS |
| edge | +9.87% | PASS |
| sharpe | 10.27 | PASS |
| capital_util | 68.4% | PASS |

**그러나 universe baseline conditioning inheritance** = 진정한 event alpha 아님 (paradigm 101 narrow-scope life-changing FAIL false-positive 동형 재발견).

#### Agent 권고
1. Lesson #33 정식 입안 검토 (paradigm-architect spec hook 의무)
2. Day 7 baseline 우선 모드 유지
3. KR equity DART entry-side family retire 정식 amendment — 5 graveyards 누적 결정적 폐기
4. R-2 자동 진행 금지

#### Campaign 진행 상태 갱신 (2026-05-19 15:45 KST)
- 누적 graveyards: **102** (+1 정식)
- Inventory-halt 사례: 2 / Substrate-halt 사례: 1
- R-5 시드: 8 unchanged
- Family retire (formal Tier 4): 7 + 1 advisory caution (**KR DART entry-side family 5 graveyards 누적 결정적 강화 4 axes exhausted**)
- Lessons: 30 confirmed + 3 amendment confirmed (#26 amendment 3x + #27 amendment 5x + #28 5x + #31 2x + substrate audit CONFIRMED 자격 2x) + 4 candidates (#30 + #32 LEVEL coherence 2 dogfoods + **NEW #33 POST-CONDITIONING payoff coherence 1 dogfood** + #8 amendment)
- Verdicts: 2 confirmed (#29 cross-proxy + NARROW_SCOPE_LIFE_CHANGING_FAIL) + BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT 정식 + **NEW BROAD_FALSIFIED_CONDITIONING_TRAP candidate**
- [[project_paradigm_102_vol_expansion_conditioning_trap]] 신설

---

**END Mid-Q3 Update + Track 3 Final + 2026-05-19 paradigm 97 inventory halt + 2026-05-19 batch paradigm 97/98/99 graveyards + 2026-05-19 paradigm 100 candidates 2x halt + 메타 회고 + 2026-05-19 paradigm 100 정식 graveyard milestone + 2026-05-19 paradigm 101 정식 graveyard universe drift artifact + 2026-05-19 paradigm 102 정식 graveyard conditioning trap** — 다음 candidate (Day 30 baseline 측정 + lifecycle live mode 결과 우선, 2026-05-29+ campaign 재개, **잔존 family-distinct path = external-event non-DART / DART decorrelated outcome / non-announcement event types 3개 한정**).
