# paradigm 209 — `alt_per_sym_bybit_vs_binance_oi_velocity_divergence_z_spike_directional_4h_bilateral`

**Status**: R-0 INVENTORY HALT — R-1 NOT DISPATCHED
**Verdict**: `R0_HALT_BY_DNA_DUPLICATE_QUADRUPLE_PRIOR_PARADIGM_104_R1_BROAD_FALSIFIED_PLUS_PARADIGM_166_R0_HALT_PLUS_PARADIGM_187_R0_HALT`
**Date**: 2026-05-22 18:17 KST
**Counter**: 208 → 209 (substantive R-0 increment per paradigm 138/139/140/151/154/155/159/161/163/164/165/166/167/187 precedent)
**Predecessor**: paradigm 208 `alt_per_sym_funding_rate_jump_event_anchored_8h_signed` R-1 GRAVEYARD `BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED` (2026-05-22)
**Dogfood**: Lesson #69 8-item strict template post-CONFIRMED **Nth dogfood** SUCCESS (Items 1+4 HARD FAIL = R-0 halt unambiguous, 4th generation of identical paradigm class blocked); **Lesson #61 amendment 10th consecutive post-confirmation SUCCESS**; Lesson #62 boundary DNA 4-dim audit **0/5 strict HARD FAIL** vs paradigm 104; Lesson #56 OUTCOME-LEVEL family proxy NEUTRAL (halt cause upstream).

## Hypothesis (proposed but blocked)

Per-sym **Bybit OI 1h velocity (Δ%) vs Binance OI 1h velocity (Δ%) divergence**:
- `divergence_score = bybit_oi_velocity − binance_oi_velocity`
- 30d rolling z-score on 1h frame
- |z|≥2 spike trigger × bar direction signed × 4-quadrant SNT
- Universe: 7 deep syms (paradigm 103/104 cohort intersection)
- Hold: 4h primary + 8h/12h/24h sweep
- Mechanism: cross-venue smart-money OI displacement detection (informed-flow venue selection)
- Substrate: `backend/runs/ohlcv_cache/{binance_oi,bybit_oi}/{SYM}_1h.joblib` (paradigm 104/103 영구 자산) + 4h forward OHLCV

## Lesson #69 8-item strict template result

### Item 1 — Lesson #61 amendment slug grep (CRITICAL — QUADRUPLE prior-art found)

```bash
ls research_track/ | grep -iE "bybit.*binance|cross_venue|venue_divergence|oi_velocity_diverge|cross_exchange_oi"
```

Returns:
```
alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h               (paradigm 148, GRAVEYARD)
alt_bybit_to_binance_lead_lag_oi_delay_directional_4h                  (paradigm 147v2, GRAVEYARD)
alt_bybit_to_binance_oi_divergence_z_directional_4h                    (paradigm 187, R-0 INVENTORY HALT 2026-05-22 10:15 KST) ← DNA EXACT MATCH (8 hours ago)
alt_cross_exchange_oi_divergence_bybit_vs_binance_directional_4h       (paradigm 166, R-0 INVENTORY HALT 2026-05-21 21:35 KST) ← DNA EXACT MATCH
cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h  (paradigm 104, R-1 BROAD_FALSIFIED_PRIMARY_HOLD 2026-05-19 17:36 KST) ← DNA EXACT MATCH — actually executed
```

**Verdict**: paradigm 104 executed R-1 with full 4-quadrant SNT measurement on identical 7-sym universe + 4h primary hold + cross-venue Bybit/Binance OI z-score statistic. paradigm 166 and paradigm 187 each subsequently R-0 HALTED the same hypothesis class. The proposed paradigm 209 adds a **velocity-Δ wrapper** on top of the same cross-venue Binance/Bybit OI statistic family — paradigm 104 already measured the OI **level differential** z-score, which subsumes the velocity Δ form (`Δlevel = velocity`; rolling z-scoring the difference of velocities vs rolling z-scoring the difference of levels both reduce to the cross-venue OI imbalance per-sym z-score family). **HARD FAIL on Item 1** — 4th generation of identical paradigm class.

### Item 2 — Lesson #28 amendment substrate-shape audit

- **Substrate-existence**: PASS — `backend/runs/ohlcv_cache/binance_oi/*_1h.joblib` and `backend/runs/ohlcv_cache/bybit_oi/*_1h.joblib` 영구 자산 (paradigm 104 backfill 325.5s wall-clock, 7 deep syms × 869d, data window ratio 1.000).
- **Substrate-shape**: PASS — 1h frame for velocity computation at 4h hold is feasible; no shape problems.
- **Verdict**: PASS (moot — halt cause upstream Item 1 DNA duplicate).

### Item 3 — Lesson #11 sample density

paradigm 104 already measured directly on identical universe:
- |z|≥2.0: A_focus n=7,174 / B_focus n=6,763 (all 10 quarters ≥30, PASS)
- |z|≥2.5: A_focus n=3,425 / B_focus n=2,774 (all 10 quarters ≥30, PASS)

For the velocity-Δ form, the cross-correlation between `Δbybit − Δbinance` and `bybit − binance` (level diff) is structurally tight at 1h frame on identical 30d window, so the density profile carries over within ~10-15%. **PASS (moot)**.

### Item 4 — DNA 4-dim audit table vs paradigm 104 (Lesson #62 strict count)

| Dimension | paradigm 104 (R-1 GRAVEYARD) | paradigm 209 (proposed) | Strict count |
|---|---|---|---|
| **Statistic class** | `(binance_OI − bybit_OI)` 30d-median-norm + 30d z-score on 1h frame | `(bybit_oi_velocity − binance_oi_velocity)` 30d rolling z-score on 1h frame | **NOT STRICT** — velocity-Δ is the first difference operator of level-Δ; both reduce to per-sym cross-venue OI imbalance z-score family. The rolling-z-score wrapper on first-difference vs level is an algebraic differencing within a 30d window — does NOT introduce a new mechanism axis |
| **Universe** | 7 deep-syms (AVAX/BCH/BNB/DOGE/LINK/SOL/XRP) | 7 deep-syms (paradigm 103 cohort intersection, identical cohort) | **NOT STRICT** — exact match |
| **Entry-side trigger** | \|z\|≥2.5 directional both sides + sweep to z=2.0 (n=7,174/6,763) | \|z\|≥2 directional both sides | **NOT STRICT** — paradigm 104 already swept z=2.0 cell at identical density |
| **Mechanism alpha** | cross-venue OI imbalance reveals capital flow direction | cross-venue smart-money OI displacement detection (informed-flow venue selection) | **NOT STRICT** — identical mechanism statement re-labeled. "Smart-money displacement" = "capital flow direction" with new vocabulary, no new causal axis |
| **Hold horizon** | 4h primary + 60m/480m/1440m sweep | 4h primary + 8h/12h/24h sweep | **NOT STRICT** — 4h primary identical, 8h (=480m) cell already measured, 12h interpolatable, 24h (=1440m) already measured |

**Strict count: 0/5** — Lesson #62 **HARD FAIL** (required ≥2/5). DNA duplicate confirmed at maximum strength. This is the **identical 0/5 strict result** that paradigm 166 (2026-05-21) and paradigm 187 (2026-05-22 morning) both produced. **paradigm 209 = 4th generation re-attempt of the same hypothesis**.

### Item 5 — Family-proxy cross-reference (Lesson #56 OUTCOME-LEVEL)

Cross-exchange family Tier 4 retire **9 cumulative graveyards**:
- paradigm 103 `cross_exchange_funding_spread_binance_bybit_alt_directional_8h` (BROAD_FALSIFIED_FEE_FLOOR)
- paradigm 104 `cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h` (BROAD_FALSIFIED_PRIMARY_HOLD) ← **DNA EXACT MATCH**
- paradigm 105 `cross_exchange_funding_spread_binance_bitget_alt_illiquid_venue` (illiquid venue path closeout)
- paradigm 147v1 / v2 `bybit_to_binance_lead_lag_oi_delay` (Tier 4 retire)
- paradigm 148 `bybit_to_binance_lead_lag_PRICE_delay` (Tier 4 retire)
- paradigm 160 `cross_exchange_volume_share_rotation` (Tier 4 retire, fee-floor)
- paradigm 166 `alt_cross_exchange_oi_divergence_bybit_vs_binance_directional_4h` (R-0 INVENTORY HALT 2026-05-21) ← **DNA EXACT MATCH**
- paradigm 187 `alt_bybit_to_binance_oi_divergence_z_directional_4h` (R-0 INVENTORY HALT 2026-05-22) ← **DNA EXACT MATCH**

paradigm 209 would be **10th cumulative blocked instance** in the cross-exchange family. paradigm 22 R-5 LIVE funding_dispersion ETCUSDT remains sole family exception.

**Lesson #56 OUTCOME-LEVEL prediction NEUTRAL** — halt is upstream DNA duplicate (Item 1+4), not downstream OUTCOME proxy. Instance counter unchanged. The OUTCOME-LEVEL family proxy framework prediction for the cross-exchange family (fee-floor / primary-hold trap convergence) was already realized by paradigm 104 itself; paradigm 209's halt is the upstream slug-grep / DNA-duplicate gate.

### Item 6 — Alpha decay 5-pattern audit (MANDATORY 6th operational dogfood)

paradigm 104 era stratify (already-measured):
- 2024Q1: +24.21bp / +1.87 t (✓)
- 2024Q2: +0.36bp / +0.03 t (✓ borderline)
- 2024Q3: +3.76bp / +0.45 t (✓ borderline)
- **2024Q4: +69.73bp / +3.96 t (✓ LARGE — carries 36% cumulative mean)**
- **2025Q1: −30.97bp / −3.44 t (✗ LARGE reversal)**
- 2025Q2: +20.17bp / +1.64 t (✓)
- 2025Q3: +39.21bp / +3.04 t (✓)
- 2025Q4: −4.84bp / −0.40 t (✗)
- 2026Q1: −3.75bp / −0.43 t (✗)
- 2026Q2: +3.68bp / +0.38 t (✓)

**5-pattern classification**: **pattern 4 "single-quarter outlier driven" / pattern 3 "alternating sign monotonic decay"** — 2024Q4 single-quarter outlier carries 36% of cumulative mean, followed by 2025Q1 large reversal, then alternating sign through 2025–2026 with mean magnitudes shrinking. Mirror velocity wrapper would inherit this exact pattern (1h frame first-difference on 30d window does not de-correlate from the level-diff trajectory on a 4h hold horizon).

**paradigm 209 in cross-venue category era pattern**: would be a re-instance of paradigm 104's pattern 4/3 hybrid. Item 6 audit thus contributes a halt-reinforcing signal (proposed mechanism inherits a known broken alpha trajectory).

### Item 7 — SNT structural integrity (paradigm 206 1.83x / paradigm 207 2.79x reference)

Cross-set asymmetric magnitudes verify: paradigm 104 measured |A_focus gross|=25.70bp vs |B_focus gross|=5.12bp = **5.02× asymmetry** at primary horizon (Binance>Bybit side carries continuation; Bybit>Binance side does not). This is well above the paradigm 206 1.83x / paradigm 207 2.79x reference — structurally Lesson #39 sub-class B "mechanism-inverted" antipattern territory (A_focus carries direction, B_same does not, mirrors strongly negative — the asymmetric venue dynamics are real but trapped in the upward-bias / pool-drift mechanism at primary 4h).

Velocity-Δ wrapper would not break this asymmetry — the same Binance-side OI displacement mechanism dominates regardless of whether the input is level or first-difference of level. **PASS (asymmetric structural verify), moot due to upstream halt.**

### Item 8 — Concentration + Temporal Independence (paradigm 206+207+208 CONFIRMED + paradigm 208 amendment, 4th dogfood candidate)

paradigm 104 measured directly:
- **A_focus Concentration FAIL**: 2/7 syms ci_pos = 0.286 (< 0.30 threshold). 3/7 syms strongly NEGATIVE (AVAX −31.57, BNB −30.25, SOL −57.55). Directionally heterogeneous — not just sparse.
- **Per-quarter pos_t**: 7/10 (PASS ≥0.50) but driven by 2024Q4 single-quarter +69.73bp + 2025Q1 −30.97bp reversal — small-sample Concentration Gate blind-spot (lesson #26 territory).
- **Temporal cluster ratio**: NOT explicitly measured in paradigm 104 R-1 (pre-Item 8 amendment), but the rolling 30d z-score on 1h frame at 4h hold ≈ 720 1h-bars in window vs 4 1h-bars per trade — adjacency ratio would be substantial (estimated ≈0.5–0.7 for spike triggers across 7 syms × 2.5yr).

For paradigm 209 velocity-Δ wrapper on identical universe + window + hold: temporal_cluster_ratio inherits the same 1h-bar autocorr profile (paradigm 207 0.0138 antipattern risk applies but not as severely as paradigm 207's BTC RV anchor — divergence z-score across 7 disjoint syms has better natural decorrelation). sym_ci_pos_ratio on A_focus continuation = 2/7 = 0.286 FAIL (mirror-identity exclusion amendment applies; A_focus continuation alone is below the 0.30 threshold).

**Item 8 verdict**: would FAIL on sym_ci_pos_ratio (paradigm 208 amendment applied on A_focus continuation only). Moot due to upstream halt — but reinforces the halt decision.

## Verdict tree

1. **Item 1 slug grep HARD FAIL** — quadruple prior-art (paradigm 104 R-1 BROAD_FALSIFIED + paradigm 166 R-0 + paradigm 187 R-0) exact-class match
2. **Item 4 DNA 4-dim audit 0/5 strict HARD FAIL** (Lesson #62 boundary — identical result to paradigm 166 + paradigm 187)
3. Item 2 substrate PASS (moot)
4. Item 3 sample density PASS (moot)
5. Item 5 family-proxy NEUTRAL (halt cause upstream)
6. **Item 6 alpha decay 5-pattern audit halt-reinforcing** (pattern 4/3 hybrid inherited from paradigm 104)
7. Item 7 SNT structural verify (moot)
8. Item 8 Concentration would FAIL on sym_ci_pos_ratio (moot, halt-reinforcing)

**Cumulative halt signal**: **2 HARD FAIL + 2 halt-reinforcing + 2 moot PASS + 1 moot verify + 1 NEUTRAL** = **R-0 inventory halt unambiguous (4th generation of identical paradigm class)**

## Why the dispatch message claimed "5/5 strict distinct" (factual error, identical pattern to paradigm 187)

The dispatch task message §family-distinct strict 5/5 audit asserted:
> "5/5 strict distinct 자격 검증 의무: statistic class: cross-venue OI velocity divergence z-score (NEW); universe: 7 deep syms (paradigm 103 cohort intersection); entry-side: 4h spike-trigger event (sparse class); mechanism: cross-venue smart-money OI displacement detection (NEW); hold: 4h/8h/12h/24h sweep"

**Factual error breakdown**:
- "statistic class: NEW" — FALSE. `(bybit_velocity − binance_velocity)` rolling 30d z-score = the **first difference** of `(bybit_level − binance_level)` over 1h, then rolling z-scored on a 30d window. paradigm 104's statistic `(binance_level − bybit_level)` 30d-median-normalized then 30d z-scored on 1h frame is the **level** form of the same cross-venue OI imbalance — both are members of the cross-venue OI imbalance z-score family. Velocity wrapper does NOT change the mechanism axis.
- "universe: 7 deep syms (paradigm 103 cohort intersection)" — explicit IDENTITY admission, not distinctness.
- "entry-side: 4h spike-trigger event (sparse class)" — paradigm 104 entry-side IDENTICAL (4h frame, |z|≥2-2.5 trigger, classified as sparse class).
- "mechanism: cross-venue smart-money OI displacement detection (NEW)" — FALSE. paradigm 104 graveyard §Cross-paradigm 103 comparison explicit: "OI level differential carries stronger signal than rate differential" — identical "smart-money OI displacement" mechanism statement with re-labeled vocabulary.
- "hold: 4h/8h/12h/24h sweep" — paradigm 104 hold 60m/240m/480m/1440m sweep covers the same cells (8h=480m, 24h=1440m).

**Correct count: 0/5 strict distinct.** Identical blind-spot pattern to paradigm 166 (2026-05-21) and paradigm 187 (2026-05-22 morning). The dispatch §Lesson #62 reasoning failed to recognize that the velocity-Δ first-difference wrapper does not introduce a new statistic class — it is an algebraic transform within the same cross-venue OI imbalance z-score family.

## Lesson observations from this halt

### Lesson #61 amendment 10th consecutive post-confirmation SUCCESS

paradigm 209's halt was caught at Item 1 slug grep (Lesson #61 amendment). 10 consecutive successful dogfoods of the post-confirmation slug-grep gate (paradigms 178/186/187 + 7 others). Permanent asset eligible confirmed; this is by far the most reliable single prescreen item in the 8-item template.

### Lesson #69 8-item template Items 1+4 dual-HARD-FAIL pattern strengthened

3rd consecutive instance (paradigms 166 → 187 → 209) where Items 1 and 4 both HARD FAIL on the **same paradigm 104 prior-art** — confirming that the cross-venue OI imbalance hypothesis class is an attractor in the autonomous dispatch suggestion space (likely because: (a) Bybit V5 substrate verified 영구 자산, (b) 7-sym deep cohort verified, (c) the "cross-exchange divergence" framing reads as novel to surface-level pattern matching). **Permanent annotation needed** in `lesson_prescreen_checklist.md` for the cross-venue OI imbalance class to flag it as the most-attempted DNA-duplicate hypothesis (4 attempts in 3 days). Velocity / first-difference wrappers, normalization swaps (30d/90d, median/mean), sign-convention flips, and slug re-orderings all reduce to the same statistic class.

### Lesson #62 boundary DNA 4-dim audit 5/5 strict — 3rd consecutive 0/5 result on same paradigm 104 prior-art

paradigm 166 + paradigm 187 + paradigm 209 all produced **identical 0/5 strict count** against paradigm 104. The boundary DNA test is now **3-instance confirmed** for the cross-venue OI imbalance class as a hard-block attractor. Recommend the lesson_prescreen_checklist be amended with an explicit annotation: "if Item 1 grep returns ANY of {paradigm_104, paradigm_166, paradigm_187, paradigm_209} family slugs, halt immediately without further item evaluation — DNA 4-dim audit known 0/5 strict on this class."

### Lesson #56 OUTCOME-LEVEL family-proxy NEUTRAL (3rd consecutive NEUTRAL on this class)

Halt is upstream DNA duplicate (Items 1+4), not downstream OUTCOME proxy. Family-proxy 11th instance unchanged (paradigm 209 NEUTRAL, not advancing counter).

### Lesson #69 Item 6 alpha decay 5-pattern audit operational value confirmed

Item 6 halt-reinforcing signal generated automatically from paradigm 104 era stratify retrieval. The 5-pattern audit (operational dogfood #6) correctly identified that paradigm 209 would inherit paradigm 104's pattern 4/3 hybrid trajectory — supporting the halt decision with mechanism-level evidence beyond pure DNA duplication. **Item 6 5-pattern audit confirmed operationally valuable as supplementary halt-reinforcement** even when the primary halt cause is upstream Items 1+4.

## Resources spent

- **Compute saved**: ~50-80 min wall-clock (paradigm 104 R-1 was 325.5s backfill + ~30 min sweep + measurement; paradigm 209 would have been substantively identical with velocity-wrapper recomputation overhead). Halt at Item 1 slug grep + Item 4 DNA audit table cost ~3 min.
- **Permanent assets preserved (no new backfill)**: existing Bybit V5 + Binance OI cache + 7 deep syms 4h OHLCV joblib cache unchanged.

## paradigm 210 next-action recommendation (Lesson #61 amendment permanent inventory check 의무)

**Recommended path for paradigm 210**:

1. **HARD CONSTRAINT (mandatory)**: Lesson #61 amendment slug grep MUST be the very first step before any DNA audit. For paradigm 210 candidates, the grep pattern must include ALL of:
   - `bybit|binance|cross_exchange|cross_venue|venue_divergence|oi_diverge|oi_imbalance|oi_displacement|oi_velocity|oi_lead_lag|funding_spread|funding_dispersion`
   - If ANY return → halt immediately, do not enter Item 4 DNA audit (since paradigm 166+187+209 all confirmed 0/5 strict on Item 4).

2. **Recommended FRESH dimension paths (NOT cross-venue OI / funding family / volume share)**:
   - **(a) event-anchored category** distinct from funding boundary / delisting / unlock (e.g., scheduled earnings-equivalent for crypto: token-economics events like emission halving, validator slashing events, governance vote outcomes — substrate availability prescreen via Lesson #28 amendment mandatory)
   - **(b) intraday microstructure category** distinct from 5m microstructure advisory caution family (e.g., 1m or 15m bar frame, NOT 5m; OR taker-buy ratio cross-product distinct from paradigm 72 family)
   - **(c) cross-asset broadcast category** with Lesson #67 ESCAPE verification — BTC dominance regime × alt rotation, or stablecoin supply growth × alt continuation (substrate prescreen mandatory)

3. **AVOID** these classes for paradigm 210 (10+ confirmed Tier 4 retire / advisory caution / DNA-duplicate attractor):
   - Cross-venue OI imbalance (any wrapper: velocity / level / ratio / spread / divergence / displacement / dispersion)
   - Funding axis (any sub-class: level / sign-flip / velocity / dispersion / jump / spread)
   - Volume share rotation (paradigm 94/95/160 family)
   - 5m microstructure single-domain (paradigm 80/82/83/85 family)
   - KR equity post-earnings (paradigm 92/93 family)
   - RV intraday cross-family (paradigm 136/202/203 memorial)

4. **Continuous-parallel campaign policy** ([[feedback-paradigm-campaign-continuous-parallel]] + [[feedback-persistence-over-efficiency]]) **strict 준수**: dispatch paradigm 210 immediately, no pause recommendation; dispatch failure rate is expected by policy.

## Memory policy compliance verified

- [[feedback-persistence-over-efficiency]]: dispatch 지속, R-0 HALT은 실패 누적 정상의 일부
- [[feedback-paradigm-campaign-continuous-parallel]]: dispatch 일시정지 권고 금지 — paradigm 210 즉시 dispatch 권고 (위 §next-action recommendation)
- [[feedback-direct-recommendation]]: 분기점 옵션 나열 금지 — paradigm 210 paths 1-3 직접 권고
- [[feedback-no-freemium-trial]]: paradigm 209 substrate는 영구 자산 only, freemium 위반 없음
- [[feedback-life-changing-strategy-criterion]]: paradigm 104 already-measured life-changing 4-dim FAIL on edge dim (0.26%/trade at 480m) — paradigm 209 would inherit this constraint
- [[feedback-timestamp-kst-suffix]]: 응답 마지막 줄 KST timestamp 의무

---

**Final verdict**: `R0_HALT_BY_DNA_DUPLICATE_QUADRUPLE_PRIOR_PARADIGM_104_R1_BROAD_FALSIFIED_PLUS_PARADIGM_166_R0_HALT_PLUS_PARADIGM_187_R0_HALT`

paradigm 209 R-1 NOT DISPATCHED. 4th generation re-attempt of identical cross-venue OI imbalance z-score paradigm class blocked at R-0 inventory check.
