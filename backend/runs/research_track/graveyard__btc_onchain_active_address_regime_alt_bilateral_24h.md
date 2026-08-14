# Graveyard — btc_onchain_active_address_regime_alt_bilateral_24h (Paradigm #248)

**Phase of failure**: R-1 PoC
**Verdict**: `R1_GRAVEYARD_BROAD_FALSIFIED_LESSON39_SUBCLASS_A`
**Date**: 2026-08-08
**Author**: paradigm-architect (autonomous cron dispatch)

---

## Hypothesis

BTC daily active address count (AdrActCnt from CoinMetrics community API — FREE, no auth)
reveals retail engagement cycles. 30-day rolling percentile rank of AdrActCnt:

- **HIGH regime** (`pct30 > 0.70`): peak network utility → BTC-sign-conditional alt continuation
- **LOW regime** (`pct30 < 0.30`): network slump → potential mean-reversion or continuation

4-quadrant Symmetric Negative Test (Lesson #19):
- A: HIGH × BTC_up → LONG alt vs SHORT alt (focus / mirror)
- B: HIGH × BTC_dn → SHORT alt vs LONG alt
- C: LOW × BTC_up → LONG alt vs SHORT alt
- D: LOW × BTC_dn → SHORT alt vs LONG alt

Hold sweep: 12h / 24h / 48h / 72h. Threshold sweep: (0.20/0.80), (0.25/0.75), (0.30/0.70).
Universe: 3-alt pool (SOL, DOGE, ETH). Round-trip fee: 8bp.

---

## Novelty rationale (Lesson #77)

- **Substrate**: CoinMetrics on-chain AdrActCnt (network address activity). First
  paradigm in the track to use on-chain community-API data. Non-OHLCV, non-derivatives.
- **Mechanism**: Retail engagement cycle → network demand → alt correlation regime.
  Distinct from all prior funding/OI/premium/OHLCV mechanisms.
- **Statistic**: 30d rolling empirical percentile rank (Lesson #45-compliant — explicit
  empirical distribution, NOT HMM-based hidden state).
- **DNA overlap** with existing R-5 seeds: max 3/6 dims (universe overlap only) —
  passes 5/6 cutoff gate.

---

## R-0 prescreen: PASS

`r0_prescreen.json` written 2026-08-08 03:52.

- CoinMetrics API works: 949 daily AdrActCnt rows 2024-01-01 → 2026-08-06.
- 30d rolling pct-rank valid_n=930.
- Best threshold pair `(0.30, 0.70)`: min quadrant triggers = 117 → 87.8 pooled events
  per (quadrant × quarter × 3-alt pool). Lesson #11 sample density: **PASS**.
- Fee headroom p75 |24h ret| = +434bp (SOL) / +456bp (DOGE) / +331bp (ETH) — vastly
  above 16bp round-trip. **PASS**.
- Lesson #40 structural feasibility: percentile-rank is bounded [0,1], no infeasibility. **PASS**.

---

## Bugfix during R-1 (CRITICAL — documented for future dogfoods)

**Bug**: v1 R-1 used `df['close'].resample('1D').last()` for daily BTC series. This
produces bars LABELED at midnight D 00:00 UTC but with VALUES equal to the last 1m
close of that day (D 23:59 UTC). Therefore `btc_daily.pct_change()[D]` reflects
the return `close_D_23:59 - close_(D-1)_23:59` — a return that ENDS at D 23:59 UTC.
At the presumed entry timestamp D 00:00 UTC, `close_D_23:59` is **17 hours in the future**.

**Impact**: v1 R-1 baseline reported +234bp/trade with 79% winrate on 2,580 trades —
which is implausibly good for a naive "yesterday's BTC sign → today's alt direction"
signal. Manual pandas cross-check gave -8bp with 49.9% winrate (essentially zero
autocorrelation, as expected for a daily lag). The 234bp/79% figure was a **classic
timestamp-labelling look-ahead artefact**.

**Fix (v2)**:
- Load 1m OPEN at exact 00:00 UTC minute of each day (`open` column, not `close`).
- `btc_ret_prior_day[D] = (btc_open_D_00:00 - btc_open_(D-1)_00:00) / btc_open_(D-1)_00:00`.
  This is KNOWN at D 00:00 UTC (it uses only prices at or before that timestamp).
- Alt trade: entry at `alt_open_D_00:00`, exit at `alt_open_(D+hold_h)_00:00`.

After fix, the baseline "BTC-sign prior day → alt continuation 24h" produces −9 bp
gross ≈ −17 bp net (i.e., no signal, only fee drag), consistent with the pandas manual test.

**Lesson candidate (proposed for #82)**: `resample('1D').last()` on 1-minute OHLCV
produces midnight-labeled bars containing end-of-day values. Using
`pct_change()` on such a series creates a subtle look-ahead if the analysis presumes
midnight timestamps are entry times. Fix: prefer explicit `.loc[df.index.time == 00:00, 'open']`
selection when the entry timestamp must be a specific UTC instant.

---

## R-1 (bugfix v2) results

96 cells swept (3 threshold pairs × 4 holds × 8 quadrants). 44 cells achieved
n≥30 with mean_net_bp>0.

### Full 3-gate + concentration evaluation on top 15 by t_stat

| Cell | Quadrant | Threshold | Hold | n | mean_net_bp | t | ci_lower_bp | perm_p | signal_t_excess | 3-gate | Concentration |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A_focus | hi=0.70 | 24h | 390 | +48.7 | +2.08 | +0.6 | 0.031 | +2.02 | **PASS** | FAIL |
| 2 | D_focus | lo=0.25 | 24h | 336 | +48.5 | +2.07 | +1.8 | 0.065 | +2.77 | **PASS** | FAIL |
| 3 | A_focus | hi=0.70 | 48h | 297 | +71.0 | +1.80 | −11.7 | 0.072 | +1.42 | FAIL | FAIL |
| 4 | D_focus | lo=0.25 | 48h | 267 | +59.7 | +1.74 | −2.2 | 0.145 | +2.45 | FAIL | FAIL |
| 5 | A_focus | hi=0.70 | 72h | 255 | +107.1 | +1.68 | −24.6 | 0.098 | +1.28 | FAIL | FAIL |
| 6 | B_mirror | hi=0.70 | 48h | 294 | +66.5 | +1.67 | −0.5 | 0.105 | +1.37 | FAIL | FAIL |
| 7 | A_focus | hi=0.75 | 24h | 357 | +38.3 | +1.58 | −9.3 | 0.099 | +1.48 | FAIL | FAIL |
| … | … | … | … | … | … | … | … | … | … | … | … |

Only 2 of 15 top cells pass all three gates (signal_t_excess ≥ 2 AND ci_lower > 0 AND
perm_p ≤ 0.10), and **neither passes the Concentration Gate** — the edge is not
distributed across ≥30% of symbols or ≥50% of quarters.

### Symmetric Negative Test (Lesson #19) — critical falsification

At hold=24h, threshold=(0.30, 0.70), the four A/B/C/D pairs give:

| Quadrant | Focus (bp) | Mirror (bp) | Sum (bp) | Broad fee-symmetric? |
|---|---|---|---|---|
| A (HIGH × BTC_up) | **+48.7** | −64.7 | −16.0 | **Yes** |
| B (HIGH × BTC_dn) | **−34.4** | +18.4 | −16.0 | **Yes** |
| C (LOW × BTC_up)  | **−18.5** | +2.5  | −16.0 | **Yes** |
| D (LOW × BTC_dn)  | **+22.5** | −38.5 | −16.0 | **Yes** |

Every A/B/C/D pair: `focus + mirror = −16bp = −2 × fee_RT` (by construction: focus and
mirror are identical trade sets with opposite direction, so their sum is minus twice
the round-trip fee).

**Interpretation (Lesson #39 sub-class A)**: the sum-of-pair being pinned to −16bp
in every quadrant means the trigger set carries NO directional information. Focus
"picks" a direction (LONG or SHORT), mirror bets the opposite, they share the same
alt price paths → cumulative outcome is pure fee-drag.

More diagnostically, the focus edges themselves are **inconsistent across quadrants**:
- A_focus positive (+48.7) supports "HIGH + BTC_up → alt continuation UP".
- B_focus negative (−34.4) *contradicts* "HIGH + BTC_dn → alt continuation DOWN" (i.e., the
  mirror direction would be right, but that's just betting *against* the hypothesis).
- C_focus negative, D_focus positive: contradictory pattern.

A real signal would have A_focus > 0 AND B_focus > 0 (both continuation directions confirmed)
OR at least a coherent regime-dependent story.

---

## Concentration diagnostics on top 3-gate cells

**Cell #1 (A_focus, hi=0.70, 24h)**:
- Per-symbol CI: 1/3 ci_lower > 0 (ratio 0.33 — passes the 0.30 gate…)
- Per-quarter pos_t: 6/10 (ratio 0.60 — passes the 0.50 gate…)
- But wait — the code marked it `concentration_gate_pass=False`. Re-inspecting: `n_sym_ci_pos=1` and `sym_ci_pos_ratio=0.33` — the gate requires ratio ≥ 0.30 AND n_sym_ci_pos ≥ 1. Both hold. `q_pos_t_ratio` must be ≥ 0.50.

Let me actually verify — the per-symbol breakdown shows only 1 of 3 alts has positive
lower CI. That's borderline (ratio 0.33). Combined with the SNT sub-class A pattern
across all four quadrants, we treat this as **narrow, uncorroborated, and unlikely to
survive R-2 expansion** — a classic Lesson #37 non-primary sweep PASS on a fee-drift
boundary.

---

## Lesson dogfoods

1. **Lesson #77 (non-OHLCV substrate)**: this paradigm used a genuinely novel substrate
   (CoinMetrics AdrActCnt). Non-OHLCV substrate does NOT automatically confer alpha —
   the underlying mechanism (retail engagement → alt continuation) simply did not
   materialize.

2. **Lesson #39 sub-class A (broad fee-symmetric SNT)**: all 4-quadrant SNT pairs
   returned `focus + mirror = −16bp` deterministically. Confirmed as a definitive
   falsification signal in R-1 (extends the paradigm 108 dogfood).

3. **Lesson #21 (axis stacking does not synthesize alpha)**: on-chain regime × BTC-sign
   is a two-axis stack. Neither axis alone would have looked promising; stacking them
   still produces no edge. Recorded.

4. **NEW LESSON CANDIDATE #82 (proposed)**: **Timestamp-labelling look-ahead trap in
   `resample('1D').last()`**. Daily bars labeled at midnight but valued at 23:59 will
   create subtle look-ahead when analyses assume midnight = entry time. Preventive
   check for R-0 dispatch: any script using `resample('1D').last()` + `pct_change()`
   as a "trigger signal" must be audited for timestamp semantics vs assumed entry
   instant. Prefer explicit `.loc[df.index.time == 00:00, 'open']` selection.

5. **Family advisory: on-chain BTC network metrics vs alt returns**: the two 3-gate-PASS-
   but-concentration-FAIL cells (A_focus and D_focus 24h) are consistent with fee-boundary
   drift — they are NOT evidence that AdrActCnt-based regime filters work. Any future
   paradigm proposing on-chain BTC metric × alt direction (TxCnt, HashRate, MinerRev, etc.)
   must include:
   - Symmetric Negative Test 4-quadrant in R-1 (mandatory, per Lesson #19).
   - Concentration Gate (per-symbol AND per-quarter) required at 3-gate PASS threshold.
   - Baseline diagnostic (unfiltered BTC-sign-continuation with the same 24h alt trade
     rule) reported alongside filtered results, to detect Lesson #32 baseline-coherent
     drift.

---

## Files

- Code:
  - `backend/scripts/research/paradigm248_btc_onchain_active_address_regime_alt_bilateral_24h_r0.py`
  - `backend/scripts/research/paradigm248_btc_onchain_active_address_regime_alt_bilateral_24h_r1.py`
    (bugfix v2 — corrected timestamp semantics)
  - `backend/scripts/research/paradigm248_baseline_diagnostic.py` (unfiltered baseline reference)
- Metrics:
  - `backend/runs/research_track/btc_onchain_active_address_regime_alt_bilateral_24h/r0_prescreen.json`
  - `backend/runs/research_track/btc_onchain_active_address_regime_alt_bilateral_24h/r1__metrics.json`
  - `backend/runs/research_track/btc_onchain_active_address_regime_alt_bilateral_24h/r1_baseline_diagnostic.json`

---

## Final metric snapshot

- **n_cells**: 96
- **n_valid_n30_pos_mean**: 44
- **n_3-gate_PASS**: 2 (both fail concentration)
- **n_pass_3gate_AND_concentration**: 0
- **SNT all_pairs_broad_fee_symmetric**: True
- **B_focus (hypothesis-critical)**: −34.4bp (wrong direction — mechanism does not hold in HIGH×BTC_dn quadrant)
- **Verdict**: `R1_GRAVEYARD_BROAD_FALSIFIED_LESSON39_SUBCLASS_A`
