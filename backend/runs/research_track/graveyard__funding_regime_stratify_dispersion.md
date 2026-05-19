# Graveyard — funding_regime_stratify_dispersion (paradigm 98 / batch P2)

**Date**: 2026-05-19 KST 12:00 (batch ad-hoc R-1 P2)
**Phase**: R-1
**Verdict**: BROAD_FALSIFIED
**Type**: E (event-study)

## Hypothesis

BTC funding rate 30d rolling regime (HIGH p80+ vs LOW p20- vs MID) conditional, cross-section dispersion mean-reversion strength asymmetry. paradigm 69 highvol motif × funding regime 차원 결합 시 HIGH-funding regime (leverage stress) → cs_z(funding LEVEL) MR 강화 가설.

## DNA distinct from existing paradigms

| Paradigm | Axis mismatch |
|---|---|
| funding_dispersion R-5 seeded | adds regime stratify — axis 5 (aggregate vs stratified) |
| paradigm 69 btc_rv_highvol | regime statistic = RV vs funding rate — axis 2 |
| paradigm 22 funding_carry | per-sym 3 syms vs universe-wide stratify — axis 5 |

R-0 inventory check: ≤ 4/6 DNA overlap — family-distinct PASS, dispatch authorized.

## R-1 setup

- Universe: 14 OHLCV-aligned syms (same as P1)
- Substrate: `binance_funding_rate` + ohlcv joblib cache + BTC 30d rolling funding regime
- Regime: HIGH = BTC funding ≥ rolling 30d p80; LOW = ≤ p20; MID otherwise (rolling within 30d window)
- Trigger: cs_z(funding LEVEL) > +2 (HIGH outlier) or < -2 (LOW outlier), focus HIGH regime
- Hold sweep: {4h, 8h, 16h}, focus 8h
- 4-quadrant Symmetric Negative Test per regime
- Panel: **36,252 cycles / 864 days / 2.37 yr** — regime counts {HIGH: 11,127 / MID: 15,328 / LOW: 9,797}

## R-1 results — focus cell (HIGH regime, z=2.0, hold=8h)

| Cell | n | mean_bp_post_fee | signal_t_excess | ci_lower_bp | perm_p_two | 3-gate |
|---|---|---|---|---|---|---|
| HIGH A focus high LONG | 128 | +15.72 | +0.54 | -76.71 | 0.750 | FAIL |
| HIGH A mirror high SHORT | 128 | -31.72 | -0.21 | -130.99 | 0.561 | FAIL |
| HIGH B mirror low LONG | 789 | -6.49 | -0.16 | -24.84 | 0.530 | FAIL |
| HIGH B focus low SHORT | 789 | -9.51 | +0.04 | -28.89 | 0.539 | FAIL |

## Regime asymmetry diagnostic (B focus low SHORT z=2.0 hold=8h per regime)

| Regime | n | mean_bp | sigex | ci_lower_bp |
|---|---|---|---|---|
| HIGH | 789 | -9.51 | +0.04 | -28.89 |
| MID | 994 | -26.18 | -1.51 | -44.11 |
| LOW | 677 | -12.56 | -0.68 | -31.32 |

MID regime B SHORT actually most negative (sigex -1.51 anti-MR direction) — opposite of hypothesis. Regime stratification did not unlock alpha.

## Life-changing 4-dim (HIGH regime A LONG)

- trades_per_year: 54.1 (PASS ≥12)
- per_trade_edge_pct: **+0.157%** (FAIL — gate ≥2%)
- capital_util: 0.049 (FAIL — gate ≥0.30)
- annualized_sharpe: 0.21 (FAIL — gate ≥1.5)

## Why broadly falsified

HIGH regime A LONG showed +15.72bp mean post-fee — direction matches hypothesis (high funding stress + high cs_z dispersion outlier → fade up). BUT sigex only +0.54 (insufficient — need ≥2.0) and CI lower -76.71bp (massive variance, n=128 too small to differentiate). The "positive mean" was driven by ~3-4 outlier events.

B focus (low cs_z + SHORT) at -9.51bp shows no fade either — null result direction-symmetric.

Funding-LEVEL dispersion remains regime-blind. Adding BTC funding regime as a conditioner did not amplify signal; if anything MID regime showed the strongest anti-MR direction (continuation, not reversion).

## Family implications

Same as P1 — confirms funding single-signal family retire (Lesson #18 / Tier 4). Regime conditioning of funding-only mechanisms = no escape route. Funding × non-funding multi-axis (e.g., funding × vol regime × time-of-day, per family retire amendment) remains untested.

## Artifacts

- code: `backend/scripts/research/funding_regime_stratify_dispersion_r1.py`
- metrics: `backend/runs/research_track/funding_regime_stratify_dispersion/r1__metrics.json`
- Mint log: `/tmp/p2_funding_regime.log`
- INDEX entry: registered + graveyarded 2026-05-19

## Lesson candidates

None new. Confirms existing #14 vol-regime stratify in funding context — regime stratify alone cannot transform aggregate noise into directional alpha when underlying statistic class is fully exhausted.
