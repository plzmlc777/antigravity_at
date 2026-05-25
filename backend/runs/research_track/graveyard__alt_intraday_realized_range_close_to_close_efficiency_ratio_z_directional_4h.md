# GRAVEYARD — paradigm 137 alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h

**Date**: 2026-05-21 11:44 KST
**Phase**: R-1 (R-2 not dispatched)
**Verdict**: `BROAD_FALSIFIED_A_FOCUS_NEGATIVE`
**Sub-class**: A pair both negative (chop regime ratio carries no fade alpha) + B_focus drift_continue narrow CI miss
**Host**: hcp_local
**Paradigm Number**: 137
**Cumulative graveyards after this entry**: 137 (paradigm 136 11:33 KST precedes)
**Streak**: 9-streak non-PASS (129-137)

## Hypothesis (Yang-Zhang / Garman-Klass 2000 efficiency ratio)

Per-symbol 1h OHLC:
- Per-bar Parkinson range component: P_t = (1/(4 ln 2)) × (log(high/low))²
- Per-bar close-to-close variance component: C_t = (log(close/close_prev))²
- 24h rolling sums: SumP_24h, SumC_24h
- Efficiency ratio: ER_t = SumP_24h / SumC_24h
- Log transform: log_ER (centered around 0 under diffusion null)
- Per-symbol 30d rolling z-score on log_ER

Trigger: |z_logER| > 2

Direction semantics (academic interpretation):
- z_logER > +2 (chop regime, range >> close): mean-reversion → **A_focus = fade trigger-bar move**
- z_logER < -2 (drift regime, close >> range): momentum → **B_focus = continue trigger-bar move**

Forward hold: 4h directional / debounce 8h / 12 alts (paradigm 133/134/136 cohort)

## Family-distinct claim (Lesson #44 20th xref dogfood)

- paradigm 67/68/69 BTC 1d RV cross-asset: **DISTINCT** — per-sym 1h intra-OHLC ratio
- paradigm 124 kurtosis/skewness: **DISTINCT** — 2nd-order RV decomposition
- paradigm 125 quarticity bipower (R-0 halt Lesson #40): **DISTINCT** — log-transform applied
- paradigm 129 raw Parkinson high-low (GRAVEYARD): **DISTINCT** — Parkinson AS NUMERATOR of ratio (regime classifier NOT vol magnitude)
- paradigm 130 ATR breakout: **DISTINCT** — pure RV ratio decomp
- paradigm 133 vol-of-vol 2nd-order: **DISTINCT** — 1st-order ratio
- paradigm 134 signed semivariance UP/DOWN ratio: **DISTINCT** — RANGE/CLOSE decomposition axis
- paradigm 135 VRP cross-domain ratio (R-0 halt Lesson #54): **DISTINCT** — INTRA-domain within-OHLC (Yang-Zhang established literature, not ad-hoc mixing) — **Lesson #54 confirmed compliant**
- paradigm 136 intraday 1h std (R-0 halt Lesson #55): **DISTINCT** — ratio classifier (NOT magnitude)

## R-0 prescreen results (PASS, dispatched to R-1)

### Universe
- 12 alts loaded, full_window=799d, 0/12 short-window syms (no Lesson #30 violation)

### Lesson #21 sub-finding magnitude-ratio prescreen (MANDATORY) — PASS
- cond_a corr(SumP, SumC) > 0.95: **1/12 syms** (FILUSDT 0.972 only; halt threshold ≥10)
- cond_c log_ER overall std < 0.20: **0/12 syms** (range 0.264 - 0.303)
- cond_b ratio_p50 mean=1.160, max_dev=0.064 (informational, normal Yang-Zhang regime)
- **Verdict: PASS** — Parkinson and close-to-close variance carry independent information; not collapsed to common magnitude factor

### Lesson #34 empirical z_logER distribution (n=60,000 sampled)

| pct | z_logER |
|---|---|
| p1  | -2.06 |
| p5  | -1.53 |
| p10 | -1.24 |
| p50 | -0.12 |
| p70 | +0.43 |
| p90 | +1.28 |
| p95 | +1.73 |
| p99 | +2.72 |

z_min=-3.77, z_max=+7.36. Both sides reachable.

### Lesson #40 verification — PASS
- log-transform + z-score reformulation per Lesson #40 guidance
- n_above_pos2 = 1969 (3.28%), n_below_neg2 = 701 (1.17%)

### Lesson #55 candidate asymmetric z detection — **SYMMETRIC** (paradigm 136 fail mode AVOIDED)
- asymmetry_ratio = 2.81 (< 5.0 cutoff)
- log-transform successfully restored negative side (paradigm 136 had no log transform, asym_ratio=16.5)
- **Lesson #55 candidate evidence: log-transformation prescription works for non-negative ratio statistics**

### Lesson #11 density — PASS
- A_chop (z>+2): 1264 triggers, 10/10 quarters ≥30 measurable
- B_drift (z<-2): 640 triggers, 8/10 quarters ≥30 measurable

### Lesson #46 REFINEMENT 12th dogfood (stratified n=50×4q) + sub-amendment 12th

R-0 stratified 4-quadrant gross (n=189 total):
- A_focus chop_fade: gross=**-2.28bp** / net=-18.28bp / t=-0.12 (~noise)
- A_mirror chop_continue: gross=+2.28bp / net=-13.72bp / t=+0.12
- B_focus drift_continue: gross=**-37.62bp** / net=-53.62bp / t=-1.13 (strong negative)
- B_mirror drift_fade: gross=+37.62bp / net=+21.62bp / t=+1.13 (mirror likely PASS candidate)

Per-quarter sign-flip detection (n=50 first-50):
- A_focus chop_fade: signs=[-1, +1, +1, +1] — **1 flip** (Q1 2024 outlier -79bp)
- B_focus drift_continue: signs=[-1, -1, -1, -1] — **0 flips, ALL NEGATIVE**: [-69, -41, -31, -27 bp]

**STRONG WARNING raised**: B_focus drift_continue strat-R-0 shows 4/4 quarters NEGATIVE (mechanism direction inverted candidate).

## R-1 full-data results (BROAD_FALSIFIED)

### 4-Quadrant SNT (1904 triggers total, candidate pool n=56,833)

| Quadrant | n | gross_bp | net_bp | obs_t | null_t | sigex | ci_lower_bp | perm_p | 3gate |
|---|---|---|---|---|---|---|---|---|---|
| A_focus chop_fade | 1264 | +4.46 | -11.54 | -1.98 | -3.00 | +1.02 | -22.67 | 0.170 | **FAIL** (excess/ci/perm all FAIL) |
| A_mirror chop_continue | 1264 | -4.46 | -20.46 | -3.50 | -3.00 | -0.51 | -32.09 | 0.676 | FAIL |
| B_focus drift_continue | 640 | **+18.40** | +2.40 | +0.26 | -2.16 | **+2.42** | **-15.85** | **0.010** | **NEAR-MISS** (excess+perm PASS, CI FAIL) |
| B_mirror drift_fade | 640 | -18.40 | -34.40 | -3.72 | -2.16 | -1.56 | -53.36 | 0.931 | FAIL |

### Concentration diagnostics (Lesson #16 STRICT)

| Quadrant | n | q_pos_t | sym_ci_pos | conc_gate |
|---|---|---|---|---|
| A_focus chop_fade | 1264 | 3/10 (0.30) | 0/12 (0.00) | FAIL |
| A_mirror chop_continue | 1264 | 3/10 (0.30) | 0/12 (0.00) | FAIL |
| B_focus drift_continue | 640 | 4/9 (0.44) | **0/12 (0.00)** | FAIL |
| B_mirror drift_fade | 640 | 1/9 (0.11) | 0/12 (0.00) | FAIL |

**Concentration STRICT FAIL on all 4 quadrants** (0/12 syms ci_pos universal).

### Lesson #46 sub-amendment 12th dogfood post-R-1 per-quarter full

- A_focus chop_fade: signs=[-1, -1, -1, +1, +1, -1, -1, -1, -1, +1] — **3 flips**, 3/10 pos / 7/10 neg
- B_focus drift_continue: signs=[+1, +1, -1, +1, -1, -1, +1, -1] — **5 flips**, 4/8 pos / 4/8 neg

Note: B_focus full-data per-quarter is **MORE positive (4/8)** than the stratified R-0 4-quarter view (0/4) — the stratified Q1+Q4+Q3+Q2 sample happened to over-weight negative quarters. The Lesson #46 sub-amendment warning was directionally informative but exact verdict differed.

### Lesson #52 a/b pattern detection
- Both fade quadrants positive (A_focus + B_mirror): **NOT triggered**
- A_focus (chop_fade) +4.46bp gross / B_mirror (drift_fade) **-18.40bp** gross
- "fade" semantic not uniformly positive across regimes → mechanism does not exhibit "broad fade alpha across vol regimes"

### Lesson #53 candidate detection
- A direction inverted: focus -4.46 / mirror +4.46 → false (gap 4.46 bp << 20 bp threshold)
- B direction inverted: focus +18.40 / mirror -18.40 → **false (B_focus is the POSITIVE side; mirror is more negative)**
- **Lesson #53 NOT triggered** — B_focus drift_continue is the correctly-signed direction (just CI miss)

## Diagnosis

### Why A side (chop regime z>+2) fails

A_focus chop_fade returns ~0 gross (+4.46bp), well below 16bp fee floor. A_mirror chop_continue worse (-4.46bp gross). **Chop regime ratio carries no directional information** at 4h horizon — when range >> close (low net drift, high intra-bar churn), the next 4h is essentially noise regardless of fade vs continue framing.

Interpretation: high efficiency ratio (range dominates) is a **dispersion regime indicator** (price thrashes within a band), but it does not predict NEXT 4h direction. Yang-Zhang (2000) was developed for variance ESTIMATION efficiency, not directional prediction.

### Why B side (drift regime z<-2) is closer but still fails

B_focus drift_continue: **gross +18.40bp** (just above 16bp fee floor), sigex +2.42, perm_p 0.010 — **2 of 3 R-1 gates PASS**. But:
- ci_lower **-15.85bp** (well below 0) — high cross-sectional dispersion / variance dominates mean
- Concentration STRICT FAIL: 0/12 syms with ci_pos individually
- → Mean barely clears fee floor on aggregate, but no individual symbol shows independent ci_pos evidence

**B_mirror drift_fade -34.40bp** — strong negative, confirming drift regime DOES continue (not fade), so the mechanism direction (continue) is correct in sign, but the edge is too marginal and dispersion too high for either Lesson #16 STRICT or three-gate full PASS.

### Drift regime narrative confirmed (but sub-grade)

When close-to-close variance dominates range (z_logER<-2 = trending bar), the 4h-forward direction IS biased toward continuation. R-0 stratified estimate -37bp suggested fade; full-data +18bp suggests continue. The discrepancy is because:
- Stratified Q1+Q4+Q3+Q2 = 4-quarter slice oversamples bear-regime quarters
- Full data 10-quarter aggregation balances regimes
- Drift continuation IS the true effect, but it's only marginally above fee floor

### Range estimator family 2nd dogfood

- paradigm 129 raw Parkinson high-low: GRAVEYARD (vol magnitude failed)
- paradigm 137 Parkinson/close ratio (Yang-Zhang efficiency ratio): GRAVEYARD (ratio CLASSIFIER fails — A side noise, B side near-miss sub-grade)

**Range estimator family Tier 4 retire CANDIDATE elevation eligible**: 2 dogfoods with distinct semantics (magnitude vs ratio classifier) both failing on different mechanisms. However, formal retire requires 3 dogfoods per protocol; deferred to next range-family dispatch. Range axis variants remaining for potential dispatch: Garman-Klass (open-close + range, distinct from YZ ratio), Rogers-Satchell (range + drift correction).

## Lessons applied verification

| Lesson | Compliance |
|---|---|
| #11 sample density | PASS (1264 + 640 ≥ 200 / per-quarter ≥30) |
| #16 Concentration STRICT | EVALUATED — 0/12 syms ci_pos all quadrants (universal failure) |
| #19 SNT mandatory 4-quadrant | EXECUTED in single R-1 batch |
| #20 4-cond narrow scope | N/A (no quadrant 3-gate PASS) |
| #21 axis stacking | COMPLIANT (single ratio axis) |
| #21 sub-finding magnitude-ratio | COMPLIANT, R-0 prescreen PASS (1/12 high corr only) |
| #22 frame-grade | COMPLIANT (1h base + 24h sum + 30d z = 720 obs) |
| #23 non-event-anchored | COMPLIANT (continuous rolling) |
| #28 substrate availability | COMPLIANT (1m OHLCV per-symbol available) |
| #30 data_window_ratio | COMPLIANT (12 syms all ≥ 750d, 0/12 short-window) |
| #34 empirical distribution | MEASURED (z + log_ER percentiles, std=0.28 avg) |
| #39 sub-class detection | A_broad_uniform_negative (sub-class A); NO mirror inversion |
| #40 threshold attainability | PASS (z range [-3.77, +7.36], log+z reformulation works) |
| #41 amendment dual-mode | N/A (no PASS quadrant) |
| #43 trap awareness | direction from regime semantic + trigger-bar sign documented |
| #44 amendment xref 20th dogfood | EXECUTED |
| #45 family-distinct | COMPLIANT (explicit z-threshold, NO HMM) |
| #46 REFINEMENT 12th dogfood | EXECUTED — stratified strat warning B 0/4 NEG; full-data 4/8 (less alarming) |
| #46 sub-amendment 12th dogfood | EXECUTED — per-quarter sign-flip full data |
| #52 a/b pattern | NOT triggered (asymmetric fade returns) |
| #53 candidate direction inversion | NOT triggered (B_focus is correctly signed direction) |
| #54 composite ratio CONFIRMED | COMPLIANT (intra-domain within-OHLC Yang-Zhang) — **distinct verdict from paradigm 135** |
| #55 candidate asymmetric z (paradigm 136 fail mode) | **AVOIDED via log-transform** — asym_ratio 2.81 vs paradigm 136 16.5; **Lesson #55 prescription validated** (log-transform for non-negative ratio statistics restores symmetric z distribution) |

## Lesson #55 candidate evidence accumulation (2nd dogfood)

paradigm 137 demonstrates **the proper Lesson #55 prescription**:
- paradigm 136 (raw 1h vol magnitude, no log): asym_ratio 16.5 → R-0 HALT
- paradigm 137 (log-transform on Yang-Zhang ratio): asym_ratio 2.81 → symmetric, R-1 dispatchable

This is a **counter-example proof** for the Lesson #55 candidate prescription: when statistic is non-negative aggregate (raw std, raw ratio of non-negatives), apply log-transform before z-score to restore symmetric trigger feasibility. Lesson #55 candidate now has **2 dogfoods (paradigm 136 fail + paradigm 137 prescription success)** — eligible for formal CONFIRMED elevation evidence.

## Verdict reasoning

- Cumulative graveyards: **137** (was 136, +1)
- Streak: **9-streak non-PASS** (paradigm 129-137)
- R-5 yield: 10/137 = 7.30%
- No quadrant satisfies three-gate or Concentration STRICT
- B_focus drift_continue is **closest near-miss**: 2/3 three-gate PASS, but CI dispersion fails and Concentration universal fail
- Hypothesis effectively falsified: Yang-Zhang efficiency ratio decomposition does not produce 4h-forward directional alpha above fee floor with cross-symbol robustness

## Range estimator family status update (2nd dogfood)

- **paradigm 129** raw Parkinson high-low magnitude: GRAVEYARD (BROAD_FALSIFIED)
- **paradigm 137** Parkinson/close-to-close efficiency ratio: GRAVEYARD (BROAD_FALSIFIED, A side noise + B near-miss)
- Family retire CANDIDATE elevation: **eligible** (2 dogfoods, distinct statistic semantics, both fail)
- Formal retire (3 dogfoods) NOT yet — next range axis candidate (e.g., Garman-Klass full estimator, Rogers-Satchell) may be dispatchable if found family-distinct AND novel mechanism

## Path forward / next candidate recommendation

paradigm 137 closes the **Yang-Zhang range/close ratio** axis. Remaining within-OHLC RV decomposition axes to consider:
- Garman-Klass full estimator (uses open + close + high + low — different from paradigm 137 which uses high/low and close-only)
- Rogers-Satchell (range + drift correction, distinct from YZ)
- Realized bipower variation (Barndorff-Nielsen, jump-robust) — **paradigm 125 already R-0 halted Lesson #40 (raw form)**; log-transform variant possible

**HOWEVER**: 9-streak non-PASS over paradigms 129-137 (intraday vol family heavy concentration) suggests the **realized vol family axis is approaching saturation**. Recommend pivoting to:
- **Cross-domain non-RV axes**: OI/funding-anchored event detection (paradigm 22 + 79 + others already validated as R-5 / partial seed), but most single-funding variants exhausted per funding family Tier 4 retire (lessons §family).
- **Time-anchored boundary events**: hourly/4h session-boundary OR daily-close volatility imprint (distinct from rolling continuous z)
- **Cross-asset lead-lag** with non-stale design (paradigm 67-69 BTC RV ancestor R-5 SEEDED is the gold standard reference)

Next dispatch candidate suggestion: a **non-RV** axis to break the 9-streak. Pre-empt: consult [[project-paradigm-queue-2026q3]] §6 for unpicked NOVELTY ≥4/5 candidates outside RV/vol family.

## Artifacts

- R-0 script: `backend/scripts/research/paradigm137_r0_prescreen.py`
- R-1 script: `backend/scripts/research/paradigm137_r1.py`
- R-0 metrics: `backend/runs/research_track/alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h/r0_prescreen.json`
- R-1 metrics: `backend/runs/research_track/alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h/r1__metrics.json`
- Graveyard: `backend/runs/research_track/graveyard__alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h.md`
