# realized_vol_asymmetry — Graveyard Note (2026-05-06, 49th graveyard, 57th paradigm overall)

## 설계
Q3 #9 — skewness_regime (graveyard) cousin. Upside vs downside realized vol 분리:
- upside_vol = sqrt(mean(r²) for r > 0) over rolling N
- downside_vol = sqrt(mean(r²) for r < 0) over rolling N
- asymmetry = downside_vol - upside_vol
- asym_z = z-score over rolling M

Modes: fade (extreme asymmetry → reversion), follow (asymmetry continues regime).

가설: skewness_regime은 distribution 전체 3rd moment 사용 → 정보 dilute. 명시적 upside/downside 분리는 directional info 보존.

## R-1 SOL sweep (36 specs, fade × follow × 18 configs each)
**1/36 PASS** alpha+sharpe ≥ 0:
- fade_vw288_ez2.5_h24: alpha 21.94/sharpe **0.03**/721 trades — essentially zero signal

All other 35 specs negative sharpe (-0.15 to -3+). Catastrophic.

## R-2/R-3 SKIPPED — paradigm-level fail
1/36 PASS with sharpe 0.03 is basically noise. No signal worth perm test.

## §3-G strong: skewness_regime cousin confirmed graveyard pattern
Both paradigms test "asymmetric distribution" hypothesis on returns. Different formulations (3rd moment vs vol decomposition) extract same underlying info. Both graveyard.

**Lesson**: Return distribution moments (skew, kurt, vol asymmetry) all fail at this granularity (5m crypto). Crypto returns are too noisy at intra-day TF for distribution moments to extract directional signal.

For asymmetric vol info to work, need:
- Longer aggregation (1h/4h/1d) — but then trade frequency low
- External regime indicator (funding/OI) to filter — but §3-J two-seeded-fade-joint risk
- Combine with intra-bar SHAPE info (wick) — but §3-G/§3-H combination risks

57th paradigm graveyard. Q3 #9. Distribution-moment family fully saturated (skewness, kurtosis, info entropy, vol asymmetry).

## Q3 status update (9/9 graveyard)
| # | Paradigm | Outcome | Lesson |
|---|---|---|---|
| 1 | oi_funding_corr_regime | §3-D §3-J | two-seeded fade joint |
| 2 | wick_reversal | POSITIVE 3σ | NEW dim shape proven |
| 3 | wick_reversal_volume | §3-H 3rd | filter monotonic degrade |
| 4 | wick_reversal_multibar | POSITIVE SOL 4.49σ | §3-C single-symbol |
| 5 | range_expansion | §3-K | shape > magnitude |
| 6 | wick_prior_joint | §3-L | binary AND ≠ filter |
| 7 | vwap_deviation | §3-D §3-M | reference-price = trend |
| 8 | btc_eth_3way_lead_lag | §3-H §3-N | N-way AND degrades |
| 9 | realized_vol_asymmetry | §3-G | distribution moments saturated |
