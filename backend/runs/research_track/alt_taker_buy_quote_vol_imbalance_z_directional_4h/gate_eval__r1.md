# R-1 Gate Evaluation — paradigm 142-v2

**Paradigm**: alt_taker_buy_quote_vol_imbalance_z_directional_4h
**Counter**: 142
**Phase**: R-1
**Run timestamp**: 2026-05-21 04:05:25 UTC
**Wall clock**: 2.2s

## Hypothesis
Per-symbol 4h bar `taker_buy_quote_volume / quote_volume` imbalance ratio (centered at 0.5), 30d (180-bar) rolling z-score. |imbalance_z| > 2.0 → 4h directional continuation (pos → LONG, neg → SHORT).

## R-0 Prescreen — PASS
- LESSON40_ATTAINABILITY: 14/14 syms reach both ±z>2 thresholds.
- LESSON11_DENSITY: per-cell pos=197.0 / neg=197.9 (≥30 required).
- LESSON30_WINDOW: 1.00 uniform (all 14 syms 4920 bars 2024-02-01 → 2026-04-30).

## R-1 4-quadrant SNT (Lesson #19 mandatory)
Primary hold = 4h (1 bar). Universe = 14 alts. n_events: pos=1859 / neg=1872.

| Quadrant | n | mean_bp | sigex | perm_p | ci_lower_bp | 3-gate | concentration |
|---|---|---|---|---|---|---|---|
| **A focus** pos × LONG | 1859 | -7.83 | -0.759 | 0.230 | -15.40 | FAIL | FAIL |
| A mirror pos × SHORT | 1859 | -8.17 | +0.204 | 0.580 | -15.67 | FAIL | FAIL |
| **B focus** neg × SHORT | 1872 | -1.69 | +1.822 | 0.972 | -8.86 | FAIL | FAIL |
| B mirror neg × LONG | 1872 | -14.31 | -2.409 | 0.008 | -22.08 | FAIL | FAIL |

## Hold sweep (Lesson #37 full grid scan)
**A_focus_LONG (pos trigger)**:
| hold | n | mean_bp | sigex | perm_p | ci_lo_bp | 3-gate |
|---|---|---|---|---|---|---|
| 4h | 1859 | -7.83 | -0.759 | 0.230 | -15.40 | FAIL |
| 8h | 1857 | -9.51 | -0.750 | 0.229 | -20.67 | FAIL |
| 12h | 1857 | +1.26 | +0.724 | 0.860 | -11.93 | FAIL |

**B_focus_SHORT (neg trigger)** — *finding of note*:
| hold | n | mean_bp | sigex | perm_p | ci_lo_bp | ci_up_bp | prob_pos | gates (sig/perm/ci) |
|---|---|---|---|---|---|---|---|---|
| 4h | 1872 | -1.69 | +1.822 | 0.972 | -8.86 | +6.08 | 0.328 | F/F/F |
| 8h | 1872 | +1.38 | +1.870 | 0.958 | -8.93 | +12.32 | 0.601 | F/F/F |
| **12h** | **1872** | **+13.67** | **+3.430** | 0.332 | **-0.45** | +27.77 | **0.972** | T/F/F |

B_focus_SHORT 12h: sig_t_excess gate PASS (3.43 ≥ 2.0), ci_lower_bp -0.45 marginally below 0 (one-gate-from-3-gate-PASS), bootstrap prob_positive 97.2%. **perm_p=0.332 still fails** — observed t-stat not separable from fee-drift null at 4-quadrant trigger density. Hold extension beyond paradigm-specified 4h tested grid (12h = 3 bars), no 3-gate cell discovered.

## Lesson #39 sub-class detection
- sub_class_A (broad-uniform-negative): **NO** (B_focus_SHORT positive sigex, not all 4 ≤ -2)
- sub_class_B (mechanism-inverted): **NO** (mirrors don't dominate focus by 1.5+ sigex)
- A_focus_sigex -0.76 / A_mirror_sigex +0.20 (focus weaker, mirror near 0 — pure noise on A-side)
- B_focus_sigex +1.82 / B_mirror_sigex -2.41 (focus positive but sub-2σ, mirror strongly negative)

→ **B-side asymmetry**: neg trigger → market drifts down (mirror LONG loses, focus SHORT mildly favored). A-side pos trigger has no directional info.
→ This is NOT lesson #39 sub-class A or B, but reveals a *broken-symmetry single-side weak signal* pattern.

## Lesson #16 Concentration Gate — all FAIL on focus quadrants
Both A_focus and B_focus → concentration_gate_pass = False (per-quarter or per-symbol thresholds unmet at 4h hold).

## Lesson #46 stratified n=50×4q + sign-flip
- A_focus: 10 quarters measurable, 3 pos / 7 neg, 5/9 sign flips (strong-alt=False, but neg-majority confirms A-side anti-signal).
- B_focus: 10 quarters measurable, 5 pos / 5 neg, 4/9 sign flips (strong-alt=False, but coin-flip = no consistent edge).

## Life-changing 4-dim (Lesson NARROW_SCOPE_LIFE_CHANGING_FAIL prevention)
| Side | trades/yr | edge/trade | util | sharpe | all-pass |
|---|---|---|---|---|---|
| A_focus_LONG | 828 | -0.08% | 37.8% | -1.35 | FAIL |
| B_focus_SHORT | 834 | -0.02% | 38.1% | -0.29 | FAIL |

Both sides edge negative, sharpe negative — life-changing layer would have rejected even if 3-gate passed.

## Verdict: **BROAD_FALSIFIED**

A_focus pos×LONG: focus quadrant net loss -7.83bp, sigex -0.76 (below null mean). No directional information in positive imbalance z trigger.

B_focus neg×SHORT: mild positive sigex (+1.82 at 4h, +3.43 at 12h) but 3-gate primary cell 0/3 PASS; only sig_t_excess gate clears at 12h; ci_lower -0.45 just below 0; perm_p 0.33 cannot reject null.

B mirror neg×LONG: strongly negative (sigex -2.41) — net market does drift down after neg-imbalance trigger, but only weakly (-14.3bp gross becomes -22.3bp net after fee), insufficient to give the SHORT side a clean fee-cleared edge.

The aggressive USD sell ratio z-score does contain *some* downward bias prediction (B-side asymmetry), but **the edge is sub-16bp at 4h fee floor and only emerges at hold≥12h after partial drift**. At that horizon perm null also drifts (perm_p=0.33), so the signal is indistinguishable from fee-aware random sampling.

## Lesson #44 amendment 25th xref (Family-distinct verification)
- paradigm 72 (5m taker_buy_vol BROAD_FALSIFIED): distinct via 4h frame + USD-denominated quote. **Result CONFIRMS family pattern: aggressive taker side flow → no fee-cleared 4h directional edge.**
- paradigm 127/128 (volume burst R-5 LIVE 30m): distinct dispatch confirmed (continuous z vs burst spike). 142-v2 fail does not affect 127/128 substrate.
- paradigm 140 (CVD ratio): distinct via quote-denomination. Both fail at 4h frame.
- Funding family (22/132/138-141): distinct axis confirmed.

## Lesson #52-#56 detection
- Lesson #52 (sub-fee mean-reversion in mirror not pure direction-bet) — partial: B mirror neg×LONG sigex -2.41 perm_p 0.008 (significant down-drift), but this is mechanism direction not pure direction-bet.
- Lesson #53 (asymmetric A vs B substrate availability) — NO, density symmetric pos=1859 / neg=1872.
- Lesson #54 (single-axis stacking trap) — NO, paradigm 142-v2 is single-axis (imbalance z) by design.
- Lesson #55 (one-sided substrate justification) — NO, both sides empirically available.
- Lesson #56 candidate (mirror direction inversion in symmetric paradigm) — partial: A pos × neither LONG nor SHORT gives signal, B neg × SHORT marginally aligned with hypothesis. Not a clean inversion.

## NEW Lesson #57 candidate (1st dogfood)
**Aggressive taker quote-volume imbalance z-score → 4h directional continuation BROAD_FALSIFIED on Binance perp 14-alt universe**.

Combined with paradigm 72 (5m taker_buy_vol) + 140 (CVD ratio) failures, this is the **3rd consecutive failure of taker-side aggressive flow as a 4h directional alpha source** on the perp universe. Possible family pattern: aggressive taker flow leaks information *during* the bar, by bar-close the price has already absorbed the asymmetry, leaving 4h forward return as residual noise dominated by fee.

→ Recommend **escalate Lesson #57 candidate to formal candidate** after 1 more dogfood (paradigm 143+ on quote-vol axis variant). 2nd consecutive same-axis broad falsification triggers candidate, 3rd triggers CONFIRMED.

→ Provisional advisory: **quote-volume / taker-quote axis 4h directional continuation paradigms** flagged for sample density × fee-floor pre-execution scrutiny.

## Cumulative campaign state post-142
- Total graveyards: **142** (141 → 142)
- R-5 LIVE: **10** (unchanged)
- continuous-parallel **14-streak non-PASS** (was 13)
- R-5 yield: **6.59%** (10/142 → before: 10/141)
