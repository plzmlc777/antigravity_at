# Graveyard — funding_velocity_cross_section_dispersion (paradigm 97 / batch P1)

**Date**: 2026-05-19 KST 12:00 (batch ad-hoc R-1 P1)
**Phase**: R-1
**Verdict**: BROAD_FALSIFIED
**Type**: E (event-study)

## Hypothesis

8h funding cycle 시점, sym i의 funding rate **변화율** Δf(i,t) = funding(i,t) - funding(i,t-8h).
동일 cycle universe-wide median + std로 cross-section z-score `cs_z_Δf` 계산.
|cs_z_Δf| > 2.0 outlier → mean-reversion fade.

## DNA distinct from existing paradigms

| Paradigm | Axis mismatch |
|---|---|
| funding_dispersion R-5 seeded (ETC) | statistic L (level) vs Δ (velocity) — axis 2 |
| paradigm 96 sign flip | categorical (sign change) vs continuous (Δ z) — axis 2 + axis 4 |
| paradigm 73 funding × OI joint | single funding axis vs joint axis — axis 4 |

R-0 inventory check: ≤ 4/6 DNA overlap with each — family-distinct PASS, dispatch authorized.

## R-1 setup

- Universe: 14 OHLCV-aligned Binance USDS-M perps (ADA/AVAX/BCH/BNB/BTC/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP)
- Substrate: `binance_funding_rate` DB (~2,593 cycles per sym, 8h cycle; WIFUSDT 5,085 cycles 4h cycle) + ohlcv joblib cache
- Trigger: per-cycle cross-section z-score of Δf(i,t) using universe median ± std
- Hold sweep: {4h, 8h, 16h} forward returns from `entry = cycle_ts + 1min`
- 4-quadrant Symmetric Negative Test (Lesson #19) — focus z=2.0, hold=8h
- Fee 8bp round-trip / cooldown 8h per sym
- Panel: **36,211 cycles / 864 days / 2.37 yr**

## R-1 results — focus cell (z=2.0, hold=fwd_ret_8h)

| Cell | n | mean_bp_post_fee | signal_t_excess | ci_lower_bp | perm_p_two | 3-gate |
|---|---|---|---|---|---|---|
| A focus high LONG | 1,300 | **-8.62** | -0.20 | -26.07 | 0.456 | FAIL |
| A mirror high SHORT | 1,300 | -7.38 | +0.60 | -25.68 | 0.746 | FAIL |
| B mirror low LONG | 1,262 | -8.47 | -0.18 | -26.27 | 0.469 | FAIL |
| B focus low SHORT | 1,262 | -7.53 | +0.58 | -26.94 | 0.726 | FAIL |

## Life-changing 4-dim (focus A LONG)

- trades_per_year: 549.6 (HIGH ample)
- per_trade_edge_pct: **-0.086%** (gate ≥2% — FAIL by 23x)
- capital_util: 0.50 (HIGH ample)
- annualized_sharpe: -0.61 (negative — FAIL)

## Why broadly falsified

All 4 quadrants cluster near fee floor (-7.4 ~ -8.6bp after 8bp fee). Mean signed but indistinguishable from fee drag — null mean t-stat from permutation pool was sufficient to absorb any "signal". Cross-section velocity of funding **alone** has no directional alpha.

Mechanism interpretation: Δf cross-section dispersion = leverage shock magnitude in symbol space at boundary, but this magnitude doesn't translate to price overshoot direction. Markets price the funding shift symmetrically (longs/shorts adjust quickly via boundary unwind), leaving no after-event drift.

## Family implications

Confirms funding family retire (Lesson #18 / family retire Tier 4, 2026-05-19). Cross-section velocity sub-class is the 4th independent funding-only mechanism falsification:
- paradigm 22 funding_carry (R-5 seeded, narrow 3-sym carry — exception)
- paradigm 73 funding × OI joint (graveyard)
- paradigm 79 funding extreme level retry (graveyard)
- paradigm 96 sign flip (graveyard)
- **paradigm 97 cross-section velocity (this graveyard)**

Funding axis single-signal variants — including LEVEL/Δ/sign — are now empirically exhausted across all known statistical class transforms.

## Artifacts

- code: `backend/scripts/research/funding_velocity_cross_section_dispersion_r1.py`
- metrics: `backend/runs/research_track/funding_velocity_cross_section_dispersion/r1__metrics.json`
- Mint log: `/tmp/p1_funding_velocity.log`
- INDEX entry: registered + graveyarded 2026-05-19

## Lesson candidates

None new — confirms existing #18 + family retire grid.
