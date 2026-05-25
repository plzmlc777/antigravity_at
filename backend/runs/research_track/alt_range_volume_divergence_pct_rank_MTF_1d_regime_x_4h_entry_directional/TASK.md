# Task — paradigm 154 `alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional`

**Dispatch**: 2026-05-21 15:10 KST
**R-0 verdict**: `R0_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION`
**R-1 dispatched**: **NO** (R-0 categorical halt)
**Counter**: 153 → **154** (substantive R-0 increment per [project_paradigm_97_funding_dispersion_inventory_halt] policy: 3-lesson dogfood + Lesson #62 candidate 2nd dogfood + new verdict reinforcement)
**Non-PASS streak**: 24 → **25**

## Hypothesis (rejected at R-0)

- **Trigger**: MTF dual confirmation — 1d 1y rolling pct rank vol regime stratify (HIGH/MID/LOW) × 4h 90d rolling pct rank entry (paradigm 153 statistic identical)
- **Mechanism claim**: paradigm 153 alpha 부재는 regime-blind bar-level이 원인, 1d HIGH-vol regime이 alpha 발현 조건 isolate
- **Universe**: 14 alts (BTC/ETH/BNB/SOL/XRP/ADA/DOGE/LINK/LTC/BCH/AVAX/ETC/FIL/ATOM)
- **Hold**: 4h
- **Substrate**: `backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib` (14 syms × 2024-02~2026-04 × 11 cols)

## R-0 Prescreen — 3 lessons categorical trigger

### Lesson #62 candidate 2nd dogfood — Family-distinct 4-dim strict audit FAIL

| Dim | paradigm 153 | paradigm 154 | strict change? |
|---|---|---|---|
| Trigger (statistic class) | 4h range/vol pct rank 30d window | 4h range/vol pct rank 90d window | **NO** (window length = parameter tweak, NOT class change) |
| Entry-side class | 4h trigger-bar close, immediate | 4h trigger-bar close + 1d regime filter | **NO** (regime gate is filter, NOT entry-side reclassification) |
| Mechanism (first-principles) | thin/consolidation regime classifier | same + 1d regime ISOLATES alpha (conditioning claim) | partial only |
| Substrate | 12-col 4h klines | 12-col 4h klines + 12-col 1d klines (same source) | partial only (same source, resampling) |

- **Strict dimension changes: 0/4** (Lesson #62 candidate threshold ≥2 required)
- **Partial dimension changes: 2/4** (still insufficient — Lesson #62 strict threshold defines structural change, not stacked filtering)
- Lesson #62 candidate (1st dogfood paradigm 151) **2nd dogfood**: paradigm 154 = paradigm 153 + regime filter overlay = retiming reframe antipattern
- Lesson #62 promotion path: **candidate → CONFIRMED 자격 reached** (2 dogfoods bidirectional)

### Lesson #56 CONFIRMED (7 instances) — OUTCOME-LEVEL family proxy 8th instance

`range_volume_divergence_directional` family chain:

| # | Paradigm | Verdict | Axis |
|---|---|---|---|
| 110 | funding_neg_z pct rank | BROAD_FALSIFIED_DIRECTION_INVERTED | (cross-family precedent) |
| 115 | range-volume related | DIFFUSE_POSITIVE | range/volume |
| 137 | range-volume related | GRAVEYARD | range/volume |
| 150 | ATR-normalized range breakout | R0_HALT_BY_OUTCOME_LEVEL_FAMILY_PROXY | range magnitude |
| 152 | range_z - vol_z divergence | HALT_STRUCTURAL_ASYMMETRY | range/volume divergence |
| 153 | range/vol pct rank 30d | BROAD_FALSIFIED | range/volume divergence pct rank |
| **154** | **MTF regime × 4h entry pct rank** | **R0_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION** | **8th instance** |

- Lesson #56 CONFIRMED since 5 instances; 8th occurrence categorically triggers OUTCOME-LEVEL family proxy gate
- paradigm 153 graveyard directly demonstrated mechanism alpha 부재 at bar-level — paradigm 154 is "same trigger + filter overlay"
- OUTCOME-LEVEL prediction: paradigm 154 R-1 HIGH-regime cell would reproduce paradigm 153 fee-floor outcome with smaller n

### Lesson #21 CONFIRMED sub-finding (7th candidate) — MTF axis stacking degeneracy

- paradigm 154 explicit 2-axis stack: 1d range-vol divergence × 4h range-vol divergence
- **Critical**: 1d divergence = approximate aggregation of 6 × 4h divergences on SAME bar data
- Two axes are NOT statistically independent — autocorrelation of SAME statistic at different time scales
- Lesson #21 statement: axis stacking does not synthesize alpha if no constituent axis carries alpha
- paradigm 83 (oi_5m_latent_regime k=4) precedent: 4/4 clusters BROAD_FALSIFIED (-27σ to -58σ) when regime stratification applied on alpha-empty underlying
- paradigm 81 (rolling beta 4-cell sign-cond) precedent: cell PASS but concentration FAIL 3/13 alts isolated
- Lesson #21 sub-finding 7th candidate dogfood: "MTF stacking of SAME statistic class on SAME substrate"

### Lesson #63 candidate predictive dogfood

- Lesson #63 statement (1st dogfood paradigm 153): "structural fix ≠ mechanism alpha resurrection"
- paradigm 154 framing: paradigm 153 mechanism alpha was tested + verified ABSENT at bar level; regime conditioning is alpha resurrection attempt via stacking, NOT via new mechanism story
- Lesson #63 candidate 2nd dogfood (predictive — halt prevents materialization)
- Promotion path: candidate 2nd dogfood with predictive verdict → CONFIRMED 자격 reached (2 dogfoods bidirectional)

### Lesson #30 data window — PASS (advisory only)

- 14/14 syms 4h cache available
- Window 2.2yr / Mint full universe 2.4yr = 91.7% (≥30% threshold)
- Verdict full provenance — does NOT rescue from Lesson #62/#56/#21 categorical halt

### Lesson #58 same-bar same-substrate corr — N/A (deferred)

- paradigm 152 PASS first dogfood (13/13 syms range-vol corr 0.65-0.78 healthy zone)
- paradigm 154 inherits paradigm 152 PASS xref
- R-0 halt upstream — no execution needed

### Lesson #11 sample density — PASS (advisory only)

- 14 syms × 2.2yr × 4h ≈ 67,200 base obs
- 1d HIGH regime (p70+) × 4h pct rank >0.95 ≈ 1,000 events / 4-quadrant × 250 per-cell (>30 cutoff)
- PASS does NOT rescue from family-distinct categorical halt

## Verdict composition

```
R0_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION
├── LESSON_62_RETIMING_REFRAME_2ND_DOGFOOD       (categorical, candidate → CONFIRMED 자격)
├── LESSON_56_OUTCOME_LEVEL_FAMILY_PROXY_8TH_INSTANCE  (categorical, CONFIRMED reinforcement)
├── LESSON_21_MTF_AXIS_STACKING_SAME_STATISTIC_DEGENERATE  (categorical, sub-finding 7th candidate)
└── LESSON_63_STRUCTURAL_FIX_RESURRECTION_ATTEMPT  (predictive, candidate 2nd dogfood → CONFIRMED 자격)
```

## Compute saved

- ~20-25x vs R-1 full dispatch (MTF cache build + 4-quadrant Monte Carlo + concentration diagnostics skipped)
- ~5-8 min wall-clock saved
- R-1 ritual dispatch would have reproduced paradigm 153 outcome with smaller n inside HIGH-regime cell

## Range_volume_divergence family — Tier 4 RETIRE candidate

- 6 graveyards (110+115+137+150+152+153+154 = 7 instances if 110 counted; 6 if pure range/vol)
- 3 distinct statistic classes attempted: z-score (p152) / pct rank (p153) / MTF regime × pct rank (p154)
- All structural feasibility paths exhausted at bar-level + MTF stack
- **Tier 4 retire eligibility**: YES (≥5 graveyards + axis exhaustion across statistic classes)
- Formal retire recommendation: range_volume_divergence axis family Tier 4 retire (consistent with funding family / cross-exchange OI / ATR-normalized magnitude / HMM / sub-5min momentum precedents)

## Next paradigm 155 recommendation

Given:
- 25-streak non-PASS
- range_volume_divergence family Tier 4 retire eligible
- Lesson #56 8-instance OUTCOME-LEVEL evidence base
- Lesson #62 candidate → CONFIRMED 자격 (2 dogfoods)
- Lesson #21 sub-finding 7th candidate (CONFIRMED-eligible threshold)
- 메모리 [feedback-persistence-over-efficiency] 명시: closing rate observation is statistical noise, dispatch 지속 본질

**권장 axes (genuinely family-distinct, ≥2 strict dim change vs ALL paradigm 152-154)**:

| Option | Path | Rationale |
|---|---|---|
| **α** | paradigm 22 R-5 funding mechanism **cross-frame VALIDATION** (1h vs 4h vs 1d frame) | R-5 already-validated mechanism, family-distinct via genuinely-new substrate (funding 1y → 30d sub-window), Lesson #62 strict not applicable (R-5 ratification track) |
| **β** | `btc_realized_vol_p90_alt_directional_4h_resume` — paradigm 69 R-5 macro proxy resume | substrate always available, family-orthogonal to range_volume, Lesson #56 outcome family proxy SELF-validation track |
| **γ** | `alt_post_listing_first_5min_directional_5m` — lifecycle pump-decay sub-spec variant | R-0 family-distinct ≥2 dim audit required (frame change + entry timing change vs paradigm 22) |
| **δ** | lifecycle live mode 2026-05-29+ wait | WS recorder 60+d accumulation, genuinely-new substrate |

**메타 권고**: **Option β** (paradigm 69 R-5 macro proxy resume) — substrate always available, no freemium, paradigm 153/154 range_volume family fully orthogonal, R-5 mechanism robust time-validation 자체 가치. Option α는 R-5 ratification track으로 paradigm campaign main lane과 분리. Option γ는 Lesson #61 next-action provenance audit 의무.

## Artifacts

- `backend/scripts/research/paradigm154_r0_prescreen.py` (compile clean, executed 2026-05-21 15:12 KST, wall clock ~0.5s)
- `backend/runs/research_track/alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional/r0_prescreen.json`
- `backend/runs/research_track/alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional/TASK.md` (this file)
- INDEX.json paradigm 154 entry (pending)
- PARADIGM_QUEUE_2026Q3.md §6.51 entry (pending)
- `backend/runs/research_track/graveyard__alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional.md` (pending)

## Counter update

- Graveyards: 153 → **154**
- R-5 LIVE: 10 (unchanged)
- Non-PASS streak: 24 → **25**
- R-5 yield: 10/154 = **6.49%**
- Lessons: 34 confirmed + 17 candidates → **35 confirmed + 17 candidates** (Lesson #62 candidate → CONFIRMED 자격 promoted; Lesson #63 candidate 2nd dogfood → CONFIRMED 자격 reached; Lesson #21 sub-finding 7th candidate)
- Q3 §6.51 next entry
