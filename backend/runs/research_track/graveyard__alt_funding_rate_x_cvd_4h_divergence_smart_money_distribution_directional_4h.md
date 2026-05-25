# Graveyard — paradigm 138 alt_funding_rate_x_cvd_4h_divergence_smart_money_distribution_directional_4h

**Phase**: R-0 prescreen HALT (R-1 never dispatched)
**Verdict**: `R0_HALT_LESSON_40_STRUCTURAL_THRESHOLD_INFEASIBLE_SYMMETRIC`
**Date (KST)**: 2026-05-21 11:56
**Cumulative graveyard count**: 138 (was 137 paradigm Yang-Zhang efficiency ratio)
**Streak**: 10-streak non-PASS (129-138)

## Hypothesis (user-proposed, ad-hoc R-1 dispatch)

Crowded LONG position (funding deeply negative) + smart money distribution (CVD net SELL)
= directional confluence → SHORT 4h.

- Axis 1 (funding): 4h funding rate ≤ -50 bp (extreme LONG-crowded)
- Axis 2 (CVD): 4h cumulative volume delta ratio = (taker_buy - taker_sell) / total ≤ -0.1
- Joint trigger A: both axes confluence → SHORT 4h
- 4-quadrant SNT: A_focus/A_mirror (funding ≤-50bp × CVD ≤-0.1 × SHORT/LONG),
  B_focus/B_mirror (funding ≥+50bp × CVD ≥+0.1 × LONG/SHORT)

## R-0 Sequential Prescreen (paradigm-architect spec — Lesson #40 FIRST per Lesson #40 dogfood)

### STEP 1 — Lesson #40 structural threshold attainability — **FAIL**

Per-sym funding rate distribution (8h frame, bp, 16 audit syms 2.4yr DB):

| sym | n | p1 | p10 | p50 | p99 | min | max | ≤-50bp% | ≥+50bp% |
|---|---|---|---|---|---|---|---|---|---|
| AVAXUSDT | 1095 | -3.99 | -1.63 | 0.34 | **+1.00** | -6.63 | +1.00 | 0.00% | 0.00% |
| DOGEUSDT | 1117 | -1.36 | -0.63 | 0.43 | **+1.00** | -2.60 | +4.53 | 0.00% | 0.00% |
| ETHUSDT  | 1095 | -1.51 | -0.38 | 0.36 | **+1.00** | -3.65 | +1.00 | 0.00% | 0.00% |
| LINKUSDT | 1095 | -1.71 | -0.47 | 0.64 | **+1.00** | -3.01 | +1.00 | 0.00% | 0.00% |
| SOLUSDT  | 1117 | -4.65 | -1.01 | 0.18 | **+1.00** | -30.28 | +2.59 | 0.00% | 0.00% |
| HBARUSDT | 1113 | -2.72 | -1.07 | 0.30 | **+1.00** | -4.81 | +1.00 | 0.00% | 0.00% |
| AXSUSDT  | 1608 | **-68.31** | -16.65 | -1.27 | **+1.00** | -200.00 | +1.00 | **2.67%** | 0.00% |
| COMPUSDT | 1113 | -33.92 | -3.69 | 0.25 | **+1.00** | -147.18 | +1.00 | **0.45%** | 0.00% |
| LDOUSDT  | 1113 | -1.35 | -0.47 | 0.48 | **+1.00** | -3.44 | +1.00 | 0.00% | 0.00% |
| ETCUSDT  | 1113 | -2.49 | -0.94 | 0.57 | **+1.00** | -8.89 | +1.00 | 0.00% | 0.00% |
| UNIUSDT  | 1113 | -1.47 | -0.40 | 0.66 | **+1.00** | -3.02 | +3.11 | 0.00% | 0.00% |
| ICPUSDT  | 1113 | -10.82 | -2.87 | 0.21 | **+1.00** | -74.08 | +1.00 | **0.18%** | 0.00% |
| WLDUSDT  | 1113 | -8.27 | -1.93 | 0.48 | **+1.00** | -12.66 | +2.09 | 0.00% | 0.00% |
| TONUSDT  | 2227 | -2.13 | -0.80 | 0.30 | **+0.50** | -5.41 | +1.11 | 0.00% | 0.00% |
| JUPUSDT  | 2227 | -4.23 | -1.61 | 0.00 | **+0.50** | -10.15 | +0.50 | 0.00% | 0.00% |
| PYTHUSDT | 2227 | -3.23 | -1.01 | 0.31 | **+0.50** | -46.56 | +0.53 | 0.00% | 0.00% |

**Empirical reality**:
- B-side (+50 bp): **0/16 syms reach ≥ +50 bp at any time** (Binance regular tier funding rate hard caps at +0.01% = +1.00 bp; TON/JUP/PYTH special tier capped at +0.50 bp)
- A-side (-50 bp): only 3/16 syms reach (AXS 2.67% / COMP 0.45% / ICP 0.18%) — universally rare leverage liquidation episodes (AXS min -200 bp, COMP min -147 bp)
- **Symmetric ±50 bp trigger STRUCTURALLY INFEASIBLE on raw 8h-frame funding rate**

### STEP 2 — Lesson #28 substrate availability — PASS (CVD axis)

- OHLCV DB: `taker_buy_base_asset_volume` column **ABSENT** (only total `volume`)
- Microstructure joblib `runs/microstructure/{SYM}_full_metrics.joblib`:
  `taker_buy_sell_ratio` column, 5m frequency, span 2024-02-23 to 2026-05-02 (~800d)
- CVD ratio proxy via `(TBR - 1) / (TBR + 1)` per 5m, 4h aggregation = mean over 48 bars
- 13/13 cohort syms substrate present

**CVD axis feasible**; but R-0 halt at STEP 1 funding axis precludes joint test.

## Lesson #44 21st-amendment cross-reference

- **paradigm 22 funding-carry R-5 SEEDED** (HBAR/AXS/COMP): uses **per-sym z-score normalized funding**, NOT raw bp threshold. Exact reformulation guidance.
- **paradigm 72 taker_buy_volume_5m_zscore GRAVEYARD**: 5m taker volume z-score BROAD_FALSIFIED, family Tier 4 retire (Q3 §6.2 #10). paradigm 138 CVD axis = ratio (not volume magnitude) → DNA-distinct, but funding axis disqualifies before substrate question.
- **paradigm 73/96/97/98/99/103/132 funding family Tier 4 retire**: cumulative funding axis exhaustion; paradigm 22 (z-score) and paradigm 79 (ETC dispersion) sole exceptions.
- **paradigm 109+110 Lesson #40 dogfood CONFIRMED**: non-negative aggregate statistic + symmetric z≤-T structurally infeasible. **paradigm 138 raw ±50 bp on funding is IDENTICAL antipattern (3rd instance: 109 + 110 + 138)**. Funding rate hard-capped at +1 bp regular tier on the upside.
- **paradigm 137 Yang-Zhang efficiency ratio GRAVEYARD (2026-05-21 11:49 KST)**: 9-streak non-PASS predecessor; paradigm 138 was user-requested non-RV pivot to break streak. paradigm 138 halts at R-0 for orthogonal reason (funding raw threshold infeasibility, NOT vol family saturation).

## Lesson #40 3rd dogfood instance — sub-amendment elevation

paradigm 109 + 110 established Lesson #40 CONFIRMED via z-score on non-negative variance/RV.
**paradigm 138 extends Lesson #40 scope to bounded exchange-set rate parameters**:

- Funding rate is **asymmetric exchange-set bounded** (positive side hard-capped at +1 bp regular / +0.5 bp tier, negative side allowed to extreme during liquidation).
- Same Lesson #40 antipattern signature: "structural distribution shape precludes symmetric ±T trigger".
- Differs from 109+110 (non-negative aggregate) by being **asymmetrically bounded** (not non-negative; can go negative deeply, just cannot go positive far).

**Lesson #40 sub-amendment candidate (3rd dogfood)**: extend from "non-negative aggregate statistics" to "non-negative aggregate OR asymmetrically exchange-bounded scalars". R-0 prescreen STEP 1 already catches both via empirical p1/p99 measurement; no script change needed, only lesson text expansion.

## Reformulation paths offered to user (R-0 output)

1. **Path 1 (RECOMMENDED for redispatch)**: per-sym funding z-score (paradigm 22 R-5 approach) × CVD z-score. Lesson #21 2-axis admissible (paradigm 132 trap was 3-way). Must demonstrate individual-vs-joint sigex synthesis (Lesson #21 6th dogfood).
2. **Path 2**: cross-sectional funding percentile rank per-timestamp across 13 alts, bottom 10%.
3. **Path 3**: funding rate Δ ≥ X bp per-period (acceleration). Risk: paradigm 96 sign-flip graveyard.
4. **Path 4**: drop funding axis, CVD ratio 4h alone. Risk: paradigm 72 taker fee-floor inheritance (would need 4h frame to break 5m-bar constraint).

## Family-distinct conclusion

paradigm 138 attempted to introduce **NEW CVD axis** (4h cumulative volume delta ratio) confluence with funding. CVD axis genuinely novel vs paradigm 72/127/128 — but funding axis raw-bp threshold formulation is **Lesson #40 antipattern (3rd dogfood)** and Funding family Tier 4 retire applies regardless. The paradigm cannot proceed without funding axis reformulation.

## Verdict signature

- **Lesson #40 paradigm 109+110+138 = 3rd dogfood** (formal elevation sub-amendment candidate: asymmetrically exchange-bounded scalars subsumption)
- **Lesson #44 21st xref dogfood** completed (12 paradigms cross-referenced)
- **Funding family Tier 4 retire REAFFIRMED** (8 cumulative funding-axis variants graveyarded; only paradigm 22 + 79 R-5 exceptions stand)
- **Range estimator family dogfood count UNCHANGED** at 2 (paradigm 138 not vol/range family)

## Artifacts

- R-0 script: `backend/scripts/research/paradigm138_r0_prescreen.py`
- R-0 metrics: `backend/runs/research_track/alt_funding_rate_x_cvd_4h_divergence_smart_money_distribution_directional_4h/r0_prescreen.json`
- Graveyard report: this file
- Counter: 137 → **138**
- Streak: 9 → **10** (129-138 non-PASS)
- Lessons inventory: 33 confirmed + 6 candidates (Lesson #40 sub-amendment 3rd dogfood candidate added)

## Next-candidate recommendation

**Pivot away from funding axis raw-threshold formulations entirely** for 14-day cooldown (next eligible 2026-06-04). User-paths 1 (z-score reformulation) and 4 (CVD alone, 4h frame) remain admissible if user explicitly redispatches with reformulated trigger.

**Non-funding, non-RV, non-CVD pivot candidates** (avoid 10-streak axis):
- **Path A**: OI velocity sign-conditional on 4h frame (paradigm 71 was 240m hold; 4h × sign-conditioning candidate distinct)
- **Path B**: 1m volume burst directional CONTINUATION 4h (paradigm 127+128 R-5 are 30m/60m hold; 4h frame extension)
- **Path C**: cross-sectional momentum dispersion (per-timestamp rank × decay 4h)
- **Path D**: idle — Day 7 baseline 2026-05-28 D-7 priority (paper paradigm 127+128 baseline measurement)

**RECOMMENDED**: Path D (idle until Day 7 baseline measurement window). 10-streak axis saturation + funding family closed + RV family closed + frontier scout 5 consecutive halt/falsified = paradigm dispatch yield approaching zero. Day 7 baseline 2026-05-28 D-7 / D-Day 2026-06-03 D-13 priority window.
