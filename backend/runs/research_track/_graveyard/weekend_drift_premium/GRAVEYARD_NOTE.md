# weekend_drift_premium — Graveyard (2026-05-06, 28th paradigm)

> §3-G family-extension of premium_index_zscore + 모든 candidates 이미 다른 paradigm으로 시드됨. 5/5 perm PASS이지만 σ moderate (1.9-3.9σ vs premium 5-9σ).

## 설계
원래 가설: 24/7 crypto market에서 weekend institutional arb desk 부재 → premium drift → Mon 정상화 mean-reversion.

**가설 검증 결과**: fade(mean-revert) 모드 catastrophic, **follow(momentum) 모드 작동**. → 가설 wrong, 실제로는 weekend에 premium drift CONTINUES (not reverts). Friday entry + premium follow가 paradigm essence.

## R-1 SOL DoW comparison (follow z=1.5 h=3)
| dow | alpha | sharpe | trades |
|---|---|---|---|
| Mon (0) | +22 | -1.09 | 5 |
| Tue (1) | +56 | +0.76 | 8 |
| Wed (2) | +52 | +0.70 | 8 |
| **Thu (3)** | **+111** | **+2.78** | 7 (peak) |
| **Fri (4)** | **+70** | **+1.66** | 7 |
| Sat (5) | +60 | +1.08 | 10 |
| Sun (6) | +16 | -1.47 | 8 |

Pattern: **Thu/Fri/Sat "pre-weekend cluster" 강함**, Mon/Sun 약함. Thursday 최강이지만 §3-F selection bias risk → Friday entry로 R-2 진행.

## R-2 multi-symbol Friday follow z=1.5 h=3
| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades | Cutoff |
|---|---|---|---|---|---|---|---|
| **HBAR** | +115.73 | +1.76 | 8.4 | 75.0 | 6.48 | 8 | 3/5 |
| **AXS** | +100.91 | **+2.59** | **0.0** | **100.0** | **∞** | 5 | 4/5 |
| **LDO** | +115.60 | +1.54 | 14.7 | 66.7 | 3.53 | 9 | 3/5 |
| **UNI** | +91.82 | **+2.15** | 1.6 | 85.7 | 30.35 | 7 | 4/5 |
| **DOGE** | +84.95 | **+2.49** | **0.0** | **100.0** | **∞** | 5 | 4/5 |
| AVAX | +99.03 | +1.53 | 15.1 | 75.0 | 3.80 | 8 | 3/5 |
| SOL | +70.23 | +1.66 | 4.1 | 57.1 | 5.64 | 7 | 3/5 |
| ETC | +82.97 | +1.22 | 14.6 | 66.7 | 2.92 | 9 | 3/5 |
| LINK | +54.00 | +0.80 | 14.3 | 75.0 | 2.00 | 8 | 3/5 |
| COMP | +22.29 | -0.39 | 43.4 | 60.0 | 0.71 | 10 | 1/5 |

- **alpha pos: 10/10**, sharpe pos: 9/10, alpha mean **+83.75**

## R-3 perm test n=200 (Friday follow z=1.5 h=3)
| Symbol | Real α | perm_p | rand_mean | rand_std | σ |
|---|---|---|---|---|---|
| HBAR | 115.73 | **0.0000** | 49.17 | 17.17 | **3.9σ** |
| AXS | 100.91 | 0.0050 | 41.15 | 19.91 | 3.0σ |
| UNI | 91.82 | 0.0150 | 37.25 | 19.85 | 2.7σ |
| LDO | 115.60 | 0.0200 | 51.22 | 25.10 | 2.6σ |
| DOGE | 84.95 | 0.0400 | 46.59 | 20.46 | 1.9σ |

**5/5 perm PASS** but **moderate σ** (1.9-3.9σ vs premium_index_zscore 5-9σ).

## §3-G family-extension 결정적 증거

1. **Same data source**: premium close (premium_index_zscore와 동일)
2. **Same direction**: follow momentum (premium_index_zscore와 동일)
3. **Same z-score** (30d rolling)
4. **다른 점은 Friday filter only**

**Random_mean 37-51 매우 높음** — random shuffle premium에서도 Friday-only follow 신호로 baseline alpha 형성. premium 데이터의 base signal이 random에도 leak → 진짜 weekend-specific 신호 미약.

**Real alpha vs random_mean 비율**:
- premium_index_zscore DOGE: 348 / 30 = **12×** ratio
- weekend_drift DOGE: 85 / 47 = **1.8×** ratio

→ weekend_drift는 premium_index_zscore의 30% 정보, 70% 노이즈 (Friday 필터링).

## §3-E 모든 candidates 이미 시드됨
| Symbol | weekend_drift seed candidate | 기존 시드 |
|---|---|---|
| HBAR | new | funding_carry 472fafc0-65a (perm 0.000) |
| AXS | new | funding_carry accc65a5-e27 (perm 0.000) |
| LDO | new | premium_index_zscore a2f423ae-2ce (5.7σ) |
| UNI | new | autocorr_regime 469a7a29-9be (perm 0.000) |
| DOGE | new | premium_index_zscore 07934d53-b9d (9.0σ) + lead_lag b5041367-5a6 |

**0개 새 symbol unlock** — 모두 강한 paradigm seed로 이미 cover.

## R-5 SKIPPED → graveyard

근거:
1. §3-G strong: premium_index_zscore의 Friday-restricted 변형 (random_mean 47 = base alpha leak 큼)
2. 모든 5 strong candidates 이미 시드됨 (다른 paradigms으로)
3. R-2 alpha 10/10 + R-3 5/5 perm PASS는 paradigm-level 입증이지만 새 alpha source 없음
4. Friday DoW cluster 효과는 premium 신호의 일부 — 진짜 새 차원이 아님

## Lesson — 32 paradigm 후 결정적 통찰

> **§3-G family-extension 유형**:
> 1. **Power transform** (lag-2 PACF after lag-1 ACF; kurtosis after skewness) — random 모멘트 family extension
> 2. **Calendar/timing restriction** (premium_index_zscore Friday-only filter) — random_mean 기저 신호 leak
> 3. **Ensemble of seeded** (joint_3signal_ensemble) — component seeds correlation 누적
>
> 모두 perm test PASS 가능하지만 **σ가 component seeds보다 명백히 작다** (50-30% 정보).
>
> **새 alpha source 발굴 = 새 데이터 도메인 또는 진짜 새 차원**. Calendar filter, ensemble, power transform은 모두 §3-G.
>
> 32 paradigms 후: **paper-pool 14종 X premium/funding/OI/lead_lag/autocorr 5 seeded paradigms = 사실상 모든 강한 alpha 발견 완료**. 추가 paradigm은 데이터 backfill 필요 또는 portfolio-level multi-symbol paradigm 영역으로.
