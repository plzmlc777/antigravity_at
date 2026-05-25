# Paradigm 148 R-1 Gate Evaluation

**Date**: 2026-05-21 14:08 KST  
**Phase**: R-1 (executed)  
**Compute**: substrate backfill 256s + R-1 9.8s = ~4.4 min total  
**Universe**: deep-7 [AVAX,BCH,BNB,DOGE,LINK,SOL,XRP] × 2024-01-01..2026-05-19 (870d)  
**Frame**: 15min substrate → 1h velocity z (30d rolling std) → 4h forward hold

## Headline Result

**Overall verdict raised by script: `PASS_R1_FULL`** (3 cells: D15min_A_focus_zpos_LONG, D15min_B_mirror_zneg_LONG, D30min_A_focus_zpos_LONG)

**Substantive verdict after Lesson #39 + Lesson #8 + Lesson #32 antipattern analysis: `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG`**

The PASS cells are a Lesson #39 sub-class A "broad-uniform mirror antipattern" dogfood + Lesson #8 universal LONG bias dogfood. R-1 mechanism premise FALSIFIED.

## 4-Quadrant × 4-Δ Pattern Matrix (16 cells)

| Δ (min) | A focus (z>+2, LONG) | A mirror (z>+2, SHORT) | B focus (z<-2, SHORT) | B mirror (z<-2, LONG) |
|---|---|---|---|---|
| 15 | **+9.20bp PASS** sigex+8.84 | -25.20bp FAIL sigex-5.59 | -25.73bp FAIL sigex-4.59 | **+9.73bp PASS** sigex+8.55 |
| 30 | **+9.45bp PASS** sigex+9.03 | -25.45bp FAIL sigex-5.97 | -24.57bp FAIL sigex-4.35 | +8.57bp CONC sigex+8.16 |
| 60 | +8.52bp CONC sigex+8.59 | -24.52bp FAIL sigex-5.56 | -23.20bp FAIL sigex-4.14 | +7.20bp CONC sigex+7.67 |
| 120 | +8.81bp CONC sigex+8.78 | -24.81bp FAIL sigex-5.69 | -21.02bp FAIL sigex-2.90 | +5.02bp CONC sigex+6.58 |

**Critical pattern**: ALL LONG cells (regardless of z sign) are POSITIVE; ALL SHORT cells (regardless of z sign) are NEGATIVE. The trigger sign carries **zero directional information**.

## Antipattern Detection (Substantive Falsification)

### Lesson #39 sub-class A — broad-uniform mirror antipattern (DOGFOOD)

Mirror exact symmetry check (Δ=15min):
- A focus (z>+2 LONG): +9.20bp
- A mirror (z>+2 SHORT): -25.20bp
- Difference: 9.20 - (-25.20) = 34.40bp
- Expected if zero-info trigger (only direction bet matters): A focus - A mirror ≈ 2 × universe baseline LONG drift + 16bp round-trip fee × 2 = ~34bp ✅ **MATCH**

This is the textbook Lesson #39 sub-class A pattern: trigger has zero directional info, mirror is exact symmetric around fee-floor center, both broad-uniform-LONG-positive / -SHORT-negative.

### Lesson #8 universal LONG bias amendment (DOGFOOD)

Both A focus AND B mirror are LONG cells, both +9bp. Both A mirror AND B focus are SHORT cells, both -25bp. The "alpha" is purely **LONG-bias on high-volatility events** — not a trigger-sign-conditional signal. This is the Lesson #8 universal upward drift artifact that paradigm 99 first dogfooded.

### Lesson #32 universe-baseline-coherent A_focus vs B_baseline drift (DOGFOOD)

Baseline check: in HIGH-volatility events (|Bybit_z|>2), the Binance 4h forward return has a LONG bias of ~+9bp regardless of Bybit z-sign. This is consistent with vol-cascade LONG continuation in crypto perp (paradigm 69 R-5 family already monetizes this with HIGH-vol filter + LONG bias). 

**paradigm 148 PASS cells are likely re-discovering paradigm 69 family alpha through a different substrate proxy** (Bybit price velocity ≈ HIGH realized vol proxy at cross-venue level). NOT a novel lead-lag mechanism.

### Walk-forward fragility (Lesson #26 + paradigm 87 dogfood pattern)

Quarter-stratified t-stat for D15min_A_focus_zpos_LONG:
- 2024Q1-Q4: +2.30 / +1.12 / -0.02 / +5.94 (mostly positive)
- 2025Q1-Q2: +2.63 / +0.26 (weakening)
- 2025Q3-Q4: +2.10 / **-2.66** (reversal start)
- 2026Q1-Q2: **-2.51 / -3.24** (sharp negative recent quarters)

Recent 4 quarters (2025Q4-2026Q2) are 3/4 NEGATIVE with t-stats ≤ -2.50. **R-2 walk-forward 5-fold TS-CV would fail 1-2/5 at best** — paradigm 87 (binance_delisting) dogfood pattern exactly: small-sample quarter blind spot + recent regime reversal.

### Per-symbol concentration narrow (Lesson #16)

3/7 syms ci_pos (43%): BCH/DOGE/XRP only. 4/7 syms (AVAX/BNB/LINK/SOL) ci_lower negative. Carried by:
- XRPUSDT: +26.7bp ci_lo +15.0 (dominant carrier)
- DOGEUSDT: +16.1bp ci_lo +3.5
- BCHUSDT: +11.1bp ci_lo +0.8 (marginal)

Removing XRP+DOGE+BCH → remaining 4 syms (AVAX/BNB/LINK/SOL) ci_lower ALL negative → narrow-scope concentration on 3 high-vol meme/legacy syms, not a structural cross-venue lead-lag effect.

## Verdict Tree Applied

```
R-1 3-gate (mechanical): 3 cells PASS_R1_FULL (sigex+8 / ci_lower>0 / perm_p=0.000)
  └─ Lesson #39 sub-class A mirror antipattern test
       ├─ Mirror exact symmetric ±16bp fee? YES (A focus +9.20 vs A mirror -25.20 = -34.40 ≈ -2×fee - 2×alpha)
       ├─ Both mirrors broad-uniform? YES (LONG always +9bp, SHORT always -25bp)
       └─ TRIGGER HAS ZERO DIRECTIONAL INFO
            └─ Lesson #8 universal LONG bias detection: PASS cells = LONG-only on high-vol events
                 └─ Lesson #32 universe-baseline drift: paradigm 69 family proxy re-discovery
                      └─ SUBSTANTIVE VERDICT: BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG
```

## Confirmed/Observed Lessons in this R-1

| Lesson | Status | Note |
|---|---|---|
| #8 universal LONG bias | DOGFOOD (3rd-eligible) | Both z>+2 LONG AND z<-2 LONG positive; trigger sign zero-info |
| #11 sample density | PASS empirically | n_obs ~15,000/cell, far above 30/cell floor |
| #16 Concentration | 3/7 syms ci_pos PASS but narrow (XRP+DOGE+BCH carriers) | Mechanical PASS but substantive narrow-scope warning |
| #19 4-quadrant SNT × Δ sweep | EXECUTED 16 cells one batch | Lesson #39 antipattern detected via this protocol — protocol PASS |
| #21 axis stacking | EXEMPT via #58 (cross-substrate) | Single trigger axis (Bybit z) |
| #26 walk-forward fragility prescient | DETECTED ex ante | Quarter degradation 2025Q4-2026Q2 → R-2 5-fold TS-CV almost certain FAIL |
| #28 substrate availability | PASS | Bybit V5 + Binance archive both verified live |
| #30 data window ratio | =1.000 (full window) | 870d × 7 syms × 15min frame, Bybit/Binance overlap perfect |
| #32 universe-baseline drift | DOGFOOD | paradigm 69 vol-cascade LONG family proxy re-discovery |
| #34 empirical distribution prescreen | PASS | |z|>2 empirical rate ~5% (15,000/93,000 ≈ 16% trigger window) |
| #39 sub-class A broad-uniform mirror | DOGFOOD (4th-eligible) | Exact mirror symmetry + uniform LONG positive / SHORT negative |
| #40 threshold attainability | PASS | Bidirectional |z|>2 attainable |
| #44 amendment xref 32nd | DOGFOOD | paradigm 8/26/32/39/56/69 family enforcement at R-1 outcome level |
| #45 HMM/unsupervised prohibition | PASS | Pure parametric z |
| #46 stratified n=50×4q + sign-flip STRONG WARNING | DETECTED | A_focus quarter sign flip (Q4 2024 +5.94 → Q4 2025 -2.66) |
| #56 statistic reformulation 6th-instance | OUTCOME-LEVEL DOGFOOD | R-0 gate PASS but R-1 outcome reveals re-discovery of paradigm 69 family via different substrate proxy |
| #58 cross-substrate exemption | APPLIED | Bybit klines + Binance klines = 2 substrates, Lesson #21 sub-finding exempt |

## Verdict — Final

**Mechanical R-1**: `PASS_R1_FULL` (3 cells satisfy 3-gate + Concentration Gate)

**Substantive R-1**: `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG`

The mechanical PASS is a Lesson #39 sub-class A antipattern + Lesson #8 universal LONG bias artifact + Lesson #32 universe-baseline drift on a paradigm 69 family proxy. The Asian-retail-front-running mechanism premise is **FALSIFIED**: trigger sign carries zero directional information, "alpha" is purely LONG-bias on high-volatility events (paradigm 69 family re-discovery at cross-venue substrate).

**R-2 promotion: BLOCKED**. Promoting to R-2 would re-test paradigm 69 family alpha at a less-efficient proxy with severe 2025Q4-2026Q2 walk-forward degradation, almost certain TS-CV FAIL pattern matching paradigm 87.

## NEW Lesson #59 candidate (1st dogfood)

**"Cross-exchange PRICE lead-lag at 15min+ frame in liquid perp markets is structurally a paradigm 69 family proxy, NOT a novel mechanism class"**

When cross-exchange PRICE velocity z trigger at 15min+ frame produces:
- BOTH LONG quadrants positive (A focus + B mirror)
- BOTH SHORT quadrants negative (A mirror + B focus)
- Mirror exact symmetric ±16bp fee gap

→ This is mechanistically equivalent to "high realized vol filter + LONG continuation" (paradigm 69 family), with Bybit velocity z serving as a noisier proxy for Binance HIGH-vol regime. Cross-exchange channel adds noise without adding mechanism.

**Implication**: Future cross-exchange PRICE lead-lag dispatches at 15min+ frame must explicitly compare PASS cells against paradigm 69 family proxy hypothesis (single-exchange HIGH-vol LONG continuation). If mechanically PASS but the 4-quadrant pattern matches Lesson #39 sub-class A + Lesson #8 + Lesson #32 → substantive `BROAD_FALSIFIED_DIRECTIONAL_BIAS_NOT_LEAD_LAG` regardless of mechanical 3-gate result.

## Resources committed

- **Substrate backfill**: 256s (4.3 min) — 7 syms × Binance 15m archive (83,520 bars/sym) + Bybit V5 klines (83,425 bars/sym)
- **R-1 compute**: 9.8s (16 cells × stratified perm + bootstrap CI)
- **Total wall-clock**: ~4.5 min
- **Artifacts**: r0_prescreen.json + r1__metrics.json + this gate_eval + graveyard report

## Permanent assets

- `backend/runs/ohlcv_cache_15m/bybit_klines/` — 7 syms × 15min × 870d (permanent, reusable for future cross-exchange paradigms)
- `backend/runs/ohlcv_cache_15m/binance_klines/` — 7 syms × 15min × 870d (permanent, reusable)
- `backend/scripts/research/paradigm148_backfill_klines.py` — substrate backfill infrastructure
- `backend/scripts/research/paradigm148_r1.py` — cross-exchange 4-quadrant SNT × Δ sweep template
