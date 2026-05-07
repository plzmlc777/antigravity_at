# taker_flow_zscore — Graveyard Note (2026-05-06, 23rd paradigm)

## 설계
5m granularity microstructure joblib `taker_buy_sell_ratio` (실현된 aggressive flow imbalance) rolling 288-bar(24h) z-score. 두 모드:
- `fade` (climax reversal): TBS_z > entry → SHORT; < -entry → LONG
- `follow` (momentum): TBS_z > entry → LONG; < -entry → SHORT

## 데이터 처리 발견
원본 TBS는 heavily right-skewed (max 12.7 vs min 0.07). 단순 z-score는 z>2 occurred 4.34% but z<-2 only 0.05% — 신호 비대칭. **log(TBS) 변환** 후 symmetric (z>2: 2.16%, z<-2: 2.21%) — 이 형태로 PoC 진행.

## R-1 SOL sweep 결과 (log(TBS) z-score)
| mode | spec | alpha | sharpe | mdd | trades |
|---|---|---|---|---|---|
| fade | z=1.5 h=12~48 | -65~-18 | -6.5~-0.7 | 58~99 | 1936~5844 |
| fade | z=2.0 h=12~48 | -45~-33 | -3.4~-1.6 | 70~80 | 1507~3061 |
| **fade** | **z=2.5 h=24** | **+35.1** | **+0.20** | **26.7** | 974 |
| fade | z=2.5 h=12 | +20.9 | -0.50 | 25.9 | 1127 |
| fade | z=2.5 h=48 | +1.7 | -0.79 | 42.9 | 783 |
| follow | 모든 spec | -25~-66 | -2~-10 | 58~100 | — |

R-1 marginal PASS (best fade z=2.5 h=24 alpha+sharpe ≥ 0).

## R-2 multi-symbol (10종, fade z=2.5 h=24)
- **alpha pos: 3/10** (SOL +35, LDO +0.7, DOGE +0.2 — 1개만 의미 있음)
- **sharpe pos: 1/10** (SOL +0.20만)
- alpha mean -7.0
- 7/10 catastrophic 음수 (HBAR -10, AXS -14, LINK -27, ETC -27, COMP -20)

top_global_lsr_divergence(22번째 graveyard, alpha 2/10 sharpe 2/10)와 거의 동일 패턴. SOL outlier만.

## 보조: TBS × Price joint signal (oi_price_decoupling 패턴 응용)
7종 quick test, both confirm/invert_decouple modes z=2.0 h=24:
- confirm: alpha 4/7 양수 (mean +17), but sharpe 0/7 양수 (best AXS sharpe +0.27)
- invert_decouple: 신호 너무 희소 (n=1~7 trades, 통계적 의미 없음)

oi_price_decoupling AVAX(alpha 145/sharpe 1.73)와 비교:
- TBS × Price 최선 AXS confirm: alpha +53/sharpe +0.27 — **2-6× 약함**

## R-3 SKIPPED — paradigm-level fail

## Lesson — 본 트랙의 핵심 통찰
**Pattern emerging from 23 paradigms (5 seeded, 18 graveyard)**:
- ✅ **Joint flow signals** (OI Δ × Price Δ in oi_price_decoupling) → STRONG
- ❌ Single-feature z-score in microstructure (LSR, TBS) → WEAK
- ❌ Joint TBS × Price → WEAK (TBS lacks information density of OI flow)

**OI는 microstructure 데이터에서 unique 강한 signal**:
- OI는 cumulative commitment level — 한 번 build되면 기록됨
- TBS는 5m volume ratio — noisy, sticky, 단기 fluctuation
- LSR은 positioning state — 종목별 microstructure로 noisy
- 오직 OI Δ × Price Δ 결합만이 perm 0.000 6.7σ 강도

**다음 시도 방향**:
- 다른 데이터 도메인(book_depth, premium_index — 새 차원)
- 또는 joint OI × Funding × Price (3-feature combo, but oi_price_decoupling family-extension §3-G 위험)
- microstructure joblib 단일 컬럼 paradigm 추가 시도 권장 안 됨 (LSR/TBS 모두 fail)
