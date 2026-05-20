# Graveyard — paradigm 114 alt_range_breakout_24h_trailing_high_continuation_long_2h

**Verdict**: `BROAD_FALSIFIED_FEE_FLOOR`
**Phase**: R-1 (single dispatch, halted per continuous-parallel campaign policy)
**Date**: 2026-05-20 KST
**Host**: hcp_local (paradigm-architect agent)
**Wall clock**: 2.3 seconds (cache reuse from paradigm 113)
**Total graveyards including this**: 114

## Hypothesis

Classic CTA / turtle-trader / Donchian channel breakout — NEVER tested as a paradigm in 113 graveyards.

When an alt's 1h close exceeds the prior 24h trailing high (rolling max of prior 24 hourly closes, excluding current bar) AND no other breakout (up or down) occurred in the prior 12h → continuation LONG for next 2h. Mirror: close < prior 24h trailing low → continuation SHORT.

The 12h debounce ensures FRESH breakout (not consecutive bars grinding the level).

## 5-axis novelty (4/5 NOVEL ex ante)

| Axis | Verdict | Rationale |
|---|---|---|
| Statistic | NOVEL | trailing max/min over fixed window = pure deterministic price-level event. All 113 prior paradigms used z-scores / percentile rank / ratios / regime classifications. No prior catalog entry on Donchian-style level breakout. |
| Universe | not novel | standard 13-alt |
| Frame | partial | 1h × 2h same as paradigm 113 frame, but trigger axis (hour-of-day vs trailing-extremum) is categorically different mechanism |
| Mechanism | NOVEL | trend-following / breakout continuation — first instance of this class in catalog (not momentum z-score, not mean-reversion, not regime-conditional, not event-anchored) |
| Trigger | NOVEL | deterministic price-level crossing + 12h debounce — discrete event-time trigger, not statistical threshold |

DNA collision check vs existing `range_compression_directional_break_alt_30m_240m` (graveyard 2026-05-15): 4/5 dim distinct. That paradigm tested STATISTICAL compression (path tortuosity z ≥ 2.5 + |return| > 2× vol). This paradigm tests PRICE-LEVEL breakout (rolling extremum threshold). NOT a DNA collision.

## R-0 prescreens

| Lesson | Result |
|---|---|
| #11 sample density | PASS — per-quarter up=158.8, dn=166.4 ≫ 30 floor (n_quarters=9) |
| #19 SNT 4-quadrant | implemented in single batch |
| #20 narrow-scope | debounced trigger rate 1.25%/hr up + 1.32%/hr dn → narrow but not extreme; life-changing 4-dim layer included |
| #21 axis-stacking diagnostic | included (breakout-only vs joint(breakout+debounce)) |
| #28 substrate availability | PASS — paradigm 113 joblib cache reused (13 alts × 24mo × 312 files, ~11MB, load time 0.3s) |
| #30 data window ratio | PASS — 2.0yr / 2.4yr = 83% |
| #34 empirical distribution | measured; raw 9.7% / 9.9% up/dn, debounced 1.25% / 1.32% (12.9% / 13.3% retention) |
| #39 sub-class A antipattern | flagged because mathematical mirror by construction = perfect ±5.41bp; however interpretation requires care (see below) |
| #40 structural threshold feasibility | PASS — rolling extremum always exists |

## R-1 Results — 4-quadrant SNT (primary hold=2h, debounced)

| Quadrant | n | gross_bp | net_bp | obs_t | ci_lower_bp | ci_upper_bp | perm_p | sigex | gate_3 | conc | q_pos | syms_ci_pos |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A_focus break_up LONG** | 2858 | **+5.41** | -2.59 | -0.94 | -8.02 | +2.69 | 0.994 | **+2.54** | FAIL | FAIL | 2/9 | 0/13 |
| A_mirror break_up SHORT | 2858 | -5.41 | -13.41 | -4.85 | -18.69 | -7.99 | 0.045 | -1.75 | FAIL | FAIL | 2/9 | 0/13 |
| **B_same break_dn SHORT** | 2995 | **+6.07** | -1.93 | -0.80 | -6.65 | +3.13 | 0.991 | **+2.34** | FAIL | FAIL | 4/9 | 0/13 |
| B_mirror break_dn LONG | 2995 | -6.07 | -14.07 | -5.82 | -19.13 | -9.35 | 0.014 | -2.23 | FAIL | FAIL | 1/9 | 0/13 |

**Key statistical findings:**
1. **A_focus + B_same BOTH show positive gross** (+5.41bp / +6.07bp) — continuation mechanism EXISTS as a price phenomenon. `signal_t_excess` > 2.0 on both focus quadrants confirms the observed t-stat is 2σ above the fee-drift null mean → genuine alpha above fee structure baseline.
2. **But max gross < 16bp fee floor** → net edge negative → uneconomic.
3. CI bounds on net include zero (both focus CIs span 0), so even at gross the effect is borderline at this sample size.
4. **Per-symbol concentration = 0/13** — no single alt has bootstrap CI lower > 0 net. The thin edge is broadly distributed (good for robustness, bad for capital concentration).
5. Mirror quadrants have strongly negative net (-13.4bp / -14.1bp) and significant perm_p — confirms direction is correctly attributed (mirrors LOSE meaningfully).

## Lesson #21 axis-stacking diagnostic (POSITIVE — debounce synthesizes alpha)

| Variant | A_focus net_bp | B_same net_bp |
|---|---|---|
| Raw breakout (no debounce) | -5.52 | -8.20 |
| **Joint (breakout + 12h debounce)** | **-2.59** | **-1.93** |

`joint_synthesizes_alpha_A = True`, `joint_synthesizes_alpha_B = True`. The 12h debounce CORRECTLY filters out lower-quality consecutive-grind breakouts. This validates the debounce design but does NOT save the paradigm from the fee floor.

## Hold sweep on A_focus (Lesson #37 full scan)

| hold (h) | n | gross_bp | net_bp | sigex | gate_3 | conc |
|---|---|---|---|---|---|---|
| **1h** | 2858 | **+6.95** | -1.05 | **+4.29** | FAIL | FAIL |
| 2h (primary) | 2858 | +5.41 | -2.59 | +2.54 | FAIL | FAIL |
| 4h | 2858 | +6.61 | -1.39 | +2.20 | FAIL | FAIL |
| 8h | 2858 | +6.27 | -1.73 | +1.67 | FAIL | FAIL |

`lesson37_sweep_scan.n_sweep_cells_3gate_AND_conc_pass = 0`. No cell across hold sweep clears 3-gate AND Concentration AND life-changing. 1h hold is best (gross +6.95bp, sigex +4.29 strong) but still net -1.05bp because fee dominates.

## Lesson #39 symmetry diagnostic — special note

`A_focus_gross = +5.41bp`, `A_mirror_gross = -5.41bp`, sum = 0.0 → `is_perfect_mirror = True`.

However this does **NOT** trigger Lesson #39 sub-class A (broad-uniform-negative). Sub-class A requires that BOTH focus and mirror show uniformly-negative signal (i.e. trigger has zero directional info, joint signal is pure direction-bet + fee drag). Here:
- A_focus gross **+5.41** and B_same gross **+6.07** are both **positive** → trigger DOES carry directional info.
- The "mirror" is perfect because mirror = LONG vs SHORT on same trigger set = mathematically forced to be ±(same gross).

The correct interpretation is **fee floor**: mechanism exists but gross magnitude < fee. This is Lesson #39 antipattern format only superficially — substantively this is the "Lesson #35 fee-trap" mode (paradigm 104 candidate), NOT the "no directional info" mode.

## Life-changing 4-dim (A_focus)

| Dim | Threshold | Observed | Pass |
|---|---|---|---|
| trades/yr | ≥ 12 | 1433.9 | YES |
| edge/trade | ≥ +2.0% | **-0.026%** | **NO** |
| capital util | ≥ 30% | 32.7% | YES |
| ann. sharpe | ≥ 1.5 | **-0.66** | **NO** |
| ALL 4-dim | | | **FAIL** |

Even at the gross level (gross_mean +0.054%/trade < 2% threshold), this paradigm cannot pass the life-changing edge dimension. Trailing-breakout in liquid alt perps is structurally a thin-edge / high-frequency / high-utilization mechanism — antithetical to "life-changing" per-trade economics.

## Why this paradigm fails

1. **Mechanism is real but thin**. Both up-break LONG and dn-break SHORT show positive gross with sigex > 2.0 over n=2858+ each. Donchian breakout DOES produce a small directional drift on Binance perp alts.
2. **Fee floor**. At 8bp/leg = 16bp round-trip, even the best sweep cell (1h hold gross +6.95bp) is sub-fee by ~9bp.
3. **No concentration**. 0/13 alts have bootstrap-CI-positive net edge. The signal is broadly distributed (every alt sees a similar thin breakout drift) — there's no concentrated subset to lever onto.
4. **Life-changing structurally incompatible**. Edge per trade (gross +0.05%, net -0.03%) is two orders of magnitude below the +2% life-changing threshold.

## Comparison to existing paradigms

| Paradigm | Direction | Gross | Net | Verdict |
|---|---|---|---|---|
| 103 cross_ex_funding_spread | LONG | +12-14bp | sub-fee | BROAD_FALSIFIED_FEE_FLOOR |
| 104 cross_ex_OI_differential (240m) | LONG | +25.7bp | sub-fee | BROAD_FALSIFIED + NARROW |
| **114 trailing_breakout** | LONG/SHORT | **+5.4-6.1bp** | sub-fee | BROAD_FALSIFIED_FEE_FLOOR |

The Donchian-style breakout produces the THINNEST positive gross of the three recent fee-floor graveyards. Trailing-extremum is a weaker continuation trigger than venue-spread (p103) or OI-differential (p104).

## Family / lesson implications

**Does NOT trigger family retire.** Breakout / trend-following / Donchian is a first-instance class. One graveyard is insufficient evidence to retire the broader "level-crossing" axis. Future variants to consider:

1. Longer window (7d / 14d / 30d trailing extremum) — but `range_compression_directional_break_alt_30m_240m` already showed compression-on-vol approach failed. Pure level approach also fails at 24h, may also at longer.
2. ATR-anchored / vol-normalized breakout (close > prior 24h max + k × ATR) — would shift trigger rate down + cell sample size; need #11 prescreen.
3. Volume-confirmed breakout (close > prior 24h max AND volume > 90th percentile prior 24h) — adds confirmation axis; risks Lesson #21 axis stacking trap (must show synthesis > volume-alone).
4. Asymmetric debounce window (24h or 48h instead of 12h) — diagnostic already shows joint synthesizes alpha; longer debounce might tighten further but unlikely to clear fee floor since max raw gross is only ~7bp.

**Lesson candidate**: "deterministic price-level extremum triggers on liquid alt perps produce single-digit-bp gross drift — uneconomic at 16bp retail fee." Not yet promoted to formal lesson (n=1 dogfood); flag for future +1 graveyard in this class to promote.

## Files

- code: `backend/scripts/research/paradigm114_alt_range_breakout_24h_trailing_high_continuation_long_2h_r1.py`
- metrics: `backend/runs/research_track/alt_range_breakout_24h_trailing_high_continuation_long_2h/r1__metrics.json`
- log: `backend/runs/research_track/alt_range_breakout_24h_trailing_high_continuation_long_2h/r1__stdout.log`
- INDEX entry: `backend/runs/research_track/INDEX.json` :: `alt_range_breakout_24h_trailing_high_continuation_long_2h`

## Next action

`graveyard` — strict halt per continuous-parallel campaign policy. No R-2 dispatch.

Optionally, future paradigm 115 could try ATR-normalized breakout (path variant #2 above) to test whether normalization concentrates the signal onto a subset of alts.

---

KST 2026-05-20 13:25
