# Graveyard — paradigm 117 `alt_extreme_24h_drawdown_24h_reversion_long`

**Verdict**: R3_FAIL_OOS (multi-axis concerns: also FAIL_SURVIVORSHIP gating + Caveat 1 F mechanism asymmetry)
**Date**: 2026-05-20 KST
**Killed at**: R-3 robustness audit

## Hypothesis recap

Alt 24h cumulative log return ≤ −15% triggers forward LONG 24h continuation
(capitulation mean-reversion paradigm).

## Lifecycle summary

| Phase | Verdict | Key metric |
|---|---|---|
| R-1 (24h hold via Lesson #37 sweep verdict scan) | PASS_R1_FULL | n=406, sigex+8.71, lc4 4/4, primary 4h cell flat |
| R-2 (24h hold primary) | R2_PASS | All 5 gates clear (pool-drift OK, TS-CV 4/5, threshold monotone, broad-shoulders top-3 PASS, lc4 4/4) |
| R-3 (7-caveat robustness) | **R3_FAIL_OOS** | OOS edge ratio 0.65 (Train→OOS decay 35%), OOS lc4 3/4 |

## R-3 caveats outcome

| # | Caveat | Outcome | Detail |
|---|--------|---------|--------|
| 1 | Lesson #39 real 4-quadrant SNT | **F (informational)** | B_same (PUMP×SHORT) sigex 0.28 — mechanism CLASS asymmetric |
| 2 | Regime stratify (3×3) | **P** | 8/9 cells positive, no cell t<-2.0 |
| 3 | SL/TP grid (5×7) | **P** | Plateau 6 cells, seed SL=0.25 TP=0.30 |
| 4 | Correlation existing paradigms | **P** | Max cosine 0.243 (funding_carry) ≤ 0.7 |
| 5 | TIA exclusion | **INFO** | Uplift +9.75% < 10% threshold |
| 6 | Survivorship cohort | **F (gating)** | Conservative R-5 edge -0.59%/trade << 2% bar |
| 7 | Holdout OOS | **F (marginal)** | Edge ratio 0.65 in 0.50/0.70 gap |

## Primary failure: holdout OOS decay

- **Train period** (2024-05-30 ~ 2025-06-30): n=288 trades, edge +2.978%/trade, sigex +8.12, Sharpe 7.12, lc4 4/4
- **OOS period** (2025-07-01 ~ 2026-04-30): n=118 trades, edge +1.929%/trade, sigex +3.51, Sharpe 3.57, **lc4 3/4** (edge dim fails 2%)
- **Edge ratio**: 0.65 (35% decay)

Signal is still statistically real on OOS (sigex 3.51, perm_p 0.002, direction
positive), but has decayed past the **life-changing 2%/trade threshold**.

## Secondary concern: survivorship-cohort bias

R-3 probed 8 candidate "delisted" symbols via Binance Vision archive:
- Truly delisted within window: MATICUSDT only (n=2 triggers, +5.89% — too sparse)
- Quality-tier-lower still-listed: BAKEUSDT (n=30, **−7.93%/trade**), CTSIUSDT (n=20, −0.91%/trade), FTMUSDT (n=11, +0.14%)
- Pooled extended cohort: n=63 triggers, edge **−3.86%/trade**

**Conservative R-5 edge** (50% surviving + 50% extended cohort) = **−0.59%/trade << 2% life-changing threshold**

The 28-alt R-2 universe was implicitly hand-picked for tier-1 liquidity. The
mechanism does NOT generalize to weaker still-listed alts — BAKE/CTSI show
continuation (NOT reversion) after −15% drawdowns. This is NOT classical
survivorship bias but a **cohort-tier selection bias** which is equally
disabling for life-changing R-5 deployment.

## Tertiary concern: mechanism CLASS asymmetric (Caveat 1)

True Lesson #39 4-quadrant SNT (PUMP mirror) revealed:
- A_focus (drawdown × LONG): sigex +8.71 ✓
- A_mirror_real (drawdown × SHORT): −8.71 (mathematical mirror — sanity check)
- **B_same_sign (PUMP × SHORT)**: sigex **+0.28** ✗ (null!)
- B_mirror_real (PUMP × LONG): sigex +1.20 (also null)

The euphoria-correction symmetric mirror IS NOT REAL. The hypothesis "extreme
24h magnitude → mean-revert" is too broad — actually "**fear-driven
capitulation** → bounce", direction-asymmetric (likely driven by forced
deleveraging cycle: LIQ cascade clears + funding flip + late shorts cover).

This is informational by spec (Caveat 1 F alone doesn't auto-fail) but
materially changes the mechanism narrative — paradigm is much narrower than
originally framed.

## Lessons captured

### Candidate Lesson #41 — "R-2 broad-shoulders + monotone + TS-CV all-pass does NOT predict R-3 OOS PASS"

R-2 5 gates can all be GREEN while OOS holdout shows substantive temporal
decay (35% in 10 months). Decay can be enough to drop edge below
life-changing 2%/trade bar even with otherwise healthy stats (sigex 3.51,
direction positive). Mandate: holdout OOS must be checked at R-3 with strict
edge_ratio ≥ 0.70 AND life-changing 4-dim independently on OOS subset.

### Candidate Lesson #42 — "Mechanism CLASS asymmetry (capitulation vs euphoria) undetectable in R-1/R-2 single-axis measurement"

R-1 4-quadrant SNT is mathematical-mirror only (A_mirror = −A_focus
identity). The TRUE mechanism class test requires an ORTHOGONAL trigger
(PUMP × SHORT vs drawdown × LONG, not just drawdown × SHORT). This must be
added to R-3 as a mandatory caveat for any "extreme magnitude → mean-revert"
class paradigm. The directional asymmetry of capitulation vs euphoria is
mechanism-structural, not noise.

### Candidate Lesson #43 — "Survivorship probe via quality-tier-lower still-listed weakness reveals cohort-bias gap even when true delisting substrate is unavailable"

Binance Vision archive does not preserve full history for symbols delisted
before late 2023. But probing still-listed weak-tier alts (BAKEUSDT,
CTSIUSDT, etc.) for the same trigger reveals whether the mechanism
generalizes beyond the implicitly hand-picked tier-1 cohort. If extended-tier
probe shows opposite-direction result, the mechanism's broad-cohort
generalization is at risk. Must be added to R-3 as a mandatory probe.

## Files

- Script: `backend/scripts/research/paradigm117_r3_alt_extreme_24h_drawdown_24h_reversion_long.py`
- Metrics: `backend/runs/research_track/alt_extreme_24h_drawdown_24h_reversion_long/r3__metrics.json`
- FAIL report: `backend/runs/research_track/alt_extreme_24h_drawdown_24h_reversion_long/r3_FAIL.md`
- Stdout log: `backend/runs/research_track/alt_extreme_24h_drawdown_24h_reversion_long/r3__stdout.log`
- BTC 1h archive cache: `backend/runs/research_track/alt_extreme_24h_drawdown_24h_reversion_long/btc_cache/` (24 monthly joblib, ~50MB)

## Possible future re-test

If a more focused sub-paradigm targeting **only the bear × mid_vol and
bear × high_vol regime cells** (where edge is +4.80%/trade × 2.80%/trade
respectively, n=158 combined) can be defined with adequate sample density
and OOS stability, that subset MIGHT warrant R-5 seed. The 28-alt × all-regime
broad scope does not.

Trigger conditions for sub-paradigm:
- BTC 30d return < −5% (BEAR trend regime)
- BTC 30d vol > p33 (MID or HIGH vol regime)
- Alt 24h return ≤ −15% (capitulation trigger unchanged)
- Forward 24h LONG hold (unchanged)
- Limit universe to tier-1 alts only (28 liquid majors, exclude TIA optional)

Sample density check needed first: ~158 trades over 2yr ≈ 79/yr, satisfies
12/yr threshold but is sparse for further stratification.

## R-2 inheritance retained

- R-2 caches preserved (klines_cache + paradigm117 outputs)
- BTC 1h archive cache (24 months ~50MB) is reusable for future R-3 BTC regime stratify

## Final disposition

**Graveyard**. Halt at R-3. NOT promoted to R-4 elite gate.

Awaiting user disposition: either (a) accept graveyard verdict, or (b)
authorize a tighter sub-paradigm re-scope per the "possible future re-test"
spec above (would re-enter at R-1 with sub-paradigm dispatch).
