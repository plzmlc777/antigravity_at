# paradigm 163 — `alt_microstructure_orderflow_imbalance_cvd_divergence_post_session_open_continuation_directional_4h`

## Dispatch context

- Source: §6.60 paradigm 162 next-action Option ζ (Lesson #61 amendment 5th post-confirmation STRICT)
- User dispatch policy: continuous-parallel + persistence amendment (no time-gating dispatch)
- Hypothesis class: 2-axis joint (CVD divergence × post-session-open anchor) × directional 4h continuation

## Hypothesis (user-provided text)

- Trigger statistic 1: per-symbol CVD proxy = rolling 4h `taker_buy_quote_volume - implied_sell_volume` (or imbalance ratio centered at 0.5)
- Trigger statistic 2: price direction (close-to-close) vs CVD direction sign mismatch = divergence event
- Anchor: session open boundary {00:00, 08:00, 16:00} UTC ± 1 bar
- Forward window: 4h hold continuation in CVD-sign direction
- 4-quadrant SNT: A pos divergence × LONG cont / A mirror × SHORT / B neg divergence × SHORT cont / B mirror × LONG

## R-0 INVENTORY HALT — Lesson #61 amendment 5th post-confirmation dogfood (STRICT)

**Verdict**: `R0_HALT_BY_DENSE_PRIOR_FALSIFICATION_TRIPLE_FAMILY_PROXY_LESSON_61_AMENDMENT_5TH_POST_CONFIRMATION_DOGFOOD_SUCCESS`

**Decision rationale**: §6.60 next-action recommendation explicitly cited "CVD family 1 graveyard only (paradigm 86, funding-conditioned 변형)" — but exhaustive slug grep of `research_track/` reveals **three intersecting OUTCOME-LEVEL families** all with multiple graveyards inside the proposed hypothesis envelope. Lesson #61 amendment STRICT post-confirmation mandates surfacing this discovery PRE-dispatch.

## Slug grep audit (Lesson #61 amendment §1)

Grep `^alt_.*(cvd|orderflow|taker_buy|imbalance|session_open|microstructure)`:

| Slug | Paradigm | Verdict | Substrate overlap with paradigm 163 |
|---|---|---|---|
| `alt_funding_rate_x_cvd_4h_divergence_smart_money_distribution_directional_4h` | **138** | R0_HALT (Lesson #40 3rd dogfood) | CVD ratio 4h × directional 4h **identical statistic family** |
| `alt_funding_per_sym_30d_zscore_x_cvd_4h_divergence_directional_4h` | **139** | R0_HALT (Lesson #40 4th dogfood) | CVD ratio 4h × directional 4h **identical statistic family** |
| `alt_funding_per_sym_30d_zscore_NEG_ONLY_x_cvd_4h_negative_2quadrant_SNT_directional_4h` | **140** | R0_HALT (Lesson #11 joint density) | CVD ratio 4h × directional 4h **identical statistic family** |
| `alt_funding_per_sym_30d_zscore_NEG_ONLY_alone_SHORT_continuation_4h` | **141** | R-1 BROAD_FALSIFIED | Lesson #56 family direction-inversion 3rd dogfood |
| `alt_taker_buy_quote_vol_imbalance_z_directional_4h` | **142** | R-1 BROAD_FALSIFIED (0/4 quadrants) | **taker_buy_quote_volume imbalance 4h × directional 4h IDENTICAL** to paradigm 163 axis 1 |
| `alt_taker_buy_quote_vol_percentile_rank_directional_8h` | **143** | R-1 BROAD_FALSIFIED | quote_vol axis family **Tier 4 retire eligible** (Lesson #57 2nd POSITIVE dogfood) |
| `taker_buy_volume_5m_zscore_signcond` | **72** | R-1 BROAD_FALSIFIED | taker-side aggressive volume family **Tier 4 retire formal** |
| `intraday_session_open_alt_oi_acceleration_directional_30m` | **122** | R-1 BROAD_FALSIFIED (Lesson #21 4th dogfood) | **session open 00/08/16 UTC anchor** + 30m IDENTICAL to paradigm 163 anchor axis, hold 30m vs 4h only differs |
| `alt_session_boundary_NY_close_21UTC_anchored_directional_4h` | **157** | R-1 BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED_LESSON39B | **Lesson #68 candidate 1st dogfood** "Session-boundary anchor × 4h hold cross-asset fee-floor-bound mechanism-inverted antipattern" |
| `intraday_hour_of_day_anchor_alt_directional_2h` | **113** | R-1 BROAD_FALSIFIED | temporal anchor axis (paradigm 122 reference) — 0/13 syms ci_pos all 4 quadrants |

**Total proximate graveyards**: 10 (excluding R-5 LIVE paradigm 22 funding_carry which uses none of these axes).

## DNA 4-dim audit table (Lesson #61 amendment §2)

| Dim | paradigm 142 (closest) | paradigm 122 (anchor twin) | paradigm 157 (Lesson #68 1st) | paradigm 163 (this) | vs 142 | vs 122 | vs 157 |
|---|---|---|---|---|---|---|---|
| Statistic class | taker_buy_quote_vol imbalance ratio z (4h) | OI velocity z + temporal anchor | session boundary cross-asset | CVD divergence (price vs CVD sign mismatch) + post-session anchor | **BOUNDARY** (CVD divergence is composite of imbalance ratio direction + price direction — paradigm 142 statistic is single-axis subset) | partial | partial |
| Universe | 14 alts | 13 alts | 14 alts | 13 alts | identical | identical | identical |
| Entry-side class | imbalance |z| threshold (always-on) | session open + |z| dual-anchor | session boundary cross-up | post-session-open ± 1 bar × divergence event | partial | **STRICT_FAIL** (same anchor 00/08/16 UTC) | partial |
| Mechanism alpha | aggressive taker imbalance → 4h continuation | OI velocity + anchor → 30m continuation | session boundary → 4h continuation | CVD divergence + anchor → 4h continuation | **STRICT_FAIL** (both = aggressive flow → continuation 4h) | partial | **STRICT_FAIL** (both = anchor → 4h continuation) |
| Hold | 4h | 30m | 4h | 4h | identical | partial | identical |

**Strict count**:
- vs paradigm 142: **1/5 STRICT** (universe partial, others all overlapping) — **Lesson #62 STRICT family-distinct FAIL** (requires ≥2/5 STRICT)
- vs paradigm 122: **1/5 STRICT** (statistic class boundary, anchor STRICT_FAIL identical) — **Lesson #62 FAIL**
- vs paradigm 157: **1/5 STRICT** (statistic class boundary, mechanism STRICT_FAIL) — **Lesson #62 FAIL**

**Verdict: family-distinct strict 4-dim audit FAILS against 3 prior R-1 graveyards independently.**

## Family-retire eligibility cross-reference (Lesson #61 amendment §3)

| Family | Member graveyards | Tier 4 retire status | paradigm 163 violation |
|---|---|---|---|
| **taker-side aggressive volume** | 23 + 60 + 72 + 142 + 143 | **FORMAL TIER 4** (Q3 §6.2 #10 + Lesson #57 elevation) | YES — CVD = taker_buy − taker_sell composite, direct family member |
| **session-boundary anchor cross-asset × 4h** | 157 (1 graveyard, 113 + 122 adjacent) | **Lesson #68 candidate 1st dogfood** (1 more dogfood → CONFIRMED) | YES — paradigm 163 = explicit 2nd dogfood path |
| **funding × CVD joint** | 138 + 139 + 140 + 141 (4 graveyards) | Funding family Tier 4 + CVD axis 3-graveyard zone | partial (paradigm 163 drops funding axis, but CVD axis remains family-proxy) |
| **temporal anchor + magnitude conjunction** | 113 + 122 (Lesson #21 4th dogfood) | Lesson #21 antipattern confirmed | YES — paradigm 163 = anchor (00/08/16 UTC) × CVD magnitude direction = Lesson #21 stacking |

## Prior R-3+ outcome reference (Lesson #61 amendment §4)

- **paradigm 142 R-1 4-quadrant detail**: A focus pos×LONG net -7.83bp sigex -0.76 / B focus neg×SHORT net -1.69bp sigex +1.82 perm_p 0.972 — **closest empirical proxy**. Paradigm 142 used `taker_buy_quote_volume / quote_volume` imbalance ratio z (continuous, not divergence event); paradigm 163 adds divergence trigger which **reduces** sample density and adds Lesson #21 axis stacking burden. **Empirical proxy: paradigm 163 expected gross < paradigm 142 gross by mechanism subsumption.**
- **paradigm 122 R-1 4-quadrant detail**: A_focus pos→LONG net -7.02bp sigex +16.36 (inflated artifact, ci_lower -15.88), 0/13 syms ci_pos all 4 quadrants. **Same 00/08/16 UTC anchor + axis stacking** = identical predictive null.
- **paradigm 157 R-1 4-quadrant detail**: Q1 UP_LONG focus_CONT +0.79bp sigex +2.98 ci_lower -3.62 (fee-recovery zero edge), Lesson #39 sub-class B (Q3 DOWN_SHORT focus -15.38bp vs Q4 DOWN_LONG mirror -0.62bp = mechanism inverted DOWN side). **Direct predictive proxy** for paradigm 163 if session-anchor mechanism alpha exists.
- **paradigm 113 R-1**: temporal anchor 00/07/13/21 UTC × |z| ≥ 1, 0/13 syms ci_pos all 4 quadrants — temporal anchor axis itself null.

## Substrate availability (Lesson #28) — PASS but blocked

- 4h 12-col joblib cache: 14 syms verified (`ADAUSDT/AVAXUSDT/BCHUSDT/BNBUSDT/BTCUSDT/DOGEUSDT/ETHUSDT/FILUSDT/LINKUSDT/LTCUSDT/NEARUSDT/SOLUSDT/WIFUSDT/XRPUSDT`)
- `taker_buy_volume` + `taker_buy_quote_volume` + `count` columns available
- CVD proxy computable via `taker_buy_quote_volume - (quote_volume - taker_buy_quote_volume)` per 4h bar
- Substrate sufficient; halt is family-proxy + axis-stacking, NOT substrate.

## Lesson #21 axis-stacking risk (CRITICAL §4)

paradigm 163 = CVD divergence axis × session open anchor axis = **2-axis stacking**.

| Axis | Independent null verification | Source |
|---|---|---|
| CVD-direction / taker-imbalance axis | NULL (paradigm 142 4-quadrant 0/4 PASS sigex_max +1.82 perm_p 0.972) | paradigm 142 |
| Session-open 00/08/16 UTC anchor | NULL (paradigm 122 0/13 syms ci_pos all 4 quadrants) | paradigm 122 |

**Lesson #21 antipattern materialization**: stacking two **empirically-null axes** does NOT synthesize alpha. paradigm 122 is the **exact precedent**: OI velocity (null) × session open 00/08/16 UTC (null) → 0/13 syms ci_pos all 4 quadrants.

paradigm 163 substitutes the null axis "OI velocity z" with "CVD divergence" — but CVD divergence axis is **also empirically null** (paradigm 142 evidence). Lesson #21 5th dogfood predictive verdict: paradigm 163 R-1 will produce 0/13 syms ci_pos all 4 quadrants identical to paradigm 122.

## Lesson #68 candidate 2nd dogfood direct application

paradigm 157 established Lesson #68 candidate "Session-boundary anchor × 4h hold cross-asset = fee-floor-bound mechanism-inverted antipattern" 1st dogfood (NY close 21 UTC × 4h hold cross-asset 14 alts).

paradigm 163 = post-session-open 00/08/16 UTC × 4h hold cross-asset 13 alts = **direct 2nd dogfood path**.

Per paradigm 157 graveyard §Lesson #68 candidate text: "Required for CONFIRMED 자격: 1+ more dogfood (e.g., London close 16 UTC anchor, Asia open 00 UTC anchor with similar 4h × cross-asset structure)" — paradigm 163 covers Asia open 00 UTC + 08 UTC + 16 UTC simultaneously. **R-1 execution of paradigm 163 would deliver Lesson #68 CONFIRMED elevation** but at expected cost of paradigm 163 BROAD_FALSIFIED outcome (predicted by Lesson #21 + Lesson #56 + Lesson #68).

## Lesson #56 OUTCOME-LEVEL family proxy 15th instance prediction

Per Lesson #56 14-instance pattern (last instance §6.60 paradigm 162 magnitude-event family):

> axis-novelty (STRICT 3/5) alone alpha 보장 불가 결정적; OUTCOME-LEVEL family proxy (same statistic class + same hold + same universe) bound

paradigm 163 fails STRICT family-distinct against 3 prior R-1 graveyards (142 + 122 + 157), **fails Lesson #62 strict count (1/5 each)** — Lesson #56 15th instance pre-dispatch identifiable.

## paradigm 86 reference clarification (Lesson #61 amendment §1 STRICT correction)

§6.60 next-action recommendation cited "paradigm 86 funding-conditioned CVD 1 graveyard only". Audit reveals:

- paradigm 86 actual slug: `multi_day_vol_persistence_3d_alt_long_1d`
- paradigm 86 actual verdict: SAMPLE_INSUFFICIENT (Lesson #24, boundary-event horizon density)
- paradigm 86 does NOT involve CVD or funding-conditioned CVD

**§6.60 paradigm 86 reference was a factual error in the recommendation framework.** Actual CVD-family graveyards: 138 + 139 + 140 (3 R-0 halts) + 141 (R-1 BROAD_FALSIFIED) + 142 (R-1 BROAD_FALSIFIED) + 143 (R-1 BROAD_FALSIFIED) = **6 CVD/taker-side adjacent graveyards**, not 1.

This **factual error invalidates the §6.60 next-action recommendation Option ζ**. Lesson #61 amendment 5th post-confirmation STRICT dogfood **SURFACED the error pre-dispatch** — amendment template functioning as designed.

## Decision

**R-1 NOT DISPATCHED.** R-0 inventory check halt at family-proxy density.

**Halt category**: `R0_HALT_BY_DENSE_PRIOR_FALSIFICATION_TRIPLE_FAMILY_PROXY`

Per paradigm-architect spec failure protocols:
> Dogfood mismatch | STOP and re-validate gate config — do not promote until reconciled

The dogfood mismatch here is between §6.60 next-action recommendation (cited "CVD family 1 graveyard only") and actual archive state (6 adjacent graveyards). Lesson #61 amendment 5th post-confirmation STRICT dogfood **SUCCEEDED** by surfacing this mismatch.

## Counter update (campaign-level)

- Cumulative graveyards: **162 → 163** (R-0 inventory halt counted per paradigm 138/139/140 precedent — R-0 halt with formal inventory audit + verdict signature increments counter)
- Non-PASS streak: **32 → 33**
- R-5 LIVE: 11 (unchanged)
- R-5 yield: 11/163 = **6.75%**
- Lesson #61 amendment post-confirmation dogfoods: 4 → **5 consecutive SUCCESS** (amendment template 영구 자산화 6th-eligible at next instance)
- Lesson #68 candidate dogfoods: 1 (paradigm 157) → **1.5** (paradigm 163 PRE-dispatch logical extension; FORMAL 2nd dogfood deferred until R-1 dispatch decision)

## Recommended path forward (paradigm 164 candidate)

Per [[feedback-direct-recommendation]] STRICT — single recommendation, no option enumeration.

**Direct recommendation**: paradigm 164 = `alt_bvol_implied_vol_term_structure_inversion_directional_4h`

Rationale:
1. **Family-distinct STRICT 4-dim audit**: implied volatility (Deribit BVOL) term structure inversion is a NEW axis class — zero prior paradigm uses options-derived implied vol.
2. **Substrate verification needed (Lesson #28)**: Deribit BVOL has public free API (no freemium trap per [[feedback-no-freemium-trial]]) — verify in R-0 STEP 2.
3. **Mechanism class**: term-structure inversion (front-month IV > back-month IV) is **forward-looking trader stress indicator** distinct from realized statistics (paradigm 142/143 axis), distinct from session-boundary anchor (paradigm 122/157 axis), distinct from funding-axis (Tier 4 retire family).
4. **Lesson #21 escape**: single-axis paradigm (term structure ratio is one statistic, not joint with anchor).
5. **Lesson #56 family-proxy LOW**: zero prior implied-vol paradigm = zero family graveyards.
6. **Lesson #67 ESCAPE**: per-symbol BVOL exists only for BTC + ETH on Deribit — paradigm scope = BTC + ETH bilateral, not cross-asset broadcast.
7. **Lesson #68 ESCAPE**: not session-boundary axis.

**Risk**: substrate availability prescreen (Deribit BVOL public endpoint) must PASS at R-0 STEP 2. If fails, fallback paradigm 164 candidate = `alt_perp_swap_basis_term_structure_8h_vs_3m_funding_implied_carry_directional_4h` (perp 8h funding implied annualized rate vs forward-curve carry differential, substrate = funding DB which is verified).

## Artifacts

- This task md: `backend/runs/research_track/alt_microstructure_orderflow_imbalance_cvd_divergence_post_session_open_continuation_directional_4h/TASK.md`
- R-0 prescreen: NOT EXECUTED (halt at inventory audit, prior to STEP 1)
- INDEX.json entry: pending registration (R0_HALT verdict)
- PARADIGM_QUEUE_2026Q3.md §6.61 entry: pending append

## Lesson amendment proposals (Q3 §6.61 ratification batch)

| Lesson | Status update | Notes |
|---|---|---|
| **#61 amendment** | 4 → **5 consecutive post-confirmation SUCCESS** | amendment template surfaced §6.60 paradigm 86 factual error pre-dispatch |
| **#56** OUTCOME-LEVEL FAMILY PROXY | 14 → **15 instances** (triple family overlap CVD+session+temporal-anchor 사전 detection) |
| **#68** candidate session-boundary 4h cross-asset | 1 dogfood (157) → **1 dogfood + 1 PRE-dispatch logical extension** (163) — formal CONFIRMED elevation pending one additional R-1 execution from session-boundary class |
| **#62** family-distinct strict | 7 → **8 boundary dogfoods** (paradigm 163 vs 3 prior R-1 graveyards independently 1/5 STRICT each = compound failure) |
| **NEW #69 candidate** | "next-action recommendation factual audit obligation" | §6.60 cited paradigm 86 as CVD precedent but paradigm 86 is `multi_day_vol_persistence_3d` — recommendation framework must verify cited precedent paradigm number + verdict + slug before issuing next-paradigm recommendation. paradigm 163 R-0 halt = 1st dogfood. |

---

**END R-0 INVENTORY HALT**. paradigm 163 graveyard formalized per Lesson #61 amendment 5th post-confirmation STRICT dogfood. paradigm 164 권고 = `alt_bvol_implied_vol_term_structure_inversion_directional_4h` (implied vol term structure NEW axis class, substrate verification needed).
