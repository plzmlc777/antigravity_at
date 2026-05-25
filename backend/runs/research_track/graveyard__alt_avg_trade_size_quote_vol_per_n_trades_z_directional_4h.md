# GRAVEYARD: paradigm 144 — alt_avg_trade_size_quote_vol_per_n_trades_z_directional_4h

**Counter**: 144
**Phase reached**: R-0 prescreen (HALT — R-1 미실행)
**Verdict**: `R0_HALT_STRUCTURAL_AXIS_DEGENERACY`
**Date**: 2026-05-21 13:25 KST
**Wall clock**: 0.1s

## Hypothesis

- Statistic: `avg_trade_size_USD = quote_volume / count` per 4h bar
  (n_trades count column 144 paradigms 중 0회 사용 — genuinely NEW axis)
- Mechanism: high avg trade size = institutional/whale dominance, low = retail
- 30d rolling z-score per-sym
- Trigger: `|avg_size_z| > 2`
- Direction: `z > +2 → 4h LONG continuation` / `z < -2 → 4h SHORT continuation`
- Universe: 14 alts (12-col klines cache 재사용)

## R-0 Prescreen 결정적 결과 (14/14 syms)

| Gate | Threshold | Result | Pass |
|---|---|---|---|
| Lesson #11 sample density (per-cell pos) | ≥ 30 | 293.2 | ✅ |
| Lesson #11 sample density (per-cell neg) | ≥ 30 | 120.4 | ✅ |
| Lesson #40 z>+2 attainable | 14/14 | 14/14 | ✅ |
| Lesson #40 z<-2 attainable | 14/14 | 14/14 | ✅ |
| Lesson #30 n_syms loaded | ≥ 12 | 14 | ✅ |
| **Lesson #21 sub-finding axis_degeneracy** | corr<0.90 OR resid>0.20 | corr=0.954 AND resid=0.102 | ❌ |

## Lesson #21 sub-finding STRONG_AXIS_DEGENERACY 진단

### 14-sym per-sym correlation (log_qv vs log_cnt)

| Sym | corr(log_qv, log_cnt) | Var(log_ats) / Var(log_qv) |
|---|---|---|
| BTCUSDT | 0.927 | 0.141 |
| ETHUSDT | 0.920 | 0.155 |
| SOLUSDT | 0.943 | 0.114 |
| XRPUSDT | 0.978 | 0.066 |
| DOGEUSDT | 0.969 | 0.090 |
| ADAUSDT | 0.978 | 0.054 |
| AVAXUSDT | 0.941 | 0.133 |
| BNBUSDT | 0.948 | 0.128 |
| LINKUSDT | 0.964 | 0.087 |
| BCHUSDT | 0.947 | 0.121 |
| FILUSDT | 0.952 | 0.096 |
| LTCUSDT | 0.968 | 0.084 |
| NEARUSDT | 0.949 | 0.101 |
| WIFUSDT | 0.979 | 0.056 |
| **Mean** | **0.954** | **0.102** |
| **Min** | 0.920 | 0.054 |
| **Max** | 0.979 | 0.155 |

### 해석

- `quote_volume`과 `count` (n_trades)는 거의 동일한 정보 — 14/14 syms corr 0.92~0.98, mean 0.954
- `avg_trade_size = quote_volume / count`의 분산은 quote_volume 자체 분산의 **5.4~15.5% (mean 10.2%)**만 표현
- 즉 axis는 활동강도와 거의 독립인 ~10% 잔여 변동 = trivial near-noise residual
- mechanism 가설 "institutional vs retail proxy"는 **실증적으로 axis가 그 정보를 운반하지 않음**

### Lesson #54 paradigm 137 antipattern 강한 일치

- paradigm 137 Yang-Zhang Parkinson/close = same-bar same-substrate ratio (이미 BROAD_FALSIFIED)
- paradigm 144 quote_volume/count = same-bar same-substrate ratio (동일 4h bar 두 raw column)
- 구조적 동형 → R-1 dispatch 시 ~99% BROAD_FALSIFIED 예측
- Lesson #21 sub-finding pre-execution halt = R-1 자원 절약 의도된 작동

## Lesson Confirmations

### Lesson #54 same-bar same-substrate ratio antipattern — 3rd dogfood

| Dogfood | Paradigm | Verdict |
|---|---|---|
| 1 | paradigm 137 Yang-Zhang Parkinson/close | R-1 BROAD_FALSIFIED |
| 2 | (이전 confirmed-elevation 자격 이전 사례) | confirmed elevation 발의 |
| **3** | **paradigm 144 quote_vol/count R-0 STRUCTURAL HALT** | **R-0 STRUCTURAL_AXIS_DEGENERACY** |

→ Lesson #54 정식 CONFIRMED 유지 + Lesson #21 sub-finding ↑ formal sub-pattern 승급 자격

### Lesson #21 sub-finding magnitude-ratio prescreen — 2nd dogfood

| Dogfood | Paradigm | Detection |
|---|---|---|
| 1 | (이전 first sub-finding 발견 사례) | candidate 발의 |
| **2** | **paradigm 144 corr 0.954 + resid 0.102** | STRUCTURAL_AXIS_DEGENERACY HALT 첫 사용 |

→ Lesson #21 sub-finding CONFIRMED-eligible 자격 (2회 양방향 dogfood)

## NEW Lesson #58 candidate

**Same-bar same-substrate ratio R-0 prescreen 의무화**

R-0 prescreen 단계에서 ratio statistic의 두 component (분자 A, 분모 B)에 대해:

1. `corr(log A, log B)` 측정 (위쪽 tail bounded 변수는 raw 사용)
2. `Var(log(A/B)) / Var(log A)` residual variance share 측정

기준값:
- **STRUCTURAL_AXIS_DEGENERACY HALT**: mean corr ≥ 0.90 **AND** mean residual share ≤ 0.20
- **WARNING ONLY** (dispatch 허용): 0.80 ≤ mean corr < 0.90

Lesson #54 family (same-bar same-substrate ratio)에서는 위 prescreen 의무 적용. 다른 family (cross-substrate, cross-bar, cross-frame)는 informational only.

## Family-distinct 입증 (zero novelty axis 비교)

| Paradigm | Distinction |
|---|---|
| paradigm 72 taker_buy_vol | taker-side action vs total quote_vol / count (no taker filter) |
| paradigm 127/128 R-5 volume burst | 1m binary burst vs 4h continuous ratio z |
| paradigm 140 CVD ratio | directional flow vs trade size |
| paradigm 142-v2 quote_vol imbalance z | taker_buy_quote/quote (flow direction) vs quote_vol/count (size aggregation) |
| paradigm 143 quote_vol percentile | imbalance percentile vs avg_size z-score |
| paradigm 137 Yang-Zhang | **Lesson #54 precedent — same-bar same-substrate ratio antipattern** |
| Lesson #57 family | taker filter 무관 (paradigm 144 = total quote_vol 사용) |

→ axis novelty 입증 OK이나 **mechanism content 부재** (axis가 정보를 운반하지 않음)

## Lessons applied

- Lesson #11 sample density: PASS (293.2 / 120.4 per-cell)
- Lesson #19 4-quadrant SNT: N/A (R-1 미실행)
- Lesson #21 sub-finding magnitude-ratio prescreen: **FAIL → R-0 HALT**
- Lesson #30 data_window_ratio: 1.00 (full window 14 syms)
- Lesson #40 structural threshold: PASS (z-score unbounded)
- Lesson #44 amendment 27th xref: 7개 family 비교 (72 / 127-128 / 140 / 142-v2 / 143 / 137 / funding family)
- Lesson #45 no HMM/unsupervised: compliant (deterministic z-score)
- **Lesson #54 same-bar same-substrate ratio**: 3rd dogfood — STRUCTURAL HALT
- Lesson #57 family evasion: compliant (no taker filter)
- **NEW Lesson #58 candidate**: same-bar same-substrate ratio R-0 prescreen 의무화

## 영구 인프라 변경

**Zero new infra** — 12-col klines cache 재사용. R-0 prescreen 로직 일반화 가능 (Lesson #58 candidate 후속).

## 산출물

- `backend/scripts/research/paradigm144_r0_prescreen.py` (260 lines)
- `backend/runs/research_track/alt_avg_trade_size_quote_vol_per_n_trades_z_directional_4h/r0_prescreen.json`
- `backend/runs/research_track/graveyard__alt_avg_trade_size_quote_vol_per_n_trades_z_directional_4h.md` (본 파일)
- `backend/runs/research_track/INDEX.json` paradigm 144 entry + counter 143 → 144

## Counter / Streak

- 누적 graveyards: **144** (143 → 144, R-0 HALT 사례 carries counter per memory convention)
- non-PASS streak: **16-streak** (129-144)
- R-5 시드 10 LIVE (변화 없음)
- R-5 yield: **6.94% (10/144)**
- Lessons: 33 confirmed + 9 candidates (Lesson #58 추가 candidate)
- D-Day 2026-06-03 D-13

## 다음 candidate 권고 (axis 메모리 [Persistence over efficiency])

paradigm 144 R-0 STRUCTURAL HALT는 axis novelty (n_trades 첫 사용) 가 mechanism content를 보장하지 않음을 결정적으로 입증. 이후 candidate는 다음 중 우선:

1. **n_trades column NOT as ratio denominator** — n_trades 자체를 z-score 또는 percentile rank 변환 (count axis 독립 신호)
2. **Cross-substrate ratio** (same-bar same-substrate 회피) — 예: 24h count vs 1h count ratio (frame mismatch), 또는 cross-symbol count rank
3. **Funding-decoupled non-taker venue arbitrage** — paradigm 103 cross_exchange_funding_spread family path 잔여 3개 중 illiquid venue 또는 cross-ex OI divergence

권고 1순위: **`alt_n_trades_count_30d_zscore_directional_4h`** — count 자체 z-score (ratio 회피). corr(log_qv, log_cnt) 0.95+ 이므로 count 단일 axis는 quote_volume 단일 axis와 거의 동일 → axis 자체가 알파 운반체일 가능성 낮음. 따라서 권고 2순위로 격하.

권고 1순위 수정: **`alt_count_z_residual_after_quote_vol_z_directional_4h`** — count z-score - quote_vol z-score (cross-component orthogonalization residual) = avg_trade_size axis와 동등하나 명시적 residual 정의. 또는 count z-score after regressing out quote_vol z (실질적 Lesson #21 sub-finding 회피 path). 단 이는 paradigm 144와 사실상 동등 statistic → axis-distinct 자격 미달.

**최종 권고**: **funding-decoupled non-taker venue arbitrage path 진입** — Lesson #54 family 완전 회피, cross-substrate 보장.
