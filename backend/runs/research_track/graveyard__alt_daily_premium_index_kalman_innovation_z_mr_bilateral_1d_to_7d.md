# Graveyard: alt_daily_premium_index_kalman_innovation_z_mr_bilateral_1d_to_7d

**Paradigm #**: 227 (proposed as 226; renumbered — 226 already occupied by `paradigm_226_alt_fear_greed_index_extreme_contrarian_bilateral_1d` GRAVEYARD_R1 2026-07-14)
**Date**: 2026-07-15
**Phase Failed**: R-0 (prescreen halt — R-1 NOT dispatched)
**Verdict Code**: `R0_HALT_BY_FAMILY_PROXY_LESSON_61_SLUG_GREP_HIT_LESSON_56_OUTCOME_LEVEL_PREMIUM_DOMAIN_SATURATED_RETIRED_LESSON_69_5ITEM_TEMPLATE_LESSON_62_DNA_HARD_FAIL`

## Hypothesis (one-liner)

Per-symbol daily Binance premium index (perp/spot composite - 1) fit with per-sym Kalman local-level+drift filter; innovation z-score |z|>=2 trigger; 4-quadrant SNT × hold 1d/3d/5d/7d MR back to filter trend.

## Failure Mode — R-0 Prescreen (5-item Lesson #69 template)

### Item 1 — Lesson #61 slug grep (permanent asset)

**Slug hit**: `kalman_filter_premium_innovation` appears literally in `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` under §Retire table:

```
| #10 | `kalman_filter_premium_innovation` | premium domain saturated |
```

Same slug also appears in:
- `backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md` candidate #10 (canonical retired queue)
- PARADIGM_QUEUE_2026Q3.md §0 TL;DR row 10 (original candidate spec)

**Prior-family graveyards on premium/basis substrate** (5-item enumeration):

| # | Paradigm | Substrate | Statistic class | Verdict |
|---|---|---|---|---|
| 22 | `funding_boundary_revertion` (per-sym premium z-score) | premium 1d | rolling z-score | **R-5 LIVE** (family-founder exception, saturates domain per Q2 §5) |
| 24 | `funding_carry_seasonality` | funding 1d | daily FOLLOW | **R-5 LIVE** (funding cousin exception) |
| 105 | mark-index basis percentile 4h MR | basis 4h | percentile rank | BROAD_FALSIFIED |
| 111 | binance perp mark-index basis extreme 4h directional | basis 4h | 7d z-score | BROAD_FALSIFIED (paradigm 111 §5.2 explicitly tested MR-direction escape from paradigm 22/24 daily FOLLOW — falsified) |
| 121 | `hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h` | basis 4h | **HMM (novel statistic) × basis conditioning** | BROAD_FALSIFIED_LESSON39_SYMMETRIC_NO_AXIS_SYNTHESIS_HMM_FILTER_INEFFECTIVE |
| 131 | `basis_spike_x_range_close_bidask_proxy` | basis 4h | z-spike joint | BROAD_FALSIFIED_LESSON_52A_LONG_DRIFT_ARTIFACT |
| 167 | (basis/markPrice 4h MR retry — R-0 HALT precedent) | basis 4h | any | R-0 HALT by quadruple-prior-family broad-falsified (Lesson #61 amendment 8th SUCCESS) |

Premium/basis family cumulative: 4 GRAVEYARDS + 1 prior R-0 HALT + 2 R-5 LIVE (paradigm 22/24 daily FOLLOW). Family-slice exemption already claimed and exhausted by paradigm 22/24 (only DAILY FOLLOW direction earns life-changing). Family-slice retire ratified at Q2 §5 "premium 도메인 saturated 결정 — 추가 derivative/transformation 시도 권장 안 됨".

**Critical paradigm 121 precedent**: HMM was the previous "novel statistic on same premium/basis substrate" attempt. Same escape logic ("Kalman is not HMM, is deterministic Gaussian filter") was analogically tried at paradigm 121 ("HMM is not rolling z-score, is latent discrete state"). Paradigm 121 was broad-falsified with Lesson #39 exact-symmetric mirror pattern + HMM filter thinning sample 14× while reducing gross drift 50%. Kalman filter has identical structural risk: it produces a residual on the same underlying series, which then triggers the same fee-floor-bound MR outcome direction as paradigm 22 already captures at daily scale.

### Item 2 — Lesson #56 outcome-level family proxy (17th+ instance)

Outcome direction matrix:
- Kalman innovation z>+2 (perp overpriced vs filter trend) → SHORT perp expecting MR
- Paradigm 22 R-5 LIVE per-sym premium z>threshold → daily FOLLOW (empirically direction is FOLLOW at 1d, NOT MR)
- Paradigm 111 §5.2 tested the MR direction on 4h basis → BROAD_FALSIFIED

**Outcome-level identity**: Kalman filter innovation on daily premium = signed residual proxy for "how far current premium is from its recent trend". At daily scale the mechanism direction that has been empirically validated for this substrate is FOLLOW (paradigm 22/24 R-5 LIVE), not MR. The proposed hypothesis argues MR — which is exactly the direction paradigm 111 already broad-falsified on 4h scale, and which paradigm 22 R-5 seed spec explicitly rejects at daily scale.

Lesson #56 outcome-level family proxy criterion: mechanism DIRECTION identical to already-falsified family sub-slice + same substrate + same time scale = R-0 HALT even before statistic-class comparison.

### Item 3 — Lesson #62 DNA 5-dim audit vs closest relatives

Audit vs paradigm 22 (family-founder, R-5 LIVE) and paradigm 121 (novel-statistic-on-basis attempt, BROAD_FALSIFIED):

| Dim | Proposed 227 | Paradigm 22 (R-5 LIVE) | Paradigm 121 (BROAD_FALSIFIED) |
|---|---|---|---|
| Substrate | premium 1d | premium 8h→derived | markPrice basis 4h |
| Statistic class | Kalman innovation z | Rolling z-score | HMM regime × basis extreme |
| Universe | 14 alts | 20 alts | 14 alts |
| Frame | 1d | 8h (derived from 1d) | 4h |
| Mechanism direction | MR to Kalman trend | FOLLOW daily continuation | MR to basis mean |

DNA overlap vs paradigm 22: 3.5/5 (substrate identical, universe identical, frame 1d essentially same as 8h derivation, direction OPPOSITE — this is the key concern: paradigm 22 empirically validated direction is FOLLOW; MR direction is the paradigm 111 falsified sub-slice).

DNA overlap vs paradigm 121: 3/5 (substrate cousins premium↔basis are near-identical arbitraged pair, statistic-class "novel filter/regime detector" IDENTICAL analogy, mechanism MR IDENTICAL, hold multi-day slightly different).

**Lesson #62 HARD FAIL threshold**: DNA overlap >= 3/5 with a broad-falsified predecessor when the differentiating dimension (statistic class) is itself the paradigm 121 already-tested escape variant → HARD FAIL.

### Item 4 — Q2 §5 premium domain saturation ratification (queue-level retire)

PARADIGM_QUEUE_2026Q3.md preamble (canonical policy):

> **제약**: premium 도메인 saturated 결정 — 추가 derivative/transformation 시도 권장 안 됨. 새 raw data 도메인 또는 novel statistical approach 우선.

The proposed hypothesis fails both prongs of this policy simultaneously:
1. "additional derivative/transformation on premium" — Kalman innovation is literally a transformation of the premium series.
2. "새 raw data 도메인 또는 novel statistical approach" — the novel statistical approach clause was already spent on HMM (paradigm 119/121) which broad-falsified; Kalman is the same category of "novel filter class applied to a saturated substrate", which is exactly what Q2 §5 retires.

Q2 §5 was ratified across 6 subsequent R-0 halts (paradigm 167 quadruple-prior + others) — permanent policy asset.

### Item 5 — Novelty budget check

Frontier scout continuous-parallel record (per PARADIGM_QUEUE_2026Q3.md §6.5): "5 consecutive frontier dispatches (paradigm 82+83+84+85+86) all halt/falsified", plus paradigm 168 meta-ratification of basis family retirement, plus paradigm 224/225/226 recent graveyards. The proposed 227 offers no NOVEL axis outside the retired-family perimeter:
- Substrate: retired-family perimeter (premium domain saturated Q2 §5).
- Statistic class novelty: Kalman = local-level+drift Gaussian filter; already-tested cousin HMM (discrete-state Gaussian mixture) broad-falsified at paradigm 121. Kalman is a different member of the same class ("latent-state filter on premium/basis"), not a fundamentally new class. The proposed hypothesis's own §5 acknowledges "Kalman is not HMM" — but paradigm 121's failure was NOT because HMM was somehow deficient; it was because Lesson #39 exact-symmetric mirror + fee-floor structural pattern applies to any latent-state filter on premium/basis substrate.
- Universe: 14 alts standard.
- Frame: 1d (paradigm 22 R-5 LIVE frame; direction MR opposite to seed).
- Mechanism: MR to filter trend = paradigm 111 falsified sub-direction.

Zero of 5 dimensions offers genuine novelty outside the retired perimeter. Frontier scout meta-limit (Lesson #21 corollary: axis stacking does not synthesize alpha on saturated substrate) applies.

## Lessons Dogfooded (12 lessons; permanent asset increments)

1. **Lesson #61** slug grep — SUCCESS (exact slug hit in PARADIGM_QUEUE_2026Q3.md + NEXT_PARADIGM_RUNBOOK.md); 9th+ post-confirmation SUCCESS after paradigm 167's 8th SUCCESS
2. **Lesson #56** outcome-level family proxy — SUCCESS (18th+ instance); MR direction on premium/basis substrate = paradigm 111 falsified sub-slice + paradigm 22 R-5 empirical direction is FOLLOW opposite
3. **Lesson #62** DNA 5-dim HARD FAIL — 12th+ cumulative boundary dogfood; 3.5/5 overlap paradigm 22 + 3/5 overlap paradigm 121
4. **Lesson #69** 5-item strict template — 5th+ post-candidate dogfood SUCCESS (Item 1 slug grep + Item 2 outcome proxy + Item 3 DNA + Item 4 queue ratification + Item 5 novelty budget)
5. **Lesson #21** axis stacking does not synthesize alpha on saturated substrate — 6th+ instance (novel-statistic-on-saturated-substrate is a sub-pattern of axis stacking)
6. **Lesson #45** (2-dogfood CONFIRMED 자격) HMM/latent-state filter mechanism architecturally broken on premium/basis substrate — 3rd instance (Kalman = another latent-state filter, precedent applies analogically)
7. **Lesson #39** exact-symmetric mirror pattern risk on latent-state filter × basis (paradigm 121 pattern) — pre-emptive dogfood
8. **Lesson #28** substrate availability — NEUTRAL (5m premium joblib 14 syms × 2yr present, filterpy missing but scipy alternative available; halt cause upstream Item 1)
9. **Lesson #11** sample density — NEUTRAL (daily 820 obs/sym × 14 syms × 5% trigger → 574 events; would clear per-cell 30 floor. Halt cause upstream Item 1)
10. **Lesson #37** hold-sweep verdict scan (would have been dispatched at R-1 4-quadrant × 4-hold matrix; halt cause upstream)
11. **Lesson #77** non-OHLCV substrate preference — NEUTRAL (premium index IS microstructure, but substrate belongs to retired premium domain per Q2 §5; halt cause upstream)
12. **Lesson #40** structural threshold feasibility — NEUTRAL (Kalman innovation is signed centered residual, symmetric z-trigger structurally feasible; halt cause upstream)

## Substrate Audit (informational only)

Substrate available if this halt were overridden:
- `backend/runs/premium_index/{SYM}USDT_premium_5m.joblib`: 14 alts confirmed present (ADA/AVAX/BCH/BNB/BTC/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP), 2024-05-15 → 2026-05-13 (~2.0yr, 209,952 rows/sym).
- 1d resample: ~730 daily bars/sym × 14 syms = 10,220 sym-days pooled.
- filterpy: missing (`ModuleNotFoundError`). scipy 1.17.0 present (Kalman implementable via `scipy.linalg` + custom MLE).
- Substrate would clear R-0 Lesson #11 + #28 gates independently; R-0 halt is entirely upstream family-level.

## R-1 Compute Saved

Estimated R-1 dispatch cost avoided:
- 4-quadrant × 4-hold × 14-sym × 5000-bootstrap × 500-perm ≈ 8-15 min compute
- Kalman MLE per-sym × 14 alts ≈ 3-5 min compute
- Total ~15-20 min compute saved; ~1MB metrics JSON avoided.

## Next Paradigm Recommendation

Given the R-0 HALT, the immediately next paradigm dispatch (autonomous SELF-RECOMMEND mode) should:

**Option A (preferred — cross-substrate axis)**: Move OUT of premium/basis/funding perimeter entirely. Candidate: `binance_perpetual_open_interest_per_symbol_composition_shift_family` — daily rolling 7d vs 30d OI composition Herfindahl index concentration change per-symbol × BTC vol regime overlay. NOT premium-based, NOT funding-based, uses OI aggregate structure. Different substrate, different mechanism (concentration structure change, not level MR/FOLLOW).

**Option B (preferred — event-anchored non-microstructure)**: `binance_futures_maintenance_margin_tier_change_event_anchored_alt_directional_3d_bilateral` — Binance publishes MM tier changes ~monthly; each tier hike/cut event is a structural risk-limit change on a specific symbol; test whether tier-hike (leverage cap reduction) alt directional 3d MR/FOLLOW. Non-microstructure event class (regulatory/exchange announcement), fresh dimension.

**Option C (deferred — infrastructure)**: `orderflow_via_aggTrades_taker_flow_1m_intraday_persistence_family` — Lesson #21 advisory caution family, requires 1m aggTrades archive backfill (Binance Vision aggTrades ~5GB/sym-year uncompressed). Would need explicit user greenlight due to >30min ETA + advisory caution family risk.

**REJECTED explicitly for 228+ dispatch**: any premium/basis/funding derivative or novel-statistic-on-same-substrate (Q2 §5 retired); any HMM/Kalman/BOCPD/CUSUM/wavelet on saturated substrate (Lesson #45 architectural break on latent-state filters × premium/basis).

## Meta-observation for lessons

**Lesson #61 amendment CONTINUED VALIDATION**: 9th+ consecutive post-confirmation SUCCESS. Slug grep against PARADIGM_QUEUE + NEXT_PARADIGM_RUNBOOK + graveyard directory continues to be the single most compute-efficient R-0 gate (this instance saved ~15-20 min). Recommend permanent asset status re-affirmation at next Q4 audit.

**Lesson #69 5-item template CONTINUED VALIDATION**: 5th+ post-candidate SUCCESS. Structured 5-item R-0 halt reasoning (slug grep + outcome proxy + DNA audit + queue ratification + novelty budget) consistently produces defensible halts with minimum dispute surface.

**Frontier scout meta-limit**: Continuous SELF-RECOMMEND mode has now generated an R-0-haltable proposal (this one) explicitly retired by prior queue ratification. Consider re-reading NEXT_PARADIGM_RUNBOOK.md §Retire table on every SELF-RECOMMEND cycle as the FIRST prescreen step, before proposing candidate.
