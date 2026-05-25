# GRAVEYARD — paradigm 136 alt_intraday_1h_log_return_std_24h_window_z_directional_4h

**Date**: 2026-05-21 11:29 KST
**Phase**: R-0 (R-1 not dispatched)
**Verdict**: `R0_HALT_INSUFFICIENT_DENSITY_LESSON_11_23_ASYMMETRIC_Z_DISTRIBUTION`
**Host**: hcp_local
**Paradigm Number**: 136
**Cumulative graveyards after this entry**: 136 (paradigm 135 VRP precedes 11:23 KST same day)

## Hypothesis

1st-order intraday vol statistic NEW family:
- Per-symbol 1h close-to-close log_ret
- 24h rolling window std of log_ret_1h (24 obs)
- Per-symbol 30d (720h) rolling z-score on vol
- Trigger: |z_vol| > 2 (intraday vol regime extreme)
- Direction matching: trigger-bar 4h log-return sign (vol = magnitude only, direction from price action)
  - Simplified to **z-sign as primary direction**: z>+2 high vol regime → LONG (vol continuation), z<-2 low vol → SHORT (low vol regime trend)
- Forward hold: 4h, debounce 8h
- Universe: 12 alts (paradigm 133/134 cohort, ADA Lesson #30 excluded)

## Family-distinct claim (verified via Lesson #44 19th xref dogfood)

- paradigm 67/68/69 (BTC 1d close-to-close RV): **DISTINCT** — per-sym 1h intraday vs BTC 1d cross-asset
- paradigm 124 (kurtosis/skewness 3rd/4th moments): **DISTINCT** — 2nd-order total std
- paradigm 125 (quarticity bipower jump test): **DISTINCT** — pure std stat, NOT ratio test
- paradigm 129 (Parkinson high-low range): **DISTINCT** — close-to-close std (NOT high-low)
- paradigm 130 (ATR breakout level): **DISTINCT** — pure std, NOT breakout
- paradigm 133 (vol-of-vol 2nd-order clustering): **DISTINCT** — 1st-order (NOT std-of-std)
- paradigm 134 (signed semivariance asymmetry): **DISTINCT** — total std (NOT up/down decomposed)
- paradigm 135 (VRP composite ratio): **DISTINCT** — single raw stat (NO division/composite, Lesson #54 compliant)
- paradigm 69 BTC RV highvol R-5 SEEDED: **frame+source distinct** — per-sym 1h intraday vs BTC 1d cross-asset (mechanism direction OVERLAPS however — high-vol regime → LONG continuation; noted below)

## R-0 prescreen results

### Universe (12 alts loaded, all 12 pass Lesson #30 30% window)
- AVAX 755d / BCH 798d / BNB 798d / DOGE 767d / ETH 795d / FIL 798d / LINK 767d / LTC 798d / NEAR 798d / SOL 795d / WIF 799d / XRP 798d
- full_window=799d, **0/12 short-window syms** (no Lesson #30 violation)

### Lesson #34 empirical z-distribution (n=60000 sampled)

| pct | z_vol value |
|---|---|
| p1  | -1.68 |
| p5  | -1.29 |
| p10 | -1.08 |
| p50 | -0.33 |
| p70 | +0.10 |
| p90 | +1.03 |
| p95 | +1.79 |
| p99 | +4.14 |
| min | **-2.53** |
| max | **+8.24** |

**Critical asymmetry**: z_vol distribution heavily right-skewed.
- z>+2 (HIGH vol): **2498/60000 = 4.16%** empirical
- z<-2 (LOW vol): **179/60000 = 0.30%** empirical
- **13.9x asymmetry** between high-vol and low-vol regimes
- z_min only -2.53 (vs z_max +8.24) — vol cannot drop arbitrarily far below baseline (non-negative aggregate floor)

### Trigger count
- z>+2 (pos): n=1598 across 12 syms × 799d max
- z<-2 (neg): n=97 across 12 syms × 799d max
- **16.5x trigger asymmetry**

### Lesson #11 per-quarter density (≥30 cutoff)

**Pos (z>+2) per-quarter**:
```
2024Q1=30, 2024Q2=149, 2024Q3=158, 2024Q4=323, 2025Q1=162,
2025Q2=214, 2025Q3=198, 2025Q4=139, 2026Q1=204, 2026Q2=21
```
→ measurable: **9/10 quarters** (only 2026Q2 partial 21 < 30, recent quarter)

**Neg (z<-2) per-quarter**:
```
2024Q2=16, 2024Q3=13, 2024Q4=14, 2025Q2=2,
2025Q3=22, 2025Q4=9, 2026Q1=2, 2026Q2=19
```
→ measurable: **0/10 quarters** (max single quarter = 22 < 30 cutoff)

→ **B side (z<-2) fails Lesson #11 strict per-quarter density on all 10 quarters**.

### Lesson #40 structural threshold attainability

- z_max_reachable_pos2: **TRUE** (+8.24 max, well above +2)
- z_min_reachable_neg2: **TRUE** (-2.53 min, marginally below -2)
- Verdict: `PASS` (mechanically reachable both sides)
- **NUANCE**: although both sides structurally reachable, the empirical DENSITY of the negative side is 13.9x lower → effectively unreachable for per-quarter validation

### Lesson #46 sub-amendment 11th dogfood (CONFIRMED-eligible) — stratified n=50 × 4 quarters

Strategy: `temporally_stratified_n50x4q_total_n=170`
Quarters: 2024Q1 (oldest), 2024Q4 (Q3 third), 2025Q3 (2/3rd), 2026Q2 (newest)

**4-quadrant stratified estimate**:
| quadrant | n | gross_bp | net_bp | t |
|---|---|---|---|---|
| A_focus (z>+2, LONG)  | 147 | **+88.77** | **+72.77** | **+4.13** |
| A_mirror (z>+2, SHORT) | 147 | -88.77 | -104.77 | -4.13 |
| B_focus (z<-2, SHORT) | 23 | +8.27 | -7.73 | +0.96 |
| B_mirror (z<-2, LONG) | 23 | -8.27 | -24.27 | -0.96 |

**Per-quarter sign-flip detection**:
| quarter | A_focus n | A_focus gross_bp | B_focus n | B_focus gross_bp |
|---|---|---|---|---|
| 2024Q1 | 30 | **+267.28** | 0 | NA |
| 2024Q4 | 46 | +33.83 | 4 | +33.08 |
| 2025Q3 | 50 | +68.92 | 0 | NA |
| 2026Q2 | 21 | +1.34 | 19 | +3.05 |

- A_focus signs: **[+1, +1, +1, +1]** — **0 flips, UNIFORMLY POSITIVE** (4/4 quarters positive)
- B_focus signs: [+1, +1] (only 2/4 quarters measurable, both positive, but n<30 unstable)
- Lesson #46 sub-amendment: **TRUE NEGATIVE warning correct** (A side consistent strength — STRONG INDICATIVE of real mechanism)

### Decay pattern within A side (per-quarter gross_bp)

2024Q1 +267.28 → 2024Q4 +33.83 → 2025Q3 +68.92 → 2026Q2 +1.34

Notable: 2024Q1 peak (+267bp) → recent quarter compression toward noise (+1.34bp). Suggests A side directional alpha **decayed** over 2.4 years. Recent (2026Q2) effectively zero net of fee.

## Halt reason

**Primary**: Lesson #11 strict per-quarter density (B side z<-2: 0/10 quarters ≥30 trigger sample).

**Secondary**: Lesson #19 SNT 4-quadrant requirement structurally violated — z<-2 B side cannot generate ≥30 events per quadrant per quarter on 2.4yr × 12-sym universe. Universe expansion does not solve (z<-2 is empirically only 0.30% of vol observations, a structural property of non-negative aggregate distribution).

**Tertiary** (advisory): even on A side where signal is real (t=+4.13, all 4 sampled quarters positive), the per-quarter gross_bp shows clear **temporal decay** (2024Q1 +267bp → 2026Q2 +1.34bp). A R-1 dispatch would likely produce CONCENTRATED_R1_PASS (2024Q1 single-quarter driving) or NARROW_SCOPE_LIFE_CHANGING_FAIL (recent quarter sub-fee).

**Mechanism overlap caution** (paradigm 69 BTC RV highvol family):
- paradigm 69 R-5 SEEDED mechanism = HIGH vol regime → 13 alts LONG continuation (4h hold). p=0.000, sigex +13.45, 2.4yr 767 events
- paradigm 136 mechanism = per-sym HIGH 1h-intraday vol → same-sym 4h LONG
- Although frame-distinct (1d BTC cross-asset vs per-sym 1h intraday), the **directional alpha mechanism is the same family** (high-vol regime → momentum continuation LONG).
- This raises **paradigm 69 R-5 spillover risk**: paradigm 136 A side strength may simply be re-discovery of paradigm 69's mechanism on per-sym 1h frame.
- If paradigm 136 were to proceed to R-1 + R-3, correlation against paradigm 69 entries would need explicit Lesson #45 family-distinct verification.

## Lessons applied at R-0

- **#11 sample density** — FAIL on B side (0/10 q measurable)
- **#16 Concentration Gate** — deferred to R-1 (not reached)
- **#19 SNT mandatory** — structurally incomplete on B side
- **#21 axis stacking** — COMPLIANT (single statistic axis)
- **#21 sub-finding magnitude-ratio** — COMPLIANT (single raw signal, NOT 2-signal composite)
- **#22 frame-grade** — COMPLIANT (1h frame, 24 obs window, 720 obs z baseline)
- **#23 boundary cycle horizon density** — STRESSED on B side (continuous rolling but z<-2 too sparse)
- **#28 substrate availability** — PASS (1m OHLCV cache reused)
- **#30 data_window_ratio** — PASS (full window 12/12 syms)
- **#34 empirical distribution** — PASS, but exposed 13.9x asymmetry that drove halt
- **#40 structural threshold** — PASS mechanically, but density on negative side empirically infeasible
- **#44 amendment xref 19th dogfood** — SUCCESS (pre-dispatch family-distinct verified against 14 prior paradigms incl. paradigm 69 R-5 mechanism overlap caution surfaced)
- **#45 family-distinct** — COMPLIANT (explicit z-threshold, NOT HMM)
- **#46 AMENDMENT REFINEMENT 11th dogfood (CONFIRMED-eligible)** — STRATIFIED n=50×4q measurement; A side TRUE NEGATIVE warning (signs all +1)
- **#54 composite ratio/division** — COMPLIANT (single raw stat, NO division/ratio)

## Side discovery — A side real but decaying signal

Even though full paradigm halts at R-0, the A side (z>+2 HIGH vol → LONG 4h continuation) shows:
- Stratified t=+4.13 (well above R-1 sigex threshold)
- 4/4 quarters positive (uniformly consistent)
- Net per-trade edge +72.77bp ≈ 0.73% (sub-fee in newest quarter)
- **Temporal decay**: 2024Q1 +267bp → 2026Q2 +1.34bp (200x compression)
- Mechanism likely overlaps paradigm 69 BTC RV highvol R-5 (frame-distinct but mechanism-same family)

**Implications for future paradigm dispatch**:
- HIGH vol regime → LONG continuation family appears to be DECAYING in 2026 (paradigm 69 still PASS at R-5 seed time 2026-05-14, may need 2026Q2 baseline re-measurement)
- Asymmetric-z (one-sided trigger) paradigms should declare single-direction at R-0 a priori instead of attempting 4-quadrant SNT (NEW lesson candidate, see below)

## NEW Lesson #55 candidate (1st dogfood)

**Title**: Non-negative aggregate statistic z-score asymmetric distribution → one-sided trigger paradigms require explicit single-direction declaration at R-0 (not 4-quadrant SNT)

**Mechanism**: When the base statistic is a non-negative aggregate (std/var/range/count/RV/ATR/|return|), its 30d rolling z-score is **asymmetric** because the lower bound (0) prevents arbitrary negative deviations from baseline. Empirically the negative tail of z-score saturates near -2.5 to -3, while positive tail extends freely to +8 or beyond.

**Consequence**:
- |z|>2 symmetric trigger generates highly asymmetric event counts (paradigm 136: 16.5x asymmetry pos vs neg)
- 4-quadrant SNT (Lesson #19) cannot satisfy density requirement on negative side
- R-0 dispatch wastes paradigm slot when researcher attempts symmetric framing on inherently asymmetric statistic

**Prescription**:
- R-0 EMPIRICAL prescreen step: measure z_min and pct(z<-2) FIRST (before any R-1 generation)
- If pct(z<-2) < 1.0% or z_min > -2.5 strictly → declare paradigm as **ONE-SIDED RIGHT-TAIL TRIGGER** (z>+2 only, A focus + A mirror only)
- Skip B focus + B mirror generation; SNT reduces to 2-quadrant on A side only
- Document as `one_sided_asymmetric_trigger_paradigm` class in R-0

**Distinction from Lesson #40**:
- Lesson #40 = threshold mechanically attainable on a single side (z≤-T)
- Lesson #55 candidate = threshold reachable but empirically too sparse on one side for per-quarter Lesson #11 density

**Dogfoods needed for confirmation**: 1 (paradigm 136). Need 1 more dogfood → CONFIRMED-eligible after 2nd.

**Related prior paradigms** (retrospective):
- paradigm 124 (kurtosis/skewness): also non-negative magnitude statistics — would have benefited from this prescreen
- paradigm 125 (quarticity bipower): non-negative ratio test — relates
- paradigm 129 (Parkinson high-low range): non-negative range — relates
- paradigm 130 (ATR): non-negative ATR — relates
- paradigm 133 (vol-of-vol): non-negative std-of-std — relates
- paradigm 134 (signed semivariance): SOLVED via log-transform of ratio (Lesson #40 resolution)
- paradigm 136 (intraday 1h std): RAW non-negative std, no log/ratio reformulation → exposed

## Artifacts

- `backend/scripts/research/paradigm136_r0_prescreen.py` (R-0 script)
- `backend/runs/research_track/alt_intraday_1h_log_return_std_24h_window_z_directional_4h/r0_prescreen.json` (R-0 metrics + lesson #44 xref + family-avoidance)

## Next action

Continuous-parallel campaign per [Persistence over efficiency]:
- Counter: 135 → **136** (this entry)
- Streak: **8-streak non-PASS** (129-136)
- R-5 yield: 10/136 = 7.35%
- D-Day 2026-06-03 D-13 / paradigm 127+128 Day 7 baseline 2026-05-28 D-7
- Next dispatch candidate recommendation: see end of architect report below.

