# Graveyard — paradigm 204 alt_per_sym_90d_hurst_exponent_rescaled_range_z_spike_directional_4h_bilateral

- **Paradigm ID**: 204
- **Phase reached**: R-1
- **Verdict**: `BROAD_FALSIFIED_FEE_FLOOR` (sub-class A exact-symmetric mirror, Lesson #39)
- **Date**: 2026-05-22 KST
- **Hypothesis**: per-sym 90d rolling Hurst exponent (rescaled-range R/S) z-spike (|z|>=2 on 180d rolling) as trending-regime shift trigger; 4h forward bilateral 4-quadrant SNT on 21 syms x 2.25yr.

## Lesson #69 6-item template results

| Item | Lesson | Result |
|---|---|---|
| 1 | #61 slug grep | PASS — no existing `hurst|rescaled_range|persistence_exponent|trending_persistence|dfa_alpha` slug |
| 2 | #28 substrate-shape | PASS — 21 syms x 4h cache 2024-02-01..2026-04-30 (2.25yr / 4920 bars each) verified |
| 3 | #11 sample density | PASS — empirical 843 events / 4 quadrants = 211 per quadrant; per-sym median ~42 events; all quadrants n>=368 in primary |
| 4 | #62 DNA 4-dim | PASS — 5/5 distinct vs 20 Tier 4 retires (statistic class = Hurst R/S persistence, fresh) |
| 5 | #56 family-proxy | NEUTRAL — NEW axis class (Hurst persistence), no parent family |
| 6 | NEW alpha decay informational learning audit | EXECUTED — era stratify revealed sign-flipping (not monotonic decay); paradigm 87/136/202 alpha decay class NOT confirmed for Hurst |

## R-1 verdict snapshot (primary 4h, fee = 8bp one-side / 16bp roundtrip)

| Cell | n | gross_bp | net_bp | obs_t | signal_t_excess | ci_lower_bp | ci_upper_bp | three-gate |
|---|---|---|---|---|---|---|---|---|
| A_focus  (z>=+2 x UP x LONG cont)    | 475 | +13.28 |  -2.72 | -0.34 | **+0.41** | -18.48 | +12.39 | FAIL |
| A_mirror (z>=+2 x UP x SHORT rev)    | 475 | -13.28 | -29.28 | -3.69 | **-2.93** | -44.39 | -13.52 | FAIL |
| B_same   (z>=+2 x DOWN x SHORT cont) | 368 |  +1.33 | -14.67 | -1.47 | **-0.79** | -34.52 |  +4.37 | FAIL |
| B_mirror (z>=+2 x DOWN x LONG rev)   | 368 |  -1.33 | -17.33 | -1.74 | **-1.05** | -36.37 |  +2.52 | FAIL |

**0/4 three-gate PASS.** All gross magnitudes ≤ 13.28bp < 16bp roundtrip fee floor.

### Lesson #39 sub-class A confirmation (exact-symmetric mirror)
- A_focus +13.28bp / A_mirror -13.28bp (exact ±13.28bp)
- B_same +1.33bp / B_mirror -1.33bp (exact ±1.33bp)
- Per-quadrant returns are direction-bet outcomes (UP bar -> long = +x, UP bar -> short = -x). Trigger carries zero directional info.
- Lesson #39 sub-class A "broad-uniform-negative" antipattern verified — no mechanism direction in either UP or DOWN regime.

## Hold sweep (signal_t_excess per cell)

| hold | A_focus | A_mirror | B_same | B_mirror |
|---|---|---|---|---|
| 4h  | +0.41 | -2.93 | -0.79 | -1.05 |
| 8h  | -0.06 | -1.41 | +0.58 | -1.73 |
| 12h | -2.45 | +1.62 | -0.22 | -0.29 |
| 24h | -0.94 | +0.88 | -0.06 | +0.14 |

No cell achieves sigex >= 2.0 at any hold horizon. **No hold-plateau structure** — sigex oscillates around 0 with single-cell extremes (-2.93 4h A_mirror, +1.62 12h A_mirror) that are not consistent across adjacent horizons.

Lesson #37 full sweep verdict scan: scanned all 4 holds x 4 cells = 16 cells. **Best off-primary cell sigex +1.62 (12h A_mirror) — still < 2.0**, no non-primary 3-gate PASS to document.

## Concentration (primary 4h, per-symbol bootstrap CI)

| Cell | n_measurable | n_ci_pos | ratio_ci_pos |
|---|---|---|---|
| A_focus  | 21/21 | 0 | 0.00 |
| A_mirror | 21/21 | 0 | 0.00 |
| B_same   | 20/21 | 0 | 0.00 |
| B_mirror | 20/21 | 0 | 0.00 |

**0/21 across all four cells** = broad-uniform-negative. Top-magnitude alts (UNIUSDT +74.8bp A_focus, FILUSDT -78bp A_focus) cancel out and none reach CI positivity. Verifies Lesson #39 sub-class A pure-direction-bet structure (no symbol-level concentration).

## Quarter stratify (signal_t_excess)

| Quarter | A_focus | A_mirror | B_same | B_mirror | sample n |
|---|---|---|---|---|---|
| 2024Q3 |  nan  |  nan  |  nan  |  nan  | n<30 cells |
| 2024Q4 | -1.16 | +0.18 | -1.98 | +1.38 | 64/64/39/39 |
| 2025Q1 | -0.43 | -0.93 | +1.47 | -2.10 | 134/134/109/109 |
| 2025Q2 | +0.61 | -1.69 | +0.07 | -1.14 | 36/36/32/32 |
| 2025Q3 | +1.94 | -3.38 | -2.27 | +0.66 | 108/108/83/83 |
| 2025Q4 | +0.03 | -0.47 | +1.23 | -1.78 | 79/79/54/54 |
| 2026Q1 | -0.53 | -0.26 |  nan  |  nan  | 31/31/25/25 |
| 2026Q2 |  nan  |  nan  |  nan  |  nan  | n<30 cells |

No quarter shows a quadrant sigex >= 2.0. **Single-quarter outlier 2025Q3 A_focus +1.94 sub-threshold** — even on best single quarter the signal does not clear the gate.

## Item 6 alpha decay informational learning audit (NEW, paradigm 203 amendment)

| Era | A_focus sigex (n) | A_mirror sigex (n) | B_same sigex (n) | B_mirror sigex (n) |
|---|---|---|---|---|
| 2024 | -0.63 (70) | -0.43 (70) | **-2.87** (56) | **+2.13** (56) |
| 2025 | +0.69 (357) | -2.82 (357) | +0.99 (278) | -2.43 (278) |
| 2026 | -0.04 (48) | -1.17 (48) | **-4.18** (34) | **+2.88** (34) |

**Verdict: NO monotonic decay. Sign-flipping oscillation across eras.**
- B_same: -2.87 (2024) -> +0.99 (2025) -> -4.18 (2026) — sign-flips twice, 6-sigma swing
- B_mirror: +2.13 (2024) -> -2.43 (2025) -> +2.88 (2026) — perfect inverse of B_same (pure direction-bet artifact)
- A_focus: -0.63 -> +0.69 -> -0.04 — noise oscillation around 0
- A_mirror: -0.43 -> -2.82 -> -1.17 — consistently negative (no decay shape)

**Conclusion**: Hurst persistence statistic class does **NOT** confirm paradigm 87/136/202 monotonic alpha decay universal — instead shows pure direction-bet noise oscillation. Item 6 audit successfully distinguished sign-instability (zero-info trigger) from monotonic informational decay (real alpha learned away). **Item 6 audit dogfood success.**

## Lesson #42 11th dogfood post-SATURATED (B mirror cell)

- B mirror = Hurst z spike x bar DOWN x LONG reversal
- gross = -1.33bp, net = -17.33bp, sigex = **-1.05**, ci = [-36.37, +2.52], three-gate FAIL
- B_same (DOWN x SHORT cont) gross +1.33bp also FAIL — both fail symmetrically
- **Verdict: Lesson #42 11th dogfood NEGATIVE for Hurst persistence class.** Hurst z-spike trigger contains zero directional information; B mirror reversal cell does not surface alpha. Lesson #42 chain remains at 10 confirmed (117/158/162/179/193/194/195/196/197/198) — Hurst is the 11th attempted dogfood but FAILS to confirm; the pattern is class-specific, not universal.

## Why this paradigm failed (root cause)

1. **Direction-bet artifact (Lesson #39 sub-class A)**: A_focus and A_mirror sum to zero gross-bp (perfect mirror); same for B_same/B_mirror. The Hurst |z|>=2 trigger marks a moment of "persistence regime is unusual" but contains **no information about price direction**. Conditioning on bar UP/DOWN at trigger does not synthesize alpha — UP bar -> long simply tracks the conditional drift of UP bars under fee floor (max +13bp, below 16bp roundtrip).
2. **No symbol concentration**: 0/21 ci_pos in all 4 cells. The Hurst-z-spike triggers fire across all 21 syms (range 26-54 events) without any concentration in subsets — broad-uniform-negative.
3. **Sign-flipping across eras**: B_same and B_mirror invert signs between 2024 / 2025 / 2026 — direct evidence that the "edge" is sampling noise on a fundamentally zero-mean direction bet.
4. **No hold-plateau**: sigex jumps between -2.93 (4h) and +1.62 (12h) for A_mirror — single-cell outliers, no monotonic structure across adjacent horizons.

## Lesson candidates triggered/strengthened

- **Lesson #39 sub-class A**: 2nd dogfood (paradigm 108 first, paradigm 204 second) — exact-symmetric mirror with broad-uniform-negative concentration = pure direction-bet artifact. **CONFIRMED-eligible promotion candidate** (now 2 cross-class dogfoods: hour-of-day = boundary cycle, Hurst = persistence statistic).
- **Lesson #42 post-SATURATED state holds**: 11th attempted dogfood (Hurst class) negative — Lesson #42 universal does not extend to direction-bet artifact triggers. Chain remains at 10 confirmed.
- **Item 6 alpha decay informational learning audit**: dogfood success — era stratify distinguished sign-flipping (noise oscillation, direction-bet artifact) from monotonic decay. paradigm 203 amendment is operational and discriminating.

## Family-distinct verification (DNA 5/5)

vs 20 Tier 4 retires:
- statistic class = Hurst R/S rescaled-range exponent (NEW, distinct from autocorr/ACF, RV, range, volume share, funding, OI, premium, taker, skewness, kurtosis, drawdown)
- trigger frame = 90d daily aggregate -> 180d z (NEW, distinct from 5m/1h/4h tick-frame triggers)
- temporal anchor = continuous rolling (Lesson #68 ESCAPE)
- universe scope = per-sym idiosyncratic (Lesson #67 ESCAPE)
- direction logic = sign-cond bilateral 4-quadrant
DNA 5/5 confirmed distinct.

## Lesson #67/#68/#70 ESCAPE confirmation
- Lesson #67 ESCAPE: per-sym idiosyncratic, no cross-asset broadcast — CONFIRMED
- Lesson #68 ESCAPE: continuous rolling 90d/180d window, no session-boundary anchor — CONFIRMED
- Lesson #70 ESCAPE: NEW paradigm class (Hurst R/S), NOT R-5 LIVE expansion — CONFIRMED

## Artifacts

- code: `backend/scripts/research/alt_per_sym_90d_hurst_exponent_rescaled_range_z_spike_directional_4h_bilateral_r1.py`
- metrics: `backend/runs/research_track/alt_per_sym_90d_hurst_exponent_rescaled_range_z_spike_directional_4h_bilateral/r1__metrics.json`
- this graveyard: `backend/runs/research_track/graveyard__alt_per_sym_90d_hurst_exponent_rescaled_range_z_spike_directional_4h_bilateral.md`

## Counter status

- paradigm 204 = 105th R-1 graveyard (campaign total)
- Lesson #39 sub-class A: 2 confirmed dogfoods (108 + 204) -> **promotion-eligible** to CONFIRMED universal direction-bet artifact antipattern
- Item 6 (alpha decay informational learning audit): 1st operational dogfood after paradigm 203 amendment — operational/discriminating

## paradigm 205 next-action recommendation

Persistence-over-efficiency policy: dispatch continues. Lesson #61 amendment permanent inventory check obligatory (slug grep before next R-1).

**Recommended next axis class candidates** (none yet attempted, all 5/5 family-distinct ex ante):
1. **per-sym daily return Kolmogorov-Smirnov 2-sample test** (90d window-A vs 90d window-B distribution shift z-spike) — distribution-shift statistic, novel vs Hurst persistence shape
2. **per-sym Gini coefficient of intraday return distribution** (1d aggregate of 4h returns concentration) — inequality statistic, novel
3. **per-sym Hill tail-index estimator** (top-decile return tail thickness 90d rolling) — extreme-value class, novel

Direct recommendation: **candidate 1 (KS 2-sample distribution shift)** — most direction-meaningful (KS rejects null with a sign indicating which window is heavier, providing intrinsic direction), highest probability of escaping Lesson #39 sub-class A direction-bet artifact.

Continuous-parallel mandate: no pause. paradigm 205 dispatch on user trigger.
