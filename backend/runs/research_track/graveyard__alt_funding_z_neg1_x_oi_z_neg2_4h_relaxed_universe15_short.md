# Graveyard: paradigm 146 alt_funding_z_neg1_x_oi_z_neg2_4h_relaxed_universe15_short

**Verdict**: R0_HALT_SAMPLE_INSUFFICIENT (relaxed-repair attempt)
**Phase**: R-0 (R-1 dispatch 미실행)
**Date**: 2026-05-21 13:41 KST
**Parent paradigm**: 145 (cross-R5 hybrid strict, joint_n=15)
**Repair strategy**: funding_z -2.0 → -1.0 + universe 10 → 15 (AAVE excluded — funding DB 없음)
**Cumulative graveyards**: 146
**Streak non-PASS**: 18 (129-146)

## Mechanism

- Axis 1 (funding RELAXED): per-symbol funding rate 30d rolling z ≤ **-1.0** (paradigm 145: -2.0)
- Axis 2 (OI strict): 5m OI velocity z ≤ -2.0 (paradigm 21 R-5 alignment)
- Joint trigger: funding_z ≤ -1.0 AND oi_velocity_z ≤ -2.0
- Direction: SHORT 4h continuation (paradigm 22 R-5 mirror direction — Lesson #56 candidate 5th dogfood opportunity)
- Universe: 15 syms (paradigm 145 base 10 + ICP/UNI/LDO/WLD/1000LUNC)

## R-0 Prescreen Result

| Gate | Value | Threshold | Verdict |
|---|---|---|---|
| Lesson #11 sample density (joint_n_total) | **87** | ≥ 50 | PASS |
| Lesson #11 sample density (per_cell ≈ joint/4q) | **21.8** | ≥ 30 | **FAIL** |
| Lesson #21 sub-finding axis independence (max_abs_corr) | 0.050 | < 0.5 | PASS |
| Lesson #21 sub-finding residual fraction (min_resid) | 0.998 | > 0.2 | PASS |
| Lesson #40 structural threshold reachability | 15/15 funding + 15/15 OI | all syms | PASS |
| Lesson #58 candidate cross-substrate exemption | 3 substrates (funding DB + OI joblib + klines) | n/a | EXEMPT |
| Lesson #30 data window ratio | funding 365d / OI 730d = 0.50 | advisory | binding=funding |

## Diagnosis (paradigm 145 대비 개선)

| Metric | paradigm 145 (strict) | paradigm 146 (relaxed) | 회복 배율 |
|---|---|---|---|
| joint_n_total | 15 | 87 | **5.8x** |
| per_cell estimate | 3.75 | 21.8 | **5.8x** |
| funding_z<= threshold base rate | 4.5% (z<=-2) | 16-19% (z<=-1) | ~4x |
| OI z<= threshold base rate | 3% (unchanged) | 3% (unchanged) | 1x |
| universe size | 10 | 15 | 1.5x |
| proposal estimation accuracy | n/a (10x error) | 21.8 actual vs 25 expected = 12.8% error | major improvement |

**Result**: Lesson #11 per_cell cutoff 30 still missed by ~27%, despite 5.8x recovery from paradigm 145.

## Estimation Accuracy Validation (proposal 자기 진단)

- Proposal expected: **~100/yr ≈ ~25/cell borderline-PASS**
- Actual measured: joint_n_total=87 → per_cell=21.8
- Error: −12.8% (proposal 25 vs actual 21.8)
- **Lesson #11 prescreen calculation 자체는 정확** — paradigm 145의 10x estimation error 회피 성공
- Borderline 진단 (proposal "borderline-PASS") 자체가 맞았으나 cutoff side에 떨어짐

## Per-Symbol Joint Lift (axis multiplicative behavior)

- Mean joint lift vs independence baseline ≈ 1.0-1.5x (대부분)
- Lift > 1.0 (positive synthesis): BTC 1.16, SOL 1.23, DOGE 1.18, AXS 1.05, COMP 1.98, ETC 1.20, ICP 1.34, WLD 1.24, 1000LUNC 1.48 (9/15)
- Lift < 1.0 (slight anti-synthesis): ETH 0.21, AVAX 0.79, HBAR 0.85, UNI 0.58, LDO 0.72 (5/15)
- LINK 1.14 borderline (1/15)
- **Interpretation**: axes are largely independent at threshold-cell counts, no degeneracy (Lesson #21 independence confirmed) — but no strong joint amplification either

## Lessons Applied & Outcomes

| Lesson | Application | Outcome |
|---|---|---|
| Lesson #11 sample density | per_cell cutoff 30 strict enforcement | **FAIL by 27% margin (21.8 < 30)** |
| Lesson #21 sub-finding independence | cross-substrate corr/resid measurement | PASS (max_corr=0.050) |
| Lesson #40 structural threshold | per-sym z_min reachability | PASS (15/15 both axes) |
| Lesson #58 candidate cross-substrate exemption | 3 substrates exempt from same-bar antipattern | EXEMPT |
| Lesson #30 data window ratio | funding 1y binding (advisory) | applied |
| Lesson #56 candidate (R-5 mirror direction) | 5th dogfood prep (paradigm 22 LONG MR → SHORT continuation) | **NOT TESTED (R-0 halt before R-1)** |
| Lesson #21 sub-finding V1/V2/V3 (6th dogfood) | individual-vs-joint sigex measurement | **NOT TESTED (R-0 halt before R-1)** |
| Lesson #46 REFINEMENT + sub-amendment | stratified 50×4q + sign-flip WARNING | not reached |

## Next Action Recommendation

**Path 1 (further relaxation, not recommended)**: funding_z -1.0 → -0.5 + OI_z -2.0 → -1.5
- Expected per_cell ~50-60 borderline PASS
- **But statistical signal degraded**: z=-0.5 is ~30% base rate, mechanism loses "tail event" semantics
- Mechanism risk: paradigm 22/21 R-5 strict at z<=-2.0 — relaxed thresholds may not preserve LONG MR behavior, mirror direction inversion (Lesson #56) test loses meaning
- **NOT RECOMMENDED** (mechanism dilution worse than sparse halt)

**Path 2 (universe further expansion, blocked)**: AAVE/BNB/MATIC/ADA/XRP/LTC/BCH funding DB unavailable
- 9 candidate symbols 0 funding rows in `binance_funding_rate` table
- Funding backfill > 30min ETA per [[architect spec halt condition]]
- **BLOCKED until funding DB backfill** (separate infra task)

**Path 3 (CONFIRMED PROMOTION)**: funding-OI joint family axis-cross direction graveyard 누적
- paradigm 145 strict (n=15) + 146 relaxed (n=87, per_cell 21.8) 모두 Lesson #11 막힘
- **funding × OI joint axis-cross 1y substrate window 본질 한계** — 추가 axis cross 시도 권장 안 함
- Funding 1y DB 백필 후 (≥2.5y) 재시도 권장 (지금은 차단)

**Path 4 (Lesson #56 candidate 4 instances 유지)**: 5th dogfood 미실현 (R-0 halt before R-1)
- Lesson #56 candidate 여전히 4 instances (formal CONFIRMED 자격 4 dogfoods)
- 다른 R-5 mirror direction 시도 (paradigm 21 single-axis mirror, paradigm 24 premium mirror)로 5th dogfood 별도 추구

**Path 5 (RECOMMENDED — next candidate)**: paradigm 22/21 mirror direction이 아닌 substrate-distinct axis 발의
- Cross-exchange OI imbalance (Bybit V5 substrate 영구 자산 활용, paradigm 103 graveyard 이후 sub-class 잔여)
- Per-symbol funding velocity sign-flip event × OI direction strict (paradigm 79 sign-flip + paradigm 21 OI 강화)
- 5m premium z × OI level joint (paradigm 80+82 advisory caution family 잔여 sub-class)

## Counter Update

- Cumulative graveyards: 145 → **146**
- R-5 LIVE: 10 (paradigm 127+128 Mint deploy unchanged)
- Streak non-PASS: 17 → **18** (129-146)
- R-5 yield: 10/146 = **6.85%** (6.90% → 6.85%, -5bp)
- Funding-OI joint family Tier 4 retire 강화 (145 strict + 146 relaxed 누적, **funding 1y DB binding 본질 한계 확인**)

## Artifacts

- code: `backend/scripts/research/paradigm146_r0_prescreen.py`
- r0_prescreen: `backend/runs/research_track/alt_funding_z_neg1_x_oi_z_neg2_4h_relaxed_universe15_short/r0_prescreen.json`
- graveyard: `backend/runs/research_track/graveyard__alt_funding_z_neg1_x_oi_z_neg2_4h_relaxed_universe15_short.md`
