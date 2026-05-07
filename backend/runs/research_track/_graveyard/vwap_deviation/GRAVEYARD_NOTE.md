# vwap_deviation — Graveyard Note (2026-05-06, 47th graveyard, 55th paradigm overall)

## 설계
Q3 #7 — Volume-weighted average price (VWAP) reference로 deviation z-score paradigm.
- VWAP_N = Σ(close × volume) / Σ(volume) over rolling N bars
- deviation = (close - VWAP_N) / VWAP_N
- deviation_z = z-score over rolling M bars
- 두 모드: fade (deviation extreme → revert), follow (deviation extreme → momentum)

NEW dimension: institutional volume-weighted reference price (54 paradigms 미탐색).

## R-1 SOL sweep
**fade mode**: 0/36 PASS. ALL specs alpha-/sharpe- catastrophic (MDD up to 98%, 5612 trades).
**follow mode**: 2/36 PASS only.
- Best: vw=144/ez=3.0/h=24 alpha **+48.04**/sharpe **+0.62**/273 trades

Trending crypto markets favor follow over fade — price systematically above/below VWAP and trend continues. fade hypothesis was wrong direction.

## R-2 multi-symbol (10종, follow vw=144 ez=3.0 h=24)
- alpha pos: 10/10 (perfect)
- sharpe pos: **4/10** (just at fail-fast cutoff)
- alpha mean: 36.78
- **sharpe mean: -0.306 NEGATIVE** ← paradigm-level weakness
- spread enormous: AXS +0.98 to HBAR -1.60

| Sym | alpha | sharpe |
|---|---|---|
| AXS | +97.01 | +0.98 |
| SOL | +48.04 | +0.62 |
| UNI | +53.58 | +0.37 |
| ETC | +52.31 | +0.27 |
| LDO | +47.14 | -0.02 |
| AVAX | +29.67 | -0.71 |
| COMP | +9.27 | -0.82 |
| DOGE | +21.60 | -0.86 |
| LINK | +4.15 | -1.28 |
| HBAR | +4.99 | -1.60 |

## R-3 perm n=200 (shuffle volume series)
| Symbol | real_alpha | random_mean | random_std | sigma | perm_p | verdict |
|---|---|---|---|---|---|---|
| **AXSUSDT** | 97.01 | **107.81** | 24.97 | **-0.43σ** | 0.6700 | §3-D FAIL |
| SOLUSDT | 48.04 | 33.20 | 6.56 | 2.26σ | 0.0150 | borderline FAIL |

**AXS catastrophic §3-D**: random volume shuffle produces HIGHER alpha (107.81) than real (97.01). Sigma negative. Volume timing is completely irrelevant — "VWAP signal" was actually price trend-following dressed up as VWAP.

**SOL 2.26σ**: weak signal, single-symbol borderline (Q3 #4 SOL pattern again).

## Verdict — paradigm-level structural failure
1. **§3-D for AXS**: Shuffling volume yields HIGHER alpha than real. Volume timing irrelevant.
2. **§3-C for SOL**: 4th time SOL shows single-symbol weak signal (Q3 #4 wick_multibar 4.49σ, this 2.26σ, etc.)
3. **R-2 mean sharpe NEGATIVE**: Most symbols negative, only 2 positive

## Lesson — VWAP "deviation" is mostly close-price trend
VWAP and close-price are highly correlated when both use same close-price series. Rolling 24h VWAP vs current close = essentially "is price above its 24h average?" — which is a trend indicator, not volume-specific.

The volume weighting was supposed to add information about HOW the average was achieved (volume-weighted vs simple). But:
- For SOL/AXS in trending periods, volume-weighted ≈ simple-weighted after normalization
- Volume timing (when high-volume bars occurred) doesn't carry directional info
- Random shuffle of volume yields same trend signal as real volume

**§3-M 신규 antipattern**: Reference-price paradigms (VWAP, SMA, EWMA) with deviation z-score on close-price → mostly captures trend, not the reference-specific info. Permutation of weighting produces similar alpha.

**Implication**: To extract value from volume, need TIMING-DEPENDENT use:
- Volume profile concentration at price levels (intra-bar)
- Volume Δ at extreme price moves (leading indicator)
- Anomalous volume bursts (z-score with explicit threshold gating, like wick_reversal binary)

55th paradigm graveyard. Volume domain explored but reference-price formulation fails. Future direction: timing-dependent volume signals (volume burst at intra-bar event), not aggregate weighting.

## Q3 status (7/7 graveyard)
| # | Paradigm | Outcome | Lesson |
|---|---|---|---|
| 1 | oi_funding_corr_regime | §3-D §3-J | two-seeded fade joint |
| 2 | wick_reversal | POSITIVE 3σ | NEW dim shape proven |
| 3 | wick_reversal_volume | §3-H 3rd | filter monotonic degrade |
| 4 | wick_reversal_multibar | POSITIVE SOL 4.49σ | §3-C single-symbol |
| 5 | range_expansion | §3-K | shape > magnitude |
| 6 | wick_prior_joint | §3-L | binary AND ≠ filter |
| 7 | vwap_deviation | §3-D §3-M | reference-price = trend |

Q3 큐 7개 시도 중 0 R-5 시드, 1 NEW dim POSITIVE 3σ (Q3 #2 wick_reversal), 1 single-symbol POSITIVE 4σ (Q3 #4 wick_reversal_multibar SOL).
