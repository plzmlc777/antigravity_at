# Paradigm 94 — `cross_asset_volume_concentration_alt_long_1d` R-1 결과

**Dispatch**: ad-hoc user explicit, 2026-05-18 22:56 KST
**Wall-clock**: 1.49 min (foreground synchronous, no background spawn)
**Verdict**: 🪦 **BROAD_FALSIFIED_FEE_FLOOR** (+ direction inversion side discovery)

---

## 핵심 결과 한 줄

> BTC volume share z<=-1.5 → alt LONG 가설은 **focus quadrant 데이터 부족 + 16bp fee floor 미달 + mirror quadrant 강하게 inverse 입증**으로 graveyard. 본질적으로 short-data 한계 + direction 본래 가설 반대 입증.

---

## 1. r0 inventory check

**Universe 가용성** (local DB 1m OHLCV):

| Group | Symbols | Days 평균 |
|---|---|---|
| BTC (signal) | BTCUSDT | **143** (2025-12-22 → 2026-05-13) |
| 13 alts (LONG) | ADA, AVAX, BCH, BNB, DOGE, ETH, FIL, LINK, LTC, NEAR, SOL, WIF, XRP | 12종 798 + ADA **143** |
| 12 보강 (denom only) | AXS, HBAR, LDO, COMP, UNI, PYTH, TON, ETC, ICP, JUP, WLD, 1000LUNC | 798 |

- **BTC + ADA 143 days = 본질적 binding constraint** (다른 24 syms는 798 days이나 BTC signal이 143 days로 제한)
- Universe intersection 후 **common dates = 101 days** (2025-12-23 ~ 2026-04-02)
- 30d rolling z 워밍업 후 usable = **72 days** (2026-01-21 ~ 2026-04-02)
- **Mint host 미해석** (`ssh: Could not resolve hostname mint`) → local 실행으로 전환. spec 의 Mint commit 항목은 local commit으로 대체.

---

## 2. Sample density 실측 (Lesson #11 prescreen dogfood)

**Focus 트리거 sweep** (cutoff fallback chain 동작):

| cutoff | n_triggers | n_trades (×13 alts) | 결정 |
|---|---|---|---|
| z ≤ −1.5 (default) | **1** day (2026-04-01) | ~13 | **per-cell < 30 → fallback** |
| z ≤ −1.2 | 5 days | 62 | **chosen** (≥30 floor 통과) |
| z ≤ −1.0 | 6 days | 75 | (덜 strict, 미선택) |

**Mirror 트리거**: z ≥ +1.5 → 4 days / 52 trades.

**Per-cell density (focus, chosen cutoff −1.2)**:
- Per-symbol: **n=4-5** (모든 13 alts)
- Per-quarter: 2026Q1 n=39 / 2026Q2 n=23 / 2025Q4 n=0 (insufficient)
- → Lesson #11 antipattern realized: per-sym CI uninformative width, per-quarter Q4 fold 측정 불가.

---

## 3. Three-gate verdict (focus 8bp, primary OBS proxy)

| Gate | Threshold | Observed | PASS |
|---|---|---|---|
| signal_t_excess ≥ +2.0 | +2.0 | **+0.149** | ❌ |
| bootstrap_ci_lower > 0 bp | > 0 | **−70.9 bp** | ❌ |
| perm_p_one_sided_above ≤ 0.10 | ≤ 0.10 | **0.459** | ❌ |

**Focus 8bp 통계**:
- n_trades = 62, gross = +11.28 bp, **net = +3.28 bp**, t = +0.08, win = 35.5%, sharpe = +0.011
- bootstrap CI = [−70.9, +81.6] bp (very wide, prob_pos = 0.53)

**Focus 50bp stress**:
- net = −38.72 bp, sigex = −0.23 → fee saturation immediate.

**Fee floor 판정**:
- focus **gross +11.28 bp < 16 bp fee floor** → BROAD_FALSIFIED_FEE_FLOOR primary verdict.

---

## 4. Concentration Gate (Lesson #16, focus 8bp)

| Metric | Threshold | Observed | PASS |
|---|---|---|---|
| q_pos_t_ratio | ≥ 0.50 | **0.50** (1/2 measurable) | borderline |
| sym_ci_pos_ratio | ≥ 0.30 | **0.00** (0/13) | ❌ |
| n_sym_ci_pos | ≥ 3 | **0** | ❌ |
| **Overall** | — | — | ❌ |

**Per-quarter breakdown**:
- 2025Q4: n=0 (insufficient, 데이터 시작이 12/23) — measurement-impossible
- 2026Q1: n=39, mean=**+69.5 bp**, t=+1.35 (positive)
- 2026Q2: n=23, mean=**−109.1 bp**, t=−2.14 (significant negative — Q2가 평균을 끌어내림)

**Per-symbol**: 0/13 alts ci_pos. n=4-5 per sym 으로 CI 폭이 −231~−413 bp 까지 음수 방향 광활하여 신호 검출 불능.

---

## 5. Symmetric Negative Test (Lesson #19) — **DIRECTION INVERSION 결정적 발견**

| Quadrant | n_trades | net_mean (bp) | t | sigex | perm_p_above | CI lower | CI upper |
|---|---|---|---|---|---|---|---|
| focus (z≤−1.2 → alt LONG) | 62 | +3.28 | +0.08 | +0.149 | 0.459 | −70.9 | +81.6 |
| **mirror (z≥+1.5 → alt LONG)** | **52** | **+222.0** | **+2.72** | **+2.76** | **0.002** | **+74.4** | **+389.9** |

🔥 **Mirror quadrant은 three-gate 전면 PASS**:
- signal_t_excess = +2.76 ≥ 2.0 ✓
- bootstrap_ci_lower = +74.4 bp > 0 ✓
- perm_p_one_sided_above = 0.002 ≤ 0.10 ✓

→ **본래 가설 (BTC share 압축 = alt rotation)이 반전 입증**. 데이터는 BTC share **HIGH** 일 때 (BTC 거래량 집중 = 시장 risk-on/uncertainty regime) **다음날 alt LONG +222bp** 를 시사. 그러나 n_triggers=4 (4 days만 트리거)로 sample density 극히 sparse — direction inverted 가설이라도 **자체 R-1로 별도 검증 필요** ("trigger swap antipattern" lesson #69 mirror SHORT 사례 적용).

**Verdict sub-classification**: `BROAD_FALSIFIED_FEE_FLOOR` (primary, focus gross<16bp) **+ `DIRECTION_INVERTED_MIRROR_PASS_SPARSE`** (secondary side discovery, mirror PASS but n=4 triggers).

---

## 6. Cross-proxy 측정 (Lesson #29)

**Fund proxy track (BTC absolute USD-volume 30d z)**:

| Cutoff | n_triggers | chosen |
|---|---|---|
| z ≤ −1.5 | 3 | ✓ |
| z ≤ −1.2 | 6 | |
| z ≤ −1.0 | 8 | |

**Fund focus 8bp**: n_trades=39, **gross = −12.3 bp** (음수), net = −20.3 bp, sigex = −0.56, perm_p_above = 0.706 → 가설 자체 falsify (BTC 거래량 절대 작은 날 alt는 오히려 down).

**Fund mirror 8bp**: n_trades=91, gross = −64.1 bp, net = −72.1 bp, sigex = −1.12 → BTC 거래량 절대 큰 날 alt도 down (high BTC vol → alt suppression).

**Cross-proxy 교집합**:
- obs focus dates = 5, fund focus dates = 3, intersection = 1
- Jaccard = 0.143 → **non-redundant (≥0.7 redundancy cutoff 통과)**

→ Lesson #29 결과: **두 proxy 독립**, 단순 ratio z (obs) ≠ absolute flow z (fund) → 형식적 cross-proxy 통과. 단, 양 proxy 모두 fund 트랙은 focus/mirror 음수, obs 트랙은 focus 음수+ mirror만 양수 → **`SINGLE_PROXY_TRAP_OBS_MIRROR_ONLY`** 패턴 (cross-proxy validation 실질 미통과).

---

## 7. Family-distinct 확인

| 회피 대상 family | 본 paradigm 와 distinction |
|---|---|
| `5m_microstructure_single_domain_alpha_family` (advisory caution) | daily aggregation, not 5m |
| `kr_equity_post_earnings_guidance_directional_momentum_family` (Tier 4) | crypto perp |
| `geometric_path_metrics_family` | volume share ratio, not path |
| `funding_oi_joint_squeeze_family` | volume only |
| `btc_eth_5m_corr_breakdown_family` | daily, no correlation |

→ **family-distinct, new transform class** (cross-asset volume share boundary z). graveyard 사유는 family pattern 이 아닌 **데이터 부족 + 가설 방향 inverted** 단독 paradigm 단위 fail.

---

## 8. Final verdict

🪦 **`BROAD_FALSIFIED_FEE_FLOOR` (primary) + `DIRECTION_INVERTED_MIRROR_PASS_SPARSE` (secondary)**

**근거**:
1. Focus quadrant (z≤−1.2 LONG) **gross +11.28 bp < 16 bp fee floor** → 통계 verdict 무관 사전 falsify
2. Mirror quadrant (z≥+1.5 LONG) **three-gate ALL PASS** (sigex +2.76, CI lower +74 bp, perm_p 0.002) BUT n_triggers=4 → 본래 가설 반대 입증 + Lesson #69 trigger_swap_antipattern 적용 (별도 R-1 검증 의무, 자동 mirror 승계 금지)
3. Concentration Gate 명백 FAIL (sym_ci_pos_ratio=0.00, q_pos_t Q1/Q2 부호 반대)
4. Fund proxy track 양 quadrant 모두 음수 → `SINGLE_PROXY_TRAP_OBS_MIRROR_ONLY` (cross-proxy validation 실질 미통과)

**핵심 메커니즘 진단**:
- **데이터 window 본질적 부족**: BTC 1m 143 days만 local DB 보유 → 30d warmup 후 72 days 만 usable → 모든 분석 sample 한계 봉착 (Lesson #11 prescreen dogfood 성공)
- **방향 가설 inverted side discovery**: `btc_share_high_alt_long_1d` 가설 후보 (mirror quadrant +222bp/+2.76σ), 단 sparse triggers → 별도 R-1 + 데이터 확장 (≥1년) 필요. 자동 승계 금지.

---

## 9. 신규 lesson 후보

**Lesson #30 candidate (잠정)**: short-data ad-hoc R-1 에서 mirror quadrant PASS 발견 시 자동 graveyard 없이 **side discovery 명시 + 별도 정식 R-1 발의 의무**. mirror PASS = direction inversion 입증 약식 신호, 데이터 확장 시 재검증 가치 보존 (Lesson #69 trigger swap antipattern 보완: mirror **trigger 자체 inversion** 은 trigger swap 과 다른 차원).

**Lesson #31 candidate (잠정)**: **fee floor 16 bp gate 가 three-gate 우선** 적용 (현 verdict logic). 정당 → focus quadrant gross < fee floor 이면 sigex/CI/perm_p 통계 무관 자동 graveyard (직관적 우선순위). 본 paradigm 첫 dogfood.

---

## 10. 산출물

- `r1_spec.md` — 본 paradigm 사양
- `r1_metrics.json` — 전체 metrics dump (410 lines)
- `r1_summary.md` — 본 문서
- `r1_script.py` — 실행 스크립트 사본 (`backend/scripts/research/cross_asset_volume_concentration_alt_long_1d_r1.py` 원본 동기)
- `backend/runs/research_track/INDEX.md` — paradigm 94 row 추가 예정

---

## 11. HALT confirmed

✅ **R-2 미진행 명시**. 본 ad-hoc R-1 dispatch 종료. 추가 실행 = 사용자 명시 follow-up invocation 필요.

- `feedback_agent_long_background_polling.md` 준수: foreground synchronous, background task spawn 0건
- `feedback_timestamp_kst_suffix.md` 준수: 최종 KST 명시

---

## 12. 다음 단계 권장 (사용자 검토용)

| 옵션 | 설명 | ETA |
|---|---|---|
| **A) 본 paradigm 종결** | graveyard 보존, 후속 발의 보류 (Day 7 baseline 2026-05-21 우선 모드 유지) | 0 |
| **B) BTC + ADA 1m 데이터 백필** | 798 days로 확장 후 same R-1 재실행 (mirror quadrant 검증 정식화 + Lesson #11 sample 해소) | data backfill 30~60 min + R-1 1~2 min |
| **C) Mirror direction-flip 별도 R-1 발의** | `cross_asset_volume_concentration_alt_long_1d_mirror` (z>=+1.5 LONG) 단독 paradigm으로 발의 — but data 한계 동일하므로 **B 필요조건** | B 선행 |
| **D) 본 결과로 lesson #30+#31 codify** + Q3 큐 §6.2 update | Lesson 정식 승급 (mirror PASS side discovery 처리 + fee floor 우선) | 5~10 min |

권장: **A (즉시 종결) + D (lesson 문서화)**. B/C 는 데이터 백필 후 별도 ad-hoc 발의.
