# Graveyard Note — `pre_funding_window_divergence_5m_alt_240m` (82nd R-1 graveyard)

**Phase**: R-1 BROAD_FALSIFIED (Lesson #19 정확 적용)
**Date**: 2026-05-15 turn 6
**Type**: E (empirical)
**Wall-clock**: 7.8s R-1 (foreground inline, 4-quadrant single batch)

## 가설

Binance Futures USDT-M 8h funding settlement boundary (00:00 / 08:00 / 16:00 UTC) **30-60분 전 pre-event window (−60min..−30min)** 에서 premium 5m z-velocity (Δ premium z over W)와 OI 5m direction (sign(Δ OI z over W))이 **반대 부호 (divergence)** 발생 시, settlement 직후 premium 정상화 + OI 압력 해소가 일어나면서 240m hold LONG/SHORT alpha 발생 (pre-event flow timing 아비트라지).

## 4-Quadrant Symmetric Negative Test 결과 (R-1 한 batch)

| Quadrant | (pv_z sign, oi_dir) | Action | n | obs_mean_bp | sig_t_excess | ci_lower_bp | perm_p_two | 3-gate |
|---|---|---|---|---|---|---|---|---|
| **A focus** | (pv↓, oi↑) | LONG | 2,692 | −4.42 | +1.06 | −11.03 | 0.883 | **FAIL** |
| A mirror | (pv↓, oi↑) | SHORT | 2,692 | −11.58 | −0.75 | −18.97 | 0.189 | **FAIL** |
| **B same-sign** | (pv↑, oi↓) | SHORT | 2,625 | −4.85 | +0.74 | −12.28 | 0.784 | **FAIL** |
| B mirror | (pv↑, oi↓) | LONG | 2,625 | −11.15 | −0.69 | −18.10 | 0.237 | **FAIL** |

**Verdict**: BROAD_FALSIFIED (4/4 cells three-gate FAIL).

핵심 진단:
- A focus & B same-sign mean (−4.4, −4.9bp)이 mirror들 (−11.6, −11.2bp) 대비 fee **정확히 8bp 차이** = direction-bet 자체에 정보 없음. 양 방향 모두 ~−4bp만큼 cost-net 손해 = 8h boundary entry timing이 noise.
- 모든 sig_t_excess ∈ [−0.75, +1.06] → fee-drift null 대비 신호 분리 zero.
- 모든 ci_lower < 0 (A focus 최선 −11bp).

## Concentration Gate (Lesson #16) 결과 — A focus & B same-sign

**A focus**:
- q_pos_t_ratio = 2/7 = 0.29 (FAIL, floor 0.5)
- sym_ci_pos_ratio = 0/13 = 0.00 (FAIL, floor 0.30) — **13개 alt 전부 ci_lower < 0**
- Per-quarter mean_bp: 2024Q4 +4.3 / 2025Q1 −5.2 / Q2 −10.7 / Q3 −9.3 / **Q4 +9.4** (이상치) / 2026Q1 −9.9
- 어느 alt도 ci 양수 없음 → cherry-pick 여지 zero (paradigm 81의 cell 4 3/13 cluster와 달리 본 paradigm은 완전 균질 음수)

**B same-sign**:
- q_pos_t_ratio = 1/7 = 0.14 (FAIL)
- sym_ci_pos_ratio = 0/13 = 0.00 (FAIL)
- 2026Q1 mean −23bp t=−3.31 강한 음수 = mechanism 반대 방향

## Sample density (Lesson #11) 검증

- 1,624 boundaries × 13 alts = 21,112 raw rows
- valid 20,879 → divergence trigger 5,317 (25.5%)
- per-quadrant n ≈ 2,625-2,692 ≫ Lesson #11 floor 30
- **Sample density 충분 — mechanism falsification confirmed, sample issue 아님**

## Fee floor (Lesson #10) 검증

- gross |return| median = **84.78 bp** ≫ fee floor 16bp ✓
- fee floor 통과했음에도 mechanism 부재 → 가격 변동성은 있으나 directional 정보 없음

## 5-axis Novelty 사후 검증

| Axis | 평가 | 결과 |
|---|---|---|
| Data source | premium 5m + OI 5m (KNOWN) | known |
| Statistic | divergence-at-event (sign mismatch) | NOVEL |
| Time scale | event-relative pre-window (−60..−30) | NOVEL |
| Universe | 14-alt cross-sym | known |
| Mechanism | pre-event flow timing arbitrage | NOVEL |

3/5 NOVEL이었으나 → **사후 결과**: pre-event flow timing 가설은 directional signal로 작용하지 않음. settlement boundary는 funding mechanism상 fee 정산 timing일 뿐 alpha-generating event 아님.

## 사용된 데이터

- premium 5m joblib (Mint `~/auto_trading/backend/runs/premium_index/{SYM}_premium_5m.joblib`, 2024-05~2026-05 730d, 14 syms)
- OI 5m joblib (Mint `~/auto_trading/backend/runs/microstructure/{SYM}_full_metrics.joblib`)
- OHLCV 1m joblib cache (Mint `~/auto_trading/backend/runs/ohlcv_cache/{SYM}_1m.joblib`, 2.4yr)
- backfill 0 (모두 보유)

## Lesson #19 정확 적용 (재확인)

paradigm 80 (oi_premium_5m_decoupling, 5m premium z × 5m OI z **level** joint) broad-falsified에 이어 본 paradigm 82 (5m premium z-**velocity** × 5m OI **direction** at **pre-funding event** joint divergence) 또한 broad-falsified.

- Lesson #19 R-1 본체 4-quadrant 한 batch 측정 → 4/4 FAIL 즉시 결판
- mirror dispatch 시간 낭비 회피 (mirror도 정확히 fee 8bp 더 음수 = direction-bet 자체에 정보 없음 sanity check 동시 확정)
- Concentration Gate (Lesson #16) 0/13 alts ci_pos = 완전 균질 음수, **paradigm 81 cell 4의 3/13 cherry-pick (lesson #20)와 본질적으로 다른 noise 패턴**

## 5m premium × OI joint event 공간 가족 retire 후보 (paradigm 80 + 82 누적)

- paradigm 80: 5m premium z × 5m OI z **level** joint (4-quadrant broad-falsified)
- paradigm 82: 5m premium z-**velocity** × 5m OI **direction** at pre-funding event (4-quadrant broad-falsified)
- 두 paradigm 모두 5m premium × OI joint event를 directional signal로 활용 시도 → **broad-falsified**
- 그러나 single-domain premium 또는 single-domain OI는 여전히 유효 (paradigm 21 oi_price_decoupling 1d seed + premium_index_zscore/premium_velocity_zscore seeded). joint event 차원의 family-retire는 §6.4에서 검토 — premium × OI joint 5m 차원 추가 시도는 새 feature transform (premium acceleration / OI dispersion across exchanges / mark-index separate legs) 등 다른 statistic class에서만 허용.

## 메타 인정 강화 (paradigm 81에 이어)

51 → 52 R-1 graveyards. 5% PASS rate 유지. **단순 z-score/velocity/regime/joint-event/event-anchored single-signal paradigm 공간 사실상 소진**. 본 paradigm은 statistic class novelty (divergence statistic) + time scale novelty (event-relative pre-window) 2 NOVEL axes 도전했으나 mechanism 미작동.

진정 frontier는 (a) genuinely creative novel features brainstorming, (b) 새 데이터 도메인 (WS 자체 기록 60+일 누적, on-chain), (c) Day 7 baseline (2026-05-21) 우선 검증 — 추가 단순 paradigm dispatch ROI 매우 낮음.

## 산출물

- `r1__metrics.json` (1,500+ lines, 4-quadrant per-quarter + per-symbol concentration emit)
- `r1__script.py` (재현 가능 사본)
- `pre_funding_window_divergence_5m_alt_240m_r1.py` (executable on Mint)

## 다음 단계

- **R-2 진행 금지** (BROAD_FALSIFIED verdict)
- magnitude threshold sweep (θ_pv=1.0, θ_oi_rel=20bp stricter) 재시도는 sample 줄이고 cherry-pick risk만 증가 — 별도 paradigm으로 새 가설 필요 (Lesson #19 pattern + lesson #20 narrow-scope 정신)
- §6.5 paradigm 82 row 추가 (orchestrator turn)
- 메타 인정: Day 7 baseline (2026-05-21) 우선
