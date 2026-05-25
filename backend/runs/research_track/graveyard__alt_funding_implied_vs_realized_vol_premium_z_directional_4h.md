# Graveyard — paradigm 135 `alt_funding_implied_vs_realized_vol_premium_z_directional_4h`

**Verdict**: `R0_HALT_LESSON_54_MECHANISM_INCOHERENT_FUNDING_RV_FAMILY_REDUCTION`
**Phase**: R-0 (prescreen halt — R-1 not dispatched)
**Executed at KST**: 2026-05-21 11:20:42
**Host**: hcp_local
**Counter**: 134 → 135 (7-streak non-PASS: 129/130/131/132/133/134/135)

---

## Hypothesis

**Volatility Risk Premium (VRP), NEW family entry attempt**:
- Statistic: `VRP = funding_implied_vol - realized_vol`
  - `funding_implied_vol = funding_rate × 1095` (8h cycle × 3/day × 365 = annualized scaling)
  - `realized_vol = log_return_1h.std() × sqrt(24×365)` (annualized 30d rolling RV)
- Per-sym 30d rolling z-score on VRP
- Trigger: `|VRP_z| > 2`
- Direction: `VRP_z > +2` (implied >> realized "fear premium") → LONG; `VRP_z < -2` (complacency) → SHORT
- 4h forward hold, 8h debounce
- Universe: 13 funding-DB alts (paradigm 132 cohort: AVAX/AXS/COMP/DOGE/ETC/HBAR/ICP/LDO/LINK/SOL/UNI/WLD/1000LUNC)

---

## R-0 Prescreen Findings (empirical, R-1 not dispatched)

### Step A — Substrate (Lesson #28) — PASS
- 13/13 cohort syms with funding rate (~364-372d) and 1m OHLCV resampled to 1h (~755-799d)
- Funding window is binding (~370d for all alts)

### Step B — Empirical Magnitude (Lesson #54 candidate trap detection) — FAIL

**Per-sym `funding_implied_vol` vs `realized_vol` magnitude (annualized):**

| sym | implied \|abs\| p50 | implied \|abs\| p99 | rv p50 | rv p99 | ratio p50 | regime |
|---|---|---|---|---|---|---|
| AVAXUSDT | 0.0994 | 0.4364 | 0.8645 | 1.6496 | 0.115 | **RV_DOMINATES** |
| AXSUSDT | 0.1387 | 7.4801 | 0.9230 | 2.1834 | 0.150 | **FUNDING_EXTREME_TAIL** |
| COMPUSDT | 0.1095 | 3.7138 | 0.8948 | 1.7565 | 0.122 | **FUNDING_EXTREME_TAIL** |
| DOGEUSDT | 0.0705 | 0.1535 | 0.9014 | 2.1157 | 0.078 | RV_DOMINATES |
| ETCUSDT | 0.0958 | 0.2725 | 0.7592 | 1.3649 | 0.126 | RV_DOMINATES |
| HBARUSDT | 0.0824 | 0.2983 | 0.8772 | 2.4448 | 0.094 | RV_DOMINATES |
| ICPUSDT | 0.1058 | 1.1848 | 0.9300 | 2.1412 | 0.114 | RV_DOMINATES |
| LDOUSDT | 0.0686 | 0.1476 | 1.1238 | 1.6929 | 0.061 | RV_DOMINATES |
| LINKUSDT | 0.0825 | 0.1876 | 0.8517 | 1.5233 | 0.097 | RV_DOMINATES |
| SOLUSDT | 0.0698 | 0.5092 | 0.8136 | 1.3505 | 0.086 | RV_DOMINATES |
| UNIUSDT | 0.0841 | 0.1667 | 1.0010 | 2.5109 | 0.084 | RV_DOMINATES |
| WLDUSDT | 0.1095 | 0.9052 | 1.2283 | 2.0942 | 0.089 | RV_DOMINATES |
| 1000LUNCUSDT | 0.1095 | 0.9785 | 0.9085 | 2.1793 | 0.121 | RV_DOMINATES |

- **RV_DOMINATES**: 11/13 syms (`AVAX, DOGE, ETC, HBAR, ICP, LDO, LINK, SOL, UNI, WLD, 1000LUNC`). `implied/rv p50 < 0.20` — VRP ≈ −RV, paradigm reduces to RV-family signal.
- **FUNDING_EXTREME_TAIL**: 2/13 syms (`AXS, COMP`). Tail-event regime where funding spike dominates VRP — paradigm reduces to funding-family signal.
- **0/13 MIXED_REGIME**: no symbol where funding and RV scales are comparable in a way that would make VRP a genuinely new composite.

### Step C — Lesson #54 candidate trap CONFIRMED

| Trap | Empirical | Trigger threshold | Result |
|---|---|---|---|
| Sign asymmetry | avg 37.2% of `funding_implied_vol` values are negative | >30% | **TRIGGERED** |
| Family reduction | (funding-extreme + rv-dominated) / total = 13/13 = 1.00 | ≥0.70 | **TRIGGERED** |

**Mechanism story incoherence**:
1. `funding_rate × 1095` is signed (positive or negative), but true implied volatility `σ_implied ≥ 0` by definition. The construction has no Black-Scholes derivation, no option-IV equivalence, and no theoretical link to volatility-surface estimation. It is a rescaled signed funding rate with a misleading "implied vol" label.
2. The VRP subtraction empirically reduces to one of two known signals per-symbol:
   - When `|funding_rate × 1095| << RV` (11/13 alts): `VRP ≈ −RV`, so `z(VRP) ≈ −z(RV)`. The trigger `z(VRP) > +2` ≡ `z(RV) < −2` = "low realized vol" event = vol-collapse anti-spike, mechanism-adjacent to paradigm 67-69/133/134 RV family.
   - When `|funding_rate × 1095| >> RV` (2/13 alts AXS/COMP, tail events): `VRP ≈ funding_implied`, so `z(VRP) > +2` ≡ `z(funding_rate) > +2` = funding extreme positive spike, mechanism-adjacent to paradigm 73/79/96 funding family.
3. The "fear premium unwind" / "complacency reverse" mechanism story is post-hoc rationalization of a two-regime composite, not a unified mechanism.

### Step D — Lesson #44 amendment xref 18th dogfood — FAIL

Funding family Tier 4 retire (paradigm 73/79/96/97/98/99/132 + paradigm 22 exception) — 2/13 syms collide.
RV family (paradigm 67-69/118/124/125/129/133/134 — all graveyarded except p69 R-5 seed) — 11/13 syms collide.

13/13 syms collide with at least one retired family. Family-distinct claim FAILS.

### Step E — Final R-0 verdict

`R0_HALT_LESSON_54_MECHANISM_INCOHERENT_FUNDING_RV_FAMILY_REDUCTION`

---

## Lessons Activated

### Lesson #54 candidate — 2nd dogfood (TRUE POSITIVE)
"Signed decomposition of a magnitude statistic does not synthesize directional alpha without an independent mechanism story."
- 1st dogfood: paradigm 134 (signed semivariance ratio) — BROAD_FALSIFIED uniform absence.
- 2nd dogfood: paradigm 135 (funding-implied vs realized vol divergence) — R-0 trap-confirmed before R-1 dispatch (efficiency win for the lesson framework).
- **Lesson #54 elevation to formal CONFIRMED — 2 dogfoods accumulated.**

### Lesson #44 amendment xref 18th dogfood — SUCCESS
- 17 paradigm cross-references documented in R-0 prescreen.
- Family-reduction collision detected before any R-1 compute cost incurred.
- Saved ~1-2hr R-1 dispatch + cleaner verdict trail.

### Lesson #21 axis-stacking trap (subtle form) — NEW SUB-FINDING
- Original Lesson #21: explicit conjunction stacking (axis A × axis B × axis C) does not synthesize alpha.
- **New sub-finding (paradigm 135)**: derived single statistic (subtraction/ratio/log of two raw signals) can syntactically pass Lesson #21 single-axis check but still empirically be a **two-regime composite** that reduces to one of the underlying retired families per-symbol. R-0 magnitude-ratio prescreen is the new defensive prescreen.

### Lesson #46 sub-amendment STRONG WARNING — N/A (R-0 halt before R-1)
- Sub-amendment not exercised because R-0 prescreen halted dispatch.

### Lesson #41 narrow-scope pre-empt — N/A (R-0 halt before R-1)

---

## Family Verdicts (Tier 4 retire status delta)

**No new family retired** (VRP is a single attempted family entry, not a sub-class proliferation).
- Funding family Tier 4 retire: UNCHANGED (paradigm 22 R-5 seeded exception only).
- RV family: UNCHANGED (paradigm 69 R-5 seeded exception only).
- **NEW advisory**: VRP-style "derived divergence statistic" (subtraction/ratio of two underlying signals from retired families) requires R-0 magnitude-ratio prescreen to detect family-reduction trap.

---

## Path Forward — Next Candidate Recommendation

Continuing continuous-parallel policy ([Persistence over efficiency] 2026-05-21).

**Recommended**: **`alt_intraday_1h_log_return_std_24h_window_z_directional_4h`** (paradigm 134 §6.31 Rank 2 candidate).
- **Mechanism**: 1st-order intraday vol stat — 24h rolling std of 1h log-returns (NOT RV close-to-close, NOT 2nd-order vol-of-vol, NOT semivariance decomp). z>+2 trigger, 4h hold.
- **Family-distinct**: 1st-order vol level is genuinely distinct from paradigm 67/68/69 1d close-to-close RV (1d frame), paradigm 133 vol-of-vol (2nd-order temporal clustering), paradigm 134 semivariance (signed decomp). It is the "vanilla" 1st-order intraday vol stat that has NOT been tried (paradigm 67-69 was 1d frame).
- **Substrate**: 1m OHLCV cache reuse (12 alts × 750+d), no funding dependency.
- **Why now**: NOT in funding family, NOT in RV family explicitly tried (1h frame is the gap), passes Lesson #44 xref, single-axis Lesson #21 compliant, mechanism story clear (high intraday vol → mean-revert in 4h or continuation depending on direction proxy).
- **Caveat**: paradigm 67-69 BTC RV showed strong asymmetric directional alpha (paradigm 69 R-5 seeded). 1h intraday vol per-sym may share mechanism family with paradigm 69 BTC RV, but per-sym and 1h frame are both distinct dimensions. Test as `family-distinct` candidate at R-0 vs paradigm 69.

**Alternative**: defer dispatch until D-Day 2026-06-03 paper Day 30 baseline measurement (D-13), given 7-streak non-PASS and lessons accumulating faster than alpha discovery. User policy override: continuous-parallel — proceed with rank 1.

---

## Campaign State (post-§6.32)

- Cumulative graveyards: **135**
- R-5 seeded LIVE: 10 (paradigm 127+128 Mint deploy unchanged)
- R-5 yield: **7.41%** (10/135)
- **Non-PASS streak: 7** (129/130/131/132/133/134/**135**)
- Lessons: **33 confirmed + 5 candidates**
  - Lesson #44 18th xref dogfood — SUCCESS
  - **Lesson #54 formal CONFIRMED elevation eligible (2 dogfoods)**
  - New Lesson #21 sub-finding "derived single statistic two-regime composite" — promoted to advisory caveat in skill
- D-Day 2026-06-03 D-13 / paradigm 127+128 Day 7 baseline 2026-05-28 D-7

---

## Artifacts

- R-0 prescreen script: `backend/scripts/research/paradigm135_r0_prescreen.py`
- R-0 metrics: `backend/runs/research_track/alt_funding_implied_vs_realized_vol_premium_z_directional_4h/r0_prescreen.json`
- Graveyard (this file): `backend/runs/research_track/graveyard__alt_funding_implied_vs_realized_vol_premium_z_directional_4h.md`
- R-1: **NOT DISPATCHED** (R-0 prescreen halt)
