# Graveyard — `dart_supply_contract_announce_kr_equity_long_5d`

**Phase**: R-1 PoC complete.
**Verdict**: `CONCENTRATION_FAIL` (R-1) + `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` (auxiliary).
**Date**: 2026-05-19 KST.
**Paradigm count**: 101 (cumulative R-1+ graveyards).
**Hypothesis class**: KR equity DART year-round filing (agent-recommended frontier from paradigm 100 next-step).

---

## Hypothesis tested

KR equity 단일판매·공급계약체결 공시 (single sales/supply contract announcement) = immediate market attention information event. Announce day + 1d open entry, +5d hold LONG, KOSPI200 + KOSDAQ150 universe.

Mechanism class analogy: paradigm 87 binance_delisting_announce (immediate market attention) + lifecycle_pump_decay (entry-side immediate demand). Year-round filing distribution distinct from paradigm 100 Q1-clustered guidance amendments.

---

## R-0 prescreen — `GO_R1`

R-0 substrate audit (~54 min DART scan):
- 305,214 KR equity disclosures scanned (corp_cls Y+K, 2024-01-01 .. 2026-05-19)
- 2,421 matched (filter: 단일판매 + 공급계약 + universe 350)
- Quarterly distribution **year-round** (paradigm 100 trap successfully avoided): 10/10 quarters all ≥ 88 events, max/min 400/150 ratio 2.7×
- 127 unique triggered stocks (36% of universe)
- **density_pass=True (per_qtr=242.1 ≥ 30)** + **n_measurable_quarters_pass=True (10 ≥ 4)** → R-1 GO

R-1 filter (focus mechanism, exclude 해지/자회사/거래정지) reduced to 2,058 events; OHLCV-matched 2,009 with valid returns across 115 distinct stocks.

---

## R-1 4-quadrant Symmetric Negative Test (Lesson #19) — primary hold=5d

| Cell | n | gross_bp | net_bp (50bp fee) | t_obs | signal_t_excess | perm_p_upper | ci_lower_bp | three_gate |
|---|---|---|---|---|---|---|---|---|
| **A focus announce × LONG** | 2009 | +102.9 | **+52.9** | +2.49 | **−0.75** | 0.808 | +12.1 | **FAIL** |
| A mirror announce × SHORT | 2009 | −102.9 | −152.9 | −7.18 | +0.82 | 0.143 | −192.5 | FAIL |
| **B baseline non_announce × LONG** | 14886 | +118.4 | **+68.4** | +8.83 | — | — | +53.0 | FAIL |
| B baseline non_announce × SHORT | 14886 | −118.4 | −168.4 | −21.75 | — | — | −183.7 | FAIL |
| A focus @ 100bp fee stress | 2009 | +102.9 | +2.9 | +0.14 | −0.71 | 0.778 | −37.9 | FAIL |

**Critical pattern**: **A focus LONG net (+52.9bp) < B baseline LONG net (+68.4bp).** The supply contract announcement under-performs random non-announce same-universe entry by ~15bp/5d. The observed t-obs +2.49 is misleading because the null pool (universe random entries) yields **null_mean_t = +3.24σ** under the same 50bp fee regime — i.e. the universe baseline carries a positive drift that is intrinsically larger than the focus subset.

**signal_t_excess = −0.75** (5d), −1.65 (3d), +1.27 (10d). All three holds fail signal_t_excess ≥ 2.0 threshold. The announcement contributes ZERO information net of universe drift.

A mirror SHORT also fails (Lesson #8 mirror-only trap NOT triggered — both directions sub-fee). Consistent with broad falsification.

---

## R-1 Cross-proxy strict (Lesson #29) — both proxies FAIL at primary 5d

| Track | Split | n | net_bp | t_obs | Hypothesis-coherent? |
|---|---|---|---|---|---|
| Observable (entry gap) | gap_pos | 1139 | +52.8 | +1.73 | gap_pos ≈ gap_neg → **NO** sentiment differentiation |
| Observable (entry gap) | gap_neg | 870 | +53.1 | +1.85 | same |
| Fundamental (freq_6m) | freq_low_33pct (informative) | 679 | +57.4 | +1.54 | freq_low < freq_high → **INVERSE** of hypothesis |
| Fundamental (freq_6m) | freq_high_33pct (noise) | 678 | +121.9 | +3.00 | high-freq announcers OUTPERFORM |

- **obs_proxy_gap_pos_minus_neg_bp = −0.3** (essentially zero) → sentiment proxy null
- **fund_proxy_freq_low_minus_high_bp = −64.5** (inverse) → frequent announcer = better return, not noise

The "information event with attention demand" hypothesis is **rejected**: high-frequency announcers OUTPERFORM low-frequency announcers by ~65bp/5d net. This indicates the apparent signal is **company-quality selection bias** (growth companies announce contracts frequently), NOT an event-driven information shock.

At hold=10d, the inversion persists: freq_high +394.9bp vs freq_low +218.7bp (−176.2bp differential). Cross-proxy strict definitively reject the mechanism class.

---

## R-1 Concentration Gate (Lesson #16 + #26 amendment) — FAIL

### Per-quarter t-stat (Lesson #26 amendment, n_measurable_quarters ≥ 4 satisfied at 10/10)

| Hold | n_measurable | n_pos_t | quarter_pos_t_ratio | PASS ≥ 0.5? |
|---|---|---|---|---|
| 3d | 10 | 3 | 0.30 | **FAIL** |
| 5d | 10 | 7 | 0.70 | PASS |
| 10d | 10 | 7 | 0.70 | PASS |

5d/10d quarter-stability PASS. Year-round distribution genuinely avoided paradigm 100 trap. R-0 prescreen of agent dispatch spec confirmed valid for this dimension.

### Per-symbol bootstrap CI (Lesson #16)

| Hold | n_measurable | n_ci_pos | symbol_ci_pos_ratio | PASS ≥ 0.30? |
|---|---|---|---|---|
| 3d | 61 | 2 | 0.033 | **FAIL** |
| 5d | 61 | 4 | 0.066 | **FAIL** |
| 10d | 61 | 15 | 0.246 | **FAIL** (24.6% < 30%) |

**Per-symbol concentration heavily fails** — only 4-15 of 61 measurable symbols have CI lower bound > 0. The "signal" is dominated by a long tail of high-variance symbols where the bootstrap CI is wide and negative. No reproducible per-symbol effect.

**Concentration Gate composite PASS = FALSE at all 3 holds.**

---

## R-1 Life-changing 4-dim measurement (mandatory)

| Hold | n_trades | trades/yr | per_trade_edge_net | annualized_sharpe | util_calendar | 4-dim PASS |
|---|---|---|---|---|---|---|
| 3d | 2009 | 865.3 | **−0.17%** | −0.75 | 0.96 | FAIL (edge + sharpe FAIL) |
| 5d | 2009 | 865.3 | **+0.53%** | +1.63 | 0.99 | FAIL (edge FAIL — 0.53% < 2.0%) |
| 10d | 2009 | 865.3 | **+2.65%** | +5.48 | 1.01 | **PASS** (all 4 dims) |

The 10d 4-dim "PASS" is **misleading universe-drift artifact**: B baseline non_announce @10d hold yields +229.8bp net (universe carries +2.30%/10d positive drift in 2024-2026 KR equity bull regime). A focus +265.3bp net is only +35.5bp/10d edge over baseline — well below the 50bp fee cushion required to survive R-2 walk-forward fold variability. This is the same trap as paradigm 95 narrow-scope life-changing false-positive: 4-dim measurement passes on universe drift, not on the event-driven signal.

---

## Lesson grid dogfood summary

| Lesson | Pre-/Post-screen result |
|---|---|
| #11 (sample density) | PASS R-0 (242 events/quarter ≫ 30 cutoff) |
| #16 (Concentration) | **FAIL** all 3 holds (symbol_ci_pos_ratio 3-25% < 30%) |
| #19 (4-quadrant Symmetric Negative) | dogfood successful — A focus + A mirror + B baseline + B baseline mirror single batch reveals A_focus < B_baseline universe-drift trap |
| #20 (sign-cond 4-cell) | N/A (no sign-conditional structure tested) |
| #26 amendment (n_measurable_quarters + quarter_pos_t_ratio) | year-round filing PASS (10/10 quarters, paradigm 100 trap avoided) — **agent dispatch design successful** |
| #27 amendment (immediate vs delayed) | disclosure_parser.py prescreen revealed NO entry for 단일판매·공급계약 — agent recommended Side.ENTRY_IMMEDIATE classification (announcement → next-bar reaction analog to lifecycle listing). Mechanism class confirmed entry_immediate but **signal NOT distinct from universe drift** |
| #28 (substrate availability) | PASS (DART substrate stable, 2.4yr full window) |
| #29 (cross-proxy strict) | **FAIL** — fundamental proxy (freq_6m) inverse of hypothesis (high-freq announcers OUTPERFORM, contradicting "information event" thesis). dogfood 3번째 catch |
| #30 (short-data verdict) | N/A (2.4yr ≈ 96% full DART window) |
| #31 (DNA inventory cross-check) | DNA ≤ 4/6 vs paradigm 87 / 100 (substrate distinct: KR equity DART vs Binance perp / KR equity DART guidance) |

**Lesson #29 cross-proxy strict** = **3rd consecutive dogfood success** after paradigm 92 (H1 earnings) + paradigm 93 (H2 guidance). The fundamental track (announcement frequency proxy for information density) inversely correlates with outcome — strongest evidence that the apparent signal is **company-quality selection bias**, NOT event-driven attention demand. The "single proxy trap" classification protects against R-2 wasted compute.

---

## Why this paradigm fails (mechanism-level diagnosis)

1. **Universe drift dominance**: KR equity 2024-01-01 .. 2026-05-19 carries +119bp/5d non_announce baseline LONG return (+8.83σ). Any "signal" sub-cell must clear B baseline + fee floor, not just t-obs > 0. A focus +52.9bp/5d **under-performs** B baseline by 15bp.

2. **Cross-proxy inverse**: frequent announcers OUTPERFORM low-frequency announcers by 64-176bp. The "information event with attention demand" thesis is rejected — frequent contract winners are growth-quality companies whose price drift is intrinsic, not announcement-event-driven.

3. **Per-symbol concentration failure**: only 4-15 of 61 measurable symbols have positive ci_lower at any hold. The aggregate "signal" is a thin tail of high-variance outliers, not a reproducible per-event effect.

4. **Distinct from paradigm 100 trap**: agent dispatch SUCCESS — year-round filing distribution genuinely satisfies Lesson #26 amendment quarter-stability prescreen (7/10 q_pos_t at 5d/10d). The failure mode is fundamentally different from paradigm 100's Q1 clustering temporal artifact: paradigm 101 has **temporal stability but cross-section concentration + universe-drift artifact**.

---

## Mechanism-class implications

### KR equity year-round-filing entry-side paradigm fails too

Combined with paradigm 92 (잠정실적 earnings gap) + 93 (가이던스 amendment) + 100 (가이던스 mean-reversion) + 101 (단일판매·공급계약 contracts), **all 5 KR equity DART entry-side momentum/attention paradigms fail R-1 or R-2**.

The accumulated pattern argues for **KR equity DART entry-side directional family Tier 4 retire amendment**:
- Already retired: post-earnings/guidance directional momentum family (paradigm 92+93+100, [[feedback_family_retire_kr_post_earnings]])
- **Amendment proposed**: KR equity DART **information-event-attention directional momentum family** (paradigm 101 single sales contracts) **also Tier 4 retire**

Common failure modes:
- (a) Universe drift dominance (KR equity 2024-2026 bull market makes naive LONG hard to beat)
- (b) Cross-proxy inverse (fundamental signal contradicts observable surprise) — Lesson #29 catches
- (c) Per-symbol concentration (signal not reproducible across triggered universe subset)

### What's left as KR equity directional paradigm space?

1. **Non-directional event paradigms** — volatility expansion, regime-shift signaling (NOT directional momentum/mean-reversion)
2. **Cross-asset paradigms** — KR equity × KRW/USD × foreign-flow (paradigm class not yet tested)
3. **Earnings preannouncement EXIT-side** — paradigm 87/88/lifecycle analog requires substrate audit (no existing KR analog known)

Agent dispatch path (b) "year-round filing" successfully exited Lesson #26 amendment trap but encountered new failure dimension (universe drift + Cross-proxy inverse). Agent dispatch path (c) "non-directional volatility event" remains untested.

---

## Lesson #32 candidate — Universe-baseline-coherent A_focus trap

**Definition**: When A_focus three-gate aggregate t-obs PASS (t_obs ≥ 2.0, ci_lower > 0) but signal_t_excess < 2.0 because null_mean_t (universe-baseline pool with same fee) also exceeds 2.0, the apparent signal is **universe-baseline drift carrying both A focus and B baseline**, NOT event-driven excess return.

**Diagnostic**: B_baseline cell (random non_announce entries from same universe) net_bp ≥ A_focus net_bp under same fee. If true, the "signal" is universe drift, not the event.

**Antipattern**: Promoting to R-2 on A_focus three-gate PASS alone without checking A_focus net > B_baseline net + fee_uncertainty_margin (~15-20bp typical) misallocates R-2 compute.

**Dogfood**: paradigm 101 (this graveyard) at all 3 holds. At hold=5d, A_focus +52.9bp vs B_baseline +68.4bp → 15.5bp shortfall, signal_t_excess = −0.75. At hold=10d, A_focus +265.3bp vs B_baseline +229.8bp → +35.5bp excess but ≪ fee 50bp safety margin, also fails signal_t_excess gate.

**Prescription**: paradigm-architect R-1 verdict tree amendment — add `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` (or `UNIVERSE_BASELINE_COHERENT_TRAP`) verdict between `BROAD_FALSIFIED_MIRROR_ONLY` and `SINGLE_PROXY_TRAP_*`. Triggered when:
- A_focus three-gate per-cell PASS (t_obs ≥ 2.0, ci_lower > 0) BUT
- signal_t_excess < 2.0 (perm null pool exceeds observed) AND
- B_baseline net_bp ≥ A_focus net_bp − 15bp

Already partially captured by signal_t_excess gate in current code, but the **diagnostic naming** is missing. Without explicit verdict class, future agents may mis-categorize as CONCENTRATION_FAIL (this paradigm's actual final verdict) when the primary failure is universe-drift artifact, not concentration.

---

## Next-step recommendations

1. **Do NOT retry single sales/supply contracts** — universe-drift dominance + cross-proxy inverse + per-symbol concentration triple-fail. Mechanism class falsified.

2. **KR equity DART entry-side directional family Tier 4 retire amendment** — extend [[feedback_family_retire_kr_post_earnings]] to include information-event-attention directional (paradigm 101). Block:
   - 단일판매·공급계약 variants (hold/threshold/universe variations)
   - 자기주식취득결정 (treasury_buyback Side.ENTRY_DELAYED) — already mechanism distinct + paradigm 100 candidate dart_treasury blocked via lesson #27 amendment
   - 5% 대량보유 (FIVE_PCT_REPORT Side.EXIT) — entry-side reclassification ambiguous

3. **Non-directional volatility event paradigm** (agent recommended path c from paradigm 100 §Next-step) **becomes the next priority**:
   - 단일판매·공급계약 announce day vol expansion / intraday range / overnight gap squared
   - NOT directional bet — vol-targeting / straddle-payoff structure
   - Substrate already cached (events_cache + OHLCV) — Phase 0/1 cost MINIMAL (~5min smoke test)

4. **Cross-asset KR equity paradigm class** (untested):
   - KR equity × KRW/USD × foreign flow (deposit + DRP)
   - KR equity × KOSPI ETF basket × cross-listing US ADR (SK Telecom / SK Hynix / 삼성전자 sponsored ADR)
   - Substrate requires Naver foreign-flow API audit + ADR price source — Phase 0 audit 2-3hr

5. **Lesson #32 (Universe-baseline-coherent A_focus trap) formal addition** to PARADIGM_QUEUE_2026Q3.md §6.2.

6. **Day 7 baseline 2026-05-21 우선 모드 유지** — paper pool baseline measurement remains the priority. Ad-hoc R-1 dispatch cumulative cost paradigm 101 = ~1hr DART API + ~5sec R-1 = ~1hr (R-0 prescreen dominated). Acceptable but R-2/R-3 expansion would be wasted compute given the diagnostic clarity.

---

## Artifacts

- code: `backend/scripts/research/dart_supply_contract_r0_prescreen.py` (R-0 prescreen)
- code: `backend/scripts/research/dart_supply_contract_r1.py` (R-1 PoC)
- R-0 metrics: `backend/runs/research_track/dart_supply_contract_announce_kr_equity_long_5d/r0_prescreen_metrics.json`
- R-0 events raw: `backend/runs/research_track/dart_supply_contract_announce_kr_equity_long_5d/r0_matched_events_raw.json` (2,421 events)
- R-1 metrics: `backend/runs/research_track/dart_supply_contract_announce_kr_equity_long_5d/r1_metrics.json`
- events cache: `backend/runs/research_track/dart_supply_contract_announce_kr_equity_long_5d/supply_contract_events_cache.joblib` (2,009 OHLCV-joined events)
- this graveyard: `backend/runs/research_track/graveyard__dart_supply_contract_announce_kr_equity_long_5d.md`

---

## Side discoveries (non-graveyard-relevant)

1. **DART pblntf_ty discovery**: 단일판매·공급계약체결 is NOT under pblntf_ty=B 주요사항보고서 — lives under pblntf_ty=I 거래소공시 (initial scan with pblntf_ty=B yielded matched=0/20016 because the disclosure category is exchange-mandated, not major-matter). Future R-0 substrate audits must NOT assume disclosure category without empirical probe.

2. **disclosure_parser.py gap identified**: no entry for 단일판매·공급계약체결. Patch deferred (no follow-up R-2 planned). If future paradigm reuses this substrate, add `SUPPLY_CONTRACT = DisclosureKind("supply_contract", Tier.A, Side.ENTRY_IMMEDIATE, "단일판매ㆍ공급계약체결")` and parsing rule `if "공급계약체결" in nm and not any(t in nm for t in ("해지", "자회사", "거래정지"))`.

3. **Quarter-stability genuinely PASSED** at primary 5d/10d hold (7/10 quarter t_pos). agent dispatch design successfully avoided paradigm 100 Q1-clustering trap. This validates the agent prescreen architecture (R-0 audit for n_measurable_quarters) — the failure mode shifted from temporal to cross-section concentration + universe-drift artifact, demonstrating the prescreen is necessary but not sufficient.

4. **Per-symbol n=8 cutoff observed**: 61 measurable symbols of 115 triggered (53%). The 54 symbols below n=8 (≤8 trigger events per symbol over 2.4yr) are the long thin tail — future paradigms reusing DART substrate should consider per-symbol n ≥ 20 minimum for inclusion in Concentration Gate measurement.

---

## Cumulative paradigm-architect spec amendments emerging from this graveyard

1. **Add verdict `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT`** to R-1 verdict tree (Lesson #32 candidate)
2. **Add lesson #32** to PARADIGM_QUEUE_2026Q3.md §6.2
3. **Extend `feedback_family_retire_kr_post_earnings`** to information-event-attention directional family (paradigm 101)
4. **r0_inventory_check skill** add disclosure_parser.py audit + DART pblntf_ty empirical probe (not assumed) for KR equity year-round-filing paradigms
5. **R-1 cell_stats `pass_three_gate` patch consideration**: explicitly add `pass_signal_t_excess_min_2` as separate flag distinct from `pass_three_gate` — current code wraps both into one flag, masking which gate fails
