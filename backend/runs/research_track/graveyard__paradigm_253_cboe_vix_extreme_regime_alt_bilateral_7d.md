# Paradigm 253 — CBOE VIX 90d z-extreme × alt bilateral 7d — GRAVEYARD (Tier3)

**Date**: 2026-08-11
**Phase reached**: Tier3 gate (post R-0 R0_PROCEED, post R-1 full sweep 168 cells)
**Verdict**: `TIER3_GRAVEYARD_ALPHA_DECAY_PLUS_FEE_SYMMETRIC`
**Lessons applied**: #11, #28, #37, #39, #40, #56, #61, #62, #77, #79, #82 candidate
**Lessons DOGFOODED (2nd sighting)**: **#39 sub-class A fee-floor symmetry** (168/168 A_sum
  and B_sum cells sum to exactly -0.16% = -2×fee, matches paradigm 239 pattern)

## Hypothesis

CBOE VIX (equity fear gauge) 90-day rolling z-score extremes predict alt bilateral
direction over 7-day holds. Four-quadrant SNT:
- A_focus / A_mirror: |vix_z| > +T triggers LONG / SHORT alt
- B_focus / B_mirror: |vix_z| < -T triggers SHORT / LONG alt

Universe: 14 alts (ADA/AVAX/BCH/BNB/BTC/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP).
Data: FRED VIXCLS daily 1990→2026-08-07 (9,247 rows), binance daily klines
2023-11-15→2026-08-10 (1,000 rows/sym).

## R-0 Prescreen — 9/9 PASS (verdict R0_PROCEED)

| Item | Test | Result |
|---|---|---|
| 1 | Lesson #61 slug grep | No prior VIX/CBOE paradigm |
| 2 | Lesson #79 predictive-content | max |corr| OOS = **0.0873** (BTC, h=7) > 0.05 ideal |
| 3 | Lesson #28 substrate | VIX 9,247 rows / 36y coverage; binance 1,000 rows/sym |
| 4 | Lesson #62 DNA | ≤3/6 overlap (vs ETF-netflow paradigm) < 5/6 fail |
| 5 | Lesson #56 family proxy | Paradigm 239 graveyard prescription: extend hold≥7d (implemented) |
| 6 | Lesson #40 structural | vix_z ∈ [-2.84, +8.51], both T=2.0 signs achievable |
| 7 | Lesson #11 density | T=1.5: 81 events / 2.6y = 31.2/yr — PASS |
| 8 | Lesson #39 axis | vix_z sign = macro fear regime, not bar_direction |
| 9 | Lesson #82 candidate | VIX close 21:15 UTC → alt entry T+1 00:00 UTC (2h45m gap clean) |

**R-0 warning that turned out to matter**: pretest showed POSITIVE corr(vix_z, fwd_ret)
(BTC OOS +0.087), implying contrarian LONG on high VIX (A_focus) as the mechanism.
But full-sample corr was near zero (BTC +0.012), so the OOS signal was regime-specific
to a recent slice — a red flag for out-of-sample persistence that manifested later.

## R-1 Full Sweep — 3 thresholds × 4 quadrants × 14 syms = 168 cells

**Three-gate PASS: 0/168 cells**. Best signal_t_excess = 1.95 (ADA T=2.0 A_mirror,
n=13). Best n≥20 cell: LINK T=1.0 B_mirror, mean_net +3.48%, sharpe +1.75, t_excess +1.15.

### Lesson #39 sub-class A — CONFIRMED at every cell

For **every** (sym, T) pair the sum `A_focus_pct + A_mirror_pct = -0.160%` and
`B_focus_pct + B_mirror_pct = -0.160%` — **exactly** -2× the 8bp round-trip fee.
Sample (T=2.0):

| sym | A_focus_pct | A_mirror_pct | A_sum_pct | fee_floor |
|---|---:|---:|---:|---:|
| BTCUSDT | -1.046 | +0.886 | -0.160 | -0.160 |
| ADAUSDT | -4.859 | +4.699 | -0.160 | -0.160 |
| FILUSDT | -6.271 | +6.111 | -0.160 | -0.160 |
| SOLUSDT | -1.853 | +1.693 | -0.160 | -0.160 |

This is the classical Lesson #39 sub-class A pattern (paradigm 239 twin): the trigger
`|vix_z| ≥ T` carries **zero directional information** over 7d holds; the axis
`sign(vix_z)` is a pure coin-flip after fee. Any apparent per-quadrant edge is
exactly the mirror of its counterpart, and both together fund the fee drag.

**Additional structural constraint**: at T≥1.5 the vix_z distribution in the
2023-11→2026-08 alt window does NOT reach ≤-1.5 (post-2020 low-VIX regime),
so B_focus/B_mirror cells at T=1.5, T=2.0 are entirely absent. Paradigm is
effectively single-sided (A-quadrants only) at meaningful thresholds.

## Tier3 Gate — 6 candidates tested, 0 PASS

| sym | quad | T | n | mean_net | raw_t | recent_1/3 | decay_ratio | G1 | G2 | verdict |
|---|---|---|---|---:|---:|---:|---:|---|---|---|
| LINK | B_mirror | 1.0 | 23 | +3.48% | 1.17 | **-2.42%** | -0.95 | FAIL | PASS | FAIL |
| XRP  | B_mirror | 1.0 | 23 | +5.59% | 0.98 | **-2.19%** | 0.00 | FAIL | PASS | FAIL |
| ADA  | B_mirror | 1.0 | 23 | +3.94% | 0.87 | **-5.00%** | -1.57 | FAIL | PASS | FAIL |
| AVAX | B_mirror | 1.0 | 23 | +4.11% | 0.89 | **-2.17%** | -0.24 | FAIL | PASS | FAIL |
| SOL  | B_mirror | 1.0 | 23 | +2.74% | 0.97 | **-1.79%** | -0.24 | FAIL | PASS | FAIL |
| XRP  | A_focus  | 1.0 | 27 | +2.29% | 1.42 | +2.16% | 0.77 | FAIL (t<1.5) | **BLOCKED** | FAIL |

**Two independent failure modes**:

1. **B_mirror alpha decay (5 cells)** — the "low VIX complacency → LONG alts as
   momentum-follow" mechanism was strongly positive in the first 1/3 of the window
   (2023-11 → 2024-11, alt bull market) but is uniformly **negative** in the recent
   1/3 (2025-11 → 2026-08). Tier3 G1 catches this via `recent_edge > 0` and
   `decay_ratio ≥ 0.30` conditions. All five cells fail both.

2. **A_focus fee-close-to-margin (1 cell)** — XRP contrarian SHORT on high-VIX days
   has +2.29% base edge, +0.14% under 1-day entry delay (94% loss of edge on delay).
   Tier3 G2 requires `net_headroom ≥ 3×`; XRP A_focus is 1.71×. This means the edge
   requires **exact T+1 execution** at day boundary; any latency destroys it. The
   current infrastructure cycle (1440 min = daily) cannot guarantee that.

## Root cause

The R-0 pretest OOS corr of +0.087 was carried by a specific regime slice that has
since ended. Two consistent structural issues:

1. **VIX z carries no per-quadrant edge** over 7d holds (Lesson #39 sub-class A
   confirmed universally, 168/168). What looked like an edge in ranked cells is
   direction-dependent noise around a symmetric fee floor.

2. **Where the mechanism did briefly work (B_mirror, low-VIX LONG)** it was
   regime-locked to the 2024 alt bull market and has fully died in the last
   ~9 months — exactly the situation tier3_gate's decay filter was designed to
   catch. This confirms Lesson #61 (predecessor monotonic temporal decay) at
   the cross-family level: alpha decay applies to macro-cross-asset paradigms
   equally to intraday RV / on-chain / funding-based paradigms.

3. **B-quadrant infeasibility at meaningful thresholds** — post-2020 low-VIX
   regime means vix_z ≤ -1.5 is empirically almost never triggered in the
   2023-11→ backtest window. Even if the mechanism existed, the sample would
   be too sparse to support it.

## Lesson candidacy

**Lesson #39 sub-class A** — 2nd DOGFOOD confirmed (1st at paradigm 108, prior
strong evidence at paradigm 239). Now upgraded from CANDIDATE to CONFIRMED status:
"For any trigger of form `|X| ≥ T` where X is a scalar aggregate statistic, if
paired A_focus/A_mirror over the same forward window sum to exactly -2×fee_rt
across ALL (sym, T) cells in a sweep, the trigger carries zero directional
information and no quadrant permutation can rescue it."

**No new lesson proposed** — 253 is a clean instance of prior Lessons #39, #61,
and #79 (with the R-0 pretest positive corr shown to be regime-dependent rather
than persistent). The infrastructure worked as designed (R-0 flagged marginal
support but permitted proceed; R-1 SNT caught the fee-floor pattern; tier3_gate
G1 caught the alpha decay; tier3_gate G2 caught the fee-close-to-margin case).

## Artifacts

- `runs/research_track/paradigm_253_.../r0_prescreen.json`
- `runs/research_track/paradigm_253_.../r1__metrics.json` (168 cells + SNT table)
- `runs/research_track/paradigm_253_.../g2_inputs.json`
- `runs/research_track/paradigm_253_.../tier3_gate__{LINK,XRP,ADA,AVAX,SOL,XRPUSDT_A_focus}.json`
- `runs/research_track/paradigm_253_.../trades__{sym}__{quad}__T{T}.json` (6 files)
- `runs/research_track/paradigm_253_.../trades_delayed__{sym}__{quad}__T{T}.json` (6 files)

## Next-direction speculation (informational, not for auto-dispatch)

- **Not**: extend VIX to VIX9D / VVIX (Lesson #56 same family)
- **Not**: retry at hold=14d or 30d (would need positive corr>0.05 pretest for
  those horizons; the recent-regime alpha decay is a substrate issue not a
  hold-window issue)
- **Maybe**: a **regime-conditioning** paradigm where VIX z is not the trigger
  itself but the filter for a different edge (e.g. crypto RV mean-reversion
  conditioned on VIX regime). This would require dispatching a fresh paradigm
  with different DNA rather than iterating 253.
