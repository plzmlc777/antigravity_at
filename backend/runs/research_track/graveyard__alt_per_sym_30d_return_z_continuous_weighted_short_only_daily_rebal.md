# paradigm 185 graveyard — SHORT-only continuous-weighted daily-rebal

- **slug**: `alt_per_sym_30d_return_z_continuous_weighted_short_only_daily_rebal`
- **counter**: 185 (substantive — R-1 follow-up extraction from paradigm 184)
- **phase**: R1_GRAVEYARD
- **verdict**: `NARROW_SCOPE_LIFE_CHANGING_FAIL`
- **run_ts**: 2026-05-22T00:01:06Z
- **dispatcher**: paradigm-architect Opus 4.7 (1M context)

---

## Mechanism

paradigm 184 LONG/SHORT decomposition empirical evidence base. SHORT-side standalone Sharpe +0.604 (paradigm 184 internal account, 0.01%/day fixed funding cost). paradigm 185 = SHORT-side isolation with 1x capital + actual binance_funding_rate DB cost model (13/14 syms × 2.25yr × 8h × 3 cycles).

- Per-sym 30d return → 90d z-score, 14 alts cohort
- SHORT weight: clip(z, -3, -0.5) where z ≤ -0.5, normalize sum(|w|) ≤ 1
- Daily rebalance; fee 8bp one-way × turnover
- Funding cost model = actual DB rates (mean +0.6 bp/8h positive carry for SHORT, +1.55% annualized yield)

## R-1 Result Summary

| Metric | Value | Notes |
|---|---|---|
| n_days_aligned | 701 | 2024-05-30 .. 2026-04-30, 9 quarters |
| **portfolio_net Sharpe** | **+0.501** | paradigm 184 SHORT-side ref +0.604, delta −0.103 |
| portfolio_net ann_return | +36.78% | (paradigm 184 SHORT-side ref +45.87%) |
| portfolio_net max_dd | −47.30% | (paradigm 184 SHORT-side ref −45.56%) |
| portfolio_net total_return | +25.57% | |
| sortino | +0.633 | |
| util_pct_capital_avg | 68.67% | (Lesson #71 path C ≥30% PASS) |
| avg_active_syms | 5.0 | (paradigm 184 SHORT side 5.0) |
| total_fee_drag_pct | 15.36% | (vs paradigm 184 SHORT-side ~10%) |
| total_funding_pnl_pct | +2.99% | actual DB; positive carry preserved |
| annualized_funding_yield | +1.55% | vs paradigm 184 fixed −3.65%/yr cost |

### Permutation test (n=1000)

| | Value |
|---|---|
| obs_sharpe | 0.5011 |
| null_mean_sharpe | −0.4769 |
| null_std_sharpe | 0.4313 |
| sharpe_excess | +0.978 |
| **z_excess** | **+2.27** (≥ 2.0 PASS) |
| **perm_p_value** | **0.013** (≤ 0.10 PASS) |

### 4-cond audit (Lesson #20 + life-changing 4-dim)

| Cond | Pass | Detail |
|---|---|---|
| 1 three-gate | **PASS** | z_excess 2.27, perm_p 0.013, sharpe_excess +0.978 |
| 2 concentration | **PASS** | 9/14 syms positive_total (ratio 0.643) |
| 3 temporal | **PASS** | 5/9 quarters positive |
| 4 life-changing 4-dim | **FAIL** | per-trade edge 2.015 bp < 200 bp; sharpe 0.501 < 1.5 |

**4-dim breakdown**:
- trades_per_yr_effective: 1825.4 ≥ 12 ✓
- per_trade_edge_bp: **2.015 < 200** ✗ (highly diluted by daily 14-sym fragmentation)
- capital_util_pct: 68.67 ≥ 30 ✓
- sharpe: **0.501 < 1.5** ✗ (paradigm 184 SHORT-side standalone +0.604 reference also sub-life-changing)

→ **NARROW_SCOPE_LIFE_CHANGING_FAIL** (lesson #20 4-cond all pass capable, but life-changing 4-dim FAIL closes door)

## Lesson #72 Boundary Verdict

**LESSON_72_STRICT_UNIVERSAL_REJECTED**

paradigm 184 SHORT-side standalone +0.604 sharpe **empirically reconfirmed at +0.501** (delta −0.103) with:
- **+1x capital deployed** (vs paradigm 184 2x gross) → fee/funding overhead halved structurally
- **Actual funding rate DB model** (paradigm 22 substrate 13/14 syms) → +1.55%/yr positive carry (paradigm 184 used fixed −3.65%/yr cost estimate)
- Net result: alpha is **independently extractable** as standalone SHORT-only strategy, NOT a paradigm 184 internal accounting artifact

Continuous-weighting framework SHORT-side mode alpha-bearing for downtrend-bias universe **CONFIRMED**. Lesson #72 strict universal claim (continuous-weighting alpha extraction impossible) **REJECTED**.

However, the alpha does NOT clear life-changing 4-dim threshold (sharpe < 1.5, per-trade edge < 200bp). Result: alpha exists but sub-grade.

## paradigm 184 Reconciliation

| Sym | paradigm 184 SHORT contrib_bp | paradigm 185 contrib_bp | paradigm 185 funding_bp | paradigm 185 total_bp | Consistency |
|---|---|---|---|---|---|
| BTCUSDT | −25 | −25 | +58 | +33 | ✓ contrib match (small) |
| ETHUSDT | **+1674** | **+1674** | +38 | +1712 | ✓ exact match |
| BNBUSDT | −623 | −623 | −1 | −625 | ✓ exact match |
| SOLUSDT | +355 | +355 | −4 | +350 | ✓ match |
| XRPUSDT | −319 | −319 | +62 | −257 | ✓ match (funding mitigated) |
| ADAUSDT | +16 | +16 | +24 | +40 | ✓ match |
| DOGEUSDT | +1274 | +1274 | +26 | +1300 | ✓ exact match |
| AVAXUSDT | −14 | −14 | −9 | −23 | ✓ match |
| LINKUSDT | **+1589** | **+1589** | +28 | +1616 | ✓ exact match |
| LTCUSDT | +88 | +88 | +38 | +126 | ✓ match |
| BCHUSDT | −1880 | −1880 | +11 | −1869 | ✓ exact match |
| NEARUSDT | **+2430** | **+2430** | +40 | +2470 | ✓ exact match |
| FILUSDT | −127 | −127 | −12 | −139 | ✓ match |
| WIFUSDT | **+2818** | **+2818** | 0 | +2818 | ✓ exact match (no funding DB) |

paradigm 184 SHORT-side standalone reconciliation **exact** (gross level, identical mechanism / universe / weights / period). funding model upgrade is purely additive: +1.55%/yr annualized contribution.

**paradigm 181 negative-syms SHORT attribution** (3/6 positive, ratio 0.5):
- LINK +1616 bp (positive)
- NEAR +2470 bp (positive)
- LTC +126 bp (positive)
- FIL −139 bp, BCH −1869 bp, BNB −625 bp (negative)

paradigm 184 spec hypothesis (paradigm 181 6 negative syms SHORT-flip → alpha recovery) **half-confirmed** (3/6 alpha-bearing under SHORT, 3/6 still alpha-void).

## Quarter Breakdown (5/9 positive)

| Quarter | n | return | sharpe | gross | funding | fee | positive |
|---|---|---|---|---|---|---|---|
| 2024Q2 | 32 | +34.47% | +5.25 | +32.00% | +0.55% | 0.82% | ✓ |
| 2024Q3 | 92 | −23.28% | −1.33 | −18.90% | +0.09% | 2.54% | ✗ |
| 2024Q4 | 92 | +16.90% | +1.44 | +19.55% | +0.88% | 1.38% | ✓ |
| 2025Q1 | 90 | +22.44% | +1.41 | +29.56% | +0.60% | 1.71% | ✓ |
| 2025Q2 | 91 | −2.54% | +0.05 | +1.90% | +0.21% | 1.52% | ✗ |
| 2025Q3 | 92 | −31.12% | −2.47 | −31.09% | +0.96% | 3.42% | ✗ |
| 2025Q4 | 92 | +20.25% | +1.32 | +27.97% | +0.02% | 2.40% | ✓ |
| 2026Q1 | 90 | +5.35% | +0.65 | +11.56% | −0.34% | 1.57% | ✓ |
| 2026Q2 | 30 | +0.00% | 0.00 | +0.00% | +0.00% | 0.00% | ✗ |

Two large negative quarters (2024Q3 −23%, 2025Q3 −31%) align with crypto rally periods (BTC strong uptrend) → SHORT-only structural exposure to bull market drawdowns. 5/9 quarter positive = cond3 PASS but volatile.

## Lesson #61 slug grep audit

Patterns checked: `short_only`, `short_continuous`, `short_weighted`, `sell_only`, `bear_continuous`. Collision count: **0**. paradigm 183 slug-miss re-occurrence prevented.

## Mirror antipattern catalog justification (CRITICAL)

paradigm 70 precedent acknowledged (btc_rv_highvol mirror SHORT: UP×LONG +113bp vs DOWN×SHORT −49bp 13σ asymmetry, auto-mirror falsified).

**paradigm 185 distinction from paradigm 70 antipattern**:
1. NOT auto-inverse of paradigm 181 LONG-only (different mechanism family)
2. **Evidence-based extraction**: paradigm 184 LONG/SHORT decomposition empirical Sharpe SHORT +0.604 standalone (paradigm 184 R-1 metrics explicit)
3. Funding model upgrade: actual DB rate (paradigm 22 substrate 13 syms × 2.25yr × 8h × 3 cycles) vs paradigm 184 fixed 0.01%/day
4. **별도 R-1 measurement obligation satisfied** (independent permutation test, n_perm=1000, z_excess +2.27)

**Mirror antipattern catalog 별도 R-1 의무 정합** ✓

## Family / Lesson Impact

- **Lesson #72 STRICT_UNIVERSAL_REJECTED** dogfood: continuous-weighting framework Tier 4 retire claim REFUTED. SHORT-only mode independently alpha-bearing (+0.501 sharpe, p=0.013) for downtrend-bias universe.
- **Lesson #71 path C ESCAPE 4번째 dogfood**: util 68.67% ≥ 30%, multi-position simultaneous, signal-intensity proportional ✓
- **Lesson #61 slug grep 6번째 dogfood** (post-paradigm 183/184): 0 collision verified pre-dispatch
- **paradigm-architect spec contribution**: actual-funding-rate model demonstrated material (+1.55%/yr) for SHORT-side continuous-weighting paradigms. Future SHORT-bearing paradigms should default to DB-based funding model, NOT fixed-rate estimate.

**Continuous-weighting framework status update**:
- paradigm 181 (long-only): graveyard, sharpe −0.422
- paradigm 184 (long-short balanced): graveyard, sharpe +0.027 (LONG side cancels SHORT alpha)
- paradigm 185 (short-only): graveyard NSLC, sharpe +0.501 (alpha exists, sub-life-changing)

Family status: **NOT Tier 4 retired**. SHORT-only path empirically alpha-bearing; LONG drag is the structural constraint. Future continuous-weighting paradigms in this DNA space should explore SHORT-side bias variants (regime-filtered SHORT, vol-adjusted SHORT, etc.) BUT life-changing 4-dim layer (sharpe ≥ 1.5, per-trade edge ≥ 200bp) is still the blocking constraint.

## paradigm 186 next-action recommendations

Three paths sorted by life-changing 4-dim feasibility:

### Path A — Regime-conditional SHORT-only (sharpe boost via filter)
- **paradigm 186A** `alt_per_sym_30d_return_z_continuous_weighted_short_only_btc_downtrend_filter_daily_rebal`
- BTC 90d return < 0 (downtrend regime filter) → SHORT enabled; else cash
- Hypothesis: 2024Q3/2025Q3 large negative quarters were bull-market drawdowns; regime filter trims them
- Expected: trades_per_yr lower (≈50% days filtered), util drop to ~35%, sharpe potentially +1.0~+1.5

### Path B — Concentration SHORT-only (per-trade edge boost via reduction to k=3-5)
- **paradigm 186B** `alt_per_sym_30d_return_z_continuous_weighted_short_only_top_k3_concentrated_daily_rebal`
- Top-3 (most negative z) only → SHORT, k=3 simultaneous
- Expected: trades_per_yr → ~1000 (vs 1825), per-trade edge boost 3-5x, sharpe maintained
- Risk: cond2 concentration FAIL (fewer syms, less diversification)

### Path C — Higher-frequency SHORT-only (vol regime / 5d hold)
- **paradigm 186C** `alt_per_sym_30d_return_z_continuous_weighted_short_only_4h_hold_higher_freq`
- 4h rebalance instead of daily; sharper signal decay
- Expected: trades_per_yr → 8000+, per-trade edge drop, sharpe stable
- Likely NSLC again unless mean-reversion 4h sharper

**Recommendation: paradigm 186A** (regime filter highest probability of life-changing 4-dim PASS). Path B secondary. Path C deprioritized.

---

**R-1 verdict**: `NARROW_SCOPE_LIFE_CHANGING_FAIL`
**Lesson #72 verdict**: `LESSON_72_STRICT_UNIVERSAL_REJECTED`
**paradigm 184 reconciliation**: ✓ exact match gross-level, +1.55%/yr funding upgrade additive
**Mirror antipattern catalog**: ✓ evidence-based extraction, NOT auto-inverse

artifacts:
- `backend/scripts/research/paradigm185_short_only_continuous_weighted_r1.py`
- `backend/runs/research_track/alt_per_sym_30d_return_z_continuous_weighted_short_only_daily_rebal/r1__metrics.json`
- `backend/runs/research_track/alt_per_sym_30d_return_z_continuous_weighted_short_only_daily_rebal/r1__timeseries.csv`
- `backend/runs/research_track/graveyard__alt_per_sym_30d_return_z_continuous_weighted_short_only_daily_rebal.md`
- `backend/runs/research_track/INDEX.json` (updated, total 94 paradigms)
