# Graveyard — paradigm 163 `alt_microstructure_orderflow_imbalance_cvd_divergence_post_session_open_continuation_directional_4h`

**Verdict**: `R0_HALT_BY_DENSE_PRIOR_FALSIFICATION_TRIPLE_FAMILY_PROXY_LESSON_61_AMENDMENT_5TH_POST_CONFIRMATION_DOGFOOD_SUCCESS`
**Phase reached**: R-0 inventory audit (PRE-prescreen STEP 1; R-1 NOT DISPATCHED)
**Date (KST)**: 2026-05-21 21:14
**Cumulative graveyards**: 162 → **163**
**Non-PASS streak**: 32 → **33**

## Hypothesis (user-dispatched per §6.60 Option ζ)

- Trigger statistic 1: per-symbol CVD proxy = rolling 4h `taker_buy_quote_volume - implied_sell_volume` (imbalance ratio direction)
- Trigger statistic 2: price direction (close-to-close) vs CVD direction sign mismatch = divergence event
- Anchor: session open boundary {00:00, 08:00, 16:00} UTC ± 1 bar
- Forward window: 4h directional hold continuation in CVD-sign direction
- 4-quadrant SNT: A pos divergence × LONG cont / A mirror × SHORT / B neg divergence × SHORT cont / B mirror × LONG
- Universe: 13 alts
- Hold: 4h primary + 8h/12h sweep

## R-0 inventory audit (Lesson #61 amendment 5th post-confirmation STRICT)

### §1 — Slug grep result (10 proximate graveyards)

```
research_track/ | grep -iE "cvd|orderflow|taker_buy|imbalance|session_open|microstructure"
```

| # | Slug | Paradigm | Verdict | Family |
|---|---|---|---|---|
| 1 | `taker_buy_volume_5m_zscore_signcond` | 72 | R-1 BROAD_FALSIFIED | taker-side aggressive volume Tier 4 |
| 2 | `intraday_session_open_alt_oi_acceleration_directional_30m` | 122 | R-1 BROAD_FALSIFIED (Lesson #21 4th dogfood) | OI velocity × session anchor Tier 4 |
| 3 | `intraday_hour_of_day_anchor_alt_directional_2h` | 113 | R-1 BROAD_FALSIFIED | temporal anchor axis |
| 4 | `alt_funding_rate_x_cvd_4h_divergence_smart_money_distribution_directional_4h` | 138 | R-0 HALT (Lesson #40 3rd dogfood) | funding × CVD joint |
| 5 | `alt_funding_per_sym_30d_zscore_x_cvd_4h_divergence_directional_4h` | 139 | R-0 HALT (Lesson #40 4th dogfood) | funding × CVD joint |
| 6 | `alt_funding_per_sym_30d_zscore_NEG_ONLY_x_cvd_4h_negative_2quadrant_SNT_directional_4h` | 140 | R-0 HALT (Lesson #11 joint density) | funding × CVD joint |
| 7 | `alt_funding_per_sym_30d_zscore_NEG_ONLY_alone_SHORT_continuation_4h` | 141 | R-1 BROAD_FALSIFIED | funding direction inversion |
| 8 | `alt_taker_buy_quote_vol_imbalance_z_directional_4h` | 142 | R-1 BROAD_FALSIFIED (4-quadrant 0/4 PASS) | **taker_buy_quote_volume imbalance 4h IDENTICAL paradigm 163 axis 1** |
| 9 | `alt_taker_buy_quote_vol_percentile_rank_directional_8h` | 143 | R-1 BROAD_FALSIFIED (quote_vol family Tier 4 eligible) | taker-side aggressive volume |
| 10 | `alt_session_boundary_NY_close_21UTC_anchored_directional_4h` | 157 | R-1 BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED_LESSON39B | **Lesson #68 candidate 1st dogfood** session-boundary × 4h cross-asset |

### §2 — DNA 4-dim audit table

| Dim | p142 (taker imbalance 4h) | p122 (session open 00/08/16 × OI vel) | p157 (NY close 21 UTC) | **p163** (this) | vs 142 | vs 122 | vs 157 |
|---|---|---|---|---|---|---|---|
| Statistic class | taker_buy_quote_vol imbalance z (4h) | OI velocity z + temporal anchor | session boundary cross-asset | CVD divergence (price vs CVD sign mismatch) + post-session anchor | BOUNDARY (CVD divergence = imbalance direction + price sign mismatch; paradigm 142 statistic is imbalance subset) | partial | partial |
| Universe | 14 alts | 13 alts | 14 alts | 13 alts | identical | identical | identical |
| Entry-side class | |z| ≥ 2 threshold (always-on) | session open + |z| dual-anchor | session boundary cross-up | post-session-open ± 1 bar × divergence event | partial | **STRICT_FAIL** (same anchor 00/08/16 UTC) | partial |
| Mechanism alpha | aggressive taker imbalance → continuation | OI velocity + anchor → continuation | session boundary → continuation | CVD divergence + anchor → continuation | **STRICT_FAIL** (both = aggressive flow continuation 4h) | partial | **STRICT_FAIL** (both = anchor → 4h continuation) |
| Hold | 4h | 30m | 4h | 4h | identical | partial | identical |

**Strict count summary** (Lesson #62 ≥2/5 STRICT 의무):
- vs paradigm 142: **1/5 STRICT** → Lesson #62 FAIL
- vs paradigm 122: **1/5 STRICT** → Lesson #62 FAIL
- vs paradigm 157: **1/5 STRICT** → Lesson #62 FAIL

**Triple compound family-distinct failure** — 1/5 STRICT against EACH of 3 prior R-1 graveyards independently.

### §3 — Family-retire cross-reference

| Family | Members | Tier 4 status | paradigm 163 status |
|---|---|---|---|
| taker-side aggressive volume | 23 + 60 + 72 + 142 + 143 | **FORMAL TIER 4** (Q3 §6.2 #10 + Lesson #57) | VIOLATION — CVD = taker_buy − taker_sell composite |
| session-boundary anchor × 4h cross-asset | 157 (+ 113, 122 adjacent) | **Lesson #68 candidate 1st dogfood** | DIRECT 2ND DOGFOOD PATH (if R-1 dispatched) |
| funding × CVD joint | 138 + 139 + 140 + 141 | Funding family Tier 4 retire | adjacent (paradigm 163 drops funding, but CVD axis remains 6-graveyard zone) |
| temporal anchor + magnitude conjunction | 113 + 122 (Lesson #21 4th dogfood) | Lesson #21 antipattern confirmed | VIOLATION — anchor (00/08/16) × CVD magnitude direction = 2-axis stacking |

**Family-proxy density**: paradigm 163 hypothesis envelope intersects **3 separate family clusters** with cumulative 10 proximate graveyards. Lesson #56 OUTCOME-LEVEL family proxy 15th instance pre-dispatch identifiable.

### §4 — Lesson #21 axis-stacking predictive verdict

paradigm 163 = CVD divergence axis × session open anchor axis = 2-axis stacking.

| Axis | Independent null evidence |
|---|---|
| CVD-direction / taker imbalance axis | NULL — paradigm 142 4-quadrant 0/4 PASS, max sigex +1.82 perm_p 0.972 (B_focus neg×SHORT artifact, fee-floor sub-grade) |
| Session-open 00/08/16 UTC anchor | NULL — paradigm 122 0/13 syms ci_pos all 4 quadrants (broad uniform negative across full panel n=14,925) |

paradigm 163 = paradigm 122 anchor axis + paradigm 142 statistic axis = stacking **two empirically-null axes** = Lesson #21 5th dogfood predictive null.

### §5 — paradigm 86 reference factual error correction (Lesson #69 NEW candidate)

§6.60 Option ζ next-action recommendation cited: "CVD family 1 graveyard only (paradigm 86, funding-conditioned 변형)".

Audit reveals:

| Reference | §6.60 cited | Actual archive state |
|---|---|---|
| paradigm 86 slug | "funding-conditioned CVD" (implied) | `multi_day_vol_persistence_3d_alt_long_1d` |
| paradigm 86 verdict | "graveyard" | SAMPLE_INSUFFICIENT (Lesson #24 boundary-event horizon density) |
| paradigm 86 axis | CVD | multi-day realized vol persistence streak length |

**§6.60 recommendation framework cited a non-existent CVD precedent.** Actual CVD-family graveyards = 6 (138 + 139 + 140 + 141 + 142 + 143), not 1.

This factual error invalidates §6.60 Option ζ DISPATCH RECOMMENDED verdict — actual CVD family graveyard density is **6× higher** than cited. Lesson #61 amendment 5th post-confirmation STRICT dogfood SURFACED this pre-dispatch.

### §6 — Substrate availability (Lesson #28) PASS

- 4h 12-col joblib cache 14 syms verified
- `taker_buy_volume` + `taker_buy_quote_volume` + `count` columns available
- CVD proxy computable
- **Substrate sufficient — halt is NOT substrate, halt is family-proxy + axis-stacking + factual-error correction**

### §7 — Lesson #11 sample density (informational PASS)

- 13 alts × 2.25yr × 4h bars ≈ 67,000 base obs
- Session open boundary 3/day × CVD divergence ~10-20% events ≈ 2,000-4,000 events
- Per-quadrant ≥ 500: PASS

### §8 — Lesson #30 data window ratio (PASS)

- 2.25yr / 2.4yr = 93.75% PASS

## Decision

**R-1 NOT DISPATCHED.** R-0 inventory audit halt PRIOR to STEP 1 prescreen execution.

Halt cause: triple compound family-proxy density (Lesson #56 15th instance) + Lesson #21 axis-stacking predictive null + Lesson #62 strict family-distinct 1/5 against 3 prior graveyards + §6.60 recommendation factual error (paradigm 86 misidentification).

Per paradigm-architect spec failure protocols:
> Dogfood mismatch | STOP and re-validate gate config — do not promote until reconciled.

Lesson #61 amendment 5th post-confirmation STRICT dogfood **functioned as designed** — surfaced §6.60 paradigm 86 cited-precedent factual error PRE-dispatch.

## Lesson #68 candidate 2nd dogfood — DEFERRED

paradigm 163 R-1 execution would deliver Lesson #68 candidate 2nd dogfood (session-boundary 00/08/16 UTC × 4h cross-asset). Predicted outcome BROAD_FALSIFIED (Lesson #21 + Lesson #56 + Lesson #68 pattern alignment).

**However**: R-1 dispatch would consume 2.85+ min wall clock + add 1 more graveyard to streak for **predictable outcome** with NO new mechanism information beyond Lesson #68 CONFIRMED elevation.

Lesson #61 amendment 5th post-confirmation STRICT dogfood explicitly designed to AVOID this — predictable-outcome dispatch is amendment failure mode. **HALT at R-0 inventory is the amendment SUCCESS path.**

Lesson #68 CONFIRMED elevation deferred to next session-boundary paradigm with **DIFFERENT** axis profile (e.g., London close 16 UTC × different statistic class, or session-boundary × cross-sectional rank instead of CVD divergence).

## NEW Lesson #69 candidate (1st dogfood)

**"Next-action recommendation factual audit obligation"**:

> R-0 inventory audit must verify cited precedent paradigm number + verdict + slug before accepting next-paradigm recommendation. Lesson #61 amendment §1 slug grep MUST cross-check against §next-action recommendation table cited precedents. paradigm 163 R-0 halt = 1st dogfood (§6.60 paradigm 86 misidentification as CVD precedent surfaced pre-dispatch).

Required for CONFIRMED 자격: 1+ more dogfood (next paradigm where next-action table cites incorrect precedent paradigm + Lesson #61 amendment §1 slug grep surfaces correction).

## Counter update

- Cumulative graveyards: **162 → 163**
- Non-PASS streak: **32 → 33**
- R-5 LIVE: 11 (unchanged; lifecycle_pump_decay R-5 promotion 2026-05-21 20:14 KST 보존)
- R-5 yield: 11/163 = **6.75%**
- Lesson #61 amendment post-confirmation dogfoods: 4 → **5 consecutive SUCCESS** (영구 자산화 6th-eligible)
- Lesson #56 OUTCOME-LEVEL FAMILY PROXY instances: 14 → **15**
- Lesson #62 family-distinct strict boundary dogfoods: 7 → **8**
- NEW Lesson #69 candidate 1st dogfood (next-action factual audit obligation)
- Lesson #68 candidate dogfoods: 1 (paradigm 157) — **unchanged** (paradigm 163 deferred per HALT decision)
- D-Day 2026-06-03: D-13
- paradigm 127+128 Day 7 baseline: D-7 (2026-05-28)

## paradigm 164 next-action recommendation (Lesson #61 amendment 6th post-confirmation STRICT)

Per [[feedback-direct-recommendation]] — single recommendation, no option enumeration.

**Direct recommendation**: paradigm 164 = `alt_bvol_implied_vol_term_structure_inversion_directional_4h`

| Audit dim | Result |
|---|---|
| Lesson #61 amendment §1 slug grep | `^alt_.*(bvol\|implied_vol\|term_structure\|deribit)` → **0 results** in archive |
| Lesson #62 family-distinct strict 4-dim | 4/5 STRICT — NEW statistic class (forward-looking IV, not realized), NEW substrate (Deribit options), NEW mechanism class (trader stress forward indicator), partial universe overlap (BTC+ETH only) |
| Lesson #56 OUTCOME-LEVEL family proxy | LOW — zero prior implied-vol paradigm in 163 archive |
| Lesson #21 axis stacking | ESCAPE — single statistic (term structure ratio front/back) |
| Lesson #28 substrate availability | **VERIFICATION NEEDED** — Deribit BVOL public API (free, no freemium per [[feedback-no-freemium-trial]]); R-0 STEP 2 must verify endpoint + data history ≥ 1yr |
| Lesson #67 ESCAPE | per-symbol BVOL (BTC + ETH only) — NOT cross-asset broadcast |
| Lesson #68 ESCAPE | NOT session-boundary axis |
| Lesson #11 sample density | 2.25yr × 8h funding cycle × 2 syms × IV inversion event rate ~5% → ~200 events / 2 syms = 100/sym, per-quarter ~12 < 30 cutoff RISK — universe expansion needed to 4-5 syms (Deribit options coverage limited) |

**Risk**: Lesson #11 sample density marginal (2 syms × 2.25yr × event rate ~5% = ~200 events total). If R-0 sample-density prescreen FAIL → fallback paradigm 164 = `alt_perp_swap_basis_term_structure_8h_funding_vs_3m_calendar_carry_differential_directional_4h` (perp 8h funding implied annualized rate vs forward-curve carry differential, substrate = funding DB which is verified, universe = 13 alts not 2).

**HALT 권고** (Lesson #61 amendment STRICT template):
- Any anchor + CVD/taker-side axis variation (paradigm 163 family-proxy violation)
- Any session-boundary × 4h variant (paradigm 157 Lesson #68 antipattern)
- Any OI velocity + temporal anchor variant (paradigm 122 Lesson #21 4th dogfood + Tier 4 retire)
- Any funding-axis variant (paradigm 22 + funding_dispersion ETC exceptions only)
- Any magnitude-event family variant (paradigm 117 + 158 + 162 + lifecycle_pump_decay R-5 protection; sub-axis additional R-1 차단 per 사용자 직접 ratify §6.60)

## paradigm-architect spec amendment 권고 (Q3 §6.61 ratification batch)

| Lesson | Status update |
|---|---|
| **#61 amendment** | 4 → **5 consecutive post-confirmation SUCCESS** (paradigm 163 surfaced §6.60 paradigm 86 factual error pre-dispatch) — 영구 자산화 strengthened |
| **#56** OUTCOME-LEVEL FAMILY PROXY | 14 → **15 instances** (triple family overlap detection pre-dispatch) |
| **#62** family-distinct strict | 7 → **8 boundary dogfoods** (paradigm 163 vs 3 prior R-1 graveyards independently 1/5 STRICT compound failure) |
| **#68 candidate** session-boundary 4h cross-asset | 1 (paradigm 157) — **unchanged** (paradigm 163 R-1 deferred per HALT) |
| **NEW #69 candidate** | "next-action recommendation factual audit obligation" — 1st dogfood (paradigm 163 surfaced §6.60 paradigm 86 misidentification) |
| **#42** mechanism CLASS asymmetric | CONFIRMED (3 dogfoods 117/158/162) per §6.60 ratification batch — paradigm-architect Lesson prescreen registered |
| **#21** axis stacking | 4 → **5th predictive dogfood** (paradigm 163 R-0 halt cited Lesson #21 + paradigm 122 anchor null + paradigm 142 axis null compound prediction; formal 6th dogfood deferred to R-1 actual measurement) |

## Artifacts

- TASK md: `backend/runs/research_track/alt_microstructure_orderflow_imbalance_cvd_divergence_post_session_open_continuation_directional_4h/TASK.md`
- Graveyard report: this file
- R-0 prescreen: NOT EXECUTED (halt at inventory audit pre-STEP 1)
- R-1 script: NOT WRITTEN
- INDEX.json entry: pending registration with R0_HALT verdict + graveyard_reason
- PARADIGM_QUEUE_2026Q3.md §6.61 entry: pending append

---

**END R-0 INVENTORY HALT — paradigm 163 graveyard 163rd**. Lesson #61 amendment 5th post-confirmation STRICT dogfood SUCCESS: §6.60 cited paradigm 86 factual error surfaced + triple family-proxy density detected + Lesson #21 + Lesson #56 + Lesson #62 + Lesson #68 + NEW Lesson #69 candidate 1st dogfood + Funding/taker-side/session-boundary family retires reinforced. paradigm 164 권고 `alt_bvol_implied_vol_term_structure_inversion_directional_4h` (NEW implied-vol axis, Deribit substrate verification needed) 또는 fallback `alt_perp_swap_basis_term_structure_carry_differential_directional_4h` (funding DB substrate verified).
