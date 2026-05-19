# Paradigm 96 — R-1 Summary

## Verdict: BROAD_FALSIFIED

`funding_rate_sign_flip_event_alt_long_4h` — categorical funding sign flip boundary event triggers no exploitable directional alpha for 13-alt LONG (or any of 4 quadrants). 96-th paradigm graveyard.

## Sample density (lesson #11)

| | n | per-quarter avg | per-symbol avg |
|---|---|---|---|
| Sub-trigger A (pos->neg) | 3,470 | ~347 | ~289 |
| Sub-trigger B (neg->pos) | 3,464 | ~346 | ~289 |
| **Total** | **6,934** | | |

**Prescreen PASS** — 1-2 orders of magnitude above lesson #11 cutoff (30/cell).

## Symmetric Negative Test 4-quadrant (lesson #19) — primary hold 240m

| Quadrant | n | mean_bp | obs_t | sig_t_excess | perm_p | ci_lower_bp | three_gate |
|---|---|---|---|---|---|---|---|
| **A LONG (focus)** | 3,448 | **-16.47** | -4.77 | -3.15 | 0.000 | -23.71 | FAIL |
| A SHORT (mirror) | 3,448 | +0.47 | +0.14 | +3.22 | 1.000 | -6.26 | FAIL |
| B LONG (same-sign) | 3,440 | -6.11 | -1.70 | -0.11 | 0.432 | -13.22 | FAIL |
| B SHORT (mirror) | 3,440 | -9.89 | -2.76 | +0.35 | 0.662 | -16.78 | FAIL |

**0/4 quadrants three-gate PASS** = BROAD_FALSIFIED.

Key reads:
- A LONG focus is **directionally wrong** — pos->neg flip is followed by 16.5bp continued DOWNDRIFT, not bounce. perm_p=0.000 means signal is structurally negative (anti-alpha).
- A SHORT mirror has positive sig_t_excess +3.22 but CI lower -6.26bp straddles 0 and perm_p=1.000 (observation is in the upper bulk of the null) — fee floor saturation, no edge.
- B LONG/SHORT essentially zero signal (sig_t_ex near 0) — neg->pos flip is non-informative.

## Hold sweep A LONG (lesson #20 cond3 input)

| hold | mean_bp | sig_t_excess | three_gate |
|---|---|---|---|
| 240m (4h) | -16.47 | -3.15 | FAIL |
| 480m (8h) | -15.94 | -2.82 | FAIL |
| 720m (12h) | -16.39 | -2.43 | FAIL |

**Monotonic across hold** — mean stays at -16bp regardless of horizon. Mechanism is robustly anti-alpha, not horizon-dependent.

## Concentration diagnostics — A LONG focus

| | value | gate |
|---|---|---|
| n_quarters_measurable | 10 | |
| n_quarters_pos_t | 2 / 10 | FAIL (0.20 < 0.50) |
| n_symbols_measurable | 12 / 13 | (BNBUSDT excluded) |
| n_symbols_ci_pos | **0 / 12** | FAIL (0/12 = 0.00 < 0.30) |

**Concentration gate FAIL across all 4 quadrants**. Per-symbol CI lower bound is negative for every measurable symbol — uniformly anti-alpha for A LONG.

## Cross-proxy (lesson #29)

| Sub | obs (n) | fund |mag_z|>=1 (n) | jaccard | obs 3-gate | fund 3-gate | both_pass |
|---|---|---|---|---|---|---|---|
| A | 3,448 | 1,638 | 0.475 | FAIL | FAIL | False |
| B | 3,440 | 1,863 | 0.542 | FAIL | FAIL | False |

Both proxies fail independently. Strong magnitude flips show same direction (-17.8bp A, -12.1bp B) — magnitude does not rescue.

## Lesson #20 4-cond

**N/A** — focus three-gate FAIL precondition not met.

## Life-changing 4-dim (focus A LONG)

| dim | value | gate |
|---|---|---|
| trades_per_yr | 1,463 | PASS |
| per_trade_edge_net_pct | **-0.165%** | FAIL |
| capital_util_pct | 66.8% | PASS |
| annualized_sharpe | -3.11 | FAIL |
| **all_pass** | **False (2/4)** | |

Trades density is excellent and capital utilization is healthy, but the per-trade edge is structurally negative — paradigm is producing reliable loss, not reliable gain.

## Final verdict

**BROAD_FALSIFIED** — funding sign flip categorical boundary event is non-predictive (or anti-predictive for A direction) over 4-12h horizons across 12 measurable alts. Family-distinct hypothesis cleanly tested with abundant sample density; mechanism falsified, not data-limited.

## Lesson candidate (informational)

Funding sign flip in the **A direction (pos->neg)** is followed by continued price weakness, not reversal. Mechanism reading: pos->neg flip implies recent price decline already drove funding negative — flip is a lagging confirmation of weakness, and that weakness extends another 4-12h. The naive "long-positioning unwind -> bounce" intuition is wrong for crypto perp at this horizon. **Possible follow-up R-1 candidate**: invert direction (A SHORT on sub-trigger A, hold 4-12h) — but R-1 here showed sig_t_excess +3.22 with CI straddling 0 and perm_p 1.00 (CI/perm fail = fee floor saturation). Edge magnitude is too thin to clear fees.

## Family classification

`funding` family — no formal Tier 4 retire (paradigm 22 R-5 seed active + paradigm 79 active variants). Sign-flip categorical transform class is now documented as graveyard — no further sign-flip variants without different direction/horizon/conditioning hypothesis.

## Mint artifacts

```
~/auto_trading/backend/scripts/research/paradigm96_funding_sign_flip_r1.py
~/auto_trading/backend/runs/research_track/funding_rate_sign_flip_event_alt_long_4h/r1/
    r1_spec.md
    r1_metrics.json
    r1_summary.md
```
