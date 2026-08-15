# paradigm 190 R-1 report — `binance_delisting_announce_short_alt_fine_hold_sweep_plateau_identification_post_announce`

**Dispatch**: 2026-05-22 KST
**Verdict**: `NARROW_SCOPE_LIFE_CHANGING_FAIL` (R-1 graveyard)
**Mode**: R-1 ONLY (R-2 자동 진행 금지)

## R-0 prescreen verdicts (all PASS pre-execution)

1. **Lesson #70 corollary scope** → `PROCEED (b) R-1 PASS follow-up hold refinement (NOT spec-adaptive expansion)`
   - paradigm 87 status = R-1 PASS_R1_FULL → R-2 FRAGILE graveyard scope (NOT R-5 LIVE survivor)
   - paradigm 190 = R-2 fail diagnosis-driven specific hold refinement, NOT generic parameter tuning
   - Lesson #70 corollary CONFIRMED universal scope = R-5 LIVE survivor narrow-cohort expansion (paradigm 22/24 specific)
   - 3rd dogfood candidate for Lesson #70 corollary scope distinction (paradigm 182/184/190)

2. **Lesson #61 slug grep audit** → PASS (`binance_delisting_announce_short_alt` paradigm 87 only; no overlap with `fine_hold_sweep` / `plateau_identification` / `hold_sweep` variants)

3. **Lesson #11 sample density** → PASS (n=57 events per hold cell — within-paradigm parameter sweep, not sample-fragmenting partition)

4. **Lesson #34 empirical distribution** → PASS (paradigm 87 measured per-event log-returns ±60bp to ±5878bp, continuous, no threshold infeasibility)

5. **Lesson #67/#68 ESCAPE** → confirmed (per-event idiosyncratic delisting marker, post-announce window not session-boundary)

6. **Lesson #71 corollary** → PROCEED (sparse-strict mode 자격 후보, paradigm 87 base spec edge=14.6% strong-prior)

## R-1 measurement (7 holds × 2 directions = 14 cells)

### A focus SHORT (paradigm 87 primary direction)

| hold |  n | sigex | perm_p | ci_lo_bp | edge% | win% | sharpe |  tpy | util% | conc | 3-gate | 4-dim |
|-----:|---:|------:|-------:|---------:|------:|-----:|-------:|-----:|------:|:----:|:------:|:-----:|
|   1h | 57 |  1.86 |  0.039 |    -47   |  4.32 | 70.2 |  24.91 | 40.6 |  0.46 | PASS |  FAIL  | FAIL  |
|   2h | 57 | -0.03 |  0.741 |   -888   |  2.15 | 70.2 |   3.79 | 40.6 |  0.93 | PASS |  FAIL  | FAIL  |
|   4h | 57 | -0.51 |  0.881 |  -1512   |  1.48 | 75.4 |   1.25 | 40.6 |  1.85 | PASS |  FAIL  | FAIL  |
|   8h | 57 |  2.23 |  0.032 |    263   |  7.73 | 71.9 |  13.82 | 40.6 |  3.70 | PASS | **PASS** | FAIL  |
|  12h | 57 |  2.95 |  0.005 |    487   |  9.50 | 77.2 |  14.91 | 40.6 |  5.55 | PASS | **PASS** | FAIL  |
|  24h | 57 |  1.73 |  0.111 |    358   |  9.07 | 68.4 |   8.36 | 40.6 | 11.10 | PASS |  FAIL  | FAIL  |
|  48h | 57 |  1.40 |  0.158 |    647   | 12.49 | 73.7 |   7.46 | 40.6 | 21.74 | PASS |  FAIL  | FAIL  |

### A mirror LONG (paradigm 87 symmetric counter-hypothesis)

| hold |  n | sigex | perm_p | ci_lo_bp | edge% | win% |
|-----:|---:|------:|-------:|---------:|------:|-----:|
|   1h | 57 | -1.50 |  0.082 |   -821   | -4.48 | 28.1 |
|   2h | 57 |  0.28 |  0.758 |   -901   | -2.31 | 29.8 |
|   4h | 57 |  0.68 |  0.883 |  -1111   | -1.64 | 22.8 |
|   8h | 57 | -2.17 |  0.041 |  -1248   | -7.89 | 28.1 |
|  12h | 57 | -2.92 |  0.008 |  -1402   | -9.66 | 22.8 |
|  24h | 57 | -1.72 |  0.117 |  -1442   | -9.23 | 31.6 |
|  48h | 57 | -1.39 |  0.158 |  -1829  | -12.65 | 26.3 |

**Direction asymmetry preserved**: paradigm 87 SHORT-dominant mechanism (forced-exit liquidity drift) confirmed across full hold sweep. Mirror LONG sigex mirrors SHORT sign exactly (8h/12h significantly negative confirming SHORT-side alpha is real, not just direction-bet noise).

## Plateau identification (SHORT)

| triple | sigex_vals | edge_vals% | pass3g | concPass | edgeSust | stable | OVERALL |
|---|---|---|:---:|:---:|:---:|:---:|:---:|
| [1h,2h,4h]     | [1.86, -0.03, -0.51] | [4.32, 2.15, 1.48]   | FAIL | PASS | FAIL | FAIL | FAIL |
| [2h,4h,8h]     | [-0.03, -0.51, 2.23] | [2.15, 1.48, 7.73]   | FAIL | PASS | FAIL | FAIL | FAIL |
| [4h,8h,12h]    | [-0.51, 2.23, 2.95]  | [1.48, 7.73, 9.50]   | FAIL | PASS | FAIL | FAIL | FAIL |
| **[8h,12h,24h]** | **[2.23, 2.95, 1.73]** | **[7.73, 9.50, 9.07]** | **FAIL** | PASS | **PASS** | **PASS** | FAIL |
| [12h,24h,48h]  | [2.95, 1.73, 1.40]   | [9.50, 9.07, 12.49]  | FAIL | PASS | PASS | FAIL | FAIL |

**Best near-plateau**: [8h, 12h, 24h] — edge_sustained + stable, but 3-gate FAIL at endpoints (24h sigex 1.73 < 2.0 cutoff). **No qualifying plateau**.

## paradigm 87 baseline direct comparison

| metric | paradigm 87 (1d ≈ 3.3d hold) | paradigm 190 best (12h) | paradigm 190 plateau-best (8h-12h-24h mean) |
|---|---:|---:|---:|
| n | 57 | 57 | 57 |
| sigex | +2.23 | **+2.95** | +2.30 |
| edge%/trade | +14.63 | +9.50 | +8.77 |
| win_rate | 71.9% | 77.2% | 72.5% |
| util% | 36.7 | 5.55 | ~6.8 |
| sharpe ann. | 6.49 | 14.91 | ~12.4 |
| tpy | 40.5 | 40.6 | 40.6 |
| 4-dim gate | **PASS** | **FAIL (util)** | FAIL (util) |
| R-2 outcome | FRAGILE_TEMPORAL_WF_FAIL | n/a (R-1 only) | n/a (R-1 only) |

**Key finding**: paradigm 190 reveals the strongest sigex localized at 12h (sigex +2.95, edge +9.50%) — STRONGER stat than paradigm 87's 1d baseline. But util% catastrophically lower (5.55% vs 36.7%) because hold is too short. The alpha-bearing window is sharper than 1d but cannot satisfy life-changing 4-dim gate at any sub-1d hold.

## paradigm 87 R-2 fail diagnosis — fine-hold-sweep does NOT solve

**paradigm 87 R-2 fail mode**: TS-CV 1/5 PASS (single Q4-2025 outlier dominance, Lesson #26 small-sample Concentration Gate per-quarter blind spot).

**paradigm 190 plateau analysis confirms**: per-quarter concentration_gate quarter_pos_t_ratio PASSES at every hold (n_quarters_measurable consistently 3 with n>=10 cutoff), but this is the SAME small-denominator blind spot from Lesson #26. Fine-hold-sweep CANNOT alleviate small-sample temporal fragility because:

1. n=57 events fixed (universe unchanged from paradigm 87)
2. Per-quarter n still 6/8/18/13/12 (same distribution)
3. Outlier-quarter dominance risk persists at every hold sub-spec
4. Util% degradation forces longer hold for life-changing 4-dim → reverts toward paradigm 87 spec → reverts to FRAGILE_TEMPORAL_WF_FAIL risk

**Conclusion**: Fine-hold-sweep is **diagnosis-illuminating** (reveals 12h sharp alpha peak) but **not diagnosis-resolving** for paradigm 87's R-2 fragility.

## Lesson #20 narrow-scope assessment

- 2 isolated 3-gate PASS cells (8h, 12h) with concentration_gate.overall_pass
- 0/2 cells pass 4-dim Frequency-First Gate (life-changing)
- Per [[feedback_narrow_scope_life_changing_fail_verdict]] (NARROW_SCOPE_LIFE_CHANGING_FAIL CONFIRMED verdict category): 3-gate PASS + concentration PASS + 4-dim FAIL → `NARROW_SCOPE_LIFE_CHANGING_FAIL`

## Final verdict

`NARROW_SCOPE_LIFE_CHANGING_FAIL` — 2/14 cells 3-gate PASS with concentration, but 0/2 satisfy life-changing 4-dim Frequency-First Gate (util% 3.7-5.5% << 30% cutoff). No qualifying 3-hold plateau. paradigm 87 R-2 small-sample temporal fragility (Lesson #26 blind spot) persists at every sub-spec.

## Lesson #70 corollary 3rd dogfood result

Successful PROCEED-with-result for R-1 PASS follow-up hold refinement scope (NOT spec-adaptive expansion). Verdict NSLC_FAIL maintains corollary distinction:
- (a) spec-adaptive expansion of R-5 LIVE survivor → HALT (paradigm 182/184 dogfoods)
- (b) R-1 PASS R-2 fail follow-up refinement → PROCEED with full R-1 measurement (paradigm 190 dogfood — this report)

3 dogfoods total → Lesson #70 corollary CONFIRMED-eligible for formal universal status promotion.

## paradigm 191 next-action recommendation

Given paradigm 190 NSLC_FAIL + paradigm 87 family fundamental constraints:

**Path 1 (HIGHEST priority)**: Halt this delisting family R-2 refinement attempts entirely. Lesson #27 entry/exit-side classification + Lesson #26 small-sample WF + fine-hold-sweep NSLC = 3-layer falsification. Delisting forced-EXIT mechanism + n=57 fixed = structural ceiling. `family_lesson_candidate`: delisting forced-exit + n<100 paradigm is structurally R-2 fragile regardless of hold spec.

**Path 2 (moderate)**: Universe expansion attempt — add Bybit / OKX historical delisting events (substrate verification 필요, [[feedback_no_freemium_trial]] check). If 3-4x sample uplift possible, retry paradigm 87 1d hold (NOT 190 fine-sweep) on expanded universe to break n=57 sample ceiling. Lesson #30 candidate (data window ratio).

**Path 3 (low)**: Brainstorm entirely new entry-side immediate-demand external-event candidate (lifecycle paradigm 22 동형). [[project_paradigm_listing_pre_announce]] + [[project_paradigm_stablecoin_mint]] graveyards demonstrate this path is exhausted for current substrate. Wait for new external event data domain ([[feedback_no_freemium_trial]] compatible).

**Recommended**: Path 1 + ratify family lesson candidate. Paradigm 190 closes paradigm 87 follow-up loop; pivot to other axes per memory `[[feedback_paradigm_campaign_continuous_parallel]]`.

## Artifacts

- `r1.py` — generated R-1 script (compiled, executed ~3min)
- `r1__metrics.json` — full per-cell metrics + plateau identification
- `backfill_ohlcv_local.py` — local re-backfill (pandas 2.3 compatible) cache regeneration
- `ohlcv_cache_local/` — 57 syms × ~5-13 day windows (440 day-files)
- `delisting_events.csv` — paradigm 87 substrate (n=57, reused)

KST 2026-05-22T12:17
