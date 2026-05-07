# premium_dispersion — Graveyard Note (2026-05-06, 26th paradigm)

## 설계
funding_dispersion (8h cross-section) + premium_index_zscore (per-symbol time-series) 의 직교 변형. 14종 daily premium close wide df 에서 매일 cross-section z-score 계산. mode='fade' (overcrowded → SHORT) 우선.

## R-1 SOL sweep (fade)
- z=0.5 h=10: alpha **+122** sharpe **+1.19** PF 1.58 mdd 40.2 (43 trades) ⭐ best
- z=1.0 h=3: alpha +43 sharpe +0.41
- z=1.5 h=10: alpha +53 sharpe +0.63 (12 trades)
- follow 모드 모든 sweep 부정적

R-1 marginal PASS but mdd 40 > 28 cutoff.

## R-2 multi-symbol (10 paper-pool, fade z=0.5 h=10)
- **alpha pos: 5/10 (50%)** — funding_dispersion 13/14 대비 결정적 약함
- sharpe pos: 5/10
- alpha mean +35.76

| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades |
|---|---|---|---|---|---|---|
| **DOGEUSDT** | **+225.75** | **+1.61** | 31.2 | 50.0 | **1.95** | 40 |
| **SOLUSDT** | +122.49 | +1.19 | 40.2 | 48.8 | 1.58 | 43 |
| HBARUSDT | +61.09 | +0.47 | 33.7 | 35.6 | 1.22 | 45 |
| ETCUSDT | +42.42 | +0.19 | 47.7 | 52.3 | 1.08 | 44 |
| LDOUSDT | +4.00 | -0.22 | 70.1 | 28.8 | 0.92 | 59 |
| AXSUSDT | -5.67 | +0.12 | 72.0 | 27.4 | 1.08 | 62 |
| COMPUSDT | -4.39 | -0.23 | 61.7 | 37.7 | 0.91 | 53 |
| LINKUSDT | -20.76 | -0.86 | 78.1 | 31.5 | 0.75 | 54 |
| AVAXUSDT | -23.49 | -1.67 | 84.8 | 27.1 | 0.59 | 59 |
| UNIUSDT | -43.89 | -3.19 | 92.3 | 27.8 | 0.34 | 54 |

DOGE 와 SOL 만 outlier — 5/10는 §3-E 기준 약함.

## R-3 perm test n=200 (fade z=0.5 h=10, top 2)
| Symbol | Real α | perm_p | rand_mean | rand_std | σ | Result |
|---|---|---|---|---|---|---|
| **DOGEUSDT** | 225.75 | **0.0400** | 57.80 | 75.85 | **2.2σ** | ✅ PASS |
| SOLUSDT | 122.49 | 0.2750 | 90.01 | 103.42 | 0.3σ | ❌ FAIL |

**1/2 perm PASS only**. random_std 75-103 매우 큼 — premium dispersion 신호는 noisy.

## §3-G family-extension 문제
- premium_index_zscore (24th seeded ⭐⭐⭐) **DOGEUSDT alpha 348 / sharpe 3.15 / perm 9.0σ**
- premium_dispersion (this) **DOGEUSDT alpha 226 / sharpe 1.61 / perm 2.2σ**

같은 데이터 도메인(DOGE daily premium)이지만 weaker transform. premium_index_zscore 시드가 이미 DOGE premium signal의 ~95% 정보 포착. premium_dispersion은 weak residual.

funding_carry → funding_dispersion 패턴은 둘 다 시드되었으나, 그 때 ETC 가 premium_dispersion DOGE 보다 훨씬 강했음 (perm 0.000 vs 0.040, 5σ vs 2.2σ). 본 paradigm은 §3-G family weak residual 패턴에 부합.

## 비교 — paradigm 강도

| Paradigm | Best perm σ | Best alpha | Best sharpe | R-2 alpha pos | Strict cutoff |
|---|---|---|---|---|---|
| **funding_dispersion** (seeded) | strong (perm 0.000 200/200) | **+138 ETC** | **+3.50** | **13/14** | 4/5 |
| **premium_index_zscore** (seeded) | **9.0σ DOGE** | **+348** | **+3.15** | 9/10 | 5/5 |
| **premium_dispersion** (graveyard) | **2.2σ DOGE** | +226 | +1.61 | **5/10** | 2/5 |

## R-5 SKIPPED → graveyard

근거:
1. R-2 alpha 5/10 catastrophically weak vs funding_dispersion 13/14 — 본질적으로 paradigm-level robust 아님
2. R-3 1/2 PASS only, DOGE 2.2σ 매우 약함
3. DOGE premium은 premium_index_zscore (perm 9σ) 시드로 이미 caught
4. 26 paradigms 후 결정: cross-section dispersion은 funding rate에서만 강함, premium에서 약함 — funding rate clamping이 cross-section signal 강도에 기여하는 듯 (premium은 raw distribution noise 더 큼)

## Lesson
- cross-section dispersion paradigm은 measurement type에 강하게 의존
- funding rate (clamped, settled) → strong cross-section signal
- premium index (raw, real-time) → weak cross-section signal (per-symbol time-series가 더 강함)
- §3-G family-extension 안티패턴 추가 사례: premium_index_zscore 시드된 후 premium 도메인 변형은 weak residual
- 결론: **다음 paradigm 시도는 새 데이터 도메인 또는 multi-domain joint signal 필요**. premium/funding/OI 도메인 saturated.
