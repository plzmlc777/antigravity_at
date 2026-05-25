# Graveyard: paradigm 133 alt_realized_vol_of_vol_2nd_order_clustering_regime_directional_4h

**Date**: 2026-05-21 10:55 KST
**Verdict**: CONCENTRATED_R1_PASS (R-1 halt — Concentration Gate FAIL)
**Phase**: R-1
**Host**: hcp_local (paradigm-architect agent dispatch)

## Hypothesis

NEW statistic class: 2nd-order realized vol clustering.

- **Step 1**: per-symbol 1h RV = sqrt(sum of 12 × 5m squared log-returns within 1h)
- **Step 2**: 24h rolling RV-of-RV = std(prior 24 hourly RV values)
- **Step 3**: per-symbol 30d rolling z-score of RV-of-RV
- **Trigger**: z > +2 (one-sided, Lesson #40 compliant for non-negative aggregate)
- **Direction**: sign(trigger-bar 4h log-return)
- **Forward hold**: 4h
- **Debounce**: 8h
- **Universe**: 12 alts (ADA excluded Lesson #30)

## R-0 prescreen results

- **Verdict**: R0_READY_FOR_R1 (PASS all gates)
- **n_triggers_total**: 1807 (pos=860 / neg=947)
- **n_quarters**: 10 (2024Q1 - 2026Q2)
- **measurable_quarters_pos / neg**: 8/10 each (Lesson #11 PASS)
- **Lesson #34 z empirical**: z_max=19.13, p99=5.44, p95=1.55, p90=0.80 (z>+2 reachable, 3.87% trigger rate)
- **Lesson #40**: PASS (one-sided z on non-negative stat, empirical z.max=19.13 ≫ +2)
- **Lesson #46 sub-amendment sign-flip**: A_focus [+,-,-,+] 2 flips / B_focus [-,+,-,-] 2 flips (alternating — early warning)

## R-1 R-1 4-quadrant SNT results

| quadrant | n | gross_bp | net_bp | obs_t | sigex | ci_lower_bp | perm_p | 3gate |
|---|---|---|---|---|---|---|---|---|
| **A_focus_z2_pos_LONG_4h** | **860** | **+37.41** | **+21.41** | **+2.29** | **+4.73** | **+2.33** | **0.000** | **TRUE** |
| A_mirror_z2_pos_SHORT_4h | 860 | -37.41 | -53.41 | -5.71 | -3.46 | -71.46 | 1.000 | FALSE |
| B_focus_z2_neg_SHORT_4h | 947 | -5.50 | -21.50 | -1.96 | +0.39 | -42.48 | 0.346 | FALSE |
| B_mirror_z2_neg_LONG_4h | 947 | +5.50 | -10.50 | -0.96 | +1.60 | -31.72 | 0.055 | FALSE |

A_focus three-gate FULL PASS (excess=TRUE / ci=TRUE / perm=TRUE).

## Concentration Gate (Lesson #16) FAIL — KEY VERDICT REASON

| quadrant | q_pos_t | quarter_ratio | sym_ci_pos | sym_ratio | gate_pass |
|---|---|---|---|---|---|
| **A_focus_LONG** | **7/9 (0.78 PASS)** | PASS | **2/12 (0.17)** | **FAIL <0.30** | **FAIL** |
| A_mirror_SHORT | 1/9 (0.11) | FAIL | 0/12 | FAIL | FAIL |
| B_focus_SHORT | 3/10 (0.30) | FAIL | 0/12 | FAIL | FAIL |
| B_mirror_LONG | 5/10 (0.50 boundary) | PASS | 0/12 | FAIL | FAIL |

### A_focus_LONG per-symbol breakdown

| sym | n | mean_bp | ci_lower_bp | ci_pos |
|---|---|---|---|---|
| WIFUSDT | 58 | +120.60 | -6.85 | FALSE |
| **DOGEUSDT** | **73** | **+88.45** | **+12.87** | **TRUE** |
| **LINKUSDT** | **65** | **+57.49** | **+4.88** | **TRUE** |
| NEARUSDT | 56 | +48.10 | -13.74 | FALSE |
| ETHUSDT | 62 | +34.65 | -5.21 | FALSE |
| SOLUSDT | 79 | +1.16 | -41.73 | FALSE |
| AVAXUSDT | 83 | -0.65 | -50.53 | FALSE |
| BCHUSDT | 81 | -5.67 | -55.96 | FALSE |
| BNBUSDT | 82 | -7.42 | -53.74 | FALSE |
| FILUSDT | 65 | -11.19 | -64.57 | FALSE |
| XRPUSDT | 80 | -11.32 | -77.23 | FALSE |
| LTCUSDT | 76 | -12.62 | -61.87 | FALSE |

**4/12 syms positive mean / 2/12 ci_pos / 8/12 syms negative or zero mean**

### A_focus_LONG per-quarter breakdown

| quarter | n | t | mean_bp | comment |
|---|---|---|---|---|
| 2024Q1 | 11 | +0.69 | +83.42 | small n |
| 2024Q2 | 74 | **+3.74** | **+90.11** | strong |
| 2024Q3 | 57 | +0.43 | +14.94 | weak pos |
| 2024Q4 | 172 | +1.15 | +33.93 | moderate pos |
| 2025Q1 | 86 | +1.36 | +53.22 | pos |
| 2025Q2 | 152 | +0.40 | +6.69 | flat |
| **2025Q3** | **103** | **-1.32** | **-23.55** | **NEG turnover** |
| **2025Q4** | **45** | **-1.33** | **-53.46** | **NEG continuing** |
| 2026Q1 | 152 | +1.53 | +23.02 | recovery |

q_pos_t 7/9 PASS BUT 2025Q3+Q4 sustained negative regime — non-stationary mechanism.

## Verdict reasoning

**CONCENTRATED_R1_PASS** — A_focus three-gate PASS but two failure modes:

1. **Concentration Gate FAIL** (Lesson #16): only 2/12 syms (DOGE+LINK) ci_pos.
   8/12 syms have negative or zero mean. The +37bp aggregate gross is driven by
   2-4 symbols (DOGE+LINK+WIF+NEAR). The 8 other syms (SOL/AVAX/BCH/BNB/FIL/XRP/LTC/ETH)
   are flat-to-negative. **Not a universe-wide mechanism**.

2. **Temporal instability** (Lesson #46 sub-amendment early warning confirmed):
   2025Q3+Q4 sustained negative (t=-1.32, -1.33; mean -23.55bp, -53.46bp).
   The mechanism worked 2024Q1-2025Q2 strongly but degraded mid-2025 onwards.
   R-0 sign-flip 2 was a true early warning.

## Lessons applied (32 confirmed + 5 candidates inventory)

- **Lesson #11**: PASS at R-0 (n=1807, measurable 8/10 quarters each direction)
- **Lesson #16**: **FAIL at R-1** (key verdict driver) — q_pos_t 0.78 PASS but sym 0.17 FAIL
- **Lesson #19**: PASS (4-quadrant SNT in single R-1 batch)
- **Lesson #21**: PASS (single trigger axis, no stacking)
- **Lesson #22**: PASS (1h base + 24h rolling RV-of-RV + 30d z, stateless quantile, 4h hold)
- **Lesson #23**: PASS (continuous rolling, no event anchor)
- **Lesson #28**: PASS (1m OHLCV substrate, 755-799 days)
- **Lesson #30**: PASS (data window 100%, no short-window syms)
- **Lesson #34**: PASS (empirical z distribution measured pre-execution)
- **Lesson #40**: PASS (one-sided z, non-negative stat, empirical z_max=19.13 ≫ +2)
- **Lesson #44**: 16th dogfood — full graveyard xref (paradigm 67/68/69/81/84/118/121/123/124/125/129/130/131/132 + 126/127/128 R-5)
- **Lesson #45**: PASS (explicit z-threshold, NOT HMM unsupervised)
- **Lesson #46 + sub-amendment**: **9th dogfood — TRUE POSITIVE WARNING confirmed**.
  Sign-flips A_focus 2 + B_focus 2 alternating R-0 indicated unstable regime;
  R-1 confirmed 2025Q3-Q4 sign-flip regime. Lesson #46 sub-amendment continues
  to fire correctly (9th dogfood, paradigm 129+130+131+132+other prior + 133).
- **Lesson #52a/b**: detection negative (both LONG NOT both positive)
- **Lesson #53 candidate**: detection negative (A_focus +37 / A_mirror -37 trivial mirror,
  no direction-inversion signal; mirror is mathematical not mechanism)

## Family-distinct verification (Lesson #45 confirmed)

- NEW statistic class **2nd-order realized volatility (std of std)** novelty CONFIRMED.
- Distinct from all 15 cross-referenced paradigms (67/68/69/81/84/118/121/123/124/125/129/130/131/132 + 126/127/128).
- HMM/unsupervised avoided. Frame-grade dense (1h base, 24h rolling, 30d z).
- Single trigger axis (Lesson #21). One-sided z (Lesson #40).

## Side discovery: NARROW-SCOPE LIFE-CHANGING analysis

Per Lesson #20 4-cond narrow-scope qualification check:

A_focus_LONG passing on DOGE+LINK isolated cells:

- DOGE: n=73 mean +88bp ci_lower +12.87bp ci_pos TRUE
- LINK: n=65 mean +57bp ci_lower +4.88bp ci_pos TRUE

Per-trade edge DOGE +88bp = +0.88% / LINK +57bp = +0.57% — both **< +2%/trade**
life-changing threshold. **Lesson #20 narrow-scope candidate NOT qualified**
per **NARROW_SCOPE_LIFE_CHANGING_FAIL** verdict (Lesson #41/Lesson #20 dual-mode).

Additionally q_pos_t at per-sym level was not measured granularly; even if narrow
scope qualified per Lesson #20, per-trade edge fails life-changing 4-dim gate.

## Continuous-parallel policy compliance

Per [feedback_paradigm_campaign_continuous_parallel] (2026-05-19 user directive):
- dispatch continues regardless of closing rate
- "실패하고 실패하고 또 실패하더라고 계속 찾아야 해" (Persistence amendment 2026-05-21)
- Counter increment: 132 → **133** (formal paradigm 133 R-1 graveyard)

## Counter status

- Cumulative graveyards: **132 → 133**
- R-5 seeded LIVE: 10 (unchanged)
- R-5 yield: 7.5% (10/133)
- Non-PASS streak: 5 (129/130/131/132/133)
- Lessons: 32 confirmed + 5 candidates (Lesson #46 sub-amendment 9th dogfood TRUE POSITIVE)

## Next-candidate recommendations

Based on paradigm 133 findings (CONCENTRATED_R1_PASS — DOGE/LINK driven 2024H2-2025H1
regime-specific mechanism degraded 2025H2):

### Path 1 (HIGH priority): Per-symbol RV-of-RV variant
- Run paradigm 133 narrow on DOGE-only or DOGE+LINK only
- Strictly verify Lesson #20 4-cond ALL PASS + life-changing 4-dim
- Expected: per-trade edge <+2%/trade fail (already documented above)
- Likely outcome: NARROW_SCOPE_LIFE_CHANGING_FAIL graveyard (3rd dogfood after 95+99)
- **NOT RECOMMENDED** — closing rate dilution + 3rd dogfood = formal NARROW_SCOPE_LIFE_CHANGING_FAIL antipattern documented

### Path 2 (MEDIUM priority): Vol-of-vol regime conditioning
- 2025Q3-Q4 negative regime suggests vol-of-vol mechanism is regime-dependent
- New paradigm 134-candidate: RV-of-RV z>+2 **conditional on BTC up-trend regime**
  - Mechanism: 2nd-order vol clustering carries directional info ONLY during BTC up-trend
  - Expected sample density: ~70% of original (BTC up-trend ~70% of period)
  - Lesson #20 4-cond risk: stratified cell density per-quarter per-quadrant <30 likely
  - **CAUTION**: paradigm 132 axis stacking trap fresh (Lesson #21 5th dogfood) —
    BTC regime conditioning IS axis stacking
  - **NOT RECOMMENDED** — paradigm 132 Lesson #21 trap repeats

### Path 3 (HIGH priority): Different 2nd-order statistic
- 2nd-order vol clustering = std of std on RV
- Variants: **std of std on log_return** (NOT RV) — different signal entirely
- 24h rolling std of 1h log_return (1st-order intra-day vol stat)
- Different from paradigm 133 because 1st-order vol stat (NOT 2nd-order)
- Lesson #44 xref needed: paradigm 67/68/69 1d close-to-close RV — distinct via 1h frame + intraday window
- Cost ~30min implementation, family-distinct novel

### Path 4 (HIGH priority): Realized semi-variance asymmetry
- Realized semivariance up vs down (Patton & Sheppard 2015)
- per-symbol 24h rolling RV_up / RV_down ratio
- Trigger: ratio z > +2 (uneven directional vol → directional info)
- Distinct from paradigm 133 (asymmetric semi-vol NOT 2nd-order vol clustering)
- Distinct from paradigm 124 (semi-variance NOT skewness/kurtosis)
- Cost ~30min implementation, family-distinct novel

### Path 5 (MEDIUM priority): Continue paradigm exploration with Path 3 or 4
- Continuous-parallel policy maintained
- D-Day 2026-06-03 D-13 / paradigm 127+128 Day 7 baseline 2026-05-28 D-7

**PRIMARY RECOMMENDATION**: **Path 4 (Realized semi-variance asymmetry)** — distinct
statistic class, asymmetric structure naturally carries directional info (unlike
2nd-order vol-of-vol where direction is mathematically separate from magnitude).
Mechanism story: down-vol > up-vol = bearish dispersion (LONG fade or SHORT lean).

## Artifacts

- R-0 script: `/home/hcpark/antigravity/backend/scripts/research/paradigm133_r0_prescreen.py`
- R-1 script: `/home/hcpark/antigravity/backend/scripts/research/paradigm133_r1.py`
- R-0 metrics: `/home/hcpark/antigravity/backend/runs/research_track/alt_realized_vol_of_vol_2nd_order_clustering_regime_directional_4h/r0_prescreen.json`
- R-1 metrics: `/home/hcpark/antigravity/backend/runs/research_track/alt_realized_vol_of_vol_2nd_order_clustering_regime_directional_4h/r1__metrics.json`
- Graveyard report: this file
