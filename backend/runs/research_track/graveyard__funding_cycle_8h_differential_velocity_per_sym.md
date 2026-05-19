# Graveyard — funding_cycle_8h_differential_velocity_per_sym (paradigm 99 / batch P3)

**Date**: 2026-05-19 KST 12:00 (batch ad-hoc R-1 P3)
**Phase**: R-1
**Verdict**: BROAD_FALSIFIED_MIRROR_ONLY
**Type**: E (event-study)

## Hypothesis

Per-sym 8h-to-8h Δfunding = funding(t) - funding(t-8h). Per-sym 30d rolling history z-score |z(Δf)| > 2.0 outlier → mean-reversion fade. Per-sym self-relative leverage velocity (NOT cross-section, NOT level).

## DNA distinct from existing paradigms

| Paradigm | Axis mismatch |
|---|---|
| paradigm 96 sign flip | categorical (sign change) vs continuous (Δ z) — axis 2 |
| paradigm 79 funding extreme level | level z vs velocity z — axis 2 |
| paradigm 22 funding_carry | 3 syms specific continuous level vs 14 syms Δvelocity — axis 5 + axis 2 |
| P1 funding_velocity cross_section | cross-section z (universe) vs per-sym history z (self) — axis 4 |

R-0 inventory check: ≤ 4/6 DNA overlap with each. The most family-distinct of the three batch candidates.

## R-1 setup

- Universe: 14 syms (same as P1/P2)
- Per-sym 30d rolling history z-score (90 cycles) of Δfunding
- 4-quadrant Symmetric Negative Test, focus z=2.0 hold=8h
- Panel: **38,618 cycles / 868 days / 2.38 yr**

## R-1 results — focus cell (z=2.0, hold=fwd_ret_8h)

| Cell | n | mean_bp_post_fee | signal_t_excess | ci_lower_bp | perm_p_two | 3-gate |
|---|---|---|---|---|---|---|
| A focus high LONG | 1,295 | **+12.44** | **+2.03** | **-4.31** | 0.205 | FAIL (ci fail) |
| A mirror high SHORT | 1,295 | -28.44 | -1.85 | -45.03 | 0.023 | FAIL |
| **B mirror low LONG** | 1,304 | **+24.00** | **+3.19** | **+5.88** | **0.028** | **PASS** |
| B focus low SHORT | 1,304 | -40.00 | -2.90 | -58.90 | 0.001 | FAIL (anti-direction) |

## Critical finding — symmetric LONG bias

Both A focus high LONG (sigex +2.03) AND B mirror low LONG (sigex +3.19) show similar magnitudes of positive return. When |z(Δf)| extreme **regardless of sign**, LONG cells outperform.

This is **not a directional mean-reversion signal** — it's a symmetric "leverage shock → upward bias" pattern. Mechanism interpretation: any large funding velocity shift coincides with intraday volatility expansion, and short-side flow exhaustion at z>2 → temporary upward drift, but symmetric in both directions of the velocity (high OR low z(Δf)).

A focus 3-gate failure cause: ci_lower -4.31bp (just barely negative — n=1,295 puts mean +12.4bp inside CI lower bound). B mirror 3-gate PASS happens to be on the cell that hypothesis expected to FAIL (low-velocity → LONG should fade UP overshoot — but here it gains).

## Concentration Gate (A focus, computed since focus)

| Metric | Value | Gate (≥) | Pass |
|---|---|---|---|
| quarter_pos_t_ratio | 0.40 | 0.5 | FAIL |
| symbol_ci_pos_ratio | 0.00 | 0.30 | FAIL |
| n_symbols_ci_pos | 0/13 | 3 | FAIL |

**Per-symbol diagnostic** (A focus high LONG):
- 8/13 syms positive mean, 5/13 negative
- 0/13 ci_lower > 0 (high variance per-sym, ~75-180 events each)
- WIFUSDT n=179 mean +57.19bp (4h cycle outlier — may skew aggregate)

Net: aggregate-level borderline sigex is driven by 4-6 outlier events per sym, not consistent edge.

## Life-changing 4-dim (B mirror LONG — 3-gate PASS cell)

- trades_per_year: 548.7 (PASS ≥12)
- per_trade_edge_pct: **+0.240%** (FAIL — gate ≥2%, **8x deficit**)
- capital_util: 0.50 (PASS ≥0.30)
- annualized_sharpe: 1.68 (PASS ≥1.5)

3 out of 4 life-changing gates PASS but per-trade edge **0.24% << 2.0% threshold** = NARROW_SCOPE_LIFE_CHANGING_FAIL category — BUT we never get there because Concentration Gate also FAIL on the corresponding focus cell and verdict tree categorized as MIRROR_ONLY (focus 3-gate FAIL → mirror PASS triggers BROAD_FALSIFIED_MIRROR_ONLY label per Lesson #8 mirror antipattern guard).

## Why broadly falsified (interpretation)

1. **Mechanism direction asymmetric in unexpected way** — both LONG cells positive, both SHORT cells negative → symmetric "any large velocity shock → upward bias" rather than MR fade direction.

2. **Concentration FAIL** — 0/13 syms with reliable edge, mean carried by outlier events per sym.

3. **Life-changing FAIL** — even if mirror cell PASS were promoted, 0.24% per-trade edge is 8x below threshold. Capital utilization is high (0.50) but edge is too thin to be life-changing.

4. **Mirror PASS antipattern** — per Lesson #8, paradigm X mirror Y PASS without focus PASS triggers antipattern caution. The mirror PASS would require its own R-1 dispatch (NARROW_SCOPE life-changing FAIL would block).

## Family implications

5th independent funding-axis single-signal mechanism falsification (after 73/79/96/97/98). The "per-sym history z(Δf)" was the most distinct variant remaining in funding family + still falsified. Funding axis single-signal sub-class formal retire (2026-05-19) further reinforced.

Critically: the **symmetric LONG bias** finding is a side-discovery worth noting — large funding velocity shocks coincide with short-term upward drift in alts, but the magnitude (0.24% per trade) is below life-changing threshold and unlikely to survive R-2 walk-forward (the 5/13 syms with negative means + 0 ci_lower > 0 → temporal instability likely).

## Artifacts

- code: `backend/scripts/research/funding_cycle_8h_differential_velocity_per_sym_r1.py`
- metrics: `backend/runs/research_track/funding_cycle_8h_differential_velocity_per_sym/r1__metrics.json`
- Mint log: `/tmp/p3_per_sym_velocity.log`
- INDEX entry: registered + graveyarded 2026-05-19

## Lesson candidates

**Lesson candidate**: Mirror-only PASS with symmetric LONG bias (both A & B LONG cells positive). Different from existing Lesson #8 mirror antipattern (which is about reflexive variant trial). New pattern: when **both 4-quadrant LONG cells** outperform but neither focus passes 3-gate fully, it's a directional bias artifact (general market drift filtered by sample selection), not mechanism alpha. Probably already covered by life-changing 4-dim gate as designed — the gate correctly catches this without needing a new lesson.

**Tentative**: defer to Q3 lesson curator. If similar pattern repeats (mirror PASS + life-changing FAIL + symmetric bias) in future paradigms, formalize as "Lesson #31 — symmetric directional bias antipattern" (joint LONG cells PASS but focus FAIL = market drift artifact, not mechanism).
