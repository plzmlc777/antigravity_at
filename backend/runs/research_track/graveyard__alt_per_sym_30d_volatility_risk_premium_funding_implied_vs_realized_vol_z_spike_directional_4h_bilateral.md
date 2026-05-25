# Graveyard — paradigm 200 `alt_per_sym_30d_volatility_risk_premium_funding_implied_vs_realized_vol_z_spike_directional_4h_bilateral`

**Verdict**: `R0_HALT_LESSON_54_FAMILY_REDUCTION_PARADIGM135_REINFORCEMENT`
**Phase**: R-0 (prescreen halt — R-1 not dispatched)
**Executed at KST**: 2026-05-22T16:10:43+09:00
**Host**: hcp_local
**Counter**: 199 → 200 (200th paradigm milestone, **non-PASS continues**)

---

## Hypothesis (200th milestone)

Volatility Risk Premium (VRP) cross-substrate fusion axis — fresh entry attempt post-paradigm 199 R-0 HALT (semivariance DNA duplicate).

- **Statistic** (paradigm 200 formula):
  - `ann_funding_vol = abs(funding_rate) × 3 × 365 × 100` (unsigned, scaled to %)
  - `ann_realized_vol = sqrt(252) × daily_return_std × 100` (daily frame, scaled to %)
  - `VRP = ann_funding_vol − ann_realized_vol`
  - 90d rolling z-score on VRP, trigger `|z|≥2`
- **Universe**: 20 alts (paradigm 198 expanded cohort)
- **Direction**: bilateral 4-quadrant SNT (A focus / A mirror / B same-sign / B mirror)
- **Hold**: 4h primary + 8h/12h/24h sweep

---

## Lesson #61 slug grep audit — DUPLICATE DETECTED

`ls backend/runs/research_track/ | grep -iE "vrp|volatility_risk_premium|funding_implied_vol|implied_vs_realized|vol_premium|funding_vs_realized"`

- **paradigm 135 prior R-0 HALT**: `alt_funding_implied_vs_realized_vol_premium_z_directional_4h`
- **paradigm 135 verdict**: `R0_HALT_LESSON_54_MECHANISM_INCOHERENT_FUNDING_RV_FAMILY_REDUCTION`
- **Formula delta vs paradigm 135**:
  1. paradigm 200 `abs(funding_rate)` instead of signed — **resolves sign asymmetry trap** (paradigm 135 1st trap)
  2. paradigm 200 daily-frame RV (`sqrt(252)×daily_std×100`) instead of 1h-frame RV (`std(log_ret_1h)×sqrt(24×365)`)
  3. paradigm 200 z-window 90d instead of 30d
  4. paradigm 200 bilateral 4-quadrant SNT instead of signed direction (Lesson #19 compliant)

paradigm 200 was a genuine attempt to resolve paradigm 135's structural traps. The formula delta is non-trivial. R-0 prescreen executed empirically rather than slug-duplicate-halt.

**Lesson #61 dogfood 3rd consecutive post-confirmation**: paradigm 178/199 success → paradigm 200 success (grep caught duplicate, formula-delta verification proceeded).

---

## R-0 Prescreen Findings (paradigm 198 20-sym cohort, paradigm 200 formula)

### Step A — Substrate (Lesson #28) — PASS

- **20/21 syms** with funding + 4h OHLCV (funding 821d / ohlcv 819d each)
- **1 skip**: WIFUSDT (no funding rate in DB)
- Sample density per-sym: `821d × 3 funding cycles/day = ~2,463 funding events` × 20 syms = **~49,260 events** (paradigm 22/170 영구 자산)
- Substrate verdict: PASS (no Lesson #28 / #11 prescreen halt)

### Step B — Empirical magnitude comparison (Lesson #54 trap detection) — FAIL

**Per-sym `ann_funding_vol` vs `ann_realized_vol` magnitude (annualized %):**

| sym | fund p50 | fund p99 | rv p50 | rv p99 | ratio p50 | ratio p99 | regime |
|---|---|---|---|---|---|---|---|
| ADAUSDT | 10.95 | 65.47 | 65.51 | 239.70 | 0.167 | 0.273 | RV_DOMINATES |
| AVAXUSDT | 10.95 | 72.19 | 71.89 | 108.48 | 0.152 | 0.665 | RV_DOMINATES |
| BCHUSDT | 10.95 | 67.72 | 60.74 | 190.42 | 0.180 | 0.356 | RV_DOMINATES |
| BNBUSDT | 0.00 | 74.40 | 39.60 | 89.46 | 0.000 | 0.832 | RV_DOMINATES |
| BTCUSDT | 6.36 | 52.88 | 36.89 | 68.63 | 0.172 | 0.771 | RV_DOMINATES |
| DOGEUSDT | 8.61 | 68.20 | 73.55 | 143.29 | 0.117 | 0.476 | RV_DOMINATES |
| DOTUSDT | 10.95 | 80.65 | 65.63 | 127.53 | 0.167 | 0.632 | RV_DOMINATES |
| ETCUSDT | 10.95 | 67.07 | 61.63 | 103.79 | 0.178 | 0.646 | RV_DOMINATES |
| ETHUSDT | 6.96 | 53.47 | 55.64 | 84.39 | 0.125 | 0.634 | RV_DOMINATES |
| FILUSDT | 10.95 | 81.09 | 71.21 | 270.10 | 0.154 | 0.300 | RV_DOMINATES |
| JUPUSDT | 5.48 | 60.19 | 83.52 | 154.60 | 0.066 | 0.389 | RV_DOMINATES |
| LDOUSDT | 10.95 | 87.43 | 93.07 | 140.29 | 0.118 | 0.623 | RV_DOMINATES |
| LINKUSDT | 10.95 | 64.64 | 66.92 | 146.46 | 0.164 | 0.441 | RV_DOMINATES |
| LTCUSDT | 9.00 | 68.39 | 56.53 | 108.66 | 0.159 | 0.629 | RV_DOMINATES |
| NEARUSDT | 10.95 | 76.16 | 80.80 | 184.38 | 0.136 | 0.413 | RV_DOMINATES |
| PYTHUSDT | 5.48 | 71.10 | 85.46 | 305.75 | 0.064 | 0.233 | RV_DOMINATES |
| SOLUSDT | 8.11 | 75.97 | 64.57 | 122.41 | 0.126 | 0.621 | RV_DOMINATES |
| UNIUSDT | 10.76 | 57.73 | 82.68 | 178.64 | 0.130 | 0.323 | RV_DOMINATES |
| WLDUSDT | 10.95 | 112.74 | 99.68 | 236.11 | 0.110 | 0.477 | RV_DOMINATES |
| XRPUSDT | 9.58 | 67.69 | 60.00 | 138.85 | 0.160 | 0.488 | RV_DOMINATES |

- **RV_DOMINATES: 20/20 syms (100%)**. `ratio p50 < 0.20` universally — `ann_funding_vol` is at ~10% of `ann_realized_vol` typically.
- **FUNDING_DOMINATES: 0/20 syms**.
- **MIXED_REGIME: 0/20 syms**.

**Comparison vs paradigm 135** (13-sym cohort, 1h-frame RV):
| Regime | paradigm 135 (13 syms, 1h RV) | paradigm 200 (20 syms, daily RV) |
|---|---|---|
| FUNDING_EXTREME_TAIL | 2/13 (15%) | 0/20 (0%) |
| RV_DOMINATES | 11/13 (85%) | 20/20 (100%) |
| MIXED | 0/13 (0%) | 0/20 (0%) |

paradigm 200's daily-frame RV (vs 1h-frame) is **more conservative** but the magnitude gap widens — funding rates are intrinsically small (typically 0.01%/8h = 10.95%/yr) regardless of RV measurement frame. The `abs()` removed sign asymmetry but the **scale mismatch is the structural trap** — and it is **invariant to frame choice**.

### Step C — Lesson #54 family-reduction trap CONFIRMED

| Trap | Empirical | Trigger threshold | Result |
|---|---|---|---|
| Sign asymmetry | abs() applied — N/A | >30% (signed) | **AUTO_RESOLVED** by abs() |
| Family reduction | (funding-dominates + rv-dominates) / total = 20/20 = **1.00** | ≥0.70 | **TRIGGERED** |

**Mechanism story collapse** (paradigm 200 specific):
1. `ann_funding_vol = abs(funding_rate) × 109500` is by construction non-negative (sign trap auto-resolved). However the magnitude is structurally bounded — typical funding rate is 0.01%/8h, producing `ann_funding_vol ~ 11%/yr`. Tail funding events (0.05-0.10%/8h) produce `ann_funding_vol ~ 55-110%/yr`.
2. `ann_realized_vol = sqrt(252) × daily_std × 100` for crypto alts is typically **60-100%/yr** at p50 and **100-300%/yr** at p99. Funding magnitude is roughly **10x smaller** than RV at typical levels and **2-4x smaller** even at tail.
3. **VRP ≈ −ann_realized_vol** for 20/20 syms in the cohort (`|ann_funding| << ann_realized_vol`). Therefore `z(VRP) ≈ −z(RV)`.
4. Trigger `z(VRP) > +2` ≡ `z(RV) < −2` = **low realized vol regime** = RV family signal (paradigm 67-69/118/124/125/129/133/134 — all graveyarded except paradigm 69 R-5 seed).
5. Trigger `z(VRP) < −2` ≡ `z(RV) > +2` = **high realized vol regime** = RV family signal too. paradigm 69 R-5 seeded covers BTC high-vol regime LONG.
6. **paradigm 200 reduces to TWO existing RV family hypotheses**: (a) low-RV regime directional trade (= paradigm 67/68 mirror, both graveyarded), (b) high-RV regime directional trade (= paradigm 69 R-5 seeded, exception).

The bilateral 4-quadrant SNT does NOT save the paradigm — it merely cells the search across (RV-low-regime, bar-UP, LONG) / (RV-low-regime, bar-UP, SHORT) / (RV-low-regime, bar-DOWN, SHORT) / (RV-low-regime, bar-DOWN, LONG). All four are RV family sub-paradigms attempted across paradigm 67-69 + 134 history (none directional-bilateral at 4h alt frame, but all converged BROAD_FALSIFIED or NARROW_SCOPE).

### Step D — Lesson #44 family-distinct reconciliation — FAIL

- **RV family collision**: 20/20 syms in RV_DOMINATES regime. RV family Tier 4 retire (paradigm 67/68/118/124/125/129/133/134 all graveyarded except paradigm 69 R-5 exception).
- **Funding family collision**: 0/20 syms in FUNDING_DOMINATES regime (paradigm 200 abs() formula + daily RV breakdown means funding magnitude is uniformly subordinate).
- **Family-distinct claim**: **FAIL** — paradigm 200 reduces to RV family signal across 100% of cohort.

paradigm 200's dispatch claim "cross-substrate fusion axis (funding × RV)" is empirically refuted — the subtraction is dominated by the RV term across the entire cohort, making it RV family in disguise.

### Step E — Final R-0 verdict

`R0_HALT_LESSON_54_FAMILY_REDUCTION_PARADIGM135_REINFORCEMENT`

---

## Lesson #54 elevation — 3rd dogfood (formal confirmed strengthening)

Lesson #54 was formally CONFIRMED at paradigm 135 R-0 HALT (2 dogfoods accumulated: paradigm 134 + 135). paradigm 200 = **3rd dogfood**.

- **1st dogfood**: paradigm 134 (signed semivariance ratio) — BROAD_FALSIFIED uniform absence.
- **2nd dogfood**: paradigm 135 (signed funding × 1095 vs 1h RV) — R-0 trap confirmed.
- **3rd dogfood**: paradigm 200 (abs(funding) × 109500 vs daily RV) — R-0 trap confirmed **despite abs() resolution attempt**.

**Key strengthening**: Lesson #54 is **invariant to formula refinements** of the same composite class (subtraction/ratio of two underlying signals from different family domains). The structural trap is **magnitude scale mismatch**, not sign asymmetry. abs() resolves sign asymmetry but **does not synthesize alpha** when one term dominates.

**Lesson #54 amendment (paradigm 200)**:
> "Derived composite of two underlying signals (funding × RV, OI × volume, etc.) must pass empirical magnitude-comparability prescreen on the **target universe** before R-1 dispatch. abs()/unsigned reformulation does NOT resolve family-reduction trap. Magnitude scale mismatch (one term <0.20 × other term at typical p50) reduces composite to single-family signal regardless of formula details."

---

## Lesson #61 amendment 3rd consecutive post-confirmation success

- paradigm 178 (2026-05-21): slug grep caught duplicate ✓
- paradigm 199 (2026-05-22): slug grep caught duplicate ✓
- paradigm 200 (2026-05-22): slug grep caught duplicate ✓ + empirical formula-delta verification proceeded
- **Lesson #61 now 3 consecutive post-confirmation successes** — workflow integration validated.

---

## paradigm 195/196/197/198 cross-class universe-level concentration limit verdict — N/A

paradigm 200 R-0 HALT before R-1 dispatch. The hypothesized 5th-statistic-class cross-class direct comparison (HYPOTHESIS X 5-class universal vs HYPOTHESIS Y cross-substrate breaks limit) **cannot be tested** because the cross-substrate fusion claim is empirically refuted at R-0 (the "fusion" reduces to RV family in 20/20 cohort).

**HYPOTHESIS X / Y verdict**: **UNTESTABLE_PARADIGM_REDUCED_TO_RV_FAMILY_AT_R0**. Cross-class universe-level concentration limit remains a 4-statistic-class hypothesis (paradigm 195/196/197/198), not 5-class.

The genuine 5th-class candidate would require a composite where **both terms have comparable magnitude** on the target universe — paradigm 200 fails that precondition empirically.

---

## Lesson #42 B mirror 11th dogfood — N/A

paradigm 200 R-0 HALT before R-1 dispatch. The post-SATURATED 11th dogfood of Lesson #42 (paradigm 117/158/162/179/193/194/195/196/197/198 chain 10/10 SATURATED) **cannot be tested** at this paradigm. Defer to next paradigm 201 candidate where R-1 dispatch actually fires.

---

## Family verdicts (Tier 4 retire status delta)

- **Funding family Tier 4 retire**: UNCHANGED (paradigm 22 R-5 exception only). paradigm 200 is not a funding family sub-paradigm — it's an RV family sub-paradigm in disguise.
- **RV family**: UNCHANGED (paradigm 69 R-5 exception only). paradigm 200 is the 10th attempt at RV family entry that converged to family-reduction trap (paradigm 67/68 graveyard / paradigm 69 R-5 / paradigm 118/124/125/129/133/134 graveyard / paradigm 135 R-0 HALT / paradigm 200 R-0 HALT).
- **Cross-substrate fusion family** (NEW class attempt): **0/2 successful** (paradigm 135 + paradigm 200 both R-0 HALT). **Family-distinct path 3rd attempt**: any future cross-substrate fusion candidate must pass empirical magnitude-comparability prescreen on the **20-sym paradigm 198 cohort** with explicit `ratio_p50 ≥ 0.30` per-sym requirement before R-1 dispatch is considered.

---

## Sparse-strict life-changing 4-dim audit — N/A

paradigm 200 R-0 HALT before R-1 dispatch. 4-dim freq gate (trades/yr ≥ 12, edge ≥ +2%/trade, capital util ≥ 30%, sharpe ≥ 1.5) cannot be computed without trade-level metrics. Defer.

---

## Campaign State (post-paradigm 200, 200th milestone)

- **Cumulative graveyards**: **200** (200th milestone non-PASS continues)
- **R-5 seeded LIVE**: 10 unchanged
- **R-5 yield**: **5.00%** (10/200) — declining from earlier 7.41% (paradigm 135 era)
- **Non-PASS streak**: continuing from paradigm 199 chain
- **Lessons**: 33 confirmed + Lesson #54 3rd-dogfood strengthening
- **D-Day 2026-06-03 D-12 / paradigm 127+128 Day 7 baseline 2026-05-28 D-6**

---

## Artifacts

- R-0 prescreen script: `backend/scripts/research/paradigm200_r0_prescreen.py`
- R-0 metrics: `backend/runs/research_track/alt_per_sym_30d_volatility_risk_premium_funding_implied_vs_realized_vol_z_spike_directional_4h_bilateral/r0_prescreen.json`
- Graveyard (this file): `backend/runs/research_track/graveyard__alt_per_sym_30d_volatility_risk_premium_funding_implied_vs_realized_vol_z_spike_directional_4h_bilateral.md`
- R-1: **NOT DISPATCHED** (R-0 prescreen halt)

---

## Path Forward — paradigm 201 next-action recommendation

Continuing continuous-parallel policy ([feedback-paradigm-campaign-continuous-parallel] 2026-05-19 + [feedback-persistence-over-efficiency] 2026-05-21).

**Recommended paradigm 201 candidate axes** (avoiding cross-substrate fusion family-reduction trap):

1. **Single-substrate intraday microburst** (paradigm 134 §6.31 Rank 2 — still pending dispatch as of paradigm 135 graveyard recommendation): `alt_intraday_1h_log_return_std_24h_window_z_directional_4h`. 1st-order intraday vol stat, 24h rolling std of 1h log-returns, z>+2 trigger, 4h hold, single-substrate (NO funding dependency, NO RV decomposition). 1h frame is the gap (paradigm 67-69 used 1d frame). Family-distinct vs paradigm 69 by frame.

2. **Cross-substrate fusion with magnitude-comparability prescreen passed**: candidates would need substrates where both terms have comparable magnitude bands per-sym (e.g., OI × volume at 5m frame both in event-z space — paradigm 132 already tested OI × funding × magnitude triple at Lesson #21 axis-stacking, graveyard).

3. **Pure event-anchored single-substrate**: liquidation cascade, listing/delisting calendar events, USDS perpetual onboard cycle. These avoid the family-reduction trap by design (single domain, single statistic).

**Strong recommendation**: Path 1 (paradigm 134 §6.31 Rank 2 candidate `alt_intraday_1h_log_return_std_24h_window_z_directional_4h`). Pending since paradigm 135 graveyard recommendation, 65+ paradigms since first deferred. Single-substrate, single-axis, Lesson #21 compliant, Lesson #54 immune (no derived composite), substrate cache available (1m OHLCV joblib), no funding DB dependency.

---

## INDEX.json update

paradigm 200 R-0 HALT registered. Counter advances 199→200 (200th paradigm milestone).
