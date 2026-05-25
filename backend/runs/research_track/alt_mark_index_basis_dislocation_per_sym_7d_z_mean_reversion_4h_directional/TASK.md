# paradigm 167 — `alt_mark_index_basis_dislocation_per_sym_7d_z_mean_reversion_4h_directional`

**Dispatched**: 2026-05-21 21:42 KST
**Phase reached**: R-0 INVENTORY HALT (R-1 NOT DISPATCHED)
**Verdict**: `R0_HALT_BY_FAMILY_PROXY_QUADRUPLE_PRIOR_BROAD_FALSIFIED_LESSON_61_AMENDMENT_8TH_POST_CONFIRMATION_SUCCESS_LESSON_69_4TH_POST_CANDIDATE_DOGFOOD_SUCCESS`
**Counter**: 166 → **167** (substantive R-0 increment per paradigm 138/139/140/151/154/155/159/161/163/164/165/166 precedent)
**Wall clock**: 0.4 min (R-0 inventory + family audit + cross-graveyard verification)
**Host**: hcp local

---

## 1. Hypothesis (proposed but blocked)

Per-symbol perp price vs index price basis dislocation 7d z-score |z|≥2 mean-reversion × 4h hold.

- **Trigger statistic**: per-sym basis ratio = (perp_close − markPrice_close) / markPrice_close, rolling 7d z-score, |z|≥2
- **Direction**: mean-reversion (perp-cheap → LONG / perp-rich → SHORT)
- **Universe**: 13 alts standard cohort
- **Hold**: 4h primary + 1h/2h/8h sweep
- **Substrate**: Binance markPriceKlines archive (free unlimited)

## 2. Lesson #69 5-item strict template result (4th post-candidate dogfood)

### Item 1 — Lesson #61 amendment slug grep (CRITICAL prior-art found)

`ls research_track/ | grep -iE "basis|mark_index|premium_index|perp_price|markPrice"` returned:

| File | Counter | Verdict | Date |
|---|---|---|---|
| `binance_perp_mark_index_basis_extreme_alt_directional_4h/` + graveyard | **paradigm 111** | `BROAD_FALSIFIED` (4-quadrant SNT 0/4 PASS) | 2026-05-20 12:08 KST |
| `hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h/` + graveyard | **paradigm 121** | `BROAD_FALSIFIED_LESSON39_SYMMETRIC_NO_AXIS_SYNTHESIS_HMM_FILTER_INEFFECTIVE` | 2026-05-20 17:21 KST |
| `alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h/` + graveyard | **paradigm 131** | `BROAD_FALSIFIED_LESSON_52A_LONG_DRIFT_ARTIFACT` (Lesson #21 4th, Lesson #52a 2nd EXPLICIT) | 2026-05-21 09:56 KST |
| `premium_index_zscore/` (R-5 LIVE) | **paradigm 22/24** | R-5 SEEDED 3x DOGE/SOL/LDO (DAILY 1d follow momentum) | 2026-05-06 |

**Plus paradigm 105 graveyard** (markPrice basis × 4h hold MR single-axis, referenced in paradigm 111 §8 graveyard) — same family.

**Cumulative basis/markPrice family graveyards at 4h hold**: 105 + 111 + 121 + 131 = **4 prior BROAD_FALSIFIED**.

**Verdict: HARD FAIL** — basis-vs-index axis at 4h hold mean-reversion direction has 4 prior broad-falsified graveyards.

### Item 2 — Lesson #28 amendment substrate-shape audit (4th post-amendment opportunity)

- Binance markPriceKlines monthly archive: prior-verified at paradigm 111 (HTTP 200 6 alts × 24mo) + paradigm 121 (1y cache reuse) + paradigm 131 (12mo reuse)
- 13 alts × 2.25yr coverage: verified ahead of time (paradigm 111 used 24mo cohort)
- basis ratio definition: paradigm 167 candidate uses (perp_close − markPrice) / markPrice vs paradigm 111 used (mark_close − index_close) / index_close — **two definitions of "basis"**:
  - paradigm 111 definition: mark vs index (settlement-anchor basis, funding-arbitraged)
  - paradigm 167 candidate definition: perp vs mark (short-term order book imbalance against settlement mark)
- **Both definitions historically arbitraged via markPrice formula itself** — Binance markPrice = (index price + EMA of perp premium), so perp_close − markPrice approximates the de-EMA-smoothed instantaneous premium component
- Substrate-shape: technically distinct but **mechanically equivalent at 4h aggregation** (markPrice EMA-smooths within minutes, 4h bar dominated by EMA-converged state)
- **Verdict**: PASS (moot — halt cause upstream Item 1)

### Item 3 — Lesson #11 sample density

- 13 alts × 2.25yr × 4h bars × ~5% |z|≥2 event rate ≈ 3,350 triggers
- Per-quadrant SNT: 3,350 / 4 ≈ 838 each
- Per-quarter measurable (9 quarters): 93 each
- **Verdict: PASS strong** (moot — halt cause upstream Item 1)

### Item 4 — DNA 4-dim audit (Lesson #62 CONFIRMED, 11th boundary dogfood)

| Dimension | paradigm 167 candidate | paradigm 111 graveyard | paradigm 121 graveyard | paradigm 131 graveyard | Strict (vs paradigm 111)? |
|---|---|---|---|---|---|
| Statistic | (perp − mark) / mark, 7d z-score | (mark − index) / index, 30d signed pct rank | mark-index basis, 1h 30d z-score | basis_z × range_close_z conjunction | **NOT STRICT** (basis-vs-mark/index z/percentile axis, window minor variant) |
| Universe | 13 alts | 6 alts | 6 alts | 6 alts | NOT_STRICT (broader scope but same family) |
| Entry-side trigger | \|z\|≥2 mean-reversion | signed pct rank ≤p05 / ≥p95 | \|z\|>2 × HMM HIGH filter | \|basis_z\|>1.5 ∩ range_close_z>1.5 | NOT_STRICT (signed extreme threshold variations all swept) |
| Mechanism alpha | basis arbitrage convergence (mean-reversion) | basis arbitrage convergence (mean-reversion) | basis arbitrage convergence × vol filter | basis convergence × range_close conjunction | **IDENTICAL** |
| Hold horizon | 4h | 4h | 4h | 4h | **IDENTICAL** |
| Frame | 4h bar (7d window) | 5m basis × 4h hold | 1h basis × 4h hold | 4h bar | NOT_STRICT (frame minor variant) |

**Strict count: 0/6 (vs paradigm 111) / 0/6 (vs paradigm 131)** — Lesson #62 HARD FAIL (11th cumulative boundary dogfood).

### Item 5 — Family-proxy cross-reference (Lesson #56 OUTCOME-LEVEL, 16 → 17 instances)

- basis/markPrice family at 4h hold MR direction: **4 prior graveyards** (105 + 111 + 121 + 131)
- paradigm 131 graveyard §"Liquidity-microstructure family advisory caution status" explicitly enumerates 105 + 121 + 131 as 3 sub-mechanism graveyards (paradigm 111 implicit ≈ 105)
- paradigm 131 graveyard §"Recommended PIVOT AWAY definitively" explicitly states: "**Liquidity-microstructure single-domain 4h-frame conjunction** (paradigm 105/111/121/131 — 3 graveyards, advisory caution)"
- paradigm 167 = **5th attempt** at this exact family (4h hold mean-reversion basis-axis directional)
- **Lesson #56 OUTCOME-LEVEL instance**: paradigm 167 R-0 halt prediction → 17th instance (basis/markPrice 4h MR family proxy 100% prior broad-falsified)
- Advisory caution **escalation eligible**: 4 graveyards + 1 R-0 halt = **5 cumulative blocked → Tier 4 retire candidate**

#### paradigm 22/24 R-5 SEEDED exception clarification

- paradigm 22/24 = premium_index_zscore at **DAILY 1d FOLLOW MOMENTUM** (DOGE/SOL/LDO seeded 2026-05-06)
- paradigm 167 candidate = **4h MEAN-REVERSION** direction OPPOSITE + timescale 6x shorter
- The hypothesis §"vs paradigm 21/24 R-5 seed" framed this OPPOSITE-direction + SHORTER-timescale as family-distinct escape path
- **CRITICAL counter-evidence**: paradigm 111 graveyard §5.2 explicitly tested this exact escape path — "Mechanism direction (mean-reversion) is the OPPOSITE of the only seeded paradigm in adjacent space (paradigm 24 daily momentum)" → paradigm 111 **BROAD_FALSIFIED anyway**
- paradigm 121 graveyard §7.3: "markPrice basis directional alpha continuously arbitraged via funding 8h cycle, no amount of conditioning saves it"
- paradigm 131 graveyard §3 confirms: paradigm 111 single-axis basis already broad-falsified (2026-05-20): A_focus pLOW LONG gross -0.37bp essentially zero alpha. paradigm 131 attempted rescue via range_close conjunction — failed.
- **The MR-direction 4h-hold sub-axis is decisively closed by 4 prior graveyards. paradigm 22/24 R-5 success is exclusively the daily-follow-momentum sub-axis, NOT the 4h-MR sub-axis.**

## 3. paradigm 166 §next-action factual error caught at paradigm 167 R-0

paradigm 166 (§6.64) authored 2026-05-21 21:35 KST recommended Option δ paradigm 167 with explicit claim:
- §6.64 line 5992: "Lesson #56 OUTCOME-LEVEL family proxy | NEUTRAL (**basis arbitrage family untouched**, no prior outcomes to predict)"
- §6.64 line 5976: "Family-distinct strict expected: 4-5/5 (single-exchange, **basis-vs-index axis untouched in 165 prior dispatches**)"

**Both claims factually false**:
- basis/markPrice family is NOT untouched — 4 prior graveyards (paradigm 105 + 111 + 121 + 131)
- Specifically paradigm 111 = single-exchange Binance perp mark-index basis at 4h hold MR direction = **EXACT same hypothesis** modulo statistic axis minor variant (signed pct rank vs 7d z-score)
- paradigm-architect orchestration did not cross-reference paradigm 111/121/131 when issuing paradigm 167 recommendation

**This is precisely the same provenance audit failure pattern as paradigm 163 (§6.60 → §6.61) and paradigm 166 (§6.63 → §6.64)**.

**Lesson #61 amendment 8th consecutive post-confirmation SUCCESS dogfood** — formal trigger for permanent asset elevation at next ratification batch.

**Lesson #69 4th post-candidate dogfood SUCCESS** — formal CONFIRMED-applied (5-item template surfaced factual error at Item 1 grep; halt issued before R-1 dispatch).

## 4. Lessons confirmed/observed in this R-0

| Lesson | Result |
|---|---|
| **Lesson #69 CONFIRMED-applied** 5-item strict template | **4th post-candidate dogfood SUCCESS** (factual prior-art surfaced at Item 1 grep; halt pre-R-1) |
| **Lesson #61 amendment** R-0 provenance audit | **8th consecutive post-confirmation SUCCESS** → permanent asset elevation **immediately ratifiable** at next §6.x batch (8th-eligible threshold reached) |
| **Lesson #62** DNA 4-dim strict count | **HARD FAIL 0/6 strict vs paradigm 111** (11th cumulative boundary dogfood) |
| **Lesson #28 amendment** substrate-shape | **4th post-amendment dogfood NEUTRAL** (substrate fine but framework applied; halt cause upstream Item 1) — CONFIRMED 자격 evaluation reached (4 dogfoods cumulative) |
| **Lesson #56** OUTCOME-LEVEL family proxy | **17th instance** (basis/markPrice 4h MR family 4 prior graveyards 100% proxy SUCCESS) — basis family Tier 4 retire candidate strengthened |
| **Lesson #21** axis stacking | NEUTRAL (single-axis hypothesis, no violation) |
| **Lesson #19** 4-quadrant SNT | DEFERRED (R-1 not dispatched) |
| **Lesson #34** empirical distribution | DEFERRED (R-1 not dispatched) |

## 5. Recommended paradigm 168 next-action

### Critical constraint state at 2026-05-21 21:42 KST

- **Basis/markPrice 4h MR family**: **5 cumulative blocked (105 + 111 + 121 + 131 graveyards + 167 R-0 halt) → Tier 4 retire ratifiable**
- Cross-exchange family: 8 cumulative blocked (decisive Tier 4 retire)
- Funding family: 11 cumulative (Tier 4 retire ratified)
- Taker imbalance directional: Tier 4 retire ratified 2026-05-21 (Lesson #57 CONFIRMED)
- OI velocity directional: 2 cumulative (Tier 4 retire candidate)
- Magnitude-confluence family: Tier 4 retire ratified
- KR post-earnings family: Tier 4 retire ratified
- Volume share cross-asset: Tier 4 retire ratified
- HMM unsupervised decomposition: Tier 4 retire candidate (paradigm 119 + 121)
- Magnitude-event family: Tier 4 retire (lifecycle_pump_decay R-5 exception)
- Calendar/clock-anchor: Lesson #56 11th instance
- ATR-normalized magnitude breakout: advisory caution
- Sub-5min momentum continuation: Lesson #60 candidate 1st dogfood
- Session-boundary × 4h: Lesson #68 candidate 2nd dogfood

### 36-streak non-PASS milestone reached. R-5 yield 6.59% (11/167). Per [[feedback_persistence_over_efficiency]] — dispatch 지속.

### Option η — `alt_perp_swap_basis_term_structure_carry_differential_directional_4h`

paradigm 164 fallback candidate referenced in §6.62. **Re-evaluate strict family-distinct count carefully**:
- vs paradigm 22/24 R-5 (premium_index daily follow): direction matters — if 4h directional carry-trade follow momentum: 2/5 strict (timescale only, mechanism same)
- vs paradigm 96/97/98/99 (funding family Tier 4 retired): if term-structure axis vs single-funding axis: minor distinct
- vs paradigm 167 (basis family blocked here): perp-vs-perp term structure ≠ perp-vs-spot basis — **family-distinct**
- **Substrate**: Binance funding DB full backfill (per [[feedback_paradigm_architect_local_context]] partial cohort)
- **Lesson #61 amendment 9th post-confirmation opportunity** (permanent asset already elevated at 8th)
- **Lesson #69 5th post-CONFIRMED dogfood opportunity**

**Expected strict family-distinct count**: 3-4/5 (timescale + statistic class + universe potentially distinct from funding family single-rate)

### Option θ — Lifecycle live mode forward-collection wait (2026-05-29+)

- 8 days until lifecycle live mode available (paradigm 87/88 lessons #26/#27 entry-side substrate requirement)
- listing day pump-and-decay variants ratified for R-5 (lifecycle_pump_decay LIVE)
- listing day +60min..+240min window forced-buyer mechanism untested in current substrate state

### Option ι (META) — Tier 4 retire RATIFICATION batch

Given 5 cumulative blocked basis/markPrice 4h MR family + 36-streak non-PASS + paradigm 166/167 consecutive next-action factual errors caught by paradigm-architect R-0 spec:

**Recommendation: PARADIGM 168 = formal Q3 §6.66 ratification batch issuance**, capturing:
1. **Basis/markPrice 4h MR sub-axis Tier 4 retire** (5 cumulative blocked, decisive)
2. **Lesson #61 amendment permanent asset elevation** (8-streak post-confirmation SUCCESS)
3. **Lesson #69 CONFIRMED formal ratification** (4 post-candidate dogfoods cumulative)
4. **Lesson #28 amendment CONFIRMED 자격 evaluation** (4 dogfoods cumulative)
5. **Lesson #56 17th instance** ratification
6. **HMM unsupervised decomposition family Tier 4 retire formal** (paradigm 119/121 + boundary)
7. **Liquidity-microstructure single-domain 4h-frame conjunction** family Tier 4 retire formal (per paradigm 131 §next-action recommendation explicitly stated)

paradigm 168 = paradigm 167 R-0 ratification entry counter-equivalent (substantive +1 with §6.66 ratification batch + Option η pick for paradigm 169).

## 6. Artifacts

- **R-0 task report**: `backend/runs/research_track/alt_mark_index_basis_dislocation_per_sym_7d_z_mean_reversion_4h_directional/TASK.md` (this file)
- **INDEX.json entry**: `paradigms.alt_mark_index_basis_dislocation_per_sym_7d_z_mean_reversion_4h_directional`
- **PARADIGM_QUEUE_2026Q3.md §6.65 entry**: appended to queue

## 7. One-liner summary

paradigm 167 (mark-index basis dislocation per-sym 7d z-score 4h MR, 13 alts) **R-0 INVENTORY HALT** via Lesson #69 5-item template Item 1 prior-art grep: basis/markPrice 4h MR family has **4 prior BROAD_FALSIFIED graveyards** (paradigm 105/111/121/131), paradigm 111 specifically = exact same hypothesis (single-exchange Binance perp mark-index basis × 4h hold MR direction) modulo statistic axis minor variant. paradigm 166 §6.64 next-action factual error ("basis arbitrage family untouched") caught at paradigm 167 R-0 — **Lesson #61 amendment 8th consecutive post-confirmation SUCCESS** (permanent asset elevation ratifiable) + **Lesson #69 4th post-candidate dogfood SUCCESS** (formal CONFIRMED-applied). Lesson #62 DNA 4-dim HARD FAIL 0/6 strict vs paradigm 111 (11th boundary). Lesson #56 17th instance. Basis/markPrice 4h MR sub-axis = **5 cumulative blocked → Tier 4 retire ratifiable**. 36-streak non-PASS. paradigm 168 next-action: Option η perp swap basis term structure carry differential (family-distinct from funding single-rate + basis-vs-spot) OR Option ι meta ratification batch §6.66.
