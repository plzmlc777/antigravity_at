# Paradigm 117 R-3 — FAIL Report

**Paradigm**: `alt_extreme_24h_drawdown_24h_reversion_long`
**R-1 alias**: `alt_extreme_24h_drawdown_reversal_long_4h`
**Phase**: R-3 robustness audit
**Verdict**: **R3_FAIL_OOS** (with multi-axis concerns)
**Date**: 2026-05-20 KST
**Wall clock**: 0.75 min

## Verdict reason (one-line)

OOS edge ratio **0.65** (Train +2.978%/trade → OOS +1.929%/trade) falls in the
MARGINAL zone (between hard-FAIL 0.50 and strict-PASS 0.70). Combined with
mechanism-CLASS asymmetry (Caveat 1 F) and severe survivorship-cohort decay
(Caveat 6 F, conservative R-5 edge **−0.59%/trade**), paradigm fails strict
R-3 PASS criteria.

## R-2 anchor recap

- A_focus 24h cell: n=406, gross +275.31bp / net +267.31bp / edge +2.673%/trade,
  sigex +8.71, perm_p 0.000, CI [+201.52, +329.38]bp.
- TS-CV 4/5 PASS, threshold sweep monotone, broad-shoulders top-3 PASS, life-changing 4/4.
- Pool-drift triage clean (drift_artifact 0%).

## R-3 Caveat-by-caveat outcomes

| # | Caveat | Outcome | Detail |
|---|--------|---------|--------|
| 1 | Lesson #39 real 4-quadrant SNT | **F (informational)** | B_same (PUMP×SHORT) sigex 0.28 < 2.0 — mechanism CLASS asymmetric |
| 2 | Regime stratify (3×3 BTC trend × vol) | **P** | 8/9 cells positive, 0 cells with t<-2.0 — regime-robust |
| 3 | SL/TP grid (5×7=35 cells) | **P** | Plateau 6 cells (edge≥2% AND Sharpe≥1.5), seed SL=0.25 TP=0.30 |
| 4 | Correlation vs existing paradigms | **P** | max cosine 0.243 (funding_carry) ≤ 0.7 — orthogonal |
| 5 | TIA exclusion analysis | **INFO** | Edge uplift WITHOUT-TIA +9.75% (below 10% threshold) — no exclusion |
| 6 | Survivorship quantification | **F (gating)** | Conservative R-5 edge −0.59%/trade fails 2%/trade |
| 7 | Holdout OOS window | **MARGINAL → F** | Edge ratio 0.65 between 0.50/0.70 boundaries |

## Caveat 1 — Real Lesson #39 4-quadrant SNT (mechanism CLASS test)

| Quadrant | Trigger | Direction | n | gross_bp | net_bp | sigex | CI_pos |
|----------|---------|-----------|---|----------|--------|-------|--------|
| A_focus | drawdown ≤ −15% | LONG @ 24h | 406 | +275.31 | +267.31 | +8.71 | ✓ |
| A_mirror_real | drawdown ≤ −15% | SHORT @ 24h | 406 | −275.31 | −283.31 | −7.46 | ✗ (mathematical mirror) |
| **B_same_sign_real** | **PUMP ≥ +15%** | **SHORT @ 24h** | **409** | **−21.06** | **−29.06** | **+0.28** | **✗** |
| B_mirror_real | PUMP ≥ +15% | LONG @ 24h | 409 | +21.06 | +13.06 | +1.20 | ✗ |

**Key finding**: The mechanism is **ASYMMETRIC**. Capitulation (drawdown ≤ −15%)
produces strong mean-reversion (+275bp gross), but euphoria (PUMP ≥ +15%) does
NOT produce symmetric mean-reversion correction. B_same_sign_real sigex = 0.28
(essentially null) demonstrates that "extreme magnitude → 24h mean-revert" is
**only true for downside extremes**, not upside.

**Mechanism implications**:
- The signal is NOT a general "extreme-magnitude class" reversion paradigm.
- It is specifically a **fear/capitulation-driven bounce** — likely driven by
  forced-deleveraging cycle (LIQ cascade clears + funding flips negative + late
  shorts cover), which is direction-asymmetric.
- This is informational-only by spec (caveat 1 F is not auto-fail unless other
  axes also fail). But it materially changes the mechanism narrative: the
  paradigm is narrower than originally framed.

## Caveat 2 — Regime stratify (PASSED)

BTC 30d trend × vol regime cells (3×3 = 9 cells):

```
              vol_low    vol_mid    vol_high
bull         +0.19%    +0.67%    +0.83%
             (n=12)    (n=36)    (n=33)
             t=0.10    t=0.66    t=0.78

neutral      +0.84%    -0.02%    +4.01%
             (n=48)    (n=25)    (n=71)
             t=0.91    t=-0.03   t=4.03

bear         +1.49%    +4.80%    +2.80%
             (n=22)    (n=113)   (n=45)
             t=1.88    t=8.43    t=2.20
```

**Cells positive: 8/9 (only neutral×mid marginally negative at -0.02%).
Cells with t < -2.0: 0.**

Mechanism concentration:
- **Bear × mid vol**: dominant cell (113 trades, +4.80%/trade, t=8.43)
- **Neutral × high vol**: secondary (71 trades, +4.01%/trade, t=4.03)
- **Bear × high vol**: tertiary (45 trades, +2.80%/trade, t=2.20)

These 3 cells together contain **229/406 = 56% of trades** and drive most of
the alpha. Mechanism is concentrated in BEAR/HIGH-VOL conditions — consistent
with the "fear-driven capitulation" narrative from Caveat 1.

Bull regime cells are sub-1%/trade (capitulation reversion much weaker when
BTC is rallying — likely because alt drawdowns during bull trends are noise
rather than fear).

## Caveat 3 — SL/TP grid (PASSED)

5 SL × 7 TP = 35 cells. Plateau (edge ≥ 2% AND Sharpe ≥ 1.5):
- SL=0.25, TP=0.10 — edge 2.32%, Sharpe 4.81
- SL=0.25, TP=0.15 — edge 2.37%, Sharpe 4.71
- SL=0.25, TP=0.20 — edge 2.40%, Sharpe 4.71
- SL=0.25, TP=0.30 — edge 2.41%, Sharpe 4.70 ⬅ **recommended seed**
- SL=0.25, TP=0.50 — edge 2.41%, Sharpe 4.70
- SL=0.25, TP=∞ (no TP) — edge 2.41%, Sharpe 4.70

**Plateau structure**: all 6 cells share SL=0.25 (very wide stop). TP varies
0.10–∞ but produces near-identical results. This indicates:
- SL=0.25 (−25% adverse move from entry) rarely hits during a 24h hold
- TP rarely hits in the achievable +5/+10/+15% range during 24h
- Effective behavior = pure 24h time-exit; SL/TP add little

**Plateau-implied seed parameters**: SL=0.25, TP=0.30 (most conservative within
plateau, allows the rare extreme bounces to capture).

Max DD across primary cell = −60.6%/trade (gross-cumulative max drawdown) —
this is **very high tail risk** even with SL=0.25. Indicates the strategy
has fat-tail loss tolerance built into its premise (some capitulations
continue down).

## Caveat 4 — Correlation vs existing paradigms (PASSED)

UTC-day direction-magnitude cosine vs derived proxies:

| Existing paradigm | Cosine | Pearson | Notes |
|-------------------|--------|---------|-------|
| btc_rv_spike_highvol_filter_alt_long_240m | -0.095 | -0.098 | (proxy: BTC RV p90 trigger flag) |
| premium_index_zscore | +0.216 | +0.096 | (proxy: sign of BTC 1d return) |
| autocorr_regime | +0.216 | +0.096 | (same proxy mechanism) |
| funding_carry | +0.243 | NaN | (always-LONG proxy = constant +1) |
| oi_price_decoupling | +0.135 | +0.137 | (proxy: BTC RV-conditional sign) |

**Max abs cosine = 0.243 (funding_carry) ≪ 0.7** — paradigm 117 trade
direction-magnitude series is orthogonal to all existing R-5-seeded paradigms.

**Caveat**: proxies are coarse mechanism approximations on UTC-day grid. A
more precise correlation would require trade-level event timestamps from
each comparator paradigm, which are not persisted. The 0.243 max is well
below 0.7 even allowing for proxy imprecision — orthogonality is robust.

## Caveat 5 — TIAUSDT exclusion (INFO)

- WITH TIA (n=406): edge 2.673%, Sharpe 5.72, lc4 4/4 PASS
- WITHOUT TIA (n=379): edge 2.934%, Sharpe 6.24, lc4 4/4 PASS
- **Edge uplift WITHOUT-TIA: +9.75%** (just below the 10% threshold for "recommend exclude")

TIAUSDT contributed sum_net = −2,658bp / n=27 in R-2 (per-trade −98.5bp).
TIA listed 2023-10, is a "newer alt" cohort member with high beta to
broader weakness. Removing TIA improves but does not transform the strategy.

**Hypothesis for TIA underperformance**: TIA experienced multiple post-listing
high-beta declines (e.g. 2024 H2 bear leg, 2025 Q1 selloff) during which it
continued lower rather than bouncing within 24h. This is a quality-tier
pattern (newer alts with low real demand keep declining post-extreme-drawdown).

**Recommendation if R-5 were to proceed**: TIA exclusion optional, not
required. Uplift below threshold (9.75 < 10%) and lc4 4/4 holds either way.

## Caveat 6 — Survivorship (FAILED gating)

**Probe results** (8 candidate "delisted" symbols):

| Symbol | Archive available | n_triggers | Per-trade net edge | Classification |
|--------|-------------------|------------|--------------------|----------------|
| LUNAUSDT | NO (2022 delisting) | — | — | Genuinely delisted (substrate unavailable) |
| FTTUSDT | YES (still in archive) | 0 | — | Quality-tier (still listed but quiet) |
| SRMUSDT | YES (sparse, 656 rows) | 0 | — | Partial delisting (substrate sparse) |
| **BAKEUSDT** | YES (full window) | **30** | **−7.93%/trade** | Still-listed weak-cohort |
| DGBUSDT | YES (full window) | 0 | — | Still-listed quiet |
| **CTSIUSDT** | YES (full window) | **20** | **−0.91%/trade** | Still-listed weak-cohort |
| **MATICUSDT** | Until 2024-09 (rebranded to POL) | **2** | **+5.89%/trade** | Genuinely delisted (truly delisted in window) |
| FTMUSDT | YES (still listed, rebranded) | 11 | +0.14%/trade | Still-listed (rebrand confusion) |

**Cohort classification**:
- **Truly delisted within window**: MATICUSDT only (n=2 triggers, +5.89%) —
  too sparse for robust survivorship adjustment.
- **Substrate-unavailable**: LUNAUSDT, SRMUSDT (substrate gap, cannot test).
- **Quality-tier-lower still-listed** (BAKEUSDT, CTSIUSDT, FTMUSDT): n=61 triggers,
  pooled edge ≈ −5.07%/trade weighted mean (BAKE −7.93% × 30 + CTSI −0.91% × 20 + FTM +0.14% × 11) / 61.

**Pooled "extended cohort" edge (8 symbols probed)**: n=63 triggers,
edge = **−3.86%/trade**.

**Conservative R-5 edge calculation**:
- Surviving cohort (R-2 anchor 28 alts): +2.673%/trade
- Mix of 50% surviving + 50% extended cohort = (2.673 + (-3.86)) / 2 = **−0.59%/trade**

**This catastrophically fails the 2%/trade life-changing threshold for a survivorship-adjusted R-5 seed.**

**Important caveat to this caveat**:
The "extended cohort" largely captures **quality-tier-lower still-listed alts**
rather than true delistings. This is **NOT classical survivorship bias**
(which would be alts that were delisted before window). It IS a **cohort
selection bias**: the R-2 universe of 28 alts was implicitly hand-picked for
high liquidity/major coverage (SOL, ETH, XRP, AVAX, etc.), excluding the
universe's weaker tail. The −5% post-drawdown continuation in BAKE/CTSI shows
that the capitulation-bounce mechanism does NOT generalize to the weaker
half of Binance USDT-perp listings.

**Conclusion**: Survivorship/cohort-bias concern is **substantive**. The R-2
result of +2.67%/trade likely reflects a 28-alt liquid-tier filter, not a
universal "capitulation → 24h bounce" mechanism. R-5 sizing assumptions
should treat the +2.67% as an **upper-bound estimate**, with realistic
deployment expectations closer to +1.0–1.5%/trade after accounting for
real-world cohort drift (additions of weaker alts to universe over time,
new listings before they reach "tier-1" liquidity, etc.).

**Per spec**: "delisted-cohort 시도 가능 + edge < 50% of surviving → R3_FAIL_SURVIVORSHIP if conservative R-5 still doesn't clear 2%/trade" — this gating condition IS met (extended cohort edge −3.86% << 50% of 2.67% = 1.34%, and conservative R-5 = −0.59% < 2%).

**Caveat 6 outcome: F (gating)**.

## Caveat 7 — Holdout OOS window (MARGINAL → F)

Split:
- Train: 2024-05-30 to 2025-06-30 (13 months, n=288 trades)
- OOS: 2025-07-01 to 2026-04-30 (10 months, n=118 trades)

| Metric | Train | OOS | Ratio |
|--------|-------|-----|-------|
| n_trades | 288 | 118 | — |
| gross_mean_bp | 305.82 | 200.86 | 0.66x |
| net edge_per_trade | 2.978% | 1.929% | **0.65x** |
| obs_t | 7.37 | 3.06 | 0.42x |
| signal_t_excess | 8.12 | 3.51 | 0.43x |
| perm_p | 0.000 | 0.002 | — |
| Trades/year | 269.0 | 160.8 | 0.60x |
| Capital util | 73.7% | 44.0% | 0.60x |
| Sharpe | 7.12 | 3.57 | 0.50x |
| Life-changing 4-dim | 4/4 | **3/4** (edge 1.929% < 2%) | — |

**Per spec verdict tree**:
- OOS edge / Train edge = **0.65** — below strict PASS threshold (0.70), above hard-FAIL (0.50). **MARGINAL.**
- OOS sigex = **3.51** — above strict PASS (2.0). **PASS.**
- OOS n = **118** — above strict PASS (100). **PASS.**
- OOS direction = positive. **PASS.**
- OOS life-changing 4-dim: **3/4** (edge 1.929% < 2% threshold). FAIL one of 4 dimensions.

**Interpretation**: The edge has decayed meaningfully (~35% degradation) but
the signal is still statistically real on OOS. The edge has crossed below
the life-changing 2%/trade threshold on OOS specifically, while remaining
positive and statistically significant.

This is the **most concerning result** of R-3:
- It's NOT a "signal disappeared" failure (sigex 3.51 is healthy)
- It's a "signal weakened past the life-changing bar" decay
- 1.929%/trade is still "good" by historical research-track standards but
  below the life-changing-strategy mandate

**Possible explanations for OOS decay**:
1. **Crowding/imitation**: extreme drawdown bounces are a textbook strategy;
   2025-H2/2026 markets may have more participants quickly arbitraging the
   reversion, reducing per-trade edge.
2. **Vol regime shift**: bear/neutral×high-vol cells (the alpha-dense ones)
   appear less frequently in late-2025/2026 (BTC was in extended bull regime
   for much of OOS window).
3. **Quality-tier drift**: more "tier-1.5" alts (TIA, SEI, SUI) added to
   universe over time, diluting tier-1 capitulation-bounce signal.

**Per spec strict verdict**: Edge ratio 0.65 < 0.70 → does not achieve PASS.
Edge ratio 0.65 ≥ 0.50 → does not trigger hard FAIL_OOS or FAIL_OOS_NOISE.
Combined with OOS lc4 3/4 (edge dimension fails), classified as **R3_FAIL_OOS (marginal)**.

## Final verdict tree application

Strict cascade per spec:

```
caveat_2 (regime): P
caveat_3 (SL/TP plateau): P
caveat_4 (correlation): P (max cosine 0.243 < 0.7)
caveat_7 (OOS): NOT PASS (edge ratio 0.65 < 0.70) AND lc4 3/4 (edge 1.929% < 2%)
→ R3_FAIL_OOS

[Even if Caveat 7 were treated as P-MARGINAL, Caveat 6 (survivorship)
would itself trigger R3_FAIL_SURVIVORSHIP per spec — conservative R-5
edge -0.59% < 2%/trade.]
```

**Primary verdict: R3_FAIL_OOS**
**Secondary concern: R3_FAIL_SURVIVORSHIP (cohort-tier bias)**
**Tertiary concern: Mechanism asymmetric (Caveat 1 F)**

## Why this paradigm fails R-3 despite R-2 PASS

R-2 measured a real, statistically robust signal on a 28-alt liquid universe
over 2 years. R-3 stress-tested this signal across 3 axes that R-2 did not
examine:

1. **Time stability (OOS holdout)**: edge has decayed ~35% from Train period
   to most recent 10-month period — below life-changing 2%/trade bar.
2. **Cohort robustness (survivorship-style)**: signal does not generalize to
   weaker-tier still-listed alts (BAKEUSDT, CTSIUSDT show −5% continuation).
3. **Mechanism CLASS symmetry (Lesson #39)**: PUMP × SHORT does NOT mirror
   drawdown × LONG (sigex 0.28 vs 8.71). The hypothesis "extreme magnitude →
   mean-revert" is too broad — actually "fear-driven capitulation → bounce".

These three R-3 caveats together substantially weaken the R-5 paper deployment
case. The strategy IS profitable on the 28-liquid-alt subset on historical data,
but the **life-changing scale** premise (≥2%/trade sustained per-event-edge)
does NOT hold under R-3 scrutiny.

## Recommendation

**Graveyard at R-3** with detailed lesson capture:

1. **Lesson candidate**: "R-2 broad-shoulders + monotone + TS-CV all pass is
   NOT sufficient to predict R-3 OOS holdout PASS — temporal decay 35% can
   take edge below 2% bar even with healthy sigex".
2. **Lesson candidate**: "Mechanism CLASS asymmetry (drawdown bounce vs PUMP
   correction) is testable in R-3 but undetectable in R-1/R-2 single-axis
   measurement".
3. **Lesson candidate**: "Survivorship probe via still-listed quality-tier
   weakness probe (BAKEUSDT, CTSIUSDT) reveals cohort-bias gap even when true
   delisting substrate is unavailable from Binance Vision archive".

**Future re-test trigger**: If a more focused sub-paradigm targeting just
the bear × mid/high vol regime cells (where edge is +4.80%/trade × 2.80%/trade)
can be defined with sufficient sample density and OOS stability, that subset
might still warrant R-5 seed. Current strategy at broader 28-alt × all-regime
scope does not.

## Files

- Script: `backend/scripts/research/paradigm117_r3_alt_extreme_24h_drawdown_24h_reversion_long.py`
- Metrics: `backend/runs/research_track/alt_extreme_24h_drawdown_24h_reversion_long/r3__metrics.json`
- Stdout log: `backend/runs/research_track/alt_extreme_24h_drawdown_24h_reversion_long/r3__stdout.log`
- BTC archive cache: `backend/runs/research_track/alt_extreme_24h_drawdown_24h_reversion_long/btc_cache/` (24 monthly joblib, ~50MB)

## Next action

**Halt at R-3 verdict. Graveyard. Awaiting user disposition.**

Do NOT auto-promote to R-4. Awaiting user decision: graveyard vs targeted
sub-paradigm re-scope (bear×mid_vol focus only).
