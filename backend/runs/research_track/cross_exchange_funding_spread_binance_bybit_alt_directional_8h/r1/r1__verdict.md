# Paradigm R-1 Verdict: cross_exchange_funding_spread_binance_bybit_alt_directional_8h

**Date**: 2026-05-19  
**Phase**: R-1 PoC  
**Host**: Mint (`mint@183.99.228.81`)  
**Wall-clock**: 18.0s

## Verdict

**`BROAD_FALSIFIED_FEE_FLOOR`**

All 4 Symmetric Negative Test quadrants at the chosen focus threshold (bp=1.0) deliver net < 0 returns. Focus-direction gross signal is positive (+12 to +14 bp) but compressed below the 16 bp round-trip fee floor. Mirror quadrants are systematically more negative than focus (confirming direction is correct), but the absolute magnitude across all 4 quadrants is fee-bound.

## Substrate verification (Lesson #28)

| Symbol | Binance funding rows | Bybit funding rows | OHLCV 1m rows |
|---|---|---|---|
| AVAXUSDT | 2,736 | 2,792 | 1,241,280 |
| BCHUSDT | 2,736 | 2,792 | 1,241,280 |
| BNBUSDT | 2,736 | 2,792 | 1,241,280 |
| DOGEUSDT | 2,748 | 2,792 | 1,241,280 |
| LINKUSDT | 2,736 | 2,792 | 1,241,280 |
| SOLUSDT | 2,748 | 2,792 | 1,241,280 |
| XRPUSDT | 2,736 | 2,792 | 1,241,280 |

All 7 / 7 deep-universe symbols passed substrate verification. Bybit V5 endpoint `/v5/market/funding/history` returned full 2.5yr history without auth. Joblib cache built at `~/auto_trading/backend/runs/ohlcv_cache/bybit_funding/` (7 files).

Window: 2023-11-15 → 2026-05-19 (915 days). Total paired rows: 19,176.

**Lesson #30 data window ratio**: 0.9989 (full universe-coherent overlap). PASS.

## 5-axis novelty (reconfirmed ex post)

| Axis | Status |
|---|---|
| Data source | NOVEL (cross-exchange paired feed — Bybit V5 first use in 102 paradigms) |
| Statistic | known (spread + rolling 90d z) |
| Time scale | known (8h funding cycle) |
| Universe | NOVEL (dual-exchange cross-sectional pairing) |
| Mechanism | NOVEL (exchange arbitrage / venue-positioning imbalance) |

3 / 5 NOVEL — PASS frontier scout 2-axis threshold.

## Sample density prescreen (Lesson #11)

Initial threshold spec (30/50/80/100 bp absolute) yielded **0 events** across all cells — the cross-exchange funding spread distribution is much narrower than hypothesized.

Empirical spread distribution per-cycle:
- p50 |spread_bp| = 0.2-0.8 bp
- p90 |spread_bp| = 1.0-1.6 bp
- p99 |spread_bp| = 2.3-3.7 bp
- max = 6-85 bp (rare events)

Recalibrated thresholds (1.0/2.0/3.0/5.0 bp + z 1.5/2.0/2.5):

| Threshold | A_focus n | B_focus n | quarters_pass(A) | quarters_pass(B) |
|---|---|---|---|---|
| bp=1.0 | 1,019 | 1,571 | 10/10 | 10/10 |
| bp=2.0 | 140 | 348 | 1/10 | 3/9 |
| bp=3.0 | 32 | 120 | 0/6 | 2/8 |
| bp=5.0 | 6 | 23 | 0/1 | 0/4 |
| z=1.5 | 1,029 | 922 | 10/10 | 10/10 |
| z=2.0 | 489 | 482 | 8/10 | 6/10 |
| z=2.5 | 197 | 265 | 2/10 | 3/10 |

**Focus chosen**: bp=1.0 (only threshold with all 4 quadrants × 4+ quarters >= 30/cell).

## Lesson prescreen sequential results

| Lesson | Applicable | Result |
|---|---|---|
| #11 sample-density | Yes | PASS at bp=1.0 (per-quarter densities 10/10) |
| #19 Symmetric Negative joint-trigger | Yes | 4-quadrant computed in single R-1 batch |
| #20 sign-cond narrow-scope | Yes | Focus FAIL → checked sweep, no isolated cell with three-gate PASS + Concentration PASS |
| #21 axis stacking | No | Single statistic (signed spread) |
| #22 stateful CP | No | No CUSUM/Page-Hinkley |
| #23 boundary-event horizon density | No | 8h cycle is high-frequency (1095/yr) |
| #24 multi-day persistence | No | 8h cycle anchor, not multi-day boundary |
| #26 temporal WF mandatory | R-2 only | Deferred |
| #27 entry-side immediate vs delayed | Yes | 8h cycle close is immediate entry trigger (entry at +1min); CLASSIFIED `immediate` |
| #28 substrate availability | Yes | PASS 7/7 with full 2.5yr Bybit history |
| #29 cross-proxy | N/A | Spread is single-domain observable; both feeds are direct observables |
| #30 data window ratio | Yes | 0.9989 — PASS (full universe-coherent overlap) |
| #32 universe-baseline-coherent A_focus trap | Yes | Universe baseline mean +1.63 bp / 240m (per-sym range -2.9 to +8.6 bp). A_focus mean must exceed this. At bp=1.0 A_focus gross +11.83bp >> baseline +1.63bp → no drift artifact. PASS. |
| #33 magnitude-conditioning trap | No | Trigger = signed spread_bp; outcome = signed fwd_ret. Independent dimensions. |

## 4-quadrant Symmetric Negative Test results (Lesson #19, single batch)

Focus setting: **bp=1.0 abs spread, hold=240m, fee=16bp round-trip**

| Quadrant | Hypothesis | n | gross_bp | net_bp | sigex | perm_p | ci_low_bp | ci_up_bp | 3-gate |
|---|---|---|---|---|---|---|---|---|---|
| A_focus | spread>+1bp → LONG (cont.) | 1019 | +11.83 | −4.17 | +1.94 | 0.983 | −16.77 | +8.43 | FAIL |
| A_mirror | spread>+1bp → SHORT (fade) | 1019 | −11.83 | −27.83 | −1.71 | 0.047 | −40.99 | −14.67 | FAIL |
| B_focus | spread<−1bp → SHORT (cont.) | 1571 | +14.33 | −1.67 | +2.87 | 1.00 | −12.41 | +9.08 | FAIL |
| B_mirror | spread<−1bp → LONG (fade) | 1571 | −14.33 | −30.33 | −2.20 | 0.008 | −41.08 | −19.59 | FAIL |

**Quadrant pair signature**: `[-, -, -, -]` (all net negative at bp=1.0)  
**Lesson #8 upward bias artifact flag**: False (A_mirror and B_mirror are MORE negative than focus — direction is correct, just fee-bound)

Note: `perm_p_two_sided=1.00` for B_focus is high because the fee-drift null distribution is centered well below 0 (mean null t ≈ -3 due to 16bp fee), so a positive observed t is "rare on the high side" but two-sided test sees it as not rare relative to symmetric tails. The B_focus sigex=2.87 is genuinely above the fee-drift null mean by ~2.9σ — but `ci_lower_bp=−12.41` (bootstrap CI on observed net returns includes 0) blocks the three-gate.

## Threshold sweep diagnostic (Lesson #20 partial-PASS scan, hold=240m)

| Cell | A_focus n / gross / sigex | B_focus n / gross / sigex |
|---|---|---|
| bp=1.0 | 1019 / +11.8 / 1.94 | 1571 / +14.3 / 2.87 |
| bp=2.0 | 140 / +28.0 / 1.59 | 348 / +32.5 / 2.54 |
| bp=3.0 | 32 / +126.4 / 2.11 | 120 / +57.9 / 2.17 |
| bp=5.0 | 6 / +196.3 / 2.00 (n too small) | 23 / +73.6 / 0.90 |
| z=1.5 | 1029 / +9.0 / 1.50 | 922 / +20.3 / 3.02 |
| z=2.0 | 489 / +10.1 / 1.12 | 482 / +21.1 / 2.25 |
| z=2.5 | 197 / +25.2 / 1.70 | 265 / +20.6 / 1.52 |

**Strongest narrow-scope candidate**: bp=2.0 B_focus  
- n=348, gross +32.47bp, net +16.47bp, sigex +2.54  
- BUT: `perm_p_two=0.675` (FAIL ≤0.10) and `ci_lower_bp=−15.24` (FAIL > 0) → 1/3 gates pass only.  
- Concentration: 0/7 symbols ci_pos, 4/7 quarters pos_t.  
- Per-quarter: 2024 Q1+Q2+Q4 positive (t>0), 2025 Q2 +Q4 NEGATIVE (t=−1.02, −0.41), 2026 Q1 skipped — **temporal instability already visible at R-1, would fail Lesson #26 walk-forward**.

bp=3.0 A_focus: gross +126bp dramatic, sigex 2.11, but n=32 only and per-symbol all skipped (<20 each). Sub-sample insufficient.

No cell satisfies Lesson #20 4-cond (three-gate ALL PASS + Concentration PASS + life-changing 4-dim PASS) — narrow-scope path **not available**.

## Hold sweep diagnostic (bp=1.0 focus)

| Hold | A_focus net_bp / sigex | B_focus net_bp / sigex |
|---|---|---|
| 60m | −11.23 / +1.93 | −11.03 / +3.12 |
| 240m | −4.17 / +1.94 | −1.67 / +2.87 |
| 480m | +5.77 / +2.31 | −12.05 / +0.39 |
| 1440m (1d) | +24.36 / +2.12 | −28.12 / −1.51 |

Asymmetric hold response: **A_focus monotonically improves with hold** (positive drift at 1d), **B_focus diverges negative** at long holds. This is mechanism-revealing — when Binance funding > Bybit (A side), the slower upward drift continues, but when Binance funding < Bybit (B side), the SHORT continuation fails at multi-cycle holds (positions reverse). Suggests the alpha is asymmetric: only the long-side has post-event continuation. **However, A_focus 1440m sigex +2.12 still has ci_lower likely negative (not measured at 1440m here).**

## Concentration Gate diagnostic (Lesson #16)

bp=1.0 focus quadrants: **0/7 symbols ci_pos in all 4 quadrants** — signal is too dispersed per-symbol to clear the 30% threshold. Quarterly: A_focus 4/10 pos_t, B_focus 4/10 pos_t (below 50% cutoff).

bp=2.0 B_focus (best non-focus cell): **0/7 symbols ci_pos**, 4/7 measurable quarters pos_t (60%, marginal). Insufficient breadth.

## Life-changing 4-dim measurement

Not computed (verdict tree: `BROAD_FALSIFIED_FEE_FLOOR` short-circuits before life-changing evaluation; no PASS or CONCENTRATED branch reached).

## Mechanism interpretation

The cross-exchange funding spread DOES carry directional information (gross-positive in focus, gross-negative in mirror, sigex > 2 in several cells, asymmetric hold response). However:

1. **Magnitude is on the order of the fee** — single-event edge ~+10-30 bp gross which fee-net annihilates.
2. **Per-symbol dispersion**: 0/7 symbols have ci_lower > 0 in any quadrant. The aggregate signal is averaging across symbols with heterogeneous responses.
3. **Temporal instability**: 2024 cohort positive, 2025 reversal (esp. B_focus 2025Q2 t=−1.02), 2026Q1 sparse. Lesson #26 walk-forward would FAIL.
4. **Asymmetric hold response on A side** (Binance>Bybit → LONG) suggests a slow leak mechanism, but multi-day holds compound noise faster than alpha.

**Funding family Tier 4 retire stands strengthened** — cross-exchange spread axis was the most plausible family-distinct exception, and it still cannot clear 16bp fee floor with directional alpha. The mechanism (venue-positioning imbalance) is too weak per-event and too dispersed across symbols.

## Verdict tree resolution

- Three-gate FAIL across all 4 focus quadrants → branch: BROAD_FALSIFIED
- Sweep scan: no narrow-scope cell with three-gate ALL PASS + Concentration PASS
- All 4 quadrants net < 0 → broad-falsified-bias check: TRUE
- Focus gross |bp| range (11.8 to 14.3) < 16bp fee floor → BROAD_FALSIFIED_FEE_FLOOR

## Next-action recommendation

**`graveyard_register_with_lesson`**

Propose lesson candidate **#34** (subject to dogfood validation):
> **"Cross-exchange single-statistic spread on liquid pairs is fee-floor bound."**  
> Even when novel-axis substrate (Bybit V5 funding) is added orthogonal to Tier 4 funding family, the cross-venue funding RATE differential at 8h granularity on USDT-perp pairs has magnitude ~p99 = 3 bp / cycle and gross 240m response ~10-30 bp — directly comparable to round-trip fee. Family-distinct novelty alone cannot overcome fee floor when the underlying market microstructure already equilibrates spreads to within fee-arbitrage tolerance. **Mechanism: cross-venue arbitrage between Binance and Bybit on liquid USDT perps is too efficient — spread→price-continuation alpha is competed away.**

Implications:
- The "family-distinct cross-exchange axis" exception path (per memory snapshot §3) is now invoked once and falsified. The funding family retire stands.
- Cross-exchange spread on **less liquid venue pairs** (e.g., Gate.io / Bitget perp vs Binance) or **lead-lag delay studies** (Bybit → Binance time-shifted) could still differ — separate paradigm proposals.
- This is the **103rd graveyard** under continuous-parallel mode.

## Artifacts (on Mint)

- Script: `~/auto_trading/backend/scripts/research/cross_exchange_funding_spread_r1.py`
- Metrics: `~/auto_trading/backend/runs/research_track/cross_exchange_funding_spread_binance_bybit_alt_directional_8h/r1/r1__metrics.json`
- Verdict: `~/auto_trading/backend/runs/research_track/cross_exchange_funding_spread_binance_bybit_alt_directional_8h/r1/r1__verdict.md`
- Bybit funding cache: `~/auto_trading/backend/runs/ohlcv_cache/bybit_funding/*.joblib` (7 files, persistent)
- Bybit substrate probe: `~/auto_trading/backend/runs/ohlcv_cache/bybit_funding/_summary.json`

## Halt confirmation

- R-1 only completed. R-2 / R-3 / R-4 NOT spawned.
- No background tasks running.
- Awaiting user instruction for graveyard register + INDEX update + Q3 queue lesson amendment.
