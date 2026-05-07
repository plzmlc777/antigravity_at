# oi_funding_corr_regime — Graveyard Note (2026-05-06, 41st graveyard, 49th paradigm overall)

## 설계
8h granularity. d_OI z-score × funding-rate z-score 결합 + rolling 30-period correlation 을 regime filter로 사용. 두 개의 시드된 강력 도메인(OI flow + funding carry) 결합 → corr regime 이 noise/signal regime 구분 하는 가설.

5m 첫 시도는 forward-fill funding이 step function 만들어 corr 0%, trade=0. 8h 정렬 frame으로 재설계.

Modes:
- `follow_long_pos`: aligned positive (OI↑ AND funding↑ z extreme) → LONG (regime momentum)
- `fade_long_pos`: aligned positive → SHORT (extreme positioning + carry → revert)

## R-1 SOL sweep (8h frame)
| mode | ez | efz | ct | h | alpha | sharpe | trades |
|---|---|---|---|---|---|---|---|
| follow | 1.0~1.5 | 0.5~1.0 | 0.0~0.2 | 3~6 | 18~47 | -4.4~-0.09 | 5~27 |
| **fade** | **1.5** | **0.5** | **0.0** | **6** | **+69.7** | **+4.04** | **12** |
| fade | 1.0 | 0.5 | 0.0 | 6 | +75.95 | +2.51 | 21 |
| fade | 1.0 | 0.5 | 0.2 | 3 | +73.66 | +2.76 | 17 |
| fade | 1.0 | 1.0 | 0.0 | 6 | +67.14 | +2.45 | 12 |

§3-A robust: relax thresholds → sharpe stays positive 1.79~4.04. Not rare-event.

## R-2 multi-symbol (10종, fade ez=1.0 efz=0.5 ct=0.0 h=6)
- alpha pos: **10/10** (perfect)
- sharpe pos: 7/10
- alpha mean: 50.23, sharpe mean: 0.559
- trades_total: 187

Top 4 by alpha+sharpe: DOGE (94.38/3.58), SOL (75.95/2.51), UNI (69.96/0.90), HBAR (49.67/0.20).

## R-3 perm test n=200 (shuffle OI series)
| Symbol | real_alpha | random_mean | sigma | perm_p | verdict |
|---|---|---|---|---|---|
| DOGEUSDT | 94.38 | ~80 | 0.73σ | 0.175 | FAIL |
| SOLUSDT | 75.95 | ~58 | 0.65σ | 0.24 | FAIL |
| UNIUSDT | 69.96 | ~70 | -0.01σ | 0.455 | FAIL |
| HBARUSDT | 49.67 | ~55 | -0.23σ | 0.565 | FAIL |

## Verdict — §3-D directional bias (random shuffle 50-85% of real alpha)
**Critical**: random_mean approximately equals real_alpha. Shuffling OI temporally STILL yields 55-80% alpha — meaning OI alignment contributed almost nothing. The fade mode mostly captured funding-rate fading alone (existing seeded `funding_carry` paradigm, alone), with OI signal adding zero incremental information on top.

This pattern matches premium_volatility_regime #1 (random_mean 31-40 vs real 88) and cross_asset_premium_spread #2 §3-D — strategies that look great on paper but fail perm test because random data produces similar alpha distributions.

## Lesson — interaction term doesn't add value when both components individually fade-tradeable
**Pattern emerging**: When a paradigm combines two seeded-strong fade signals (funding_carry + OI flow extreme), the joint signal does NOT yield orthogonal alpha — it is almost fully explained by the funding-fade component alone. The OI alignment filter adds noise without reducing variance because:
1. funding extreme z events are dense enough that fade alone captures most reversal alpha
2. OI alignment narrows the trade set but doesn't increase per-trade edge meaningfully
3. Permutation breaks OI timing but funding-fade signal remains intact → random_mean stays high

**Diversity check failure**: Even though OI is structurally orthogonal information, in this specific composition the funding signal dominated. Cross-validates §3-G filter mechanism antipattern (큐에서 signal AND-filter는 alpha 약화).

## §3-G note
- joint_3signal_ensemble (graveyard, POSITIVE但R-5 SKIP): voting-based combination, 약한 marginal value
- premium_oi_correlation_regime (graveyard 1d): same idea different domain → graveyard
- **oi_funding_corr_regime (this, 8h)**: same antipattern — combining two seeded fade signals via filter doesn't produce orthogonal alpha

**규칙 보강**: 시드된 두 fade signal의 joint 또는 corr filter 조합은 §3-D high risk. R-3 perm test에서 항상 FAIL probable. 시도 전 fail-fast 결정 트리에 추가 권장.

## 다음 시도 방향
- Joint signals where ONE component is NEW (not yet seeded) — interaction term could be orthogonal
- Or genuinely NEW data domains (liquidation API, book_depth 2y backfill)
- Avoid stacking already-seeded fade signals with filter mechanisms
