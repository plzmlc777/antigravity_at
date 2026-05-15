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

---

**END Mid-Q3 Update** — 다음 candidate (Tier 1 A) R-1 즉시 시도 가능.
