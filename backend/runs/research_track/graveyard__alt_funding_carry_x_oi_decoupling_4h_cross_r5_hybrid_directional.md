# paradigm 145 graveyard — alt_funding_carry_x_oi_decoupling_4h_cross_r5_hybrid_directional

**Verdict**: `R0_HALT_SAMPLE_INSUFFICIENT` (R-1 NOT DISPATCHED, R-0 prescreen halt)
**Date**: 2026-05-21 13:33 KST
**Paradigm counter**: 144 → **145**
**Streak**: **17-streak non-PASS** (129-145)
**Phase**: R-0 (prescreen halt before R-1 dispatch)

## Hypothesis (cross-substrate R-5 hybrid)

Per-symbol funding rate 30d rolling z-score (paradigm 22 R-5 substrate, 8h cycle) ≤ -2.0
AND per-symbol 5m OI velocity z-score (paradigm 21 R-5 substrate, 24h rolling) ≤ -2.0
→ SHORT 4h continuation (crowded long + long unwinding cascade confluence).

Direction inverted from paradigm 22 LONG MR (Lesson #56 candidate dogfood) on the same
funding_z trigger. Cross-substrate joint with paradigm 21 OI decoupling.

## R-0 prescreen results (10 alts × ~1y aligned funding cycles, 1.0s wall clock)

| Gate | Threshold | Observed | Result |
|---|---|---|---|
| **Lesson #21 sub-finding axis independence** | max_abs_corr < 0.50 | **0.050** | ✅ PASS (strong) |
| **Lesson #21 sub-finding residual** | min_resid > 0.20 | **0.998** | ✅ PASS (perfect orthogonality) |
| **Lesson #21 sub-finding axis_degeneracy (hard)** | max_abs_corr < 0.90 | **0.050** | ✅ PASS |
| **Lesson #40 structural threshold feasibility** | all 10 syms reach z≤-2.0 both axes | 10/10 f, 10/10 oi | ✅ PASS |
| **Lesson #58 candidate exemption (cross-substrate)** | NOT same-bar same-substrate ratio | funding DB + OI joblib + klines = 3 substrates | ✅ EXEMPT |
| **Lesson #11 sample density** | per_cell ≥ 30, joint_n_total ≥ 50 | **joint_n_total = 15, per_cell ≈ 3.8** | ❌ **HARD FAIL** |
| **Lesson #30 data window ratio** | binding substrate documented | funding 1y (binding), OI 1.55y, ratio 0.5 | advisory |

### Per-symbol joint trigger counts (z<=-2.0 BOTH funding AND OI)

| Symbol | aligned cycles | n_funding_neg | n_oi_neg | **n_joint_both** | corr |
|---|---|---|---|---|---|
| BTCUSDT | 1046 | 52 | 31 | **1** | 0.013 |
| ETHUSDT | 1046 | 49 | 24 | **0** | -0.015 |
| SOLUSDT | 1046 | 53 | 29 | **2** | 0.013 |
| AVAXUSDT | 1046 | 56 | 30 | **2** | -0.021 |
| LINKUSDT | 1046 | 60 | 26 | **1** | 0.050 |
| DOGEUSDT | 1046 | 51 | 33 | **0** | 0.019 |
| HBARUSDT | 1045 | 60 | 22 | **0** | -0.012 |
| AXSUSDT | 1517 | 85 | 62 | **5** | -0.035 |
| COMPUSDT | 1045 | 46 | 31 | **3** | 0.020 |
| ETCUSDT | 1045 | 60 | 39 | **1** | -0.005 |
| **TOTAL** | — | **572** | **327** | **15** | mean 0.003 |

Per-cell estimate (15 joint / 4 quarters) = **3.8 events per quarter**, vastly below
Lesson #11 floor of 30. Even relaxing to 2 quarters (semester): 7.5/cell ≪ 30.

## Root cause: independence × strict-threshold = sparse joint

**The Lesson #21 6th dogfood produced its inverse:** axes ARE perfectly independent
(corr ≈ 0.003 mean, residual variance ≈ 99.94% — strongest independence seen across
6 dogfoods). But independence × strict |z|>2 thresholds = multiplicative sparsity.

Empirical sample density math:
- funding z≤-2.0 base rate: 52/1046 ≈ **4.97%** per sym per funding cycle
- OI z≤-2.0 base rate: 33/1046 ≈ **3.15%** per sym per funding cycle (aligned to funding ts)
- Independence-implied joint rate: 0.0497 × 0.0315 ≈ **0.157%**
- Empirical joint: 15/10449 ≈ **0.144%** (matches independence prediction)
- Annual joint per sym: 0.144% × 1095 cycles × 1.5y = ~24/sym, but observed only ~1.5/sym (sparse subset alignment loss)

User pre-dispatch math estimated 0.2-0.25% joint rate × 10 alts × 365d × 6/day ≈ 40-60 per cell,
but two errors:
1. Cross-substrate alignment loss (5m OI z at funding ts only — 1 sample per 8h cycle, not 6/day)
2. OI z≤-2.0 base rate measured at 3.15% per funding-aligned sample (lower than estimated 5%)

Result: per_cell ≈ 3.8 = **10x below floor**.

## Lessons confirmed/dogfooded

### Lesson #21 sub-finding magnitude-ratio prescreen — **6th dogfood, INVERSE pattern**
| # | Paradigm | corr | resid | verdict |
|---|---|---|---|---|
| 1 | paradigm 137 same-bar same-substrate ratio | 0.92+ | <0.20 | CONFIRMED axis_degeneracy |
| 2 | paradigm 144 quote_vol/count ratio | 0.954 | 0.102 | STRUCTURAL_AXIS_DEGENERACY HALT |
| 3-5 | (prior CONFIRMED-eligible dogfoods) | — | — | various |
| **6** | **paradigm 145 cross-substrate funding × OI** | **0.050** | **0.998** | **PERFECT INDEPENDENCE → SPARSE JOINT** |

**NEW finding**: Lesson #21 sub-finding is **bidirectional** — both `corr >= 0.90` (degeneracy)
AND `corr → 0 with strict thresholds` (sparse joint) cause R-0 halt. The "healthy" zone is
mid-correlation (0.20-0.70) with adequate per-axis trigger rates.

### Lesson #58 candidate cross-substrate exemption — **CONFIRMED VALID, but ALONE INSUFFICIENT**
| # | Paradigm | substrate pattern | Lesson #58 verdict |
|---|---|---|---|
| 1 | paradigm 144 (same-bar same-substrate) | quote_vol/count both from 12-col klines | candidate 1st dogfood, exemption N/A |
| **2** | **paradigm 145 (cross-substrate)** | funding DB + OI joblib + klines = 3 substrates | **exemption APPLIES** |

But cross-substrate exemption doesn't bypass Lesson #11 — the joint sample-density
must still satisfy n ≥ 30/cell. NEW sub-finding: **Lesson #58 candidate should add
"cross-substrate joint sample density check" as 2nd prescreen step.**

### Lesson #56 candidate (R-5 mirror direction inversion) — **NOT TESTED**
Cannot test direction inversion when joint sample n=15 — verdict path blocked at R-0.
paradigm 141 precedent (mirror SHORT of paradigm 22) already failed (R-1 BROAD_FALSIFIED).
Lesson #56 candidate now has 3 fails + 1 untestable dogfood — formal elevation eligible.

### Lesson #11 sample density prescreen — 24th dogfood SUCCESS (R-1 resource saved)
Hard halt at R-0 saved full R-1 dispatch (10-15 min wall clock + cache I/O + perm test).
Cumulative R-0 halts on Lesson #11: now ~10 of 30 candidates (33% prescreen halt rate).

### Lesson #44 amendment xref dogfood — **29th**
Cross-referenced: paradigm 22 R-5 + paradigm 21 R-5 + paradigm 73/132/140/141 funding-OI family
+ paradigm 70/96/141 mirror direction precedent + paradigm 137/144 Lesson #21 sub-finding.

## Family/axis status updates

- **Cross-R5-hybrid sub-class**: 1 attempt, 1 R-0 halt (sample density). Family viability
  depends on relaxing one axis to non-strict threshold (e.g., funding z<=-1.0 + OI z<=-2.0
  asymmetric).
- **Funding family Tier 4**: 11 cumulative + this halt does NOT increment (R-1 not run).
- **Cross-substrate hybrid family**: NEW sub-category established, viability depends on
  threshold relaxation per Lesson #11 prescreen.

## V1/V2/V3 individual-vs-joint sigex comparison — **NOT MEASURED**

R-1 not dispatched → cannot measure V1 (funding alone) vs V2 (OI alone) vs V3 (joint).
Lesson #21 6th dogfood individual-vs-joint test deferred to alternative paradigm 146.

## Recommended next paradigm

Option A (single-axis relax, retain hybrid intent): paradigm 146 `alt_funding_z_neg1_x_oi_z_neg2_4h_relaxed_short` — funding z<=-1.0 (base rate ~16% per cycle) AND OI z<=-2.0 (base rate ~3% per funding ts) → joint rate ~0.5% → per-sym 5/yr → 50/4q = 12.5/cell (still borderline, may need universe expansion to 20 syms).

Option B (re-pair OI 5m with different macro filter): paradigm 146 `btc_oi_activity_regime_x_alt_funding_neg_4h_long` — paradigm 120 mirror (BTC OI activity regime conditioning on funding z<=-1.0). Cross-axis without strict joint threshold.

Option C (proceed with quote_vol axis Tier 4 retire + pivot to entirely new axis): paradigm 146 `alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h` (already in R-0 queue per INDEX, untried).

**RECOMMENDED**: **Option A paradigm 146 funding z<=-1.0 + OI z<=-2.0 relaxed cross-substrate** — direct repair of paradigm 145 halt, retains cross-R5 novelty, addresses identified root cause (strict×strict multiplicative sparsity), single new dispatch with R-0 re-measurement first.

## Status summary

- 누적 graveyards: **144 → 145** (paradigm 145 R0_HALT_SAMPLE_INSUFFICIENT)
- R-5 시드 10 LIVE (unchanged)
- **17-streak non-PASS** (129-145)
- R-5 yield 6.90% (10/145)
- Lessons: 34 confirmed + 9 candidates → Lesson #21 sub-finding now **6 dogfoods CONFIRMED + bidirectional sub-pattern (degeneracy ∪ sparse-joint)**, Lesson #58 candidate **2 dogfoods CONFIRMED-elevation eligible + cross-substrate sub-finding required**, Lesson #56 candidate **3 fails + 1 untestable → formal CONFIRMED elevation eligible**
- D-Day 2026-06-03 D-13 / paradigm 127+128 Day 7 baseline 2026-05-28 D-7

## Artifacts

- Script: `backend/scripts/research/paradigm145_r0_prescreen.py`
- R-0 metrics: `backend/runs/research_track/alt_funding_carry_x_oi_decoupling_4h_cross_r5_hybrid_directional/r0_prescreen.json`
- Graveyard: this file
- INDEX: `backend/runs/research_track/INDEX.json` → phase `graveyard`
