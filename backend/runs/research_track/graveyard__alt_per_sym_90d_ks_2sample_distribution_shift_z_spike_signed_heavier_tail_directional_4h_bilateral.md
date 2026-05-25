# paradigm 205 GRAVEYARD — KS 2-sample distribution-shift z-spike signed-tail directional 4h

**Date**: 2026-05-22 KST
**Phase**: R-1 STRICT (R-2 not dispatched)
**Verdict**: **BROAD_FALSIFIED_FEE_FLOOR + Lesson #39 sub-class A 3rd cross-class dogfood CONFIRMED**

## Hypothesis recap

- Per-sym daily-return 90d window → KS 2-sample stat (recent45d vs prior45d) → 180d rolling z → |z|≥+2 spike
- Signed direction via variance-ratio (sign=+1 recent heavier-tail / sign=−1 recent lighter-tail)
- 4-quadrant SNT × 4h/8h/12h/24h hold sweep, 20 alts × 2.25yr, FEE=8 bp net/trade

## Item-by-item Lesson #69 6-item template

| Item | Lesson | Result |
|------|--------|--------|
| 1 | #61 amendment slug grep | PASS (0 matches for ks_2sample/kolmogorov/distribution_shift/cdf_distance/variance_expansion → family-distinct) |
| 2 | #28 amendment substrate-shape | PASS (21 cache files × 4920 4h bars × 819 days ≈ 2.25yr) |
| 3 | #11 sample density | PASS (per-sym 12–63 triggers, total n=417 per hold per direction, per-cell n≥100 across years) |
| 4 | #62 DNA 4-dim | PASS 5/5 strict distinct vs 20 Tier 4 retires (new statistic class = KS distribution shift, not z-score/regime/joint) |
| 5 | #56 family-proxy | NEUTRAL (new axis class, no proxy lineage) |
| 6 | alpha decay audit (NEW operational 2nd dogfood) | **EXECUTED** — see era table below |

## 4-quadrant verdict (4 holds × 4 quadrants = 16 cells, 0/16 PASS)

| hold | quadrant | n | gross_bp | net_bp | sigex | ci_lower_bp | pass |
|------|----------|---|----------|--------|-------|-------------|------|
| 4h  | A_focus      | 417 | −11.22 | −19.22 | −1.04 | −37.40 | FAIL |
| 4h  | A_mirror     | 417 | +11.22 |  +3.22 | +1.20 | −17.95 | FAIL |
| 4h  | B_same_sign  | 406 | +11.52 |  +3.52 | +1.42 | −10.63 | FAIL |
| 4h  | B_mirror     | 406 | −11.52 | −19.52 | −1.69 | −33.68 | FAIL |
| 8h  | A_focus      | 417 | −35.25 | −43.25 | −2.12 | −71.20 | FAIL |
| 8h  | A_mirror     | 417 | +35.25 | +27.25 | +2.49 |  −2.42 | FAIL (sigex PASS, ci_lo FAIL by 2.42 bp) |
| 8h  | B_same_sign  | 406 | +27.70 | +19.70 | +2.44 |  −2.19 | FAIL (sigex PASS, ci_lo FAIL by 2.19 bp) |
| 8h  | B_mirror     | 406 | −27.70 | −35.70 | −2.47 | −57.28 | FAIL |
| 12h | A_focus      | 417 | −47.37 | −55.37 | −2.26 | −89.87 | FAIL |
| 12h | A_mirror     | 417 | +47.37 | +39.37 | **+2.91** | **+3.54** | FAIL (sigex+ci_lo PASS, **perm_p None → ineligible**) |
| 12h | B_same_sign  | 406 | +33.79 | +25.79 | +2.34 |  −3.59 | FAIL |
| 12h | B_mirror     | 406 | −33.79 | −41.79 | −2.07 | −70.62 | FAIL |
| 24h | A_focus      | 417 |  −2.62 | −10.62 | +0.25 | −61.09 | FAIL |
| 24h | A_mirror     | 417 |  +2.62 |  −5.38 | +0.44 | −59.63 | FAIL |
| 24h | B_same_sign  | 402 |  +7.04 |  −0.96 | +0.61 | −50.11 | FAIL |
| 24h | B_mirror     | 402 |  −7.04 | −15.04 | +0.04 | −62.55 | FAIL |

Note: `perm_p=None` due to `fee_aware_perm_test` early-return guard (n_obs > n_pool fraction). sigex computed analytically; three-gate FAIL anyway via ci_lower_bp criterion. 12h A_mirror is the strongest cell (sigex +2.91, ci_lo +3.54 bp) but two-gate only.

## CRITICAL: Lesson #39 sub-class A explicit avoidance verdict

**RESULT: AVOIDANCE FAILED → Lesson #39 sub-class A 3rd cross-class dogfood CONFIRMED**

| hold | A_focus gross | A_mirror gross | sum (exact-symmetric if 0) | B_same gross | B_mirror gross | sum |
|------|---------------|----------------|-----------------------------|--------------|-----------------|-----|
| 4h  | −11.22 | +11.22 | **+0.0000** | +11.52 | −11.52 | **+0.0000** |
| 8h  | −35.25 | +35.25 | **+0.0000** | +27.70 | −27.70 | **+0.0000** |
| 12h | −47.37 | +47.37 | **+0.0000** | +33.79 | −33.79 | **+0.0000** |
| 24h |  −2.62 |  +2.62 | **+0.0000** |  +7.04 |  −7.04 | **+0.0000** |

**Diagnosis**: Despite signed direction being internalized in the trigger (via variance-ratio sign), the trade-side LONG↔SHORT split on the same trigger set still produces **mathematically identical ±N bp** structure. Reason: at the cell level, "A_focus = trigger_set_S × LONG" and "A_mirror = trigger_set_S × SHORT" are forward-return-on-same-set with opposite sign. The sign of the trigger (heavier vs lighter tail) merely partitions the trigger set into two disjoint sub-sets (S+ and S−), but within each sub-set the LONG vs SHORT side remains a direction-bet of the same forward-return vector, so A_focus(S+, LONG) and A_mirror(S+, SHORT) = ±same magnitude. Same for B(S−).

**Conclusion**: Signed-trigger paradigms do NOT escape Lesson #39 sub-class A artifact when side (LONG/SHORT) is still a free axis of the 4-quadrant SNT. The artifact is structural to the SNT setup itself when forward-return is a single scalar, not specific to unsigned-trigger paradigms.

**→ Lesson #39 sub-class A formal universal status**: 3 cross-class dogfoods (paradigm 108 unsigned, paradigm 204 unsigned, paradigm 205 signed) all exact-symmetric ±N. Recommend promote Lesson #39 sub-class A to **CONFIRMED-FORMAL-UNIVERSAL** with amendment: "exact-symmetric ±N artifact applies to ANY 4-quadrant SNT structure where (trigger, side) is the cell axis with forward log-return as scalar payoff, regardless of whether trigger is signed or unsigned."

**Future-paradigm implication**: 4-quadrant SNT must use **non-mirror cells with structurally different filters** (e.g., conditional on additional state like BTC regime, vol regime, or session boundary) to break exact-symmetric. Pure (sign × side) cross product over fixed forward-return is mathematically tautological.

## Lesson #42 12th dogfood post-Hurst (B_mirror cell)

**RESULT: NEGATIVE 13th** (B_mirror = KS_z spike × recent_lighter × LONG reversal)

All 4 holds: B_mirror sigex = {−1.69, −2.47, −2.07, +0.04} ci_lo = {−33.68, −57.28, −70.62, −62.55} → FAIL all.

→ Lesson #42 dogfood streak: NEGATIVE 13th (paradigm 117/158/162/179/193/194/195/196/197/198/204/**205**). KS distribution shift class is NOT a B_mirror alpha-bearing axis. Cross-class universal NEGATIVE status reinforced.

## Item 6: Alpha decay informational learning audit (2nd operational dogfood)

| hold | quadrant | 2024 sigex (n) | 2025 sigex (n) | 2026 sigex (n) | pattern |
|------|----------|----------------|----------------|----------------|---------|
| 8h  | A_focus      | −0.36 (198) | −2.29 (194) | −1.52 (25)  | mild monotonic worsening |
| 8h  | A_mirror     | +0.62 (198) | +2.55 (194) | +1.61 (25)  | mid-era peak, 2026 slight decay |
| 8h  | B_same_sign  | +0.19 (100) | **+2.59** (189) | +0.30 (117) | **2025 peak, 2026 reverts to null** |
| 8h  | B_mirror     | −0.01 (100) | −2.34 (189) | −0.10 (117) | mid-era peak, 2026 reverts |
| 12h | A_focus      | −1.04 (198) | −1.76 (194) | −2.30 (25)  | monotonic worsening (small n in 2026) |
| 12h | A_mirror     | +1.37 (198) | +2.09 (194) | +2.41 (25)  | monotonic strengthening (small n) |
| 12h | B_same_sign  | +0.62 (100) | **+2.72** (189) | −0.02 (117) | **clear 2025 peak, 2026 fully reverts** |
| 12h | B_mirror     | −0.39 (100) | −2.40 (189) | +0.28 (117) | mid-era peak, 2026 reverts |

**Pattern verdict**: NOT pure monotonic decay (Lesson #87/136/202 cross-family universal alpha-decay-3rd-dogfood does NOT trigger). Instead **mid-era peak (2025) with 2026 reversion** for B-class cells. A-class shows mild monotonic worsening for A_focus (negative direction) and mild monotonic strengthening for A_mirror but with very small 2026 sample (n=25) — too sparse for verdict.

**→ Alpha decay universal CROSS-FAMILY 3rd dogfood: NEGATIVE (no monotonic decay observed)**. The 2025-peak/2026-revert pattern is more consistent with **regime-specific alpha emergence then dissipation** than monotonic informational learning. Documentation note: regime-specific alpha class may be its own informational pattern (mid-era market structure transient), worthy of future Lesson candidate consideration.

## Lesson #67/#68/#70 ESCAPE verification

| Lesson | Definition | ESCAPE? |
|--------|------------|---------|
| #67 | per-sym idiosyncratic, no cross-asset broadcast | ESCAPED (per-sym KS computed independently) |
| #68 | continuous rolling, no session-boundary anchor | ESCAPED (rolling 90d window, no fixed timing anchor) |
| #70 | NEW paradigm class (NOT R-5 LIVE expansion) | ESCAPED (R-1 dispatch, no R-5 expansion attempted) |

All three lessons ESCAPED — paradigm 205 is structurally novel along these axes. Failure mode is NOT one of #67/#68/#70.

## 4-dim life-changing criterion

trades/yr ≈ 417 events / 2.25yr / 20 syms ≈ 9.3 trades/yr/sym → portfolio aggregate ~185/yr (PASS trades/yr ≥ 12)
per-trade edge: max +0.45% (8h A_mirror) but ci_lo neg → FAIL
capital util: 4h hold × 20 syms ~estimable mid-band but EDGE FAIL stops here
sharpe: not computed, EDGE FAIL stops here

→ 4-dim FAIL at edge gate (no positive-CI cell exists at sigex≥2 + ci_lo>0 + perm_p≤0.10 conjunction).

## paradigm 205 family-distinct verification (Lesson #62 DNA 5/5 strict)

| DNA dim | paradigm 205 value | matches Tier-4 retire? |
|---------|--------------------|------------------------|
| statistic_class | KS 2-sample distribution shift | NO (never seen) |
| universe | 20 alts perp 4h | shared but combination novel |
| timeframe | 4h cache → daily rolling | NO |
| sign_source | variance-ratio internalized | NO (paradigm 204 used "bar direction") |
| trigger_geometry | rolling 180d z of KS stat | NO |

5/5 strict distinct, paradigm 205 family-distinct CONFIRMED.

## Verdict

**BROAD_FALSIFIED_FEE_FLOOR** at all 16 cells. Best cell (12h A_mirror) reaches sigex +2.91 and ci_lo +3.54 bp but `perm_p=None` (helper guard), and is exact-symmetric to A_focus (variance-expansion SHORT continuation, the direct opposite of the hypothesized "variance expansion continuation LONG" mechanism — i.e., the data says variance expansion **predicts SHORT**, not LONG). This is sub-class A artifact: A_mirror "PASS" is the mirror of A_focus's strong negative, not an independent alpha discovery.

## Cross-paradigm lessons promoted by 205

1. **Lesson #39 sub-class A → 3rd cross-class dogfood CONFIRMED-FORMAL-UNIVERSAL eligible** (paradigm 108 unsigned, 204 unsigned, 205 signed all exact-symmetric ±N). Recommend amendment text: "4-quadrant SNT with (sign × side) cross product produces mathematically tautological ±N exact-symmetric mirrors regardless of whether sign is internalized via trigger statistic or external bar direction. To break this, paradigms must introduce a NON-MIRROR breaking variable (BTC regime / vol regime / session boundary / cross-sym filter) on one side of each pair, or use multi-statistic non-scalar payoff."

2. **Lesson #42 NEGATIVE 13th** (B_mirror cell on KS class). KS axis NOT alpha-bearing for B_mirror.

3. **Alpha decay universal cross-family 3rd dogfood: NEGATIVE** (no monotonic decay; instead mid-era peak / 2026 revert pattern observed).

4. **NEW Lesson candidate**: "Regime-specific alpha transient" pattern (mid-era 2025 peak in sigex with 2026 reversion to null) observed in paradigm 205 B-class cells. Distinct from monotonic informational decay. Worth tagging in 4+ future paradigms before formal Lesson promotion.

## Next-action recommendation

**paradigm 206** dispatch path: per [[feedback-paradigm-campaign-continuous-parallel]] + [[feedback-persistence-over-efficiency]] direct dispatch with **structural deviation from 4-quadrant exact-symmetric SNT**:

→ **Recommended axis class**: cross-asset cascade / lead-lag (e.g., BTC distribution-shift z → 20 alt forward returns at +1d / +2d / +3d lag) — this BREAKS the 4-quadrant exact-symmetric by introducing the BTC-trigger asymmetry between A and B cells (BTC up-shift × alt LONG vs BTC up-shift × alt SHORT remain mirrors, but cross-sym B same-sign now refers to BTC down-shift events which is a DIFFERENT trigger set with different alt forward returns). Lesson #61 amendment permanent inventory check obligatory.

→ paradigm 205 informational asset: KS 2-sample + rolling z-score infrastructure for distribution-shift detection — reusable for future cross-asset paradigms where the lead variable (e.g., BTC) provides the asymmetric breaking.

→ **Lesson #69 7-item template proposal**: append Item 7 = "4-quadrant SNT structural integrity check — verify A_focus + A_mirror ≠ ±same magnitude (or accept that magnitudes WILL be symmetric and only B vs A asymmetry is meaningful)." This makes the Lesson #39 sub-class A check explicit and built-in.

## Artifacts

- code: `/home/hcpark/antigravity/backend/scripts/research/alt_per_sym_90d_ks_2sample_distribution_shift_z_spike_r1.py`
- metrics: `/home/hcpark/antigravity/backend/runs/research_track/alt_per_sym_90d_ks_2sample_distribution_shift_z_spike_signed_heavier_tail_directional_4h_bilateral/r1__metrics.json`
- graveyard: this file

**R-2 NOT DISPATCHED (strict halt per user spec).**
