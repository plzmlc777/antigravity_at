# wick_prior_joint — Graveyard Note (2026-05-06, 46th graveyard, 54th paradigm overall)

## 설계
Q3 #6 — Q3 #4 graveyard note에서 권장한 **continuous JOINT TRANSFORM**. Q3 #2 wick_reversal POSITIVE 3σ는 BINARY AND gates (wick_thresh AND prior_move_pct) 사용. JOINT TRANSFORM은 multiplicative composite로 연속 metric:
- composite = (lower_wick_frac - upper_wick_frac) * (-prior_ret_pct)
- composite_z = rolling-N z-score
- entry: composite_z > entry_z, direction = sign(wick_imbalance)

가설: continuous metric이 binary threshold noise를 줄여 4σ+ multi-symbol elevation 가능.

§3-H 회피 의도: filter가 아닌 unified composite metric.
§3-K 준수: SHAPE(wick) provides direction, magnitude integrates SHAPE+MAGNITUDE.

## R-1 SOL sweep — **0/36 PASS** (catastrophic)
**ALL 36 specs negative sharpe (-1.48 to -3.41), MDD 70-85%, trades 700-1100**.

| ez | pl | h | alpha | sharpe | mdd | trades |
|---|---|---|---|---|---|---|
| 1.5 | 6 | 6 | -55 | -3.3 | 86 | 1456 |
| 2.0 | 12 | 12 | -39 | -2.5 | 78 | 1019 |
| 2.5 | 24 | 24 | -36 | -1.9 | 76 | 1048 |
| 3.0 | 24 | 24 | -31 | -1.8 | 70 | 733 |

Even highest threshold ez=3.0 still 700+ trades + negative.

## 진단 — Binary AND was an essential noise filter
Q3 #2 wick_reversal binary trigger rate ~ 0.5-1% bars (84 trades over 6mo OOS).
This continuous composite z>2 trigger rate ~ 5-7% bars (700-1100 trades) — **5-10x denser**.

Why? 
- Binary AND requires BOTH wick_frac > 0.5 (top 10-15%) AND |prior_ret| > 0.03 (top 5-10%) → very rare joint event
- Continuous composite z fires whenever PRODUCT is extreme. Even small wick_imbalance × very-negative prior_ret = high composite. **Most "reversal" entries have weak wick → no actual liquidation reversal signal, just noise from prior_ret magnitude**.

The wick_imbalance sign in continuous mode often comes from inconsequential bars (almost-symmetric wicks barely on positive side). In binary mode, wick_thresh ensures only DOMINANT wick triggers.

## R-2/R-3 SKIPPED — paradigm-level catastrophic failure
0 PASS, 100% MDD wipeout. No spec worth testing further.

## Lesson — §3-L Continuous-multiplicative-composite without strict gates fails
**규칙**: binary threshold gates are not always §3-H filters that degrade. They can be ESSENTIAL noise discriminators when:
1. Components have heavy-tailed distributions (small magnitude common, large rare)
2. Sign of one component can flip with tiny magnitude changes
3. Composite arithmetic amplifies products even when components are weak

For wick × prior_ret specifically:
- wick_imbalance is bounded [-1, +1] and clusters near zero
- prior_ret has heavy tails
- Product can be large even when wick_imbalance is tiny → noisy direction
- Binary gate (wick_thresh > 0.5) ensures DOMINANT wick → strong direction
- Continuous z-score loses this discrimination

**§3-L** (신규 antipattern): Continuous multiplicative composite of (bounded asymmetric metric) × (heavy-tailed metric) WITHOUT separate magnitude gates → noise-dominated, more trades but worse signal. Don't replace structured AND gates with smooth composite for paradigms involving:
- Wick fractions (bounded 0-1)
- Direction indicators
- Bounded oscillators

## Q3 #2 Binary AND structure CONFIRMED as correct
This negative result strongly validates the original Q3 #2 wick_reversal design choice:
- binary wick_thresh + prior_move_pct = correct paradigm
- continuous composite = wrong paradigm

The 4σ+ elevation problem (Q3 #4 SOL only) is NOT solvable by transform smoothing. It's a §3-C single-symbol-fit issue requiring different approach.

## Q3 status (6/6 graveyard)
| # | Paradigm | Outcome | Lesson |
|---|---|---|---|
| 1 | oi_funding_corr_regime | §3-D §3-J | two-seeded fade joint |
| 2 | wick_reversal | POSITIVE 3σ | NEW dim shape proven |
| 3 | wick_reversal_volume | §3-H 3rd | filter monotonic degrade |
| 4 | wick_reversal_multibar | POSITIVE SOL 4.49σ | §3-C single-symbol |
| 5 | range_expansion | §3-K | shape > magnitude |
| 6 | wick_prior_joint | §3-L | binary gates ≠ §3-H, can be essential |

54th paradigm graveyard. Wick paradigm family essentially saturated — Q3 #2 binary AND is local optimum, all variations fail (multi-bar single-sym, volume filter degrade, joint composite noise).

## 다음 paradigm 방향
1. **다른 도메인** (aggTrades, liquidation API backfill 필요)
2. **다른 timeframe wick** (1m, 15m, 1h) — granularity §3-G risk
3. **wick × ANOTHER seeded signal JOINT** — premium_index_zscore × wick? But §3-H risk if filter
4. **새 통계적 접근** (HMM, change_point on intra-bar wick series)
