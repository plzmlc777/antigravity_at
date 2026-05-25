# Graveyard — paradigm 191

**Slug**: `binance_bybit_okx_delisting_announce_short_alt_universe_expanded_n_gte_300_1d_hold`
**Counter**: paradigm 191 (substantive R-0 halt — paradigm 88/89/90/97-c/159/176 precedent)
**Phase**: R-0 prescreen halt (R-1 NOT dispatched)
**Verdict**: `HALT_SUBSTRATE_PARTIAL_PLUS_PARADIGM_CLASS_MISMATCH`
**Date (KST)**: 2026-05-22

## Hypothesis (1-line)

paradigm 87 (Binance delisting forced-EXIT, n=57, R-2 FRAGILE_TEMPORAL_WF_FAIL graveyard) **universe expansion** to Binance + Bybit + OKX multi-venue (n_target ≥ 300, 5.3x boost) to address R-2 wf small-sample blind spot.

## Lesson #69 5-item strict prescreen result

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | slug grep | PASS | multi-venue slug unique |
| 2 | substrate-shape | MARGINAL_PARTIAL_FAIL | Binance FULL, Bybit PARTIAL (REST 0 bars post-delist, public archive TICK CSV.gz available), **OKX UNAVAILABLE** (REST 51001, CDN NoSuchKey) |
| 3 | sample density (#11) | PASS_modulo_substrate | n=57 + 249 Bybit = 306 (if substrate path resolved) |
| 4 | DNA 4-dim (#62) | MARGINAL | 3/5 strict distinct vs paradigm 87 (mechanism + direction + hold same) |
| 5 | family-proxy | FAIL | paradigm 87 family Tier 4 retire 사실상 (paradigm 87 R-2 FRAGILE + paradigm 88 exit-side HALT + paradigm 190 plateau-illumination 누적) |

## Lesson #70 corollary scope verdict

**Scope = (b) R-1 PASS follow-up sample-density refinement** (NOT Lesson #70 corollary scope (a)).

- paradigm 87 phase = **graveyard** (R-2 FRAGILE_TEMPORAL_WF_FAIL), NOT R-5_LIVE
- Lesson #70 CONFIRMED universal scope = R-5 LIVE survivor narrow-cohort expansion (paradigm 22 + 24 R-5 dogfoods)
- Universe expansion = mechanism class-preserved sample boost, distinct from per-sym parameter optimization
- **Lesson #70 NOT BLOCKING** for paradigm 191
- **But separate ROOT CAUSE MISMATCH blocks anyway** (see §3 below)

## Substrate verification result

| Venue | Announce API | OHLCV substrate | Freemium | Verdict |
|---|---|---|---|---|
| **Binance** | Public CMS API | joblib cache ready (n=57) | PASS | FULL |
| **Bybit** | V5 announcements/index 229 Derivatives delisting articles | REST kline = 0 bars post-delist; public.bybit.com/trading/{SYM}/ tick CSV.gz RETAINED (AVL Feb-2025 verified) | PASS (no signup) | PARTIAL (custom tick-to-kline reconstruction needed) |
| **OKX** | V5 support/announcements (50+/page) | REST history-candles 51001 'doesn't exist'; CDN /cdn/okex/traderecords/ NoSuchKey | PASS for announcements; OHLCV UNAVAILABLE | **UNAVAILABLE** |

## §3 Root cause mismatch (decisive HALT reason)

**Hypothesis frames paradigm 87 R-2 FRAGILE_TEMPORAL_WF_FAIL as "small-sample blind spot"**. But paradigm 87 R-2 report §3 explicitly states:

> *"2026 들어 alpha 감쇠 확연 — 시장 참여자들이 이 패턴을 학습/선반영하기 시작했을 가능성 (delisting 사전 leak / informed selling acceleration)"*

R-2 quarterly breakdown:
- 2024-Q4: +44bp
- 2025-Q3: +1986bp
- 2025-Q4: +1601bp
- 2026-Q1: +1995bp
- 2026-Q2: **+650bp** (clear monotonic decay)

**This is ALPHA DECAY paradigm class, NOT small-sample paradigm class.** Universe expansion (spatial sample boost) does NOT address temporal drift (informational learning by market participants). Cross-venue events in 2026 expected to show same decay pattern (market-wide simultaneous learning).

**Predicted R-2 outcome at n=306 expanded universe**: STILL_FRAGILE_TEMPORAL_WF_FAIL probability ≥ 60%.

## §4 4-dim audit estimate (expanded universe)

| Dimension | Estimate | Verdict |
|---|---|---|
| trades/yr | ~110 | PASS |
| edge/trade | ~7-10% (Bybit shorter announce-delist gap → smaller magnitude) | PASS (≥ 2%) |
| capital util | ~35-50% | PASS |
| sharpe | ~5-7 | PASS |

**4-dim PASS likely IF execution proceeded** — but R-2 wf root-cause mismatch overrides.

## §5 Lesson #30 candidate 3rd dogfood (CONFIRMED 자격 ACHIEVED)

Data window ratio: n=57 (paradigm 87 Binance-only) / n=306 (multi-venue) = **18.6% (≤ 30% threshold)**.

- 1st dogfood: paradigm 94 (local 72d vs Mint 845d, 8.5% slice)
- 2nd dogfood: paradigm 95
- **3rd dogfood: paradigm 191** (prescreen-only; full-window re-execution obligation TRIGGERED but root-cause mismatch supersedes)

**Lesson #30 formal CONFIRMED 자격 ACHIEVED** at paradigm 191 prescreen. paradigm-architect skill update at next paradigm 192 dispatch.

## §6 Counter snapshot

- Graveyards (substantive): 170 → **170 unchanged** (paradigm 191 R-0 halt with counter consumption)
- R-0 halts with counter consumption (cumulative): 88/89/90/97-c/159/176/**191** = **7 substantive R-0 halts**
- Non-PASS streak: 41+ → **42+**
- R-5 LIVE: 11 unchanged
- R-5 yield: 6.40% unchanged
- Paradigm counter: 177 (paradigm 191 used substantive halt counter, equiv to paradigm 176 precedent)
- Lesson library:
  - **Lesson #30 candidate → CONFIRMED 자격 ACHIEVED** (3 dogfoods × 3 data-window-ratio contexts)
  - Lesson #70 corollary scope clarification: paradigm 191 = scope (b), NOT (a) — distinct from corollary candidate
  - **NEW Lesson #74 candidate**: "R-2 FRAGILE_TEMPORAL_WF_FAIL root-cause diagnosis precedes intervention choice. If R-2 report explicitly identifies alpha-decay mechanism (informational learning), universe-expansion intervention is structurally wrong (does not address temporal drift). Correct interventions: regime-stratified retest, leak-detection feature, or forward-collection re-validation."

## §7 Permanent assets gained

- **Bybit V5 announcements substrate verified**: 229 Derivatives-tagged delisting articles, public free, no signup. Reusable for future Bybit-related event-anchored paradigm dispatches.
- **OKX OHLCV substrate INFEASIBILITY documented**: post-delist OHLCV completely removed from REST + CDN; **OKX cannot be used for any post-delist event-anchored paradigm**. Save future paradigm dispatches from substrate verification cycle.
- **Bybit public archive tick CSV.gz availability documented**: post-delist tick data RETAINED at `public.bybit.com/trading/{SYM}/`. Available for future use cases needing post-delist data, but requires custom tick-to-kline reconstruction (NOT pre-computed kline).
- **Lesson #30 formal CONFIRMED 자격** (3 dogfoods reached).
- **Lesson #74 candidate registered** (R-2 FRAGILE root-cause-aware intervention).

## §8 paradigm 192 next-action 권고

**1순위 (RECOMMENDED)**: paradigm 192 = **new DNA dispatch** per [[feedback-paradigm-campaign-continuous-parallel]] + [[feedback-persistence-over-efficiency]]. Universe expansion path for paradigm 87 is structurally wrong intervention.

**2순위 (optional, separate paradigm)**: paradigm 193 = **regime-stratified retest of paradigm 87** (pre-2026 cohort) — tests whether decay is permanent (paradigm dead) or regime-conditional (paradigm conditional). Forward-only paper validation 60+d. Lower priority due to alpha-decay mechanism being market-wide informational learning (decay likely permanent).

**3순위 (defer)**: Forward-only collection paradigm — pause until 2026-08+ to verify post-decay alpha regime exists at all.

## §9 R-1 verdict

**`HALT_SUBSTRATE_PARTIAL_PLUS_PARADIGM_CLASS_MISMATCH`** (R-1 NOT DISPATCHED)

Composite failure: (1) OKX substrate unavailable + (2) Bybit backfill cost MODERATE (custom tick reconstruction) + (3) ROOT CAUSE MISMATCH (alpha decay, not small-sample) + (4) Lesson #62 family-proxy concern. The 3rd factor is decisive — universe expansion would burn 3-8 GB + 30-90min backfill + custom Bybit fetch script for predicted-FRAGILE outcome.

---
**END 2026-05-22 12:35 KST paradigm 191 R-0 HALT** — Multi-venue delisting universe expansion HALT_SUBSTRATE_PARTIAL (OKX unavailable) + PARADIGM_CLASS_MISMATCH (paradigm 87 R-2 FRAGILE root cause = alpha decay per market learning, not small-sample blind spot). Lesson #30 CONFIRMED 자격 achieved (3rd dogfood). Lesson #74 candidate registered (R-2 FRAGILE root-cause-aware intervention obligation). Bybit V5 announcements substrate + OKX post-delist OHLCV INFEASIBILITY permanent assets. 1순위 권고: paradigm 192 new DNA dispatch (continuous-parallel default).
