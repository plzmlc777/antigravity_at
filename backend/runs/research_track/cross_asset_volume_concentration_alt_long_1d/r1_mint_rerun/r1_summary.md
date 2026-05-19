# R-1 Summary — cross_asset_volume_concentration_alt_long_1d (Mint full-data re-run)

**Paradigm ID**: 94
**Run**: r1_mint_rerun
**Execution date**: 2026-05-19 (Mint, ssh tunnel verified)
**Wall-clock**: 0.08 min (5 seconds)
**Verdict**: `BROAD_FALSIFIED_DIRECTION_INVERTED`

## Verdict

`BROAD_FALSIFIED_DIRECTION_INVERTED` — focus three-gate FAIL (ci_lower negative
+ Concentration FAIL), but **mirror three-gate FULL PASS robust** at n=702
with all four robustness layers (sigex/perm_p/ci_lower/fee floor) cleared.

Per paradigm-architect spec the focus hypothesis is **definitively falsified**
at R-1: mirror direction (BTC dominance HIGH -> alt LONG) is the actual signal
carrier on full 2.4yr data, not the original "concentration -> alt rotation"
hypothesis. Per trigger-swap antipattern (Lesson #8) and mirror antipattern
catalog, mirror-direction PASS is **not** an auto-promotion. The mirror
direction (BTC share HIGH z>=+1.5 -> alt LONG +1d) is recorded as a separate
R-1 candidate requiring user explicit dispatch.

## 1. Three-gate (focus) — FAIL

| Metric | Value | Threshold | Pass |
|---|---|---|---|
| n_trades | 845 | >=30 | ✓ |
| gross_mean_bp | 37.18 | >=16 (fee floor) | ✓ |
| signal_t_excess | +2.64 | >=2.0 | ✓ |
| perm_p_one_sided_above | 0.003 | <=0.10 | ✓ |
| bootstrap_ci_lower_bp | **-4.60** | **>0** | **✗** |

3-gate **2/3** (sigex + perm pass, **CI lower includes 0**). Focus signal is
**not robust at i.i.d. bootstrap** — confidence interval [-4.6, +65.0] crosses
zero despite high mean t-excess.

## 2. Three-gate (mirror) — PASS (full)

| Metric | Value | Threshold | Pass |
|---|---|---|---|
| n_trades | **702** | >=30 | ✓ |
| gross_mean_bp | **96.97** | >=16 (fee floor) | ✓ |
| signal_t_excess | **+6.86** | >=2.0 | ✓ |
| perm_p_one_sided_above | **0.000** | <=0.10 | ✓ |
| bootstrap_ci_lower_bp | **+59.77** | **>0** | **✓** |

Mirror direction is **3-gate FULL PASS** at n=702 with CI fully positive
[+59.8, +117.5]. This is the **diagnostic 4th gate** that the focus failed —
mirror clears all four layers including i.i.d. bootstrap. **6.86 sigex is the
strongest single R-1 signal observed in the campaign besides paradigm 69
(highvol cascade) and paradigm 87 (delisting, since R-2 collapsed)**.

## 3. Concentration Gate (Lesson #16)

### Focus
- Per-quarter: 4/10 quarters positive t (`q_pos_t_ratio=0.40 < 0.50 FAIL`)
  - Strong positive: 2024Q1 (t=+2.32), 2024Q4 (t=+3.79), 2025Q3 (t=+3.26)
  - Strong negative: 2025Q1 (t=-4.40), 2026Q2 (t=-15.62)
- Per-symbol: **0/13** syms ci_pos (`sym_ci_pos_ratio=0.00 FAIL`)
- **Concentration FAIL** — focus signal driven by 3 specific quarters, zero
  symbols robust on their own.

### Mirror
- Per-quarter: **7/10** quarters positive t (`q_pos_t_ratio=0.70 >= 0.50 ✓`)
  - 8 quarters with non-trivial size; 7 positive, only 2024Q4/2025Q1/2026Q2
    negative. Mirror is **temporally homogeneous**.
- Per-symbol: 3/13 syms ci_pos (`sym_ci_pos_ratio=0.231 < 0.30 marginal FAIL`)
  - AVAX (+114.5bp ci_lo +6.8), BCH (+164.7bp ci_lo +62.3), LTC (+89.3bp ci_lo +9.7)
  - Sub-marginal (just below 0.30): DOGE prob_pos high but ci_lo -4.3 (n=54)
- Mirror Concentration **marginal FAIL** at symbol-CI threshold but **strong
  quarter robustness** (7/10).

## 4. Fund proxy (Lesson #29 cross-proxy)

### Fund focus (BTC abs vol_usd z <= -1.5)
- n=325 (25 trigger days), gross 19.95bp (just above 16bp fee floor),
  sigex **+0.41**, perm_p 0.333, ci_lower **-18.0bp**.
- Fund focus **3-gate FAIL** strongly.

### Fund mirror (BTC abs vol_usd z >= +1.5)
- n=923, gross **+92.68bp**, sigex **+3.86**, perm_p **0.000**, ci_lower **+48.2bp**.
- Fund mirror **3-gate FULL PASS**.

### Cross-proxy overlap (obs vs fund focus)
- Jaccard 0.084 (7 days intersection / 83 union). **Cross-proxy non-redundant**.

**Cross-proxy verdict**: focus track **both** obs and fund FAIL — confirms
falsification. Mirror track **both** obs and fund PASS — mirror is real
signal, not a single-proxy artifact (Lesson #29 dogfood passes the mirror).

## 5. Comparison to prior local R-1 (72-day intersection)

| Metric | Prior local (72d) | Mint full (845d) | Diff |
|---|---|---|---|
| common_dates | 101 | 845 | **8.4x** |
| share_z usable | 72 | 816 | **11.3x** |
| Focus n_triggers | 5 (cutoff -1.2) | 65 (cutoff -1.5) | **13x** |
| Focus n_trades | 62 | 845 | 13.6x |
| Focus gross_mean_bp | +11.28 | **+37.18** | **3.3x stronger** |
| Focus sigex | +0.15 | **+2.64** | recovered |
| Focus ci_lower | -70.9 | -4.6 | tightened |
| Mirror n_triggers | 4 | **54** | **13.5x** |
| Mirror n_trades | 52 | **702** | **13.5x** |
| Mirror gross_mean_bp | +230.0 | +96.97 | regularised |
| Mirror sigex | +2.76 | **+6.86** | **2.5x stronger** |
| Mirror ci_lower | +74.4 | **+59.77** | confirmed positive |
| Verdict | BROAD_FALSIFIED_FEE_FLOOR | **BROAD_FALSIFIED_DIRECTION_INVERTED** | upgraded |

### Diagnosis

The prior local 72-day intersection (2026-01-21 ~ 2026-04-02) was **a single
regime window** (2026Q1 + early 2026Q2). On that narrow slice:
- Focus gross +11.28bp < 16bp fee floor → fee-floor verdict
- Mirror n=4 strong but underpowered → DIRECTION_INVERTED_MIRROR_PASS_SPARSE

The Mint full 2.4yr window reveals:
- **Focus is below fee-floor on 2026Q1 specifically (mean -231bp t=-4.40)**
  but **strongly above fee-floor in 2024Q1/2024Q4/2025Q3**. The 2.4yr
  aggregate is gross +37bp (clears fee floor) but bootstrap CI [-4.6, +65]
  crosses zero — focus is fragile across regimes.
- **Mirror is the actual paradigm**: n=702, 7/10 quarters positive, sigex
  +6.86, ci_lower +59.77bp. This was sparse-only-evidence (n=4) on local
  72-day window; full data confirms it is the real signal direction.
- **The hypothesis was structurally inverted**: low BTC share is not alt
  rotation leader; **high BTC share is** (BTC volume dominance phases are
  followed by alt momentum days).

## 6. Family-distinct verdict

family_distinct_new_transform_class — paradigm 80/82/83/85 (5m microstructure
advisory caution family) is different (daily aggregation), KR equity post-earnings
family (paradigm 92/93 Tier 4 retired) is different (crypto perp), geometric
path metrics, funding/OI joint event, BTC/ETH 5m corr breakdown all distinct.

Note: mirror direction (BTC share HIGH -> alt LONG +1d) is a **new transform
class** because no prior paradigm has used unsigned volume share as a momentum
trigger.

## 7. Final verdict

**`BROAD_FALSIFIED_DIRECTION_INVERTED`** — original hypothesis (compression
-> rotation) is falsified on full 2.4yr data despite the 72-day local run
suggesting fee-floor proximity. The **mirror direction** (BTC volume share
HIGH z -> alt LONG +1d) is a candidate for a separate R-1 dispatch (NOT
auto-promoted per trigger-swap antipattern Lesson #8).

### HALT confirmed
- R-2/R-3/R-4 not initiated (per agent spec + user instruction).
- Mirror direction NOT auto-dispatched (per Lesson #8 trigger-swap antipattern
  + paradigm 70 mirror antipattern catalog).
- New mirror-direction R-1 paradigm spec proposal:
  - Name: `cross_asset_volume_share_high_alt_long_1d`
  - Hypothesis: BTC daily USD-volume share z(30d) >= +1.5 (BTC dominance
    phase) -> LONG 13 alts at next-day 00:00 UTC open, hold +1d, exit close.
  - Already has R-1 evidence: n=702, sigex +6.86, perm_p 0.0, ci_lower
    +59.77bp, 7/10 quarters positive, 3/13 syms ci_pos.
  - Lessons preview for fresh R-1: Concentration sym_ci_pos_ratio 0.231 is
    marginal sub-threshold; verify with refined block bootstrap before R-2.

## 8. Lessons consumed

- Lesson #8 trigger-swap antipattern: mirror PASS does **not** auto-promote
  the mirror direction. Separate R-1 required.
- Lesson #16 Concentration Gate: focus FAIL Concentration cleanly (0/13 syms
  ci_pos) — necessary diagnostic; without it, focus's +2.64 sigex would have
  looked like a marginal PASS.
- Lesson #19 Symmetric Negative Test: 2-quadrant single-batch — mirror n=702
  vs focus n=845 demonstrates symmetric measurement criticality. Mirror would
  have been missed entirely if only focus had been measured.
- Lesson #29 cross-proxy strict: fund and obs **both** mirror-direction PASS;
  fund focus FAIL provides additional falsification for focus direction.
- Lesson #11 sample density: 12x window restoration converted a marginal
  fee-floor verdict to a definitive direction-inverted verdict.

## 9. Mint artifacts

- `~/auto_trading/backend/runs/research_track/cross_asset_volume_concentration_alt_long_1d/r1_mint_rerun/r1_metrics.json`
- `~/auto_trading/backend/runs/research_track/cross_asset_volume_concentration_alt_long_1d/r1_mint_rerun/r1_spec.md`
- `~/auto_trading/backend/runs/research_track/cross_asset_volume_concentration_alt_long_1d/r1_mint_rerun/r1_summary.md`
- `~/auto_trading/backend/runs/research_track/cross_asset_volume_concentration_alt_long_1d/r1_mint_rerun/r1_script.py`
- `~/auto_trading/backend/scripts/research/cross_asset_volume_concentration_alt_long_1d_r1_mint.py`
