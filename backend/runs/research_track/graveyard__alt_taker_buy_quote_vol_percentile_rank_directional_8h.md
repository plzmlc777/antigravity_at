# Graveyard — paradigm 143 `alt_taker_buy_quote_vol_percentile_rank_directional_8h`

**Date**: 2026-05-21 13:15 KST
**Phase halt**: R-1
**Verdict**: `BROAD_FALSIFIED`
**Cumulative graveyards**: 143
**Dispatch mode**: continuous_parallel (메모리 [Persistence over efficiency])

## Hypothesis (R-1 only)

Per-symbol 4h bar taker_buy_quote_volume / quote_volume imbalance ratio (centered at 0.5). 30d (180 bars × 4h) rolling **percentile rank** trigger:
- pct_rank > 0.95 → 8h LONG continuation (top 5% aggressive USD buy)
- pct_rank < 0.05 → 8h SHORT continuation (bottom 5% aggressive USD sell)

Universe: 14 alt perp futures × 820d. 4-quadrant SNT mandatory (Lesson #19).

## Differentiation from paradigm 142-v2 (Lesson #44 amendment 26th xref)

- **Trigger statistic**: percentile rank (distribution-agnostic, Lesson #55 candidate prescription) vs z-score (mean/std normalization)
- **Primary hold**: 8h (2 bars × 4h) — midpoint between 142-v2 4h fail and 12h B_focus sigex +3.43 hint
- Substrate: same 12-col klines cache (zero new infra)

## R-1 result

### 4-quadrant SNT (primary 8h)

| Quadrant | n | mean_bp | sigex | perm_p | ci_lo_bp | 3gate | conc |
|---|---|---|---|---|---|---|---|
| A focus pos LONG | 3577 | -3.88 | +0.327 | 0.638 | -11.91 | FAIL | FAIL |
| A mirror pos SHORT | 3577 | -12.12 | -0.792 | 0.185 | -19.56 | FAIL | FAIL |
| B focus neg SHORT | 3516 | -8.39 | +0.264 | 0.617 | -16.99 | FAIL | FAIL |
| B mirror neg LONG | 3516 | -7.61 | -0.515 | 0.300 | -15.60 | FAIL | FAIL |

All 4 quadrants broadly negative drift, no axis synthesis, no sub-class signature (Lesson #39 A/B both False).

### Hold sweep (Lesson #37)

| Hold | A_focus_LONG sigex / 3gate | B_focus_SHORT sigex / 3gate |
|---|---|---|
| 4h | -1.78 / FAIL | -0.55 / FAIL |
| **8h primary** | +0.33 / FAIL | +0.26 / FAIL |
| 12h | -0.66 / FAIL | **+1.01** / FAIL |

off-primary scan = no PASS, hold horizon expansion does not rescue.

### Life-changing 4-dim
- A focus LONG: edge -0.039% / sharpe -0.64 → FAIL
- B focus SHORT: edge -0.084% / sharpe -1.31 → FAIL

### Lesson #46 sign-flip
- A: 3 flips / 9 max, no strong-alternating
- B: 4 flips / 9 max, no strong-alternating
- Underlying signal genuinely flat-to-negative (not artifact of alternating regimes)

## Verdict reasoning

`BROAD_FALSIFIED` general category. No sub-class A (broad-uniform-negative <-2 sigex) nor sub-class B (mechanism inverted ≥+1.5 mirror dominance). Signal close to fee-drift null in both directions.

## Lesson dogfoods

### Lesson #57 — **2nd POSITIVE dogfood** (family Tier 4 retire eligible)

| sub-class | paradigm | verdict | KST |
|---|---|---|---|
| z-score 4h primary | 142-v2 | BROAD_FALSIFIED | 2026-05-21 13:09 |
| **percentile rank 8h primary** | **143** | **BROAD_FALSIFIED** | 2026-05-21 13:15 |

2 consecutive BROAD_FALSIFIED with:
- different normalization (parametric z vs non-parametric percentile)
- different primary holds (4h vs 8h)
- full hold sweeps (4h/8h/12h) all FAIL on both sides

→ **quote_vol imbalance axis 4h+ directional continuation family Tier 4 retire eligible** (formal elevation pending next campaign review)

### Lesson #55 candidate — **3rd dogfood is FAIL (not TRUE POSITIVE)**

percentile rank distribution-agnostic prescription tested as remedy for z-score asymmetry trap. Result: signal regression, not improvement.
- 142-v2 z-score B_focus 4h sigex +1.82 → 143 percentile B_focus 8h sigex +0.26 (worse)
- 142-v2 z-score B_focus 12h sigex +3.43 → 143 percentile B_focus 12h sigex +1.01 (regression -2.4σ)

**Distribution normalization is NOT the root cause** — underlying signal is genuinely absent (or fully fee-saturated). Lesson #55 confirmed-elevation impeded; prescription dogfood failed.

### Lesson #44 amendment 26th xref (dogfood)

Six family members ratified distinct prior to dispatch:
- paradigm 72 / 127 / 128 / 140 / 142-v2 / funding family
- DNA overlap dim only on trigger statistic (1/6); domain + tf + primary hold + normalization scheme all distinct

### Lesson #45 (no HMM/unsupervised) — compliant

Deterministic percentile rank computation.

### Lesson #46 — sign-flip strong WARNING N/A

Neither focus side showed strong-alternating; rules out artifact-of-noise explanation.

## Mechanism interpretation

quote_vol imbalance percentile rank trigger (both extremes) carries **no exploitable directional info at 4h-12h horizons**. Two interpretations:
1. **Fee saturation**: gross signal exists but ≤16bp fee floor (likely — 142-v2 z 12h gross +33bp = +17bp net, marginal; 143 percentile 12h gross +14bp = -2bp net)
2. **Reflexivity already priced**: aggressive buy/sell flow at 4h bar resolution is already mean-reverted by 4h-12h forward window (price absorption complete)

Combined with paradigm 72 (5m), 127/128 (30m burst), 140 (CVD ratio) — taker quote-vol axis appears **fully exploited at fast frames (5m-30m burst PASS, R-5 LIVE) and fee-saturated at slow frames (4h-12h)**.

## Campaign deltas

- graveyards: 142 → **143**
- R-5 seeded LIVE: 10 (unchanged)
- non-PASS streak: 14 → **15**
- R-5 yield: 10/142 = 7.04% → 10/143 = **6.99%**
- Lesson #57 dogfood count: 1 → **2** (CONFIRMED-elevation eligible)
- Lesson #55 candidate dogfood count: 3 (3rd FAIL)
- Lesson #44 amendment xref count: 25 → **26**
- Funding family Tier 4: 11 (unchanged)
- 12-col klines cache: reused (no new infra)

## Next candidate recommendation

paradigm 144 후보 권고: **quote_vol axis 외부 발의** (axis 자체가 4h+ fee-saturated 결정적).

Path 1 (highest-info-gain, novel axis): `alt_book_imbalance_cusum_5m_event_signed_directional_15m`
- DNA: book depth imbalance CUSUM (paradigm 84 SAMPLE_INSUFFICIENT 1h frame과 다른 5m event-based)
- Substrate: WS recorder book depth (현재 60+일 누적 진행 중)
- Risk: substrate availability (paradigm-architect agent local dev DB stale)

Path 2 (lower risk, axis switch): `alt_funding_carry_x_oi_decoupling_4h` (paradigm 22 R-5 + paradigm 21 R-5 cross-axis hybrid)
- 두 R-5 LIVE paradigm 결합 cross-axis novelty (이전 funding × OI 단순 joint event 73 graveyard와 distinct via R-5 mechanisms)

Path 3 (high risk, axis exhausted check): `alt_taker_buy_base_vol_NOT_quote_5m_directional_15m`
- DNA: paradigm 72 사촌 (base vs quote denominated 차이) — Lesson #57 family 정의 확장 검증

**권고: Path 2 alt_funding_carry_x_oi_decoupling_4h** — quote_vol axis 결정적 retire 가운데 novelty + 두 검증된 R-5 mechanism 결합 + 12-col cache 재사용 + funding DB substrate (paradigm 22 dispatch 시 백필 완료) 활용.

Path 1은 WS recorder maturity 대기 (2026-07-15+).
Path 3은 family retire 정의 직접 검증 — 사용자가 family boundary 명확화 원할 때 우선.
