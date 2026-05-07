# joint_3signal_ensemble — Graveyard with POSITIVE VALIDATION (2026-05-06, 27th paradigm)

> **Notable**: 4/4 perm test PASS, DOGE perm σ **9.6 (track 최고 기록)**, 메타-매커니즘 검증 성공.
> Graveyard 사유: §3-G 명백 — 모든 candidates 이미 시드, 새 alpha source 발굴 없음.

## 설계
3 시드된 paradigms 신호를 daily granularity에서 voting으로 결합:
- **premium_index_zscore** (24th seeded, 9σ): daily premium close 30d z, follow at |z|>2
- **oi_price_decoupling** (21st seeded, 6.7σ): 5m OI×price joint z, confirm at |z|>2 (5m→1d aggregated)
- **funding_carry** (1st seeded, perm 0.000): 8h funding rate 30-period z, fade at |z|>2.5 (8h→1d aggregated)

Voting strategies tested:
- `any_majority`: ≥1 fires; if multiple, take majority direction
- `require_2`: ≥2 agree on same direction
- `unanimous`: all 3 fire same sign
- `sum_threshold`: |signal sum| ≥ 1

## R-1 SOL sweep (require_2 h=3 best)
| Mode | Fires/803 | Alpha | Sharpe | MDD | WR | PF | Trades |
|---|---|---|---|---|---|---|---|
| any_majority h=10 | 615 | +222 | +1.71 | 47 | 53 | 1.82 | 51 |
| **require_2 h=3** | 30 | **+95** | **+2.76** | **7.1** | **83.3** | **6.37** | 12 |
| **unanimous** | **0** | 0 | 0 | 0 | - | - | 0 |

**unanimous = 0 firings 검증**: 3 paradigms은 **uncorrelated** (다른 정보) — 좋은 ensemble 조건. require_2가 best balance.

## R-2 multi-symbol (10종 require_2 h=3)
| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades | Cutoff |
|---|---|---|---|---|---|---|---|
| **DOGE** ⭐ | **+309** | **+2.85** | 8.8 | **86.7** | **14.46** | 15 | **5/5** |
| **LDO** ⭐ | **+179** | **+2.29** | 19.4 | **85.7** | 5.29 | 14 | **5/5** |
| **COMP** ⭐ | **+151** | **+1.94** | **8.5** | 61.1 | **4.00** | 18 | **5/5** |
| AVAX | +103 | +1.32 | 11.0 | 57.1 | 2.48 | 14 | 4/5 |
| SOL | +95 | +2.76 | 7.1 | 83.3 | 6.37 | 12 | 4/5 |
| UNI | +84 | +1.42 | 9.2 | 66.7 | 2.91 | 12 | 4/5 |
| ETC | +60 | +0.47 | 22.5 | 54.5 | 1.50 | 11 | 3/5 |
| HBAR | +48 | +0.13 | 28.4 | 72.7 | 1.13 | 11 | 2/5 |
| AXS | +19 | -0.36 | 49.4 | 52.9 | 0.76 | 17 | 1/5 |
| LINK | -14 | -3.09 | 52.3 | 9.1 | 0.04 | 11 | 0/5 |

- **alpha pos: 9/10**, sharpe pos: 8/10, alpha mean **+103.4**
- **3 symbols 5/5 strict** (DOGE, LDO, COMP) + 3 more 4/5
- premium_index_zscore (alpha 9/10 mean +108, 3 5/5) 와 사실상 동급

## R-3 perm test n=200 (require_2 h=3)
| Symbol | Real α | perm_p | rand_mean | rand_std | σ | Status |
|---|---|---|---|---|---|---|
| **DOGE** | 309.02 | **0.0000** | 46.25 | 27.34 | **9.6σ** ⭐ track 최고 | PASS |
| LDO | 178.78 | 0.0050 | 55.71 | 33.56 | 3.7σ | PASS |
| COMP | 150.61 | 0.0000 | 40.89 | 25.14 | 4.4σ | PASS |
| AVAX | 102.99 | 0.0400 | 52.70 | 27.88 | 1.8σ | PASS |

**4/4 PASS** at perm_p ≤ 0.04. **DOGE 9.6σ는 본 트랙 31 paradigms 중 최강 perm σ 기록.**

## §3-G family-extension 명확 — 모든 candidates 이미 시드됨

| Symbol | Ensemble seed candidate | 기존 시드 |
|---|---|---|
| DOGE | new ensemble (9.6σ) | premium_index_zscore 07934d53-b9d (9.0σ) + cross_symbol_lead_lag b5041367-5a6 → **TRIPLE redundant** |
| LDO | new ensemble (3.7σ) | premium_index_zscore a2f423ae-2ce (5.7σ) → DOUBLE |
| COMP | new ensemble (4.4σ) | funding_carry f4c8ee87-a76 (perm 0.000) → DOUBLE |
| AVAX | weaker (1.8σ) | oi_price_decoupling 2555033d-308 (6.7σ) → DOUBLE |

ensemble의 이론적 가치 = component signals 결합한 **filter quality 개선**. 실제 측정값:
- DOGE: premium 17 trades 9.0σ → ensemble 15 trades 9.6σ — 노이즈 감소 검증 ✅
- 그러나 component paradigms 시드된 후 ensemble은 새 symbol/alpha source 추가 안 됨

## 메타-매커니즘 검증 의의 (POSITIVE)

본 paradigm은 graveyard이지만 **track-level 가치 있음**:

1. **Voting mechanism 검증** — 4/4 perm PASS, unanimous 0 firings (uncorrelated) → 3 시드 paradigms은 진짜 다른 정보 보유
2. **Filter quality 검증** — DOGE 9.0σ → 9.6σ (10% 개선), trade count -12%
3. **Live trading 활용 가능** — ensemble을 confidence filter로 사용:
   - 단일 paradigm 발화 시: 표준 size
   - 2개 paradigm 발화 시: size× 1.5 (보강된 conviction)
   - 3개 paradigm 발화 시: size× 2 (very high conviction)
   - 또는 ensemble 발화시에만 entry, single paradigm은 paper만 (보수적 filter)

## R-5 SKIPPED → graveyard

근거:
1. 모든 4 strong candidates 이미 시드 (DOGE/LDO/COMP/AVAX)
2. ensemble은 component signals 결합한 변형 = §3-G family-extension
3. 새 symbol 또는 unique alpha source 추가 못함
4. 시드해도 기존 paper sessions와 correlated → paper 풀 다양성 감소

**보존 가치**: code (poc_joint_3signal_ensemble.py + r3) 향후 live trading mechanism 발전 시 referencable. 31 paradigms 중 4/4 perm PASS + DOGE 9.6σ 기록은 트랙 stat sheet에 기록.

## Lesson — 31 paradigm 후 결정적 통찰

> **시드된 paradigms은 진짜 uncorrelated alpha sources** (ensemble unanimous 0 firings 검증).
>
> **새 paradigm 발굴 = 새 데이터 도메인 또는 진짜 새 차원** (시드된 paradigm 결합/변형은 §3-G).
>
> 31 paradigms 후 도메인 saturation:
> - ✅ funding (5 시도, 2 시드 carry+dispersion)
> - ✅ premium (2 시도, 1 시드 + 1 dispersion 변형 graveyard)
> - ✅ OI (1 시도 1 시드)
> - ✅ autocorr/lead_lag (2 시도 2 시드)
> - ✅ microstructure flow (LSR/TBS 2 graveyard)
> - ✅ LOB (book_depth 1 graveyard borderline)
> - ✅ ensemble/voting (1 graveyard with positive note)
> - 🔄 positioning_dynamics (60d 누적 중 2026-07-03)
>
> 다음 시도 방향: 시간 backfill 가능한 새 데이터 도메인 (e.g., **Binance liquidation data**, **WebSocket trade events**, **option market basis**) 또는 multi-symbol portfolio-level paradigms.
