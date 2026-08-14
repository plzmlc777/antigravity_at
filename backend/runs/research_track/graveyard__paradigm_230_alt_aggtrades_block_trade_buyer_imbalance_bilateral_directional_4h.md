# Graveyard — paradigm 230 alt_aggtrades_block_trade_buyer_imbalance_bilateral_directional_4h

**Date (KST)**: 2026-07-20
**Phase halted**: R-0 (infrastructure prescreen)
**Verdict**: `R0_HALT_BY_BANDWIDTH_AND_WALLCLOCK_CAP_INFEASIBLE_AGGTRADES_BACKFILL_SCOPE_EXCEEDS_AGENT_SPEC_HARD_LIMITS`
**Mode**: SELF_RECOMMEND autonomous (queue empty 2026-07-20)
**Compute saved by early halt**: ~351 min (preprocessing wall-clock) + ~9 min (backfill download) + R-1 batch time

---

## Hypothesis under test

In Binance Futures USDT-M perpetuals, 5m aggregated aggTrades data reveals size-class buyer/seller imbalance:

- `block_concentration_z` = rolling-30d z-score of (block_vol_usd / total_vol_usd), where "block" = individual trade >= $100K USD
- `block_buyer_fraction` = buyer_initiated_block_vol / total_block_vol

Joint trigger:
- A_focus: z >= 1.5 AND buyer_fraction >= 0.65 → LONG 4h
- A_mirror: same → SHORT (SNT mirror)
- B_same_sign: z >= 1.5 AND seller_fraction >= 0.65 → SHORT 4h
- B_mirror: same → LONG

**Substrate**: `data.binance.vision/data/futures/um/monthly/aggTrades/{sym}/{sym}-aggTrades-{YYYY}-{MM}.zip`
**Universe**: 13 alts (paradigm 69 R-5 universe)
**Hold**: 4h (Lesson #57 exempt from 5m+60m taker family retire per dispatch claim)

---

## R-0 Prescreen — HARD_FAIL on infrastructure

### Item 2 (Lesson #28 + candidate extension) — substrate volume audit

The dispatch briefing estimated `13 syms × 6 months × ~60MB compressed = ~4.7 GB`.

Actual HEAD-probe measurements (19 sym-month combinations sampled):

| Sym class | Sample sym-months | Avg MB/month | Extrapolated (13 syms × 6 mo) |
|---|---|---|---|
| Tier A (BTC/ETH) | 6 probes: BTC 340/692/700 MB, ETH 371/731/638 MB | **546 MB** | 2 syms × 6 × 546 = **6.55 GB** |
| Tier B (mid: DOGE/WIF/AVAX/LINK/NEAR) | 5 probes: DOGE 74-390, WIF 24-266 | ~200 MB | 5 syms × 6 × 200 = **6.00 GB** |
| Tier C (low: BNB/SOL/LTC/BCH/FIL/XRP) | 6 probes: LTC 26-115, FIL 28-57, SOL 173 | ~100 MB | 6 syms × 6 × 100 = **3.60 GB** |
| **Total compressed** | | | **16.15 GB** |
| Total uncompressed (5-10× zip ratio) | | | **80-160 GB** |

**Hypothesis underestimate factor: 3.4×** (actual 16.15 GB vs briefed 4.7 GB).

### Hard limits violated

| Cap | Spec source | Measured | Ratio |
|---|---|---|---|
| Backfill compressed volume | `.claude/agents/paradigm-architect.md` — "if > 10GB or > 30min ETA → STOP" | 16.15 GB | 1.62× |
| Preprocessing wall-clock per test | same — "Single test run > 60 min wall-clock → halt" | ~5.85 hr (351 min) for 13 syms × 6 mo × 4.5 min/sym-month weighted avg | 5.85× |
| Download ETA (only sub-check that would pass) | 30 MB/s CloudFront ICN53 → 16.15 GB ≈ 9 min | 9 min | 0.30× (pass in isolation, but bandwidth cap still binding) |

Preprocessing throughput reasoning: BTC-month aggTrades ≈ 30-40M CSV rows → pandas groupby 5m bar with size-class conditional sum ≈ 50k rows/sec on the current host → ~13 min per BTC-month, ~5 min per mid-cap-month, ~1 min per low-cap-month.

### Predecessor advisory reinforcement

`backend/runs/research_track/alt_daily_premium_index_kalman_innovation_z_mr_bilateral_1d_to_7d/r0_prescreen.json` (paradigm 227, 2026-07-15) explicitly recommended in `next_paradigm_recommendation.option_C_deferred_infrastructure`:

> "orderflow_via_aggTrades_taker_flow_1m_intraday_persistence_family — requires 1m aggTrades archive backfill (>30min ETA + Lesson #21 advisory caution family), needs explicit user greenlight"

The autonomous self-recommend queue proposed the 5m frame variant WITHOUT the explicit user greenlight paradigm 227 predecessor called for. Downgrading from 1m to 5m frame does not reduce raw archive volume (files are still monthly aggregated tick records; frame choice affects only downstream aggregation).

---

## Items PASSED before the halt

For completeness, items downstream of item 2 that would have PASSED (had infrastructure permitted continuation):

| Item | Lesson | Verdict | Note |
|---|---|---|---|
| 1 | #61 slug grep | PASS | no prior "aggtrades" slug in INDEX/graveyard/runs |
| 4 | #62 DNA 5-dim audit | PASS_NOVEL | 4/5 new axes vs closest paradigms (taker family 23/60/72 substrate + statistic-class + mechanism + frame all differ; OI-share family 228/229 substrate + statistic-class + mechanism + frame all differ) |
| — | #40 structural threshold | PASS | `block_buyer_fraction` bounded [0,1] and `block_concentration_z` is signed centered residual — symmetric threshold structurally feasible |
| — | #77 non-OHLCV substrate preference | PASS | aggTrades individual trade records IS non-OHLCV microstructure, matching #77 preference |

Item 3 (Lesson #11 sample density) was NOT MEASURED because empirical trigger-rate probing requires unblocking backfill (chicken-and-egg with item 2 hard fail).

Item 5 (Lesson #57 exemption argument) was NOT ADJUDICATED — the dispatch claim that size-class ≥$100K + 4h hold escapes the paradigm 23/60/72 taker family Tier 4 retire is logically plausible but experimentally unresolved. Adjudication deferred to a future revival with pre-built infrastructure.

---

## Novel Lesson Candidate — `backfill_volume_cap_enforcement_R0_hard_halt`

**One-line definition**: Substrate accessibility (HTTP 200 for archive files) is a necessary but not sufficient R-0 substrate audit item. The audit MUST measure total compressed backfill volume against the agent spec cap (10 GB / 30 min ETA / 60 min preprocessing per test in paradigm-architect.md), and halt if any limit is violated — BEFORE any Lesson #11 empirical sample-density measurement.

**Why it is not already covered by Lesson #28**:
- Lesson #28 covers "substrate availability at event time" (temporal existence dimension)
- This candidate covers "substrate volume within backfill-discipline cap" (volume + throughput dimensions)
- The two are orthogonal — paradigm 230 substrate has full temporal availability (Lesson #28 PASS in isolation) but blows the volume cap

**Prescription for R-0 substrate audit checklist**:
1. Slug grep (existing)
2. HTTP HEAD probe on 3-5 representative sym-months → measure `content_length`
3. Compute weighted `total_gb_compressed = Σ (n_syms × n_months × avg_mb_per_tier)`
4. HALT if:
   - `total_gb_compressed > 10 GB`, OR
   - `total_gb_compressed / bandwidth_MBps_30 > 30 min download ETA`, OR
   - `(total_gb_uncompressed_5x) / preprocessing_throughput_MBps_50 > 60 min per representative test run`

**Dogfood lineage**:
- 1st dogfood — **paradigm 230** (aggTrades 13 syms × 6 months = 16.15 GB compressed, 5.85 hr preprocessing)

**Promotion status**: CANDIDATE. Requires a 2nd dogfood (any future R-0 halt on the same volume-audit dimension) for CONFIRMED-eligible per Q3 elevation protocol.

**Relation to paradigm 227 predecessor advisory**: paradigm 227 R-0 output Option C already flagged aggTrades archive as "requires >30min ETA + explicit user greenlight" but as an *ad-hoc note* attached to a rejected candidate, not a mechanical R-0 check. This candidate formalizes that ad-hoc note into a repeatable checklist item.

---

## SELF-RECOMMEND meta-observation

Paradigm 230 is the **1st self-recommend dispatch since the paradigm 203 MEMORIAL** (2026-05-22, per PARADIGM_QUEUE_2026Q3.md §6.2) that halts at R-0 for a NEW reason (infrastructure/volume) rather than one of the previously-catalogued self-recommend saturation modes (DNA overlap, family-proxy proxy, statistic-class saturation, alpha decay documentation).

This is a distinct failure mode: the agent's own hypothesis generation is unconstrained by infrastructure budget awareness. The candidate lesson above closes that gap for future autonomous dispatches.

Per agent spec halt protocol: "SELF-RECOMMEND mode 5 consecutive non-PASS → switch to user-provided hypothesis mode 의무." This is 1/5 for the current streak. Continuous-parallel preserved; mode-switch not yet triggered.

---

## Artifacts

- R-0 prescreen JSON: `backend/runs/research_track/paradigm_230_alt_aggtrades_block_trade_buyer_imbalance_bilateral_directional_4h/r0_prescreen.json`
- This graveyard report: `backend/runs/research_track/graveyard__paradigm_230_alt_aggtrades_block_trade_buyer_imbalance_bilateral_directional_4h.md`
- No R-1 script written (halt is upstream)
- No backfill executed (halt prevents wget)
- INDEX.json update: paradigm_230 entry appended with `current_phase=R-0`, `graveyard_reason=R0_HALT_BANDWIDTH_WALLCLOCK`

## Next paradigm recommendation for autonomous queue

Route AWAY from bulk-archive substrate families (aggTrades, book depth L2 snapshots, sub-1m tick data) unless a persistent pre-aggregated cache already exists.

### Option A (preferred) — `alt_binance_perp_isolated_vs_cross_margin_oi_split_ratio_daily_z_directional_3d`
- Substrate: OI daily breakdown from Binance API/archive (isolated vs cross-margin split)
- Volume: <0.1 GB total (kilobytes/day/sym)
- Novelty axis: leverage-margin-mode composition (no prior paradigm on this dimension)
- Lesson #77 partial (mixed OHLCV/margin metadata)

### Option B (preferred) — `alt_realized_vol_signed_upside_vs_downside_asymmetry_semivar_ratio_z_directional_4h_retry_amended`
- Substrate: existing 1m OHLCV joblib cache — 0 additional backfill
- Novelty: amendment path not saturated by paradigm 134 (Lesson #54 mechanism-coherent redesign)
- Volume: 0 GB new

### Option C (deferred infrastructure precondition)
- Paradigm 230 revival ONLY if a one-time out-of-band infrastructure spike pre-computes 5m block-trade aggregates (block_vol_usd, block_buy_vol_usd, block_sell_vol_usd, total_vol_usd, block_concentration per 5m bar per sym) for ≥30 months × 13 alts, stored under ~2 GB joblib. This is a **separate infrastructure task outside paradigm-architect autonomous scope** and requires explicit user greenlight.

The hypothesis itself is NOT falsified — only infrastructure-deferred. DNA-novelty (4/5 new axes) and Lesson #57 exemption argument survive intact for future adjudication.
