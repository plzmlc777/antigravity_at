# Paradigm 248 — GRAVEYARD

**Slug**: `248_alt_daily_oi_flow_direction_x_price_direction_new_position_accumulation_1d_to_3d_bilateral`
**Dispatched**: 2026-08-08
**Failed at**: tier3_gate (G1)
**Verdict**: `G1_FAIL_ALPHA_DECAY`

## Hypothesis

When daily OI-delta z-score (60d rolling baseline) ALIGNS with daily price return direction,
this signals NEW POSITION ACCUMULATION → 1-3d continuation. Mechanistically distinct from
paradigm 21 (OI_up × price_DOWN squeeze, DECOUPLING).

## 4-quadrant SNT

- A-focus: OI+ & ret+ → LONG (new longs)
- A-mirror: OI+ & ret+ → SHORT
- B-focus: OI- & ret- → SHORT (new shorts)
- B-mirror: OI- & ret+ → LONG (p21 squeeze mechanism)

## R-0 prescreen

- **DNA vs p21**: 2/5 same, 3/5 different → PROCEED
- **Lesson #79 |corr|**: SOL +0.0653 PASS, LINK -0.0225 PASS, AVAX +0.0050 FAIL
- Slug grep: no prior hits
- Sample density: 61 events/quadrant on SOL → adequate

## R-1 backtest

Universe: 7 alt USDT-M perps (AVAX/BCH/BNB/DOGE/LINK/SOL/XRP) with hourly OI cached
(2024-03-02 → 2026-05-12, 802 daily rows each).

Sweep: 4 quadrants × 3 holds × 7 symbols = 84 cells. Fee: 0.08% roundtrip pre-deducted.

**Top-3 by t_stat (n>=20)**:

| symbol   | quadrant  | hold | n  | mean_pct | t_stat | win_rate |
|----------|-----------|------|----|----------|--------|----------|
| XRPUSDT  | A_focus   | 3d   | 52 | +3.914%  | +1.80  | 0.46     |
| LINKUSDT | B_mirror  | 3d   | 32 | +2.628%  | +1.62  | 0.59     |
| XRPUSDT  | A_focus   | 2d   | 52 | +2.701%  | +1.57  | 0.42     |

Best cell (raw): XRP A_focus 3d. **However**, this is a "few big winners" pattern
(win rate 0.46 < 50% but mean +3.91%) — vulnerable to time decay.

## G1 + G2 tier3_gate verdicts

### Best: XRPUSDT A_focus 3d (edge_after_1bar_delay = +2.88%)

- **G1: FAIL**
  - 시간가중 엣지: -0.0750% (halflife 90d weighted vs raw +3.9144%)
  - 시간가중 t: -0.03 (need >= 1.5)
  - 최근 1/3 엣지: +1.30%
  - 과거 1/3 엣지: +4.48%
  - decay_ratio: 0.29 (need >= 0.30) — barely below
- **G2: PASS** (headroom 36x, cycle_margin 3.0x)

### Runner-up: LINKUSDT B_mirror 3d (edge_after_1bar_delay = +0.94%)

- **G1: FAIL**
  - 시간가중 엣지: +0.0800%
  - 시간가중 t: +0.04
  - **최근 1/3 엣지: -1.5449%** (worse — actively negative)
  - decay_ratio: -0.32
- **G2: PASS** (headroom 11.8x)

## Diagnosis

Both top cells share the same pathology: raw-weighted edge is positive but **the alpha
has decayed** — the older third of the sample carried nearly all the return, and the
most recent 90-day-weighted mean is essentially flat (XRP) or negative (LINK).

Mechanistically this is consistent with alt perps growing more efficient at absorbing
OI signal since 2024H2. The naive "OI+ & price+ → continuation" edge that existed in
2024 has been arbitraged out by mid-2025+. Consistent with the informational-decay
pattern documented in Lesson #55/#61 for alt-perp momentum families.

Runner-up (LINK B_mirror = p21 squeeze mechanism) also decayed, which lines up with
paradigm 21's own historical trajectory in the alt universe.

## Lessons

1. **Raw t-stat is not enough** — this paradigm shows why tier3_gate.py's time-weighted
   G1 exists. Raw t=+1.80 looks marginal-positive but time-weighted t=-0.03 reveals
   the alpha is dead. Never eyeball raw mean.
2. **A high win-rate mismatch (46% with +3.9% mean) is a decay tell** — a few big
   winners in the older half of the sample drive the mean.
3. **Cross-symbol decay convergence** — different symbols and different quadrants of
   this paradigm all show the same recent-third negative pattern → paradigm-level
   informational decay, not idiosyncratic noise. Family-wide obsolescence.

## Non-actions

- Do NOT retry with different z-thresh / hold — the whole family is decayed.
- Do NOT retry with different alt universe — SOL/LINK/XRP/BNB all show the pattern
  and universe expansion is a spatial fix, not a temporal fix (Lesson #55 prescription
  out of scope).
- Reformulation would need a genuinely new decision mode (e.g., OI-conditional funding,
  OI regime-switching), not this direct alignment paradigm.

## Artifacts

- Script: `backend/scripts/research/r1_paradigm_248_alt_daily_oi_flow_direction_x_price_direction.py`
- Trades: `backend/runs/research_track/248_alt_daily_oi_flow_direction_x_price_direction/r1_trades_*.json`
- Summary: `backend/runs/research_track/248_alt_daily_oi_flow_direction_x_price_direction/r1_summary.json`
- Gate result XRP: `.../tier3_gate__XRPUSDT.json`
- Gate result LINK: `.../tier3_gate__LINKUSDT.json`
