# Graveyard — paradigm 152 `alt_range_volume_divergence_z_directional_4h`

**Date**: 2026-05-21 14:44 KST
**Phase halt**: R-0 prescreen
**Verdict**: `SAMPLE_INSUFFICIENT_STRUCTURAL_THRESHOLD_INFEASIBLE` (Lesson #40 3rd dogfood, asymmetric subtraction variant)

## Hypothesis

- **Mechanism**: range_z − volume_z divergence as thin-liquidity / consolidation regime classifier
- **Statistic**: `divergence = range_z − volume_z` (per-symbol 30d rolling z on `(high-low)/close` and `quote_volume`)
- **Trigger**: `|divergence| > 2.0`
- **Direction**: divergence > +2 → 4h mean-reversion of close direction (thin move); divergence < −2 → continuation (consolidation breakout). 4h hold, 13 alts.
- **Family-distinct claim**: range-volume divergence axis = GENUINELY NEW (151 paradigms 중 0회 사용).

## R-0 prescreen results

### Lesson #58 candidate — range vs volume per-sym corr healthy zone PASS
- 13/13 syms healthy: corr range 0.65~0.78 (BCH 0.69 / FIL 0.78 / SOL 0.75 / etc.)
- 0 degeneracy (corr ≥ 0.90), 0 near-zero (corr ≤ 0.05)
- **첫 dogfood: Lesson #58 candidate range-volume corr healthy zone check 정상 작동** — degeneracy 차단 메커니즘 정상 입증.

### Lesson #40 threshold attainability FAIL — structurally asymmetric divergence distribution

```
sym       p99      p01      max     min     n_pos(>+2)  n_neg(<-2)
ADAUSDT   1.454   -1.785    5.81   -7.16        16          41
AVAXUSDT  1.389   -1.747    6.42   -4.75        22          34
BCHUSDT   1.749   -2.261    4.93   -5.22        35          60
BNBUSDT   1.364   -1.974    5.42   -6.62        17          47
DOGEUSDT  1.352   -2.056    4.58   -4.44        17          50
ETHUSDT   1.244   -1.500    3.56   -4.12         9          20
FILUSDT   1.413   -1.812    4.93   -5.61        22          35
LINKUSDT  1.474   -2.033    6.06   -5.65        21          49
LTCUSDT   1.497   -2.012    4.94   -4.49        22          51
NEARUSDT  1.509   -2.056    5.27   -6.10        20          50
SOLUSDT   1.413   -1.624    4.30   -4.31        14          24
WIFUSDT   1.586   -2.058    4.09   -3.93        25          56
XRPUSDT   1.373   -1.909    3.69   -6.54        18          42
```

**13/13 syms positive p99 < +2.0** — positive z-threshold structurally infeasible at 99%-tile. negative p01 4 syms ≤ −2.0 PASS, 9 syms FAIL but min always ≤ −3.5.

### Lesson #11 sample density FAIL (marginal)
- per_cell_pos = 28.7 / quarter aggregated across 13 syms (< 30 cutoff)
- per_cell_neg = 62.1 / quarter (PASS)
- positive side: 258 total / 9 quarters → 4-quadrant A focus + A mirror **both starved**

## Structural diagnosis — Lesson #40 3rd dogfood, NEW sub-pattern

paradigm 109/110 confirmed Lesson #40 pattern: **non-negative aggregate statistics (std/var/count/magnitude/ATR/|return|/drawdown/RV/range) — symmetric z ≤ −T 구조적 불가**.

paradigm 152는 **subtraction variant**: divergence = range_z − volume_z. 두 highly-correlated (corr 0.65~0.78) right-skewed non-negative variables의 차이는:
- positive direction: range spike >> volume spike 필요 (rare; healthy positive corr이 결합 억제)
- negative direction: volume spike >> range spike (volume이 더 큰 dynamic range 보유, 더 자주 발생)
- 결과: divergence 분포는 negatively-skewed, |z| > 2 트리거 positive side에서 structurally infeasible (p99 < 2.0 13/13)

### Lesson #40 amendment candidate (3rd dogfood 자격)

**기존 (paradigm 109+110)**: non-negative aggregate statistic + symmetric z ≤ −T 구조적 불가

**NEW sub-pattern (paradigm 152)**: **subtraction of two correlated right-skewed non-negative aggregate statistics → divergence distribution structurally negative-skewed → symmetric +z 도달 불가**

### Lesson #11 amendment finding
positive side 28.7 < 30 cutoff, negative side 62 PASS → **asymmetric quadrant viability**: 4-quadrant SNT 중 A side (positive divergence) 완전 dispatch 불가, B side (negative divergence)만 가능. paradigm-architect spec amendment: asymmetric distribution paradigm은 자동으로 2-quadrant restricted-SNT로 다운그레이드 검토.

## Reformulation options (rejected for this paradigm)

1. **Threshold 완화 (|divergence| > 1.0)**: positive p99 1.24~1.75 → +1.0 충족, 그러나 trigger rate ~10% 너무 빈번, edge dilution risk
2. **Percentile rank trigger (top/bottom 5%)**: Lesson #40 reformulate 권장 패턴. paradigm 152 reformulate-candidate (별도 paradigm 153+로 발의 가능)
3. **Log-transform divergence**: range/volume 자체가 이미 log-scale에 가까움, 효과 미미
4. **Ratio compression (range_z / (volume_z + 1))**: Lesson #54 ratio degeneracy risk

→ **Current paradigm 152 graveyard**, reformulate variant는 별도 paradigm number 권장.

## Lessons reference

- **Lesson #11** sample density (1st amendment finding: asymmetric quadrant viability)
- **Lesson #19** 4-quadrant SNT (asymmetric distribution → 2-quadrant restricted variant)
- **Lesson #40** confirmed 3rd dogfood: subtraction of correlated right-skewed non-neg stats → asymmetric divergence (NEW sub-pattern candidate)
- **Lesson #58 candidate** range-volume corr healthy zone check — 1st dogfood PASS (prescreen 정상 작동, 차단 ≠ corr 문제 ≠ degeneracy)
- **Lesson #44 36th xref** family-distinct 입증 (range-volume divergence axis NEW)
- **Lesson #54** same-bar subtraction (not ratio), independent mechanism story 명확
- **Lesson #30** data_window_ratio: full window (4920 bars / sym), ratio 100%

## Artifacts

- `backend/scripts/research/paradigm152_r0_prescreen.py` (compile clean, executed 2026-05-21 14:44 KST)
- `backend/runs/research_track/alt_range_volume_divergence_z_directional_4h/r0_prescreen.json`

## Lesson #40 sub-pattern (3rd dogfood candidate)

> **3rd dogfood candidate** (paradigm 109 BTC RV downward × 110 fund neg z × 152 range-vol divergence subtraction):
> Subtraction of two **highly-correlated right-skewed non-negative aggregate statistics** produces a **negatively-skewed divergence distribution** where symmetric positive-z threshold is structurally infeasible. Reformulate via percentile rank (top/bottom 5%) or per-side absolute thresholds.

3rd dogfood 도달 → 형식적 confirmed 자격 부여 권장 (paradigm-architect spec next amendment).

## Counter

- Graveyards: 151 → **152**
- R-5 LIVE: 10
- Non-PASS streak: 22 → **23**
- Lessons: 34 confirmed + 15 candidates → 34 confirmed + 16 candidates (NEW: Lesson #40 sub-pattern subtraction variant 3rd dogfood)
