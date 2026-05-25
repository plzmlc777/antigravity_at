# paradigm 223 GRAVEYARD — cross-sym co-firing density regime detection

- **Slug**: `alt_cross_sym_co_firing_5plus_alts_simultaneous_realized_vol_z_spike_collective_regime_directional_4h_majority_dir`
- **Counter**: 223
- **Date**: 2026-05-25
- **Phase**: R-1 GRAVEYARD (R-2 not dispatched per STRICT directive)
- **Verdict**: `BROAD_FALSIFIED_FEE_FLOOR_DENSITY_ESCAPE_FAIL_LESSON_73_REFUTED`

## Hypothesis
Cross-sym co-firing density regime detection: in each 4h bar, if ≥5 alts simultaneously trigger `|rv_z|≥2` (7d realized vol, 60d z-window) AND ≥3 of them share same `bar_dir` (collective majority direction), enter universe-wide LONG/SHORT for 4h/8h hold. Density escape mechanism intended to defeat Item 9 capital util ceiling (paradigm 213+215+218+219+221+222 6 prior STRUCTURAL FAIL).

## R-1 result — 0/4 PASS at both holds, density escape REFUTED

### 4-quadrant SNT (hold=4h, primary)
| Cell | n | sigex | CI bp | perm_p | verdict |
|---|---|---|---|---|---|
| A_focus COFIRE UP LONG | 239 | 1.22 | [-19.39, 28.86] | 0.114 | FAIL |
| A_mirror COFIRE UP SHORT | 239 | -0.95 | [-44.86, 3.39] | 0.182 | FAIL |
| B_same COFIRE DOWN SHORT | 213 | -0.64 | [-46.98, 9.75] | 0.244 | FAIL |
| B_mirror COFIRE DOWN LONG | 213 | 1.01 | [-25.75, 30.98] | 0.152 | FAIL |

### 4-quadrant SNT (hold=8h)
| Cell | n | sigex | CI bp | perm_p | verdict |
|---|---|---|---|---|---|
| A_focus COFIRE UP LONG | 239 | 1.42 | [-19.35, 49.45] | 0.069 | FAIL (ci) |
| A_mirror COFIRE UP SHORT | 239 | -1.27 | [-65.45, 3.35] | 0.102 | FAIL |
| B_same COFIRE DOWN SHORT | 213 | -1.28 | [-75.29, 5.14] | 0.097 | FAIL (ci) |
| **B_mirror COFIRE DOWN LONG** | **213** | **1.53** | **[-21.14, 59.29]** | **0.065** | **FAIL (sigex/ci only)** |

Best cell B_mirror_DOWN_LONG hold=8h sigex=1.53 ci_lower=-21bp perm_p=0.065 — closest to PASS but sigex < 2.0 and ci_lower < 0.

### Sensitivity z=1.5, k=5: n_events=1088 (2.4x denser), A_focus sigex=1.83 perm_p=0.016 BUT ci=[-10,16]bp FAIL ci. Not rescued.

## Lesson #69 9-item template

### Item 1 (Lesson #61 INDEX.json grep) — PASS
NO_MATCH on (`co_firing`, `collective_regime`, `simultaneous_spike`, `universe_wide`, `majority_dir`). Fresh slug.

### Item 2 (Lesson #28 substrate-shape + Lesson #72 6m consistency) — PASS
20 syms × 4920 4h-bars × 2.24yr uniform start 2024-02-01 end 2026-04-30. valid z=4519 each. Rolling 6m per-cell t: A_focus 4/6 negative t, A_mirror 5/6 negative t, B_same 4/6 negative t, B_mirror 3/6 negative t — 6m consistency POOR.

### Item 3 (Lesson #11 sample density) — PASS
Co-firing event rate empirical: 452 events / 4519 valid bars = **10.0% bar rate** (estimate 3-5% was 2-3x conservative). Per-cell n=213-239 ≥ 30 minimum. Sample density adequate. Higher than expected co-firing rate suggests vol regime synchronization is structurally common.

### Item 4 (Lesson #62 DNA 4-dim 5/5 strict) — PASS
vs paradigm 195/196 (cohort selection ranking): distinct (event detection, not ranking).
vs paradigm 222 (per-sym 1d swing): distinct (cross-sym universe-wide vs per-sym).
vs paradigm 219 VWAP / 221 range compression: distinct (cross-sym co-firing vs per-sym z-spike).
vs all R-5 LIVE + 20 Tier 4 retires: cross-sym co-firing density event class is fresh. **Lesson #74 candidate ESCAPE 조건 1 met (cross-sym distinct DNA).**

### Item 5 (Lesson #56 family-proxy) — PASS
New family: cross-sym co-firing density event class.

### Item 6 (Alpha decay 5+ pattern, 13th operational dogfood) — **Pattern P1 11 CONSECUTIVE CONFIRMED. 2026 era-universal decay 9 instances CONFIRMED.**
Per-cell era stratify (primary hold 4h):
- **A_focus_UP_LONG**: 2024 +16.1bp / 2025 -5.9bp / 2026 -20.4bp → MONOTONIC DECAY (Pattern P1 type 11th confirmation)
- **A_mirror_UP_SHORT**: 2024 -32.1bp / 2025 -10.1bp / 2026 +4.4bp → MONOTONIC IMPROVEMENT (mirror image of A_focus decay)
- **B_same_DOWN_SHORT**: 2024 -56.3bp / 2025 +7.2bp / 2026 +50.5bp → MONOTONIC IMPROVEMENT
- **B_mirror_DOWN_LONG**: 2024 +40.3bp / 2025 -23.2bp / 2026 -66.5bp → MONOTONIC DECAY (Pattern P1 type)

**Two cells (A_focus + B_mirror) show monotonic 2024→2025→2026 decay, both with directional LONG continuation pattern. The 2024 alpha source is real (A_focus +16bp / B_mirror +40bp both positive 2024) but completely decays by 2026.** This is the 11 consecutive Pattern P1 universal-class extreme + 9th 2026 era-universal decay instance.

### Item 7 (SNT cross-set asymmetry, 11th instance, Lesson #75 5x test) — PASS (no Lesson #75 trigger)
A (UP majority) n=239, B (DOWN majority) n=213. Ratio 1.12x. Lesson #75 5x threshold NOT exceeded. **Structural reason**: co-firing event by construction requires ≥3 same-dir from ≥5 firers, so set sizes are bounded by directional distribution at event level (less asymmetric than per-sym z-trigger sets which paradigm 222 saw 9.81x).

### Item 8 (Concentration + Temporal Independence, cross-sym amendment candidate)
Universe-level per-quarter pos_t ratio (hold=4h):
- A_focus: 4/8 = 0.50 (borderline)
- A_mirror: 1/8 = 0.12 (very concentrated)
- B_same: 3/6 = 0.50
- B_mirror: 3/6 = 0.50

Note paradigm-architect Item 8 amendment proposed for cross-sym paradigms: use universe-level quarter concentration (single trade per event). Applied here. No cell reaches paradigm 208 threshold of consistent positive temporal independence.

### Item 9 (Life-changing 4-dim STRUCTURAL prescreen, 7th operational, Lesson #73 1st dogfood) — **STRUCTURAL FAIL 7TH OPERATIONAL + LESSON #73 REFUTED**
| Dim | 4h hold | 8h hold | Status |
|---|---|---|---|
| trades/yr per cell | 132 (A_focus) / 118 (B_same) | 132 / 118 | PASS (≥12) |
| capital util | **11.4%** | **22.8%** | **FAIL (<30%)** |
| per-trade edge | -1bp to +1bp | -1bp to +1bp | FAIL (<+2%) |
| sharpe | NA | NA | NA |

**Lesson #73 candidate "hold extension does not rescue Item 9" → REFUTED but in opposite direction: density escape via cross-sym co-firing detection ALSO fails Item 9.** Capital util computed as `h_bars × n_events / total_bars` for universe-wide trade. Even with 4h × 452 events / 3963 total bars = 11.4%, 8h doubles only to 22.8% — co-firing events at 10% bar rate × 4h hold cannot reach 30% util **structurally** because event rate × hold cannot exceed 100% × hold/period and co-firing events are mutually exclusive (one universe-wide trade per bar).

**Lesson #73 PRESCRIPTION REFUTED 1st dogfood result**: density escape mechanism (cross-sym co-firing regime detection) does NOT rescue Item 9 — co-firing events are themselves bounded by bar-rate × hold-bars × directional split. To achieve 30%+ util via cross-sym detection, would need either (a) hold > ~4 bars (= 16h+ multi-bar holding) OR (b) co-firing rate > ~30% (requires lowering k or z threshold beyond signal-noise breakeven). Neither is feasible at signal grade.

### Unconditional baseline (universe-wide aggregate)
- LONG hold=4h: n=4518 mean=**-8.88bp** t=-3.67 (significant negative drift)
- SHORT hold=4h: n=4518 mean=**-7.12bp** t=-2.95 (significant negative drift)
- LONG hold=8h: n=4517 mean=-9.67bp t=-2.82
- SHORT hold=8h: n=4517 mean=-6.33bp t=-1.85

**Universe-aggregate baseline has bilateral negative drift (8bp fee bites both directions on 4h-bar universe-mean) — this is the structural floor that defeats any sub-fee-floor signal.**

## Lesson #74 candidate ESCAPE 조건 1 verdict — **REFUTED**

paradigm 223 tested whether cross-sym co-firing regime detection is genuinely distinct DNA (ESCAPE 조건 1 for Lesson #74 `per-sym OHLCV z-spike DNA HALT_BY_DEFAULT`). Result: **cross-sym co-firing is ALSO subject to Pattern P1 universal alpha decay (11th consecutive confirmation now including cross-sym formulation).** This invalidates ESCAPE 조건 1 — cross-sym aggregation does not provide alpha-decay immunity.

→ Lesson #74 candidate elevated severity: per-sym AND cross-sym OHLCV z-spike DNA both subject to universal Pattern P1 decay. ESCAPE 조건 1 (cross-sym co-firing) FAIL. ESCAPE conditions 2-N remain untested.

## Pattern P1 universal-class extreme 11 CONSECUTIVE CONFIRMED
paradigm 213, 215, 218, 219, 221, 222 + paradigm 223 (per-sym variants) all show 2024→2025→2026 monotonic alpha decay across cells with directional continuation, including cross-sym aggregation variant. The pattern is now **trans-paradigm-class universal** (not limited to per-sym OHLCV z-spike).

## 2026 era-universal decay 9 instances CONFIRMED
paradigm 223 cells A_focus and B_mirror both show 2026 era performance is the worst of 3 eras for directional continuation cells. 9th independent instance.

## Lesson #42 24th dogfood — NEGATIVE (B mirror cell)
B_mirror_DOWN_LONG hold=8h sigex=1.53 CI=[-21,59]bp perm_p=0.065 — strongest cell of all 8 but still FAIL (sigex<2, ci_lower<0). NEGATIVE 14th in 24-test chain (10 CONFIRMED / 14 NEGATIVE / 1 PASS_AS_ARTIFACT).

## family-distinct strict 5/5 audit — PASS
1. statistic class: cross-sym ≥5 alts simultaneous |rv_z|≥2 co-firing event count (NEW)
2. universe: 20 alts (paradigm 198 cohort)
3. entry-side: cross-sym co-firing event (NEW class)
4. mechanism: collective regime majority direction (NEW)
5. hold: 4h/8h sweep

5/5 distinct verified. Fresh DNA but mechanism REFUTED.

## Lesson candidate REINFORCEMENTS for Q3 §6.2

1. **Lesson #73 REFUTED** (1st operational dogfood): density escape via cross-sym co-firing FAIL — Item 9 STRUCTURAL FAIL extends to cross-sym universe-wide event class. Hold extension and density escape BOTH fail. → **Lesson #73 reformulated**: **"Item 9 STRUCTURAL FAIL cannot be rescued by mechanism reformulation alone — requires either (a) hold ≥ 16h multi-bar (untested at this scale) OR (b) genuinely alpha-bearing trigger (axis fresh + non-OHLCV-z-spike DNA)."**

2. **Lesson #74 candidate ESCAPE 조건 1 REFUTED** (1st operational dogfood): cross-sym co-firing aggregation does NOT provide alpha-decay immunity. Pattern P1 11 consecutive now includes cross-sym variant. → **Lesson #74 severity ELEVATED**: per-sym OHLCV z-spike DNA HALT_BY_DEFAULT extends to cross-sym aggregations of z-spike DNA. ESCAPE 조건 1 INVALID. Need ESCAPE 조건 2+ tested (e.g., non-vol statistic, non-OHLCV substrate, fundamental triggers).

3. **Lesson #75 candidate cross-set asymmetry structural skew**: paradigm 223 cross-set 1.12x within 5x threshold. Cross-sym co-firing event class structurally constrains asymmetry (mutually exclusive direction within event). vs paradigm 222 per-sym 9.81x — confirms cross-set asymmetry is feature of trigger formulation, not universal mechanism. → **Lesson #75 candidate reformulated**: per-sym z-trigger sets show systemic cross-set asymmetry (UP-vol bias > DOWN-vol bias); cross-sym co-firing event sets bounded by event-construction symmetry.

4. **NEW Lesson #76 candidate**: "Cross-sym universe-wide aggregation creates structural bilateral negative drift in unconditional baseline (paradigm 223 universe-mean LONG=-8.88bp/SHORT=-7.12bp both significantly negative)." Universe-mean forward returns × any direction × fee = negative-floor structure regardless of conditioning. Implies cross-sym universe-aggregate trade design has inherent fee-bound floor independent of signal.

5. **NEW Lesson #77 candidate**: "Pattern P1 universal-class extreme alpha decay is **paradigm-class invariant** (per-sym OR cross-sym, intra-bar OR multi-bar). The 2024 alpha source for vol-z directional continuation is exogenous (likely market microstructure regime peculiar to 2024 alt-vol cycle); not recoverable via paradigm-architecture variation." This consolidates 11 consecutive Pattern P1 observations into a structural informational-learning claim.

## paradigm 224 next-action recommendation

- **STRONGLY recommend SWITCH to user-provided hypothesis mode** (paradigm-architect SELF-RECOMMEND mode-switch trigger): post-paradigm-222 1st SELF-RECOMMEND attempt (Candidate C) → BROAD_FALSIFIED + Lesson #73 PRESCRIPTION REFUTED. Mode-switch counter +1 (1 consecutive non-PASS in self-recommend). 4 more allowed before paradigm 203 MEMORIAL precedent (5 consecutive).
- If continuing SELF-RECOMMEND: **mandatory criteria**:
  - **non-OHLCV-z-spike DNA** (Lesson #74 severity ELEVATED)
  - **non-vol-derived statistic** (Pattern P1 11 consecutive consolidates rv/vol/std/range/atr family)
  - **non-universe-aggregate trade design** (Lesson #76 candidate: universe-aggregate has bilateral fee-floor structurally)
  - **non-directional-continuation cell type** (12 cells now Pattern P1 confirmed)
- If user-provided: open hypothesis frontier expansion. Suggested classes:
  - **Funding-rate cross-venue spread** (paradigm 103 Bybit substrate exists, untested cells remaining)
  - **OI velocity × premium index** (cross-substrate joint, distinct from OHLCV)
  - **Liquidation cascade detection** (event-driven, non-OHLCV)
  - **WS recorder microstructure** (after 2026-07-15 60+ days accumulation, distinct substrate)

## 메모리 정책 strict 준수 — COMPLIANT

- [[feedback-persistence-over-efficiency]] — dispatch continues, graveyard normal
- [[feedback-paradigm-campaign-continuous-parallel]] — continuous parallel preserved
- [[feedback-direct-recommendation]] — paradigm 224 next-action 권고 직접
- [[feedback-no-freemium-trial]] — zero backfill, joblib cache reuse
- [[feedback-life-changing-strategy-criterion]] — Item 9 STRUCTURAL FAIL applied
- [[feedback-timestamp-kst-suffix]] — KST timestamp 응답 마지막 줄
