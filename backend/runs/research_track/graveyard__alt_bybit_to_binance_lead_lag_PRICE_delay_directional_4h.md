# Paradigm 148 — `alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h` GRAVEYARD

**Verdict**: `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG` (NEW verdict category, R-1 executed, mechanical PASS but substantive antipattern dogfood)  
**Date**: 2026-05-21 14:08 KST  
**Phase**: R-1 (executed, R-2 promotion BLOCKED)  
**Sequence**: 148 (1st PASS_R1_FULL-mechanical after 18-streak non-PASS — but substantively FALSIFIED via Lesson #39 + #8 + #32 antipattern)  
**Compute committed**: ~4.5 min (substrate backfill 256s + R-1 9.8s)  
**Streak**: now **19-streak substantive non-PASS** (paradigms 129-148; paradigm 148 mechanically PASS but substantively falsified at antipattern level)

## TL;DR

paradigm 148 cross-exchange PRICE lead-lag dispatched after paradigm 147 v2 §next-action Option B pivot. R-0 substantive family-distinct gate PASS WITH STRONG WARNING (cross-exchange PRICE axis genuinely distinct from cross-exchange OI axis, Lesson #56 6th-instance trap not triggered at R-0 level). Substrate backfilled in 4.3 min (Bybit V5 klines 15min × 7 syms + Binance 15m archive × 7 syms × 870d).

R-1 dispatched 16 cells (4-quadrant SNT × 4 Δ shifts). **Mechanical result: 3 cells PASS_R1_FULL** (D15min_A_focus_zpos_LONG +9.20bp sigex+8.84, D15min_B_mirror_zneg_LONG +9.73bp sigex+8.55, D30min_A_focus_zpos_LONG +9.45bp sigex+9.03), all with Concentration Gate PASS at 3/7 syms ci_pos. **First PASS_R1_FULL-mechanical result after 18-streak non-PASS.**

**Substantive verdict however is BROAD_FALSIFIED**: the 4-quadrant pattern is a textbook Lesson #39 sub-class A "broad-uniform mirror antipattern" + Lesson #8 universal LONG bias artifact + Lesson #32 universe-baseline drift on paradigm 69 family proxy.

## The smoking gun — 4-quadrant pattern (Δ=15min, identical across Δ=30/60/120)

| Quadrant | Direction | Result | Sigex | Verdict |
|---|---|---|---|---|
| A focus (z>+2) | LONG | **+9.20bp** | **+8.84** | PASS_R1_FULL |
| A mirror (z>+2) | SHORT | -25.20bp | -5.59 | FAIL |
| B focus (z<-2) | SHORT | -25.73bp | -4.59 | FAIL |
| B mirror (z<-2) | LONG | **+9.73bp** | **+8.55** | PASS_R1_FULL |

**Critical observation**: Both LONG cells (regardless of z sign) win. Both SHORT cells (regardless of z sign) lose. The trigger sign carries **zero directional information**.

Mirror exact symmetry check: A focus (+9.20bp) − A mirror (-25.20bp) = 34.40bp ≈ 2×alpha (+18bp) + 2×fee (+16bp). Textbook **Lesson #39 sub-class A** exact mirror antipattern: trigger has zero directional info, signal is pure direction-bet around fee floor center.

## Why mechanical PASS but substantive FAIL

The mechanical 3-gate (sigex≥2 + ci_lower>0 + perm_p≤0.10) and Concentration Gate (3/7 syms ci_pos = 43% ≥ 30%) ARE technically satisfied for 3 cells. But substantive R-1 verdict requires antipattern detection per Lesson #19 (Symmetric Negative Test 4-quadrant) + Lesson #39 (broad-uniform mirror antipattern) + Lesson #8 (universal LONG bias) + Lesson #32 (universe-baseline drift).

**All four lessons trigger DOGFOOD**:

1. **Lesson #39 sub-class A "broad-uniform mirror antipattern"** — A focus and A mirror are exact-symmetric around fee floor; both A focus and B mirror are broad-uniform LONG-positive; both A mirror and B focus are broad-uniform SHORT-negative.

2. **Lesson #8 universal LONG bias amendment** — paradigm 99 first identified this pattern. paradigm 148 = 3rd dogfood eligible (paradigm 99 candidate + paradigm 95 + paradigm 148). PASS cells are LONG-only on high-vol events, not trigger-sign-conditional.

3. **Lesson #32 universe-baseline-coherent A_focus vs B_baseline** — the +9bp "alpha" is universe baseline LONG drift on HIGH-volatility events, not lead-lag specific. Compare with paradigm 69 R-5 LIVE family (HIGH-vol p90 filter + 13 alt LONG 240m): same mechanism class. paradigm 148 = paradigm 69 family re-discovery through cross-exchange substrate proxy.

4. **Lesson #56 6th-instance trap (OUTCOME-LEVEL)** — R-0 substantive gate PASS but R-1 outcome reveals mechanistic equivalence to paradigm 69 family (HIGH realized vol → LONG continuation). Cross-exchange PRICE channel adds noise without adding mechanism. The "Asian-retail-front-running" mechanism premise is **FALSIFIED at outcome level**.

## Walk-forward fragility (Lesson #26 + paradigm 87 dogfood pattern detected ex ante)

Quarter-stratified t-stat for D15min_A_focus_zpos_LONG:
- 2024Q1: +2.30 (n=1996, +16.1bp)
- 2024Q2: +1.12 (n=1033, +7.1bp)
- 2024Q3: -0.02 (n=1470, -0.1bp)
- 2024Q4: +5.94 (n=2729, +38.6bp) — Q4 2024 carrier
- 2025Q1: +2.63 (n=1156, +23.2bp)
- 2025Q2: +0.26 (n=1530, +1.4bp)
- 2025Q3: +2.10 (n=2120, +8.6bp)
- 2025Q4: **-2.66** (n=1112, **-18.8bp**) — REVERSAL START
- 2026Q1: **-2.51** (n=1333, **-12.4bp**) — REVERSAL CONTINUE
- 2026Q2: **-3.24** (n=784, **-18.0bp**) — REVERSAL DEEP

Recent 4 quarters: 3/4 NEGATIVE with t-stats ≤ -2.50. R-2 walk-forward 5-fold TS-CV almost certain to fail (1-2/5 PASS max) — paradigm 87 (binance_delisting) dogfood pattern.

## Per-symbol concentration narrow

PASS cell D15min_A_focus_zpos_LONG per-symbol breakdown:

| Symbol | n | mean_bp | ci_lower_bp | ci_pos |
|---|---|---|---|---|
| AVAXUSDT | 2094 | +4.4 | -6.3 | ❌ |
| BCHUSDT | 2134 | +11.1 | +0.8 | ✅ (marginal) |
| BNBUSDT | 2184 | +3.4 | -4.0 | ❌ |
| DOGEUSDT | 2274 | +16.1 | +3.5 | ✅ |
| LINKUSDT | 2168 | +4.3 | -6.1 | ❌ |
| SOLUSDT | 2191 | -2.4 | -12.1 | ❌ |
| **XRPUSDT** | 2218 | **+26.7** | **+15.0** | ✅ (dominant carrier) |

3/7 syms ci_pos (43% = Concentration Gate PASS mechanically). Substantively narrow: XRP+DOGE+BCH carry, AVAX/BNB/LINK/SOL all negative or zero. Removing XRP (dominant carrier) → remaining 6 syms mean ≈ +6bp ≈ fee floor.

## R-2 promotion: BLOCKED

Promoting to R-2 would re-test paradigm 69 family alpha at a less-efficient cross-exchange proxy with:
- Lesson #39 sub-class A antipattern confirmed (mirror exact symmetric)
- Lesson #8 universal LONG bias confirmed (both LONG quadrants win)
- Lesson #32 universe-baseline drift confirmed (paradigm 69 family equivalence)
- Lesson #26 walk-forward fragility detected ex ante (2025Q4-2026Q2 3/4 negative)
- Lesson #16 narrow-scope concentration on XRP/DOGE/BCH carriers
- Lesson #56 outcome-level 6th-instance trap (mechanism class equivalent to paradigm 69, not novel)

R-2 R-3 R-4 promotion path BLOCKED at substantive antipattern verdict.

## NEW Lesson #59 candidate (1st dogfood)

**"Cross-exchange PRICE lead-lag at 15min+ frame in liquid perp markets is structurally a paradigm 69 family proxy (HIGH realized vol → LONG continuation), NOT a novel lead-lag mechanism class"**

Detection criterion (one-batch 4-quadrant SNT result):
- BOTH LONG quadrants positive (A focus + B mirror)
- BOTH SHORT quadrants negative (A mirror + B focus)
- Mirror exact symmetric ±2×fee gap (A focus − A mirror ≈ 2×alpha + 2×fee)
- All 3 conditions → mechanical PASS but substantive `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG`

Implication: Future cross-exchange PRICE lead-lag dispatches at 15min+ frame must explicitly compare PASS cells against paradigm 69 family proxy hypothesis. If 4-quadrant pattern matches Lesson #39 sub-class A + Lesson #8 + Lesson #32 → substantive falsified regardless of mechanical 3-gate result.

## NEW verdict category — `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG`

Distinct from:
- `BROAD_FALSIFIED` (all 4 quadrants net<0; trigger has zero info AND no direction has alpha)
- `BROAD_FALSIFIED_FEE_FLOOR` (gross close to but below 16bp fee)
- `NARROW_SCOPE_LIFE_CHANGING_FAIL` (Lesson #20 4-cond ALL PASS + 4-dim freq fail)
- `CONCENTRATED_R1_PASS` (3-gate PASS + Concentration FAIL)
- `INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION` (R-0 verdict, R-1 not executed)

**Distinguishing feature**: Mechanical 3-gate + Concentration Gate PASS, but 4-quadrant antipattern (Lesson #39 sub-class A exact mirror + Lesson #8 universal LONG bias + Lesson #32 universe-baseline drift) reveals trigger has zero directional info, "alpha" is universe baseline LONG drift on volatility events, NOT mechanism-specific.

First dogfood: paradigm 148. Recommend formal verdict category addition to paradigm-architect spec.

## Cross-exchange family Tier 4 formal retire enforcement

After cumulative graveyards:
- paradigm 103 `cross_exchange_funding_spread_binance_bybit_alt` (BROAD_FALSIFIED_FEE_FLOOR)
- paradigm 104 `cross_exchange_oi_level_differential_binance_bybit_alt` (BROAD_FALSIFIED_PRIMARY_HOLD perm trap)
- paradigm 147 v1 `alt_bybit_to_binance_lead_lag_oi_delay_directional_4h` (INVENTORY_HALT_DNA_DUPLICATE)
- paradigm 147 v2 `alt_bybit_to_binance_lead_lag_oi_delay_directional_4h` (INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION)
- paradigm 148 `alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h` (BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG)

→ **6 cumulative graveyards** in cross-exchange Bybit↔Binance axis at funding/OI/PRICE substrates.

**Recommendation**: Cross-exchange Bybit↔Binance family **formal Tier 4 retire** at 1h+ frame, deep-7 universe. Future cross-exchange dispatches require:
- Sub-second HFT frame (5m or less)
- Liquidation cascade event anchor (substrate-blocked per [project-paradigm-architect_local_context])
- Genuinely illiquid venue (not Bybit which is paradigm 103-148 universe-saturated)
- OR explicit exception path documented with substrate prescreen

Paradigm 21 R-5 exception (single-exchange OI-vs-PRICE 5m decoupling) remains the only cross-exchange/cross-substrate family R-5 LIVE paradigm.

## Lessons confirmed/observed in this R-1

| Lesson | Status | Note |
|---|---|---|
| #8 universal LONG bias amendment | DOGFOOD 3rd-eligible | paradigm 99 candidate + paradigm 95 + paradigm 148 |
| #16 Concentration Gate STRICT ≥30% | mechanical PASS but narrow | XRP/DOGE/BCH carriers, 4/7 syms negative |
| #19 4-quadrant SNT × Δ sweep | EXECUTED PROTOCOL SUCCESS | One-batch 16 cells enabled antipattern detection |
| #26 walk-forward fragility prescient | DETECTED EX ANTE | Q4 2025-Q2 2026 3/4 negative t≤-2.50 |
| #32 universe-baseline-coherent | DOGFOOD | paradigm 69 family proxy re-discovery |
| #39 sub-class A broad-uniform mirror | DOGFOOD 4th-eligible | Exact ±2×fee symmetric mirror + uniform LONG-positive / SHORT-negative |
| #44 amendment xref 32nd | DOGFOOD | paradigm 8/26/32/39/56/69 ex ante R-0 + R-1 outcome cross-reference |
| #56 statistic reformulation 6th-instance | OUTCOME-LEVEL DOGFOOD | R-0 PASS but R-1 outcome = paradigm 69 family proxy, mechanism class equivalence |
| #58 cross-substrate exemption | APPLIED | Bybit klines + Binance klines |
| **#59 cross-exchange PRICE lead-lag = paradigm 69 family proxy** | **NEW candidate (1st dogfood)** | Detection: BOTH LONG quadrants positive + mirror exact symmetric → substantive falsified regardless mechanical PASS |

## Resources committed

- **R-0 prescreen artifact**: `backend/runs/research_track/alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h/r0_prescreen.json`
- **R-1 script**: `backend/scripts/research/paradigm148_r1.py`
- **Substrate backfill script**: `backend/scripts/research/paradigm148_backfill_klines.py`
- **R-1 metrics**: `backend/runs/research_track/alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h/r1__metrics.json`
- **Gate eval**: `backend/runs/research_track/alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h/gate_eval__r1.md`
- **Graveyard report**: this file
- **Wall-clock**: ~4.5 min (substrate 4.3 min + R-1 9.8s)

## Permanent assets (NEW — first 15m frame substrate cache)

- `backend/runs/ohlcv_cache_15m/bybit_klines/` — 7 syms × 15min × 870d (~25MB, reusable for future cross-exchange 15m paradigms)
- `backend/runs/ohlcv_cache_15m/binance_klines/` — 7 syms × 15min × 870d (~25MB, reusable for future Binance 15m frame paradigms)
- Both caches first-of-kind at 15min frame for research track; permanent asset for hypotheses requiring sub-4h frame

## Next-action recommendation

1. **HALT paradigm 148 at R-1 substantive verdict** with `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG` graveyard.
2. **Counter advance**: 147 → 148 (R-1 executed, distinct from R-0 inventory halt).
3. **NEW verdict category formal addition**: `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG` to paradigm-architect spec verdict tree. First dogfood paradigm 148.
4. **NEW Lesson #59 candidate**: cross-exchange PRICE lead-lag at 15min+ frame structurally paradigm 69 family proxy. 1st dogfood.
5. **Lesson #8 universal LONG bias amendment**: 3rd dogfood eligible (paradigm 99 + 95 + 148). Formal CONFIRMED 자격 promotion eligible at next session.
6. **Lesson #39 sub-class A**: 4th-eligible dogfood. Formal CONFIRMED at next instance.
7. **Cross-exchange Bybit↔Binance family formal Tier 4 retire** at 1h+ frame deep-7 universe (6 cumulative graveyards 103+104+147v1+147v2+148). Paradigm 21 R-5 single-exchange OI-vs-PRICE exception only.
8. **Priority pivot recommendation**: Day 7 baseline measurement 2026-05-28 (D-7) for paradigm 127+128 Mint deploy is now D-7. Expected value of continuing 19-streak non-PASS R-1 dispatches in heavily-explored axes is below paradigm 127+128 R-5 LIVE measurement value.

## Next candidate recommendation (continuous parallel campaign)

Given:
- 19-streak substantive non-PASS (paradigms 129-148)
- Cross-exchange family Tier 4 retire enforced
- Lesson #59 candidate added (cross-exchange PRICE 15min+ = paradigm 69 proxy)
- 8 family retires + 4 candidates + paradigm-69 family proxy detection
- D-13 to D-Day 2026-06-03

Recommend **paradigm 149 hypothesis brainstorm focus**:
- **NOT** cross-exchange any axis (cross-exchange family Tier 4 retire)
- **NOT** OI velocity / funding velocity (paradigm 71 + funding family retire)
- **NOT** 15min+ frame PRICE velocity (Lesson #59 candidate; paradigm 69 family proxy)
- **PREFER** sub-5min frame (paradigm 21 R-5 frame; not yet substrate-blocked)
- **PREFER** event-anchored single-substrate (paradigm 22 R-5 family; funding boundary event remains untested at sub-cycle proxies)
- **PREFER** liquid universe non-cross-exchange (paper pool baseline 7-13 syms)

Two specific paradigm 149 candidates worth R-0 audit:
- (a) `binance_1m_volatility_burst_event_sub5min_continuation_alt` — single-exchange 1m frame realized vol burst event-anchored, sub-5min hold, paradigm 69 frame distinction
- (b) `binance_funding_pre_settlement_30min_premium_velocity_alt` — 8h funding settlement -30min window premium velocity 1m frame, single-substrate (premium 1m), distinct from paradigm 22 carry frame

Both avoid cross-exchange family + Lesson #59 candidate + paradigm 69 frame overlap.
