# Graveyard — paradigm 113 `intraday_hour_of_day_anchor_alt_directional_2h`

- **Date**: 2026-05-20 KST
- **Phase reached**: R-1 (verdict at R-1, no R-2 dispatch)
- **Verdict**: `BROAD_FALSIFIED`
- **Predecessor**: paradigm 112 SAMPLE_INSUFFICIENT, paradigm 111 BROAD_FALSIFIED
- **Wall clock**: 0.89 min
- **Script**: `backend/scripts/research/paradigm113_intraday_hour_of_day_anchor_alt_directional_2h_r1.py`
- **Metrics**: `backend/runs/research_track/intraday_hour_of_day_anchor_alt_directional_2h/r1__metrics.json`

## Hypothesis

24h crypto market exhibits time-zone-driven flow asymmetry at 4 anchor hours UTC
(00:00 KR/JP morning open, 07:00 EU open / Asia close overlap, 13:00 US open /
EU mid-day overlap, 21:00 US close). When an alt's prior 1h bar has signed
return z-score |z|≥1.0 vs rolling 30d AND the next bar opens at an anchor hour,
the next 2h hold continues prior direction (momentum extension during
liquidity overlap).

## Substrate

- Binance public archive `data.binance.vision/futures/um/monthly/klines/{sym}/1h`
- 13 alts × 24 months (2024-05 .. 2026-04) × 1h granularity
- 17,520 rows/sym × 13 syms = 227,760 1h bars
- Archive-direct, NO DB dependency (per local-context constraint)
- Backfill 51 sec / 11.4 MB total

## Novelty self-check (ex ante)

- Statistic = hour-of-day temporal anchor × signed |z|>=1 conjunction → **NOVEL**
- Universe = 13-alt standard → NOT NOVEL
- Frame = 1h trigger × 2h hold → PARTIALLY NOVEL
- Mechanism = time-zone liquidity overlap continuation → **NOVEL**
- Trigger = anchor hour ∈ {00,07,13,21} AND signed |z|>=1 prior 1h return → **NOVEL**
- **3/5 NOVEL ex ante**. Closest adjacency: paradigm 82 pre-funding window
  divergence (8h funding boundary), distinct cycle frequency + distinct
  mechanism.

## R-0 prescreens (all PASS, dispatch justified)

| Lesson | Check | Result |
|---|---|---|
| #11 sample density | per-quarter pos_z=230 / neg_z=223 (cutoff 30) | **PASS** |
| #19 SNT mandatory | 4-quadrant in single batch | **APPLIED** |
| #20 narrow-scope | 16.7% trigger rate by def; life-changing 4-dim layer | **APPLIED** |
| #21 axis stacking | hour-only + |z|-only diagnostics measured | **APPLIED** |
| #28 substrate availability | data.binance.vision HTTP 200 verified | **PASS** |
| #30 data window ratio | 24/24 months = 100% ratio | **PASS** |
| #34 empirical distribution | frac\|z\|≥1 = 0.211 (matches parametric expectation 0.317 well) | **PASS** |
| #40 structural threshold feasibility | signed z, \|z\|≥1 trivially reachable | **PASS** |

## R-1 results — 4-quadrant SNT (primary hold = 2h)

| Quadrant | n | gross_bp | net_bp | sigex | CI_bp | perm_p | 3-gate | concentration |
|---|---:|---:|---:|---:|---|---:|:---:|:---:|
| **A focus (posZ→LONG)** | 4147 | **−3.65** | −11.65 | −0.33 | [−16.99, −6.81] | 0.390 | FAIL | 0/13 syms |
| A mirror (posZ→SHORT) | 4147 | +3.65 | −4.35 | +2.12 | [−9.19, +0.99] | 0.989 | FAIL | 0/13 syms |
| **B same (negZ→SHORT)** | 4016 | **−6.93** | −14.93 | −1.40 | [−20.69, −8.66] | 0.089 | FAIL | 0/13 syms |
| B mirror (negZ→LONG) | 4016 | +6.93 | −1.07 | +3.80 | [−7.34, +4.69] | 1.000 | FAIL | 0/13 syms |

- **Both focus quadrants gross-negative**: continuation hypothesis directionally
  inverted.
- Mirrors are **exact symmetric** (gross ±3.65 and ±6.93) by construction —
  both net ≤ 0 (fee floor saturates the small gross effect).
- Per-symbol Concentration: **0/13 syms** ci_pos in ALL 4 quadrants — broad
  homogeneous negative (NOT cherry-pick artifact).
- Per-quarter Concentration: q_pos_ratio 0.11 / 0.33 / 0.22 / 0.33 across
  quadrants — no quarter cluster.

## Lesson #21 axis-stacking diagnostic (anti-synthesis)

| Axis subset | net bp |
|---|---:|
| Hour anchor ALONE (any z), LONG | **−6.69** |
| \|z\|≥1 ALONE (any hour), LONG | **−7.35** |
| Joint (anchor AND \|z\|≥1), LONG | **−11.65** |

**Joint is WORSE than either axis alone**. Stacking the two NULL axes
compounds fee drag without synthesizing alpha. Lesson #21 antipattern
confirmed (3rd dogfood after paradigm 83 OI 5m k-means latent regime).

## Hold sweep (focus A_focus_posZ_LONG)

| hold | n | gross_bp | net_bp | sigex | 3-gate |
|---:|---:|---:|---:|---:|:---:|
| 1h | 4147 | −0.89 | −8.89 | +1.21 | FAIL |
| **2h (primary)** | 4147 | −3.65 | −11.65 | −0.33 | FAIL |
| 4h | 3986 | +2.14 | −5.86 | +1.58 | FAIL |

No plateau, no hold cell achieves 3-gate PASS. Sigex monotonically increases
toward 4h (decay of MR pressure as horizon stretches) but still sub-fee.

## Life-changing 4-dim (A focus)

| Dim | Value | Threshold | Pass? |
|---|---:|---:|:---:|
| trades_per_year | 2121.4 | ≥ 12 | ✓ |
| per_trade_edge_pct | −0.12% | ≥ +2.0% | ✗ |
| capital_util_pct | 48.4% | ≥ 30% | ✓ |
| annualized_sharpe | −3.19 | ≥ 1.5 | ✗ |
| **pass_all_4_dim** | | | **✗** |

## Conclusion

Time-zone liquidity overlap **does NOT systematically extend prior 1h
momentum** in alt-perp 2h forward windows. Mechanism is structurally absent:

1. **Both focus directions FAIL** (LONG after up-spike at anchor hr: −3.65bp
   gross; SHORT after down-spike at anchor hr: −6.93bp gross) — continuation
   is rejected.
2. **Mirrors are exact symmetric ±k bp** (by construction since trigger
   selects ± regions of same panel) and both broad-uniform-negative net
   after fee — **Lesson #39 sub-class A signature** (trigger has near-zero
   directional info; observed sign asymmetry is pure fee drag).
3. **Lesson #21 anti-synthesis**: joint axis underperforms either subset
   alone. The temporal axis (hour anchor) carries no directional info, the
   magnitude axis (\|z\|≥1) carries no directional info, and stacking them
   compounds noise.
4. **Concentration 0/13 syms** in every quadrant: no symbol-cluster carve-out
   available; narrow-scope variant (Lesson #20) ineligible.

## Lesson candidates (no new lesson required)

- **Lesson #21 axis-stacking dogfood**: 3rd successful confirmation
  (paradigm 83 OI 5m k-means + paradigm 113 hour-anchor × \|z\| stacking).
- **Lesson #39 sub-class A symmetric perfect mirror**: 3rd dogfood
  (paradigm 108 + 113). Symmetric trigger by construction (signed z ±k)
  → mirrors mathematically ±gross identical → both broad-uniform-negative
  net → trigger has zero directional info, joint signal is pure
  direction-bet + fee drag.
- **Temporal axis (hour-of-day) family advisory caution candidate**: this
  is the FIRST hour-of-day paradigm test in 112 paradigm queue. Single
  instance does NOT warrant family retire. However, future temporal-axis
  paradigm (e.g. day-of-week, week-of-month, session-boundary close
  variants) should be advisory cautioned given (a) graveyard
  funding_cycle_8h family lesson "funding × non-funding multi-axis (e.g.,
  funding × vol regime × time-of-day) remains untested" was speculative,
  and now (b) hour-of-day × \|z\| momentum is directionally falsified
  (broad-uniform-negative). Hour-of-day axis combined with NON-momentum
  signals (e.g., volume z, OI z, premium z at anchor hr) might retain
  hypothesis space but is paradigm-distinct.

## Cumulative counters

- 113th graveyard
- 8 family retires (no new retire from this dispatch)
- 35 lessons (no new lesson; 3 dogfoods reinforce existing #21 + #39 + #34)
- Continuous-parallel campaign policy maintained

## Next action

`graveyard`. Halt at R-1 per directive. No R-2 dispatch (focus FAIL).

## Files

- Script: `backend/scripts/research/paradigm113_intraday_hour_of_day_anchor_alt_directional_2h_r1.py`
- Metrics: `backend/runs/research_track/intraday_hour_of_day_anchor_alt_directional_2h/r1__metrics.json`
- Log: `backend/runs/research_track/intraday_hour_of_day_anchor_alt_directional_2h/r1__stdout.log`
- Cache: `backend/runs/research_track/intraday_hour_of_day_anchor_alt_directional_2h/klines_cache/` (312 joblib files, 11.4 MB) — preserved for any follow-up
