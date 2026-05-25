# paradigm 206 GRAVEYARD

**slug**: `alt_btc_lead_lag_90d_ks_2sample_distribution_shift_cross_asset_cascade_directional_4h_bilateral`
**counter**: paradigm 206 (post-paradigm-205 Lesson #39 sub-class A 3rd dogfood CONFIRMED-FORMAL-UNIVERSAL)
**phase**: R-1
**verdict**: **CONCENTRATION_FAIL_TEMPORAL_CLUSTER_AUTOCORRELATION_ARTIFACT** (composite: Concentration Gate symbol_ci_pos_ratio 0/20 FAIL + temporal cluster autocorrelation inflation, NOT BROAD_FALSIFIED)
**dispatch date**: 2026-05-22 KST

---

## Hypothesis

BTC 90d daily-return KS 2-sample statistic (recent 45d vs prior 45d) → 180d rolling z-score → |z| ≥ +2 spike trigger × BTC heavier-tail sign × 20 alt forward return at +1d/+2d/+3d × 4-quadrant SNT with cell-A/cell-B disjoint trigger sets (recent_heavier vs recent_lighter).

## Lesson #69 7-item template results

### Item 1 (Lesson #61 amendment slug grep)
zero hits — `grep -iE "btc_lead|btc_distribution_shift|btc_ks|btc_cascade|btc_lead_lag|cross_asset_cascade"` returns empty in research_track/. Novel slug confirmed.

### Item 2 (Lesson #28 amendment substrate-shape)
BTCUSDT 4h cache 820 daily bars 2024-02-01 ~ 2026-04-30 + 20 alts all present (ADA/AVAX/BCH/BNB/DOGE/DOT/ETC/ETH/FIL/JUP/LDO/LINK/LTC/NEAR/PYTH/SOL/UNI/WIF/WLD/XRP). archive-direct, zero backfill, [[feedback-no-freemium-trial]] FULL compliant.

### Item 3 (Lesson #11 sample density)
Trigger |z| ≥ 2.0: 33 dates, cell A 12, cell B 21. Per cell × 20 alts × +1d: A=240, B=420. Naive density >> 30 cutoff PASS. **BUT** see Item 7 — independent event count is 1 (cell A) + 3 (cell B) = 4, NOT 33.

### Item 4 (Lesson #62 DNA 4-dim 5/5 strict)
- statistic: KS 2-sample 90d → 180d z (NOVEL, not in 20 retires + paradigm 205 RV intraday)
- universe: 20 alts BTC excluded (forward set); BTC trigger source (cross-asset broadcast pattern)
- mechanism: cross-asset broadcast (BTC → alt) vs paradigm 205 per-sym idiosyncratic intraday RV
- hold: +1d/+2d/+3d daily (daily anchor distinct from paradigm 205 12h intraday peak)
- direction: bilateral 4-quadrant SNT with disjoint cell A/B trigger sets (NOVEL design)
- **Verdict**: 5/5 strict distinct PASS

### Item 5 (Lesson #56 family-proxy)
- paradigm 70 (BTC-RV-spike contagion) + paradigm 71 (BTC OI velocity) cross-asset cascade family relatives
- paradigm 70 R-2 graveyard FRAGILE_TEMPORAL_WF_FAIL — paradigm 206 reproduces same temporal sparseness via different statistic
- Family proxy: cross-asset broadcast from BTC, daily horizon, signed bilateral, 20-sym aggregate

### Item 6 (alpha decay informational learning audit — 3rd operational dogfood)

**Era stratify (+1d hold)**:
| Quadrant | 2024 | 2025 | 2026 |
|---|---|---|---|
| A_focus heavier×LONG | — | n=240 t=−2.69 (2025Q4 single) | — |
| A_mirror heavier×SHORT | — | n=240 t=+2.69 (2025Q4 single) | — |
| B_same lighter×SHORT | — | n=360 t=+2.57 mean=+59.41bp | n=60 t=+4.83 mean=+152.90bp |
| B_mirror lighter×LONG | — | n=360 t=−2.57 | n=60 t=−4.83 |

**Era pattern verdict**: 2024 era ZERO triggers (KS z-score volatility regime stable). 2025-2026 era only. **NOT monotonic decay** (paradigm 87/136/202), **NOT sign-flipping** (paradigm 204), **NOT regime-specific transient** (paradigm 205) — rather: **trigger statistic itself is regime-binary** (vol-regime episodes occurred only in 2025+, none in 2024). Era pattern: **trigger-availability binary** (new class). 2024 = zero events makes alpha decay measurement undefined for this paradigm; only 1 cell A cluster + 3 cell B clusters total.

### Item 7 (NEW, SNT structural integrity check) — first formal dogfood

**A_focus + A_mirror within-trigger sum**: 0.0 (exact ±48.52bp) → within-set mirror tautology confirmed (expected by construction).
**B_same + B_mirror within-trigger sum**: 0.0 (exact ±88.77bp) → within-set mirror tautology confirmed.
**Cross-set magnitudes asymmetric**: |A_focus| 48.52bp ≠ |B_same| 88.77bp (1.83x ratio) → **Lesson #39 sub-class A formally avoided** (cross-set asymmetric magnitudes confirmed).
**Cell A ∩ Cell B intersection**: 0 (disjoint by construction, recent_heavier vs recent_lighter mutually exclusive sign partition).

**Item 7 verdict**: **PASS — design successfully escapes Lesson #39 sub-class A exact-mirror tautology**. Cross-set asymmetry confirmed at +1d (1.83x), +2d (A=149.90 vs B=127.73, 1.17x), +3d (A=262.41 vs B=181.42, 1.45x).

**However**: Item 7 PASS does NOT imply alpha-bearing. See Concentration Gate FAIL below.

## 4-quadrant SNT verdict (+1d primary hold)

| Quadrant | n | gross_bp | net_bp | sigex | perm_p_above | ci_lo_bp | q_pos_t | sym_ci_pos | three_gate |
|---|---|---|---|---|---|---|---|---|---|
| A_focus heavier×LONG | 240 | −48.52 | −64.52 | −2.31 | 0.983 | −109.72 | 0.00 | 0.00 | FAIL |
| A_mirror heavier×SHORT | 240 | +48.52 | +32.52 | +1.95 | 0.034 | −13.37 | 1.00 | 0.05 | FAIL (ci_lo<0) |
| **B_same lighter×SHORT** | 420 | +88.77 | +72.77 | **+4.32** | 0.000 | +31.45 | 1.00 | **0.00** | **3-gate PASS / Concentration FAIL** |
| B_mirror lighter×LONG | 420 | −88.77 | −104.77 | −4.62 | 1.000 | −144.42 | 0.00 | 0.00 | FAIL |

**Concentration Gate (Lesson #16) on B_same_SHORT**: symbol_ci_pos_ratio = **0.00 (0/20)** < 0.30 threshold AND n_symbols_ci_pos = 0 < 3 threshold → **Concentration FAIL despite aggregate three-gate PASS**.

**Per-symbol ci_lower_bp (B_same SHORT @ +1d)**: ALL 20 symbols have ci_lower < 0; range −405.31 (WLD) to −11.27 (DOGE). NO symbol exhibits independent alpha — aggregate sigex inflated by cross-sectional correlation, not per-symbol mechanism.

## Hold sweep (Lesson #37 full sweep verdict scan)

| Hold | A_focus | A_mirror | B_same | B_mirror |
|---|---|---|---|---|
| +1d | −64.52bp sigex−2.31 | +32.52bp sigex+1.95 | **+72.77bp sigex+4.32 PASS** | −104.77bp sigex−4.62 |
| +2d | −149.90bp sigex−4.07 | **+117.90bp sigex+3.84 PASS** | **+127.73bp sigex+5.30 PASS** | −159.73bp sigex−5.58 |
| +3d | −262.41bp sigex−5.54 | **+230.41bp sigex+5.40 PASS** | **+181.42bp sigex+6.44 PASS** | −213.42bp sigex−6.75 |

**Non-primary cell PASS scan (Lesson #37)**: A_mirror_SHORT becomes 3-gate PASS at +2d/+3d (sigex+3.84/+5.40). B_same_SHORT 3-gate PASS at all 3 holds. **However**: all PASS cells exhibit **same Concentration Gate FAIL pattern** (per-symbol ci_pos = 0/20, 0/20, 3/20 for A_mirror@+2d).

## Trigger temporal cluster analysis (key falsification)

**Independent event count** (consecutive z≥2 dates within 5d = single regime episode):

- Cell A 12 dates → **1 independent cluster**: 2025-11-17 ~ 2025-11-28 (11d span, BTC Nov 2025 vol expansion regime)
- Cell B 21 dates → **3 independent clusters**:
  - 2025-04-25~26 (2d Apr-May 2025 vol compression)
  - 2025-05-14~06-01 (19d May-June 2025 vol compression)
  - 2026-01-05~07 (3d Jan 2026 vol compression)

**True independent BTC regime events**: cell A 1 + cell B 3 = **4 total over 2.25yr**.

**Effective n correction**: n=240 (cell A) reduces to **n_independent ≈ 20 alts × 1 cluster = 20 independent observations** (or even less with cross-sectional correlation). n=420 (cell B) reduces to **n_independent ≈ 20 alts × 3 clusters = 60 observations** with high cross-sectional correlation within each cluster.

The aggregate sigex +4.32 at B_same is **temporal cluster autocorrelation artifact** — same BTC vol regime broadcasts the same directional drift to 20 highly-correlated alts on 21 consecutive days. The fee_aware_perm_test null distribution uses i.i.d. resampling from candidate pool, which breaks down under temporal clustering.

## Final verdict

**GRAVEYARD — CONCENTRATION_FAIL_TEMPORAL_CLUSTER_AUTOCORRELATION_ARTIFACT**

Three independent fail modes confirmed:
1. **Concentration Gate symbol_ci_pos_ratio = 0/20 across all cells** — no per-symbol independent alpha; aggregate signal is cross-sectional correlation artifact within BTC regime episodes
2. **Temporal cluster autocorrelation**: 33 daily trigger dates reduce to ~4 independent BTC regime episodes (n_independent ≈ 4 events × 20 syms ≈ 80, not 240+420=660)
3. **Trigger-availability binary era**: zero triggers in 2024 era (~1yr), all in 2025-2026; paradigm cannot produce trades during stable vol regimes (sparse-trigger structural)

**Sparse-trigger structural fail** also: 4 events × 2.25yr = **1.78 events/yr** << 12/yr life-changing threshold (per [[feedback-life-changing-strategy-criterion]]). Even if Concentration Gate passed, 4-dim freq gate trades/yr FAIL pre-determined.

## Lesson contributions

### Lesson #39 sub-class A escape verdict — SUCCESS

paradigm 206 design (cell A vs cell B disjoint trigger sets via recent_heavier sign partition) **formally avoided Lesson #39 sub-class A exact-mirror tautology**. Cross-set asymmetric magnitudes confirmed at all 3 holds (1.17x to 1.83x ratio). **First successful Lesson #39 sub-class A explicit avoidance design** in paradigm catalog.

**However**: escaping sub-class A does NOT confer alpha. Item 7 PASS + Concentration Gate FAIL = **escape design is necessary but not sufficient**. paradigm-architect Lesson #39 escape skill operational but does not auto-promote.

### Lesson #71 candidate (NEW): Aggregate-significant cross-asset cascade with zero per-symbol CI = temporal-cluster correlation artifact (1st dogfood)

**Diagnostic pattern**:
- Aggregate three-gate PASS (sigex ≥ 2.0 + ci_lower > 0 + perm_p ≤ 0.10) on n=O(hundreds)
- Per-symbol CI lower 0/N ci_pos (zero symbols with independent positive CI)
- Trigger date temporal cluster count << total event count (autocorrelation)

**Mechanism**: BTC-broadcast cross-asset cascade fires same signal to N correlated alts on M consecutive days; fee_aware_perm_test i.i.d. null breaks down; aggregate sigex inflated by N×M correlated pseudo-observations.

**Prescreen prescription**:
1. Trigger date independent-cluster count check (consecutive within 5d → 1 cluster): if n_independent_clusters < 10, escalate to temporal cluster warning
2. Per-symbol CI lower scan mandatory before aggregate sigex acceptance
3. Concentration Gate symbol_ci_pos ≥ 3 syms (Lesson #16) is decisive when aggregate sigex is suspiciously high relative to event count

**Verification dogfood needed**: requires 2 more dogfoods of cross-asset broadcast paradigms with aggregate-PASS / per-sym-FAIL pattern to confirm. Provisional candidate status.

### Lesson #69 Item 7 (SNT structural integrity) — 1st formal operational dogfood

Item 7 protocol added in paradigm 206 dispatch is **operational and successfully detects within-trigger-set mirror tautology** (A_focus + A_mirror = exact ±N) AND verifies cross-set disjoint property. The check correctly identified paradigm 206 design as Lesson #39 sub-class A escape candidate. **Item 7 retained as Lesson #69 permanent 7-item template** going forward.

### Lesson #67 ESCAPE verdict — confirmed
cross-asset broadcast (BTC trigger → alt forward) is NOT per-sym idiosyncratic, NOT Lesson #67 violation. Family classification: cross-asset cascade.

### Lesson #68 ESCAPE — confirmed
continuous rolling 90d window, no session-boundary anchor.

### Lesson #70 ESCAPE — confirmed
NEW cross-asset class, NOT R-5 LIVE expansion of seeded paradigm.

## Family verdict

**BTC cross-asset cascade family** (paradigms 70 + 71 + 206): all 3 paradigms fail at R-1 or R-2 with **temporal sparseness pattern**. 
- paradigm 70: R-2 FRAGILE_TEMPORAL_WF_FAIL
- paradigm 71: R-1 BROAD_FALSIFIED_FEE_FLOOR
- paradigm 206: R-1 CONCENTRATION_FAIL_TEMPORAL_CLUSTER

3 consecutive cross-asset broadcast paradigm fails. **Advisory caution** (3rd consecutive R-1/R-2 fail). Not Tier 4 retire yet (different statistics + mechanism variations), but cross-asset cascade family **sample-density × temporal-cluster antipattern documented**.

## Files

- `backend/scripts/research/alt_btc_lead_lag_90d_ks_2sample_distribution_shift_cross_asset_cascade_directional_4h_bilateral_r1.py`
- `backend/runs/research_track/alt_btc_lead_lag_90d_ks_2sample_distribution_shift_cross_asset_cascade_directional_4h_bilateral/r1__metrics.json`

## paradigm 207 next-action recommendation

**Lesson #61 amendment permanent inventory check 의무** — paradigm 207 candidate must:
1. **NOT** be cross-asset broadcast variant (3 consecutive family fails advisory caution)
2. **NOT** be daily-anchor + rolling-window-statistic z-score (Lesson #71 candidate trigger-cluster antipattern, needs 2 more dogfoods to formalize)
3. Prefer per-symbol independent trigger paradigms where n_independent_events ≈ n_observations (no temporal clustering)
4. Continue dispatch per [[feedback-persistence-over-efficiency]] + [[feedback-paradigm-campaign-continuous-parallel]]

**Direct recommendation** ([[feedback-direct-recommendation]]): Next candidate axis = **per-symbol intraday liquidation cascade event-anchored** (cross-asset 회피 + event-anchor → temporal cluster 회피 + per-symbol natural independent events). Candidate slug: `alt_per_sym_liquidation_cascade_3sigma_event_anchored_directional_2h_signed`. Substrate audit needed (liquidation feed availability).
