# wick_reversal_multibar — Graveyard Note (2026-05-06, 44th graveyard, 52nd paradigm overall) ⭐ POSITIVE 4σ+ SOL single-symbol

## 설계
Q3 #2 wick_reversal POSITIVE 3σ borderline의 §2-A0 second-priority extension. 
가설: SUSTAINED wick dominance (rolling N-bar average) → genuine liquidation
cascade의 더 신뢰 신호 + random_std 감소로 4σ+ elevation.

§3-H 회피: sequence transformation (rolling avg), NOT AND-filter.

Entry rule:
- lwf_meanN > thresh AND prior_ret < -pm → LONG
- uwf_meanN > thresh AND prior_ret > +pm → SHORT

## R-1 SOL sweep (24 specs, n × wt × h)
**Best**: n=2/wt=0.35/h=12 alpha **+61.94**/sharpe **+1.41**/122 trades/PF 1.45.

n_bars 효과:
- n=2: marginal change vs single-bar (Q3 #2 baseline 59.60/1.51)
- n=3: monotonic degradation (best 40.27/0.54)
- n=5: completely destroyed (24-26 trades, sharpe -2.6)

§3-A check: relax wt 0.5→0.35 → trades 49→122, sharpe 0.79→1.41 (improves). NOT rare-event.

**Lesson**: wick signal은 largely INSTANTANEOUS, not sequential. n=2 averaging은 marginal smoothing이고, n≥3은 noise dilution.

## R-2 multi-symbol (10종, n=2 wt=0.35 h=12)
- alpha pos: **10/10** (perfect, vs Q3 #2 single-bar 10/10)
- sharpe pos: 7/10 (Q3 #2 single-bar 8/10 — 약간 약화)
- alpha mean: 50.66 (Q3 #2 58.36 — 약간 약화)
- sharpe mean: 0.325 (Q3 #2 0.595 — 약화)
- trades_total: 2010 (Q3 #2 1515 — 더 dense)

Top 4 by sharpe: SOL 1.41, DOGE 1.08, AVAX 0.74, HBAR 0.38.

## R-3 perm n=200 (shuffle high/low pair)
| Symbol | real | random_mean | random_std | sigma | perm_p | verdict | vs Q3 #2 std |
|---|---|---|---|---|---|---|---|
| **SOLUSDT** | 61.94 | 15.66 | **10.30** | **4.49σ** | 0.0000 | **PASS** ✅ | (12.91 →10.30, -20%) |
| AVAXUSDT | 66.24 | 1.13 | 20.63 | 3.16σ | 0.0000 | borderline | (19.96 → 20.63, +3%) |
| DOGEUSDT | 73.48 | 20.76 | 27.18 | 1.94σ | 0.0250 | FAIL | (28.71 → 27.18, -5%) |
| HBARUSDT | 56.31 | 28.49 | 21.44 | 1.30σ | 0.0900 | FAIL | (30.62 → 21.44, -30%) |

**SOL 4σ+ elevation 성공!** Multi-bar averaging이 SOL random_std를 12.91 → 10.30 (-20%) 감소 + alpha 59.60 → 61.94 (+4%) 증가 → 3.34σ → 4.49σ.

다른 symbol에서는 elevation 효과 inconsistent:
- HBAR std 30%↓ but real_alpha drop으로 sigma ↓ (0.79 → 0.38 sharpe)
- DOGE std는 유사, real_alpha 증가 but random_mean도 증가 → sigma ↓
- AVAX std 약간 증가 + real_alpha 감소 → sigma ↓

## Verdict — POSITIVE 4σ+ SOL single-symbol but §3-C concern
**Why NOT R-5 seed (despite SOL 4.49σ)**:
1. **Multi-symbol consistency**: 1/4 PASS at 4σ — seeded paradigms have 3-4/4 (premium_index_zscore 3/4, oi_price_decoupling 4/4, premium_velocity 3/10).
2. **§3-C single-symbol-fit risk**: SOL is the only symbol where random_std reduction worked.
3. **§3-G family extension**: This is wick_reversal Q3 #2 의 multi-bar variant. Per runbook: filter mechanism antipattern strengthened, transformation variants need to PASS multi-symbol consistency.
4. **Diversity**: SOL is already seeded in premium_index_zscore. Even though dimensions differ (premium 1d level vs intra-bar OHLC), §3-G concern that wick_reversal_multibar SOL might be capturing same underlying signal.

**Why POSITIVE (not §3-D dismissal)**:
1. perm_p=0.0000 for SOL (0/200 random shuffles beat real)
2. random_mean (15.66) is 25% of real (61.94) — well below §3-D 55%+ threshold
3. multi-bar transformation's std-reduction mechanism IS validated for SOL
4. NEW dimension (intra-bar OHLC wick) confirmed second time

## 핵심 lesson — n=2 averaging 효과 inconsistent
Multi-bar averaging successfully reduces random_std for **clean signal** symbols (SOL, HBAR -30%) but doesn't help for **inherently noisy** symbols (AVAX, DOGE):
- SOL: low base std (10) → averaging works marginally + alpha boost
- AVAX/DOGE: high base std (20-30) → averaging doesn't help much
- HBAR: std reduces but alpha drops more

**Generalization**: Sequence-pattern transformations help only when underlying signal already has high signal-to-noise per bar. They don't rescue weak signals.

## §3-C single-symbol-fit at NEW dimension
3rd time we see single-symbol PASS:
1. funding_premium_spread_zscore #8: SOL 3.10σ outlier
2. oi_change_acceleration_squeeze #9: ETC 3.98σ outlier
3. **wick_reversal_multibar (this)**: SOL 4.49σ outlier

Pattern: 1 symbol's idiosyncratic data fits paradigm rule. Always graveyard despite reaching 4σ.

## 다음 wick paradigm 후보 (§3-H/§3-C 회피)
Given §3-G family extension and §3-C single-symbol risk:
1. ~~wick_reversal_multi_bar~~ (this graveyard)
2. ~~wick_reversal_volume_filter~~ (Q3 #3 graveyard, §3-H)
3. **wick_reversal_aggtrades** (§2-A0 #3, ⭐⭐⭐): different data domain (aggTrades) — orthogonal upgrade not derivative
4. **wick × prior_ret JOINT TRANSFORM**: continuous metric instead of binary AND
5. **wick on different timeframe** (1m or 15m): granularity variant — §3-G risk

For elevation at multiple symbols, need DOMAIN switch (aggTrades) or TRANSFORMATION (joint metric), not derived variations of same wick metric.

52nd paradigm overall, 44th graveyard. Q3 큐 4 attempts: 1 §3-D, 1 POSITIVE 3σ, 1 §3-H, 1 POSITIVE 4σ-single-symbol. Wick-shape NEW dimension proven repeatedly but elevation difficult.
