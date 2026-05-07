# wick_reversal — Graveyard Note (2026-05-06, 42nd graveyard, 50th paradigm overall) ⭐ POSITIVE 3σ borderline

## 설계
5m candle OHLC 데이터 사용. NEW DIMENSION — close-to-close 이외에 처음 시도되는 intra-bar wick shape paradigm:
- lower_wick_frac = (min(open,close) - low) / (high - low)
- upper_wick_frac = (high - max(open,close)) / (high - low)
- prior_ret = close.pct_change(prior_lookback) — 1h 직전 가격 변화

Entry rule (liquidation cascade proxy):
- lower_wick_frac > wick_thresh AND prior_ret < -prior_move_pct → LONG (long-side liq cleared, reversal up)
- upper_wick_frac > wick_thresh AND prior_ret > +prior_move_pct → SHORT (short-side liq cleared, reversal down)
Hold N bars, SL.

## R-1 SOL sweep (81 specs)
**12/81 PASS** alpha+sharpe ≥ 0.

Top by sharpe:
| Spec | alpha | sharpe | trades | PF |
|---|---|---|---|---|
| **wt=0.5/pl=12/pm=0.03/h=12** | **+59.60** | **+1.51** | **84** | **1.64** ⭐ |
| wt=0.5/pl=12/pm=0.03/h=6 | +46.32 | +1.01 | 91 | 1.36 |
| wt=0.6/pl=12/pm=0.03/h=12 | +45.49 | +0.91 | 59 | 1.45 |
| wt=0.5/pl=12/pm=0.03/h=24 | +49.23 | +0.89 | 81 | 1.35 |

§3-A check: relax wick from 0.7 to 0.5 → trades 33 → 84, sharpe 0.53 → 1.51. **NOT rare-event** (relax IMPROVES sharpe).
Pattern: prior_lookback=12 (1h prior), prior_move=0.03 (3% prior move) sweet spot — wick reversal needs both extreme directional move AND wick rejection.

## R-2 multi-symbol (10종, primary spec wt=0.5 pl=12 pm=0.03 h=12)
- **alpha pos: 10/10** ⭐ (perfect, similar quality to seeded paradigms)
- **sharpe pos: 8/10** (only AXS -0.33, LDO -0.09 negative)
- alpha mean: **+58.36** (큐 전체 비교 매우 강함)
- sharpe mean: 0.595
- trades_total: **1515** (avg 150/symbol)

| Symbol | alpha | sharpe | trades | PF |
|---|---|---|---|---|
| HBAR | +71.50 | +0.79 | 127 | 1.27 |
| AVAX | +69.24 | +0.87 | 102 | 1.28 |
| ETC | +69.57 | +0.66 | 89 | 1.35 |
| DOGE | +63.76 | +0.82 | 137 | 1.22 |
| UNI | +61.81 | +0.55 | 191 | 1.15 |
| SOL | +59.60 | +1.51 | 84 | 1.64 ⭐ |
| COMP | +52.87 | +0.48 | 141 | 1.12 |
| LDO | +51.59 | -0.09 | 249 | 0.98 |
| LINK | +50.21 | +0.69 | 118 | 1.19 |
| AXS | +33.42 | -0.33 | 277 | 0.95 |

## R-3 perm n=200 (shuffle high/low pair, preserve open/close → wicks at random times)
| Symbol | real_alpha | random_mean | random_std | random_max | sigma | perm_p | verdict |
|---|---|---|---|---|---|---|---|
| **SOLUSDT** | 59.60 | 16.53 | 12.91 | 58.21 | **3.34σ** | **0.0000** | borderline FAIL |
| **AVAXUSDT** | 69.24 | 9.58 | 19.96 | 49.76 | **2.99σ** | **0.0000** | borderline FAIL |
| DOGEUSDT | 63.76 | 20.42 | 28.71 | 86.39 | 1.51σ | 0.0550 | FAIL |
| HBARUSDT | 71.50 | 33.96 | 30.62 | 115.39 | 1.23σ | 0.1200 | FAIL |

**0/200 shuffles beat real for SOL/AVAX** — perm_p exactly 0. Signal IS real, just falls below 4σ elite cutoff due to **high random_std** (wide distribution of random outcomes).

## Verdict — POSITIVE 3σ borderline (NEW dimension proven exists)
**Why NOT R-5 seed**: 4σ cutoff not met for any symbol. Maximum sigma 3.34σ (SOL).
**Why POSITIVE**: 
1. perm_p=0.0 for SOL/AVAX (0 of 200 random shuffles beat real) — strong evidence signal is non-random
2. random_mean is 14-49% of real (clean §3-D — far below the 55-85% antipattern threshold)
3. R-2 alpha pos 10/10 + sharpe pos 8/10 — multi-symbol robust direction
4. Truly NEW DIMENSION — first paradigm using intra-bar wick shape (50개 paradigm 중 처음)

## Lesson — wick shape is real signal, but high variance
Wick reversal paradigm is the first to confirm intra-bar high/low shape carries directional information beyond close-to-close returns. The signal is **directionally correct** (10/10 alpha pos) but has **high noise variance** that limits per-symbol sigma to 3σ range.

**Pattern**: This matches the §3-A relaxation insight — relaxing wick threshold (0.7→0.5) dramatically improved sharpe (0.53→1.51). The signal benefits from MORE samples, not extreme rare-event filtering. With n=200 trades, signal-to-noise ratio still doesn't reach elite gate.

## Future re-test 후보 방향
1. **Combine with volume**: wick + above-median volume might filter noise
2. **Longer holds**: hold_bars 12 → 24 or session-bar holds (until next 5m close after H+1h)
3. **Multi-bar wick aggregation**: 3-bar consecutive wick dominance (rarer but stronger)
4. **Re-test with richer data**: aggTrades data (when backfilled for paper-pool symbols) could provide trade-level liquidation proxy stronger than wick estimate

## §3 anti-pattern check — clean
- §3-A: relax improves → not rare-event ✓
- §3-B: full data, no max-bars ✓
- §3-D: random_mean is 14-49% of real (vs §3-D 55-85% threshold) ✓
- §3-E: 10/10 alpha pos ✓
- §3-F: real-time wick computation ✓
- §3-G: NEW dimension (no prior wick paradigm) ✓
- §3-J: single-domain, no joint with seeded fade ✓

50th paradigm. Non-saturation, non-§3-G — clean POSITIVE just shy of elite cutoff.
